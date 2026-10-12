"""Operator-only signing backend. Public web root never serves private keys."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,os,uuid,shutil,threading,ssl
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from pdfmanager.remote.protocol import sign,canonical,stamp,version,origin,activation_code,MAX_INSTALLER
from pdfmanager.remote.client import digest
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

class AdminWorkspace:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);os.chmod(self.folder,0o700)
        self.web=self.folder/'public';(self.web/'control').mkdir(parents=True,exist_ok=True);(self.web/'updates').mkdir(exist_ok=True)
        self.key=None;self.lock=threading.RLock()
    def unlock(self,password):
        if len(password)<12:raise ValueError('Hasło klucza musi mieć co najmniej 12 znaków.')
        path=self.folder/'management-signing.pem'
        if path.exists():self.key=serialization.load_pem_private_key(path.read_bytes(),password.encode())
        else:
            key=Ed25519PrivateKey.generate();blob=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password.encode()))
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(blob)
            self.key=key
        if not isinstance(self.key,Ed25519PrivateKey):raise ValueError('Nieprawidłowy typ klucza.')
    def configuration(self,url):
        if not self.key:raise ValueError('Najpierw odblokuj klucz administratora.')
        origin(url)
        pem=self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        ca=self.folder/'tls-ca.crt'
        return {'schema':1,'public_key':pem,'base_url':url.rstrip('/'),'extra_ca_pem':ca.read_text() if ca.exists() else ''}
    def devices(self):
        p=self.folder/'devices.json';return json.loads(p.read_text()) if p.exists() else {}
    def register(self,device,label):
        with self.lock:return self._register(device,label)
    def _register(self,device,label):
        device=str(uuid.UUID(device.strip()));items=self.devices();items.setdefault(device,{'label':label.strip() or device,'sequence':0,'blocked':False});self.save_devices(items)
    def save_devices(self,items):atomic_write_bytes(self.folder/'devices.json',json.dumps(items,ensure_ascii=False,indent=2).encode())
    def command(self,device,blocked,reason='',update=None):
        with self.lock:return self._command(device,blocked,reason,update)
    def _command(self,device,blocked,reason='',update=None):
        if not self.key:raise ValueError('Odblokuj klucz administratora.')
        uuid.UUID(device);items=self.devices();row=items[device];row['sequence']+=1;row['blocked']=bool(blocked)
        if update is None and blocked:row['block_generation']=row['sequence']
        issued=stamp();payload={'schema':1,'purpose':'control','device':device,'sequence':row['sequence'],'blocked':bool(blocked),'block_generation':row.get('block_generation',0),'reason':reason[:500],'issued':issued,'expires':issued+90*86400}
        if update:payload['update']=update
        envelope=sign(payload,self.key)
        # Persist the sequence before exposing a command; never reuse it after a crash.
        self.save_devices(items);atomic_write_bytes(self.web/'control'/(device+'.json'),canonical(envelope));return envelope
    def grant(self,device,days):
        if not self.key or device not in self.devices():raise ValueError('Odblokuj klucz i wybierz instalację.')
        if not 1<=days<=3650:raise ValueError('Podaj okres od 1 do 3650 dni.')
        issued=stamp();payload={'schema':1,'purpose':'activation','device':device,'days':days,'nonce':uuid.uuid4().hex,'issued':issued,'expires':issued+7*86400}
        return activation_code(payload,self.key)
    def release(self,installer,release_version,url):
        installer=Path(installer);origin(url);version(release_version)
        if installer.suffix.lower()!='.exe' or not 1<=installer.stat().st_size<=MAX_INSTALLER:raise ValueError('Wybierz instalator Windows EXE do 512 MB.')
        sha=digest(installer);target=self.web/'updates'/(sha+'.exe')
        if not target.exists():
            from pdfmanager.pdf_engine.io_utils import atomic_copy_file
            atomic_copy_file(installer,target)
        if digest(target)!=sha:raise ValueError('Kopia instalatora jest uszkodzona.')
        return {'version':release_version,'url':url.rstrip('/')+'/updates/'+sha+'.exe','sha256':sha,'size':target.stat().st_size}
    def create_tls(self,url,password):
        """Private LAN CA: explicit trust via exported public configuration."""
        import ipaddress
        from urllib.parse import urlsplit
        from cryptography import x509
        from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import hashes
        origin(url);host=urlsplit(url).hostname
        if (self.folder/'tls-server.key').exists():raise FileExistsError('Certyfikat już istnieje. Nie nadpisano kluczy.')
        ca=rsa.generate_private_key(public_exponent=65537,key_size=3072);server=rsa.generate_private_key(public_exponent=65537,key_size=2048);now=datetime.now(timezone.utc)
        ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'PDFManager Administrator LAN CA')])
        cert=x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True).sign(ca,hashes.SHA256())
        try:san=x509.IPAddress(ipaddress.ip_address(host))
        except ValueError:san=x509.DNSName(host)
        server_cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)])).issuer_name(ca_name).public_key(server.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365)).add_extension(x509.BasicConstraints(ca=False,path_length=None),True).add_extension(x509.SubjectAlternativeName([san]),False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False).sign(ca,hashes.SHA256())
        for name,key in [('tls-ca.key',ca),('tls-server.key',server)]:
            fd=os.open(self.folder/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(password.encode())))
        (self.folder/'tls-ca.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM));(self.folder/'tls-server.crt').write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

def serve(workspace,port,certificate,key,password,host='0.0.0.0'):
    root=workspace.web.resolve()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            import re
            from collections import deque
            if self.path!='/hello':self.send_error(404);return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=2048:raise ValueError('Nieprawidłowy rozmiar zgłoszenia.')
                data=json.loads(self.rfile.read(size));device=str(uuid.UUID(data['device']));version(data['version'])
                with workspace.lock:
                    items=workspace.devices()
                    if device not in items and len(items)>=1000:raise ValueError('Limit instalacji.')
                    row=items.setdefault(device,{'label':'Instalacja '+device[:8],'sequence':0,'blocked':False})
                    row.update(last_seen=datetime.now(timezone.utc).isoformat(),version=data['version']);workspace.save_devices(items)
                self.send_response(204);self.send_header('Content-Length','0');self.end_headers()
            except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.send_error(400)
        def do_GET(self):
            from urllib.parse import urlsplit
            import re
            path=urlsplit(self.path).path
            if re.fullmatch(r'/control/[a-f0-9-]{36}\.json',path):mime='application/json'
            elif re.fullmatch(r'/updates/[a-f0-9]{64}\.exe',path):mime='application/octet-stream'
            else:self.send_error(404);return
            target=root/path.lstrip('/')
            if target.is_symlink() or not target.resolve().is_relative_to(root) or not target.is_file():self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(target.stat().st_size));self.send_header('Cache-Control','no-store');self.end_headers()
            try:
                with target.open('rb') as stream:shutil.copyfileobj(stream,self.wfile,1024*1024)
            except (BrokenPipeError,ConnectionResetError):pass
        def setup(self):super().setup();self.connection.settimeout(30)
        def log_message(self,*args):pass
    class Server(ThreadingHTTPServer):
        daemon_threads=True;request_queue_size=16
        slots=threading.BoundedSemaphore(16)
        def process_request(self,request,address):
            if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
            try:super().process_request(request,address)
            except Exception:self.slots.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:self.slots.release()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(certificate,key,password)
    server=Server((host,port),Handler);server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();return server
