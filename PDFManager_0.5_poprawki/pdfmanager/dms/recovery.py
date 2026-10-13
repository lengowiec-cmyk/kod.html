"""Durable working copies, conflict checks and backups outside user documents."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import uuid
from PySide6.QtCore import QStandardPaths
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes,atomic_copy_file

def data_dir():
    root=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))/'PDFManager'
    root.mkdir(parents=True,exist_ok=True)
    import os
    os.chmod(root,0o700)
    return root

def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
    return sha.hexdigest()

# Bez retencji folder `backups/` rósłby bez końca — każdy "Zapisz" dopisywał
# kopię i nigdy jej nie usuwał. Ogranicz liczbę kopii per plik oraz łączny
# rozmiar folderu, usuwając najstarsze kopie (po czasie modyfikacji).
MAX_BACKUPS_PER_FILE = 5
MAX_BACKUPS_TOTAL_BYTES = 2 * 1024**3  # 2 GiB

def prune_backups(folder, name, *, max_per_file=MAX_BACKUPS_PER_FILE, max_total_bytes=MAX_BACKUPS_TOTAL_BYTES, protected=None, document_id=None):
    if max_per_file<1 or max_total_bytes<0:raise ValueError('Nieprawidłowe limity kopii zapasowych.')
    folder=Path(folder)
    everything=sorted((p for p in folder.iterdir() if p.is_file()),key=lambda p:p.stat().st_mtime)
    # A single oversized backup must survive: recovery takes priority over the cap.
    keep=Path(protected) if protected is not None else (everything[-1] if everything else None)
    same_name=[p for p in everything if p.name.endswith('_'+name) and (document_id is None or p.name.startswith(document_id+'_'))]
    for path in list(same_name):
        if len(same_name)<=max_per_file:break
        if path==keep:continue
        path.unlink(missing_ok=True);same_name.remove(path)
    everything=[p for p in everything if p.exists()]
    total=sum(p.stat().st_size for p in everything)
    for path in everything:
        if total<=max_total_bytes:break
        if path==keep:continue
        size=path.stat().st_size;path.unlink(missing_ok=True);total-=size

class WorkingCopy:
    def __init__(self,source,root=None):
        self.root=Path(root) if root else data_dir()/'recovery'
        self.folder=self.root/uuid.uuid4().hex;self.folder.mkdir(parents=True)
        self.source=Path(source).resolve();self.path=self.folder/self.source.name
        try:
            atomic_copy_file(self.source,self.path)
            self.baseline=digest(self.path);self.dirty=False;self.write_manifest()
        except Exception:
            import shutil
            shutil.rmtree(self.folder,ignore_errors=True)
            raise
    def write_manifest(self):
        atomic_write_bytes(self.folder/'session.json',json.dumps({'pid':__import__('os').getpid(),'source':str(self.source),'file':self.path.name,'baseline':self.baseline,'dirty':self.dirty,'updated':datetime.now(timezone.utc).isoformat()},ensure_ascii=False).encode('utf-8'))
    def changed(self):self.dirty=True;self.write_manifest()
    def save(self,target=None,*,allow_conflict=False):
        with document_save_lock(target or self.source):return self._save_locked(target,allow_conflict=allow_conflict)
    def _save_locked(self,target=None,*,allow_conflict=False):
        target=Path(target or self.source).resolve()
        if target==self.path.resolve():raise ValueError('Wybierz plik poza katalogiem odzyskiwania.')
        if target==self.source and (not target.exists() or digest(target)!=self.baseline) and not allow_conflict:
            raise ValueError('Oryginał został zmieniony poza aplikacją. Zapisz pod nową nazwą.')
        backup=None;target_baseline=digest(target) if target.exists() else None
        if target.exists():
            folder=self.root.parent/'backups';folder.mkdir(parents=True,exist_ok=True)
            import os
            document_id=hashlib.sha256(os.path.normcase(str(target)).encode('utf-8')).hexdigest()[:16]
            backup=folder/(document_id+'_'+uuid.uuid4().hex+'_'+target.name+'.pdm')
            from pdfmanager.security.cache import crypt_file
            crypt_file(target,backup)
        atomic_copy_file(self.path,target,expected_target_sha=target_baseline)
        self.source=target;self.baseline=digest(target);self.dirty=False;self.write_manifest()
        if backup is not None:
            try:prune_backups(folder,target.name+'.pdm',protected=backup,document_id=document_id)
            except OSError:
                from pdfmanager.logging_setup import get_logger
                get_logger(__name__).warning('Zapisano dokument, ale nie udało się uporządkować kopii zapasowych.',exc_info=True)
        return target
    def close(self,*,keep_plain=False):
        if self.path.exists() and self.path.suffix.lower()!='.pdm':
            if digest(self.path)==self.baseline:self.dirty=False
            elif not self.dirty:self.changed()
        if self.dirty and self.path.suffix.lower()!='.pdm':
            from pdfmanager.security.cache import crypt_file
            original=self.path;encrypted=original.with_name(original.name+'.pdm');crypt_file(original,encrypted)
            self.path=encrypted
            try:self.write_manifest()
            except Exception:self.path=original;raise
            if keep_plain:self.path=original
            else:original.unlink()
        if not self.dirty and not keep_plain:
            import shutil
            shutil.rmtree(self.folder,ignore_errors=True)
    def finalize_close(self):
        if self.dirty and self.path.suffix.lower()!='.pdm':
            encrypted=self.path.with_name(self.path.name+'.pdm')
            if not encrypted.is_file():raise ValueError('Brak zabezpieczonej kopii roboczej.')
            self.path.unlink();self.path=encrypted
        elif not self.dirty:
            import shutil
            shutil.rmtree(self.folder,ignore_errors=True)

def recoverable(root=None):
    root=Path(root) if root else data_dir()/'recovery';results=[]
    for manifest in root.glob('*/session.json'):
        try:
            item=json.loads(manifest.read_text(encoding='utf-8'));path=manifest.parent/item['file']
            if path.is_file() and path.parent==manifest.parent and (item['dirty'] or digest(path)!=item['baseline']):
                results.append((path,item['source'],item['updated']))
        except (OSError,ValueError,KeyError):continue
    return sorted(results,key=lambda item:item[2],reverse=True)

from contextlib import contextmanager
@contextmanager
def document_save_lock(target):
    """Serialize cooperating PDFManager instances on this computer only."""
    import os,time
    root=data_dir()/'save-locks';root.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(os.path.normcase(str(Path(target).resolve())).encode()).hexdigest()
    path=root/(key+'.lock')
    if path.is_symlink():raise ValueError('Nieprawidłowa blokada zapisu.')
    with path.open('a+b') as stream:
        if stream.seek(0,2)==0:stream.write(b'0');stream.flush()
        deadline=time.monotonic()+5
        while True:
            from .jobs import checkpoint
            checkpoint()
            try:
                if os.name=='nt':
                    import msvcrt
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>deadline:raise TimeoutError('Inna instancja PDFManager zapisuje ten dokument. Ponów zapis.')
                time.sleep(.02)
        try:yield
        finally:
            if os.name=='nt':stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)
