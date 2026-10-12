"""Encrypted search/metadata cache. Windows protects the key with user DPAPI."""
from pathlib import Path
import os,base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def dpapi(data,unprotect=False):
    import ctypes
    from ctypes import wintypes
    class BLOB(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=BLOB(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=BLOB()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    fn=crypt.CryptUnprotectData if unprotect else crypt.CryptProtectData
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise OSError('Ochrona klucza DPAPI nie powiodła się.')
    try:return ctypes.string_at(target.data,target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data,ctypes.c_void_p))

class CacheCipher:
    def __init__(self,folder):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);os.chmod(folder,0o700)
        keyfile=folder/'cache-key.bin'
        if keyfile.is_symlink():raise ValueError('Nieprawidłowy plik klucza cache.')
        if not keyfile.exists():
            key=AESGCM.generate_key(bit_length=256);blob=dpapi(key) if os.name=='nt' else key
            try:
                fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream:stream.write(blob)
            except FileExistsError:pass
        blob=keyfile.read_bytes();self.key=dpapi(blob,True) if os.name=='nt' else blob
        self.aes=AESGCM(self.key)
    def encrypt(self,text):
        nonce=os.urandom(12);return 'enc:v1:'+base64.b64encode(nonce+self.aes.encrypt(nonce,text.encode(),b'PDFManager-cache-v1')).decode()
    def decrypt(self,value):
        if not value.startswith('enc:v1:'):raise ValueError('Niezaszyfrowany rekord cache.')
        blob=base64.b64decode(value[7:],validate=True);return self.aes.decrypt(blob[:12],blob[12:],b'PDFManager-cache-v1').decode()

def crypt_file(source,target,*,decrypt=False):
    """Authenticated streamed encryption/decryption; never commits unauthenticated data."""
    import tempfile
    from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
    from pdfmanager.dms.recovery import data_dir
    source=Path(source);target=Path(target)
    if source.stat().st_size>256*1024*1024+36:raise ValueError('Zaszyfrowana kopia przekracza limit 256 MB.')
    cipher=CacheCipher(data_dir());magic=b'PDMENC1\0'
    fd,name=tempfile.mkstemp(prefix='pdfmanager-secure-',suffix='.tmp',dir=target.parent);temporary=Path(name)
    try:
        with source.open('rb') as input_file,os.fdopen(fd,'wb') as output:
            if decrypt:
                if input_file.read(8)!=magic:raise ValueError('Nieprawidłowa zaszyfrowana kopia.')
                nonce=input_file.read(12);size=source.stat().st_size
                if size<36:raise ValueError('Niepełna zaszyfrowana kopia.')
                input_file.seek(-16,2);tag=input_file.read(16);input_file.seek(20)
                transform=Cipher(algorithms.AES(cipher.key),modes.GCM(nonce,tag)).decryptor();transform.authenticate_additional_data(magic)
                remaining=size-36
                while remaining:
                    block=input_file.read(min(1024*1024,remaining))
                    if not block:raise ValueError('Niepełna kopia.')
                    remaining-=len(block);output.write(transform.update(block))
                output.write(transform.finalize())
            else:
                nonce=os.urandom(12);transform=Cipher(algorithms.AES(cipher.key),modes.GCM(nonce)).encryptor();transform.authenticate_additional_data(magic);output.write(magic+nonce)
                for block in iter(lambda:input_file.read(1024*1024),b''):output.write(transform.update(block))
                output.write(transform.finalize());output.write(transform.tag)
            output.flush();os.fsync(output.fileno())
        temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)

def migrate_legacy_storage():
    """User-invoked migration; current/open sessions are never modified."""
    import json
    from pdfmanager.dms.recovery import data_dir
    from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
    root=data_dir();converted=0;errors=[]
    def live(pid):
        if not pid:return False
        if pid==os.getpid():return True
        if os.name=='nt':
            import ctypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=ctypes.c_void_p
            handle=kernel.OpenProcess(0x1000,False,int(pid))
            if handle:kernel.CloseHandle(ctypes.c_void_p(handle));return True
            return ctypes.get_last_error()==5
        try:os.kill(int(pid),0);return True
        except ProcessLookupError:return False
        except PermissionError:return True
    for path in (root/'backups').glob('*.pdf'):
        try:
            target=path.with_name(path.name+'.pdm');crypt_file(path,target);path.unlink();converted+=1
        except Exception as exc:errors.append(f'{path.name}: {exc}')
    for manifest in (root/'recovery').glob('*/session.json'):
        try:
            data=json.loads(manifest.read_text(encoding='utf-8'))
            if live(data.get('pid')):continue
            path=manifest.parent/data['file']
            if path.parent!=manifest.parent or path.suffix.lower()=='.pdm' or not path.is_file():continue
            target=path.with_name(path.name+'.pdm');crypt_file(path,target);data['file']=target.name;data['dirty']=True
            atomic_write_bytes(manifest,json.dumps(data,ensure_ascii=False).encode());path.unlink();converted+=1
        except Exception as exc:errors.append(f'{manifest.parent.name}: {exc}')
    for manifest in (root/'trash').glob('*/info.json'):
        try:
            data=json.loads(manifest.read_text(encoding='utf-8'));path=manifest.parent/data['name']
            if path.parent!=manifest.parent or path.suffix.lower()=='.pdm' or not path.is_file():continue
            target=path.with_name(path.name+'.pdm');crypt_file(path,target);data['name']=target.name
            atomic_write_bytes(manifest,json.dumps(data,ensure_ascii=False).encode());path.unlink();converted+=1
        except Exception as exc:errors.append(f'{manifest.parent.name}: {exc}')
    return converted,errors
