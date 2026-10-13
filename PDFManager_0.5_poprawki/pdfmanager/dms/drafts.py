"""Encrypted, bounded text drafts saved outside company/Drive document folders."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
from .recovery import data_dir
from pdfmanager.security.cache import CacheCipher
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

class DraftStore:
    def __init__(self,root=None):
        self.root=Path(root) if root else data_dir()/'text-drafts';self.root.mkdir(parents=True,exist_ok=True);self.cipher=CacheCipher(self.root)
    def key(self,source):return hashlib.sha256(str(Path(source).resolve()).encode('utf-8')).hexdigest()
    def save(self,source,data):
        value=dict(data,source=str(Path(source).resolve()),updated=datetime.now(timezone.utc).isoformat())
        raw=json.dumps(value,ensure_ascii=False)
        if len(raw.encode())>1024*1024:raise ValueError('Szkic jest większy niż 1 MB. Zastosuj tekst do PDF przed dalszą edycją.')
        target=self.root/(self.key(source)+'.enc');atomic_write_bytes(target,self.cipher.encrypt(raw).encode())
        files=sorted(self.root.glob('*.enc'),key=lambda p:p.stat().st_mtime,reverse=True)
        for path in files[100:]:path.unlink(missing_ok=True)
    def load(self,source):
        path=self.root/(self.key(source)+'.enc')
        if not path.exists():return None
        if path.is_symlink() or path.stat().st_size>1500000:raise ValueError('Nieprawidłowy plik szkicu.')
        return json.loads(self.cipher.decrypt(path.read_text(encoding='utf-8')))
    def clear(self,source):(self.root/(self.key(source)+'.enc')).unlink(missing_ok=True)
