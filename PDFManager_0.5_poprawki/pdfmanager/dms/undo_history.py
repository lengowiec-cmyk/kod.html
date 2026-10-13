"""Encrypted disk snapshots instead of keeping entire PDFs in UI RAM."""
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import dataclass
import uuid
from .recovery import data_dir,digest
from pdfmanager.security.cache import crypt_file
from pdfmanager.pdf_engine.io_utils import atomic_copy_file,atomic_write_bytes

@dataclass
class Snapshot:
    path:Path
    size:int
    checksum:str
    def __len__(self):return self.size

class UndoHistory:
    def __init__(self):
        root=data_dir()/'undo';root.mkdir(parents=True,exist_ok=True)
        self.temp=TemporaryDirectory(prefix='session-',dir=root);self.root=Path(self.temp.name)
    def capture(self,source):
        source=Path(source);target=self.root/(uuid.uuid4().hex+'.pdm')
        checksum=digest(source);crypt_file(source,target)
        return Snapshot(target,source.stat().st_size,checksum)
    def from_bytes(self,data):
        source=self.root/'input.tmp'
        try:atomic_write_bytes(source,data);return self.capture(source)
        finally:source.unlink(missing_ok=True)
    def restore(self,snapshot,target):
        with TemporaryDirectory(prefix='restore-',dir=self.root) as folder:
            source=Path(folder)/'document.pdf';crypt_file(snapshot.path,source,decrypt=True)
            if digest(source)!=snapshot.checksum:raise ValueError('Kopia cofania jest uszkodzona.')
            atomic_copy_file(source,target)
    def drop(self,snapshot):snapshot.path.unlink(missing_ok=True)
    def close(self):self.temp.cleanup()
