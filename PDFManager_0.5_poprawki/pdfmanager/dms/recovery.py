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
    root.mkdir(parents=True,exist_ok=True);return root

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
        atomic_write_bytes(self.folder/'session.json',json.dumps({'source':str(self.source),'file':self.path.name,'baseline':self.baseline,'dirty':self.dirty,'updated':datetime.now(timezone.utc).isoformat()},ensure_ascii=False).encode('utf-8'))
    def changed(self):self.dirty=True;self.write_manifest()
    def save(self,target=None,*,allow_conflict=False):
        target=Path(target or self.source).resolve()
        if target==self.path.resolve():raise ValueError('Wybierz plik poza katalogiem odzyskiwania.')
        if target==self.source and (not target.exists() or digest(target)!=self.baseline) and not allow_conflict:
            raise ValueError('Oryginał został zmieniony poza aplikacją. Zapisz pod nową nazwą.')
        backup=None
        if target.exists():
            folder=self.root.parent/'backups';folder.mkdir(parents=True,exist_ok=True)
            import os
            document_id=hashlib.sha256(os.path.normcase(str(target)).encode('utf-8')).hexdigest()[:16]
            backup=folder/(document_id+'_'+uuid.uuid4().hex+'_'+target.name);atomic_copy_file(target,backup)
        atomic_copy_file(self.path,target)
        self.source=target;self.baseline=digest(target);self.dirty=False;self.write_manifest()
        if backup is not None:
            try:prune_backups(folder,target.name,protected=backup,document_id=document_id)
            except OSError:
                from pdfmanager.logging_setup import get_logger
                get_logger(__name__).warning('Zapisano dokument, ale nie udało się uporządkować kopii zapasowych.',exc_info=True)
        return target
    def close(self):
        if not self.dirty and self.path.exists() and digest(self.path)!=self.baseline:self.changed()
        if not self.dirty:
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
