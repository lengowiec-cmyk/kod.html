"""Signed control plane over Google Drive Desktop; no public server required."""
from pathlib import Path,PureWindowsPath
from urllib.parse import urlsplit
from urllib.error import HTTPError
from datetime import datetime,timezone
import base64,io,json,os,re,uuid
from pdfmanager.remote.protocol import canonical,public_key,origin,version
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

MARKER='pdfmanager-channel.json'

def is_link(path):
    path=Path(path)
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())

def scoped_target(root,group,name):
    """Only direct channel children; reject redirected directories on Windows too."""
    root=Path(root)
    if is_link(root) or not root.is_dir():raise ValueError('Nieprawidłowy folder kanału.')
    if group not in ('control','updates','hello') or Path(name).name!=name or '/' in name or '\\' in name:raise ValueError('Ścieżka spoza kanału.')
    parent=root/group;target=parent/name
    if is_link(parent) or not parent.is_dir() or parent.resolve().parent!=root.resolve() or is_link(target):raise ValueError('Przekierowanie folderu kanału zostało zablokowane.')
    return target

def check_signature(envelope,pem,purpose):
    if set(envelope)!={'payload','signature'}:raise ValueError('Nieprawidłowe dane połączenia.')
    payload=envelope['payload']
    if payload.get('schema')!=1 or payload.get('purpose')!=purpose:raise ValueError('Nieprawidłowy typ podpisanych danych.')
    public_key(pem).verify(base64.b64decode(envelope['signature'],validate=True),canonical(payload))
    return payload

def verify_folder(folder,config):
    try:
        folder=Path(folder);marker=folder/MARKER
        if folder.name!='PDFManager-Polaczenie-'+config['workspace'][:8]:return False
        if is_link(folder) or is_link(marker) or not marker.is_file():return False
        with marker.open('rb') as stream:raw=stream.read(65537)
        if len(raw)>65536:return False
        payload=check_signature(json.loads(raw),config['public_key'],'shared-root')
        return payload['workspace']==config['workspace'] and payload['public_key']==config['public_key']
    except Exception:return False

def drive_roots():
    """Known Drive mount points only; never scan the whole system disk."""
    roots=[]
    for name in ('Google Drive','GoogleDrive','My Drive','Mój dysk'):
        p=Path.home()/name
        if p.is_dir():roots.append(p)
    if os.name=='nt':
        import ctypes
        mask=ctypes.windll.kernel32.GetLogicalDrives()
        for index in range(26):
            if not mask&(1<<index):continue
            root=Path(chr(65+index)+':\\')
            for name in ('My Drive','Mój dysk','Shared drives','Dyski współdzielone','Dyski wspólne'):
                candidate=root/name
                try:
                    if candidate.is_dir():roots.append(candidate)
                except OSError:pass
    return roots

_cached={}
def locate(config,roots=None):
    key=(config['workspace'],config['public_key'],config['folder_hint'])
    cached=_cached.get(key)
    if cached and verify_folder(cached,config):return cached
    hint=Path(config['folder_hint'])
    if verify_folder(hint,config):_cached[key]=hint;return hint
    # Letter/mount changes are common between employee computers.
    leaf=PureWindowsPath(config['folder_hint']).name if '\\' in config['folder_hint'] else hint.name
    roots=list(drive_roots() if roots is None else roots)
    count=0
    for root in roots:
        root=Path(root)
        candidates=[root,root/leaf]
        for p in candidates:
            if verify_folder(p,config):_cached[key]=p;return p
        queue=[(root,0)]
        while queue and count<2000:
            current,depth=queue.pop(0);count+=1
            if depth>=4:continue
            try:
                from itertools import islice
                children=sorted(p for p in islice(current.iterdir(),2000) if p.is_dir() and not is_link(p))[:200]
            except OSError:continue
            for p in children:
                if p.name==leaf and verify_folder(p,config):_cached[key]=p;return p
                queue.append((p,depth+1))
    return None

class FolderTransport:
    def __init__(self,config):self.config=config
    def open(self,request,timeout=None):
        url=urlsplit(request.full_url)
        if origin(request.full_url)!=origin(self.config['base_url']):raise ValueError('Plik pochodzi z innego kanału.')
        folder=locate(self.config)
        if folder is None:raise OSError('Wspólny folder Google Drive nie jest jeszcze dostępny lub zsynchronizowany.')
        if url.path=='/hello' and request.get_method()=='POST':
            raw=request.data
            if not raw or len(raw)>2048:raise ValueError('Nieprawidłowe zgłoszenie instalacji.')
            item=json.loads(raw);device=str(uuid.UUID(item['device']));version(item['version'])
            item={'device':device,'version':item['version'],'seen':datetime.now(timezone.utc).isoformat()}
            target=scoped_target(folder,'hello',device+'.json')
            atomic_write_bytes(target,canonical(item));return io.BytesIO(b'')
        if request.get_method()!='GET':raise ValueError('Niedozwolona operacja kanału.')
        if not (re.fullmatch(r'/control/[a-f0-9-]{36}\.json',url.path) or re.fullmatch(r'/updates/[a-f0-9]{64}\.exe',url.path)):raise ValueError('Ścieżka spoza kanału połączenia.')
        group,name=url.path.lstrip('/').split('/')
        target=scoped_target(folder,group,name)
        if not target.is_file():raise HTTPError(request.full_url,404,'Czeka na synchronizację',{},None)
        return target.open('rb')
