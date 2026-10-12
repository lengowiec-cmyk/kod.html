"""Outbound HTTPS only; TLS, signatures, device binding and replay protection."""
from pathlib import Path
from urllib.request import build_opener,HTTPSHandler,HTTPRedirectHandler,Request
from urllib.parse import urljoin
from urllib.error import HTTPError
import json,ssl,hashlib,tempfile,os
from pdfmanager.remote.protocol import config_check,verify,origin,MAX_MANIFEST,MAX_INSTALLER,version
from pdfmanager.remote.storage import RemoteState,load_config
from pdfmanager.remote import APP_VERSION

class RedirectPolicy(HTTPRedirectHandler):
    def __init__(self,base):super().__init__();self.allowed=origin(base)
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if origin(newurl)!=self.allowed:raise ValueError('Przekierowanie poza serwer administratora zostało zablokowane.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def opener(config):
    if config.get('transport')=='shared_folder':
        from pdfmanager.remote.shared import FolderTransport
        return FolderTransport(config)
    context=ssl.create_default_context()
    if config.get('extra_ca_pem'):context.load_verify_locations(cadata=config['extra_ca_pem'])
    return build_opener(RedirectPolicy(config['base_url']),HTTPSHandler(context=context))

class ControlClient:
    def __init__(self,config,state=None,transport=None):
        self.config=config_check(config);self.state=state or RemoteState();self.device=self.state.device();self.transport=transport or opener(self.config)
    def poll(self):
        # Only anonymous installation ID and application version are reported.
        hello={'device':self.device,'version':APP_VERSION}
        try:
            with self.transport.open(Request(self.config['base_url']+'/hello',data=json.dumps(hello).encode(),headers={'Content-Type':'application/json'}),timeout=5) as response:response.read(2048)
        except HTTPError as exc:
            if exc.code not in (404,405):raise
        url=self.config['base_url']+'/control/'+self.device+'.json'
        try:
            with self.transport.open(Request(url,headers={'User-Agent':'PDFManager/'+APP_VERSION,'Cache-Control':'no-cache'}),timeout=10) as response:
                raw=response.read(MAX_MANIFEST+1)
        except HTTPError as exc:
            if exc.code==404:return None
            raise
        if len(raw)>MAX_MANIFEST:raise ValueError('Polecenie przekracza limit.')
        envelope=json.loads(raw);payload=verify(envelope,self.config['public_key'],self.device)
        # A verified replay cannot reset local activation or block state.
        self.state.apply(payload)
        if payload['sequence']<self.state.read()['sequence']:return None
        return envelope
    def download(self,envelope,folder):
        payload=verify(envelope,self.config['public_key'],self.device)
        update=payload.get('update')
        if not update or version(update['version'])<=version(APP_VERSION):return None
        if origin(update['url'])!=origin(self.config['base_url']):raise ValueError('Aktualizacja musi pochodzić z serwera administratora.')
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);target=folder/(update['sha256']+'.exe')
        if target.is_file() and target.stat().st_size==update['size'] and digest(target)==update['sha256']:return target
        fd,name=tempfile.mkstemp(prefix='download-',suffix='.tmp',dir=folder);temporary=Path(name)
        try:
            sha=hashlib.sha256();total=0
            with os.fdopen(fd,'wb') as output,self.transport.open(Request(update['url']),timeout=30) as response:
                while True:
                    block=response.read(1024*1024)
                    if not block:break
                    from pdfmanager.dms.jobs import checkpoint
                    checkpoint();total+=len(block)
                    if total>update['size'] or total>MAX_INSTALLER:raise ValueError('Aktualizacja przekracza podpisany rozmiar.')
                    sha.update(block);output.write(block)
                output.flush();os.fsync(output.fileno())
            if total!=update['size'] or sha.hexdigest()!=update['sha256']:raise ValueError('Aktualizacja nie odpowiada podpisanej sumie SHA-256.')
            temporary.replace(target);return target
        finally:temporary.unlink(missing_ok=True)

def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
    return sha.hexdigest()

def sync_once():
    config=load_config()
    if config:
        try:return ControlClient(config).poll()
        except Exception:return None # Offline does not invent a block or erase one.
