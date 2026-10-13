"""Local encrypted work queue with optimistic concurrency and bounded records.

SQLite lives in local app data, never inside a Google Drive synced folder.
No document is modified by changing a review status.
"""
from pathlib import Path
import sqlite3,json,uuid,csv,io
from contextlib import contextmanager
from datetime import datetime,timezone
from .recovery import data_dir
from pdfmanager.security.cache import CacheCipher
STATES=('new','review','correction','ready')

class ReviewQueue:
    def __init__(self,root=None):
        self.root=Path(root) if root else data_dir()/'workflow';self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'queue.sqlite3'
        if self.root.is_symlink() or self.db.is_symlink():raise ValueError('Nieprawidłowy folder kolejki.')
        self.cipher=CacheCipher(self.root)
        with self.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS work(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=5)
        try:
            db.execute('PRAGMA secure_delete=ON')
            with db:yield db
        finally:db.close()
    def all(self):
        with self.connect() as db:rows=db.execute('SELECT id,revision,payload FROM work ORDER BY rowid DESC LIMIT 5000').fetchall()
        return [dict(json.loads(self.cipher.decrypt(blob)),id=key,revision=revision) for key,revision,blob in rows]
    def add(self,path,**fields):
        if set(fields)-{'status','owner','order','kind','note'}:raise ValueError('Nieobsługiwane pola zadania.')
        path=Path(path).resolve()
        if path.suffix.lower()!='.pdf' or not path.is_file():raise ValueError('Wybierz istniejący dokument PDF.')
        value={'path':str(path),'status':'new','owner':'','order':'','kind':'','note':'','updated':datetime.now(timezone.utc).isoformat()};value.update(fields);self.validate(value)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM work').fetchone()[0]>=5000:raise ValueError('Kolejka ma 5000 wpisów. Usuń zakończone pozycje.')
            key=uuid.uuid4().hex;db.execute('INSERT INTO work VALUES(?,?,?)',(key,1,self.cipher.encrypt(json.dumps(value,ensure_ascii=False))))
        return key
    def validate(self,value):
        if value.get('status') not in STATES:raise ValueError('Nieprawidłowy stan dokumentu.')
        if not all(isinstance(value.get(k),str) and len(value[k])<=limit for k,limit in [('path',4096),('owner',120),('order',120),('kind',80),('note',5000)]):raise ValueError('Nieprawidłowe lub zbyt długie dane kolejki.')
    def update(self,key,revision,**changes):
        if set(changes)-{'status','owner','order','kind','note'}:raise ValueError('Nieobsługiwane pola kolejki.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT revision,payload FROM work WHERE id=?',(key,)).fetchone()
            if not row or row[0]!=revision:raise ValueError('Wpis zmienił się w innym oknie. Odśwież kolejkę.')
            value=json.loads(self.cipher.decrypt(row[1]));value.update(changes);value['updated']=datetime.now(timezone.utc).isoformat();self.validate(value)
            db.execute('UPDATE work SET revision=revision+1,payload=? WHERE id=?',(self.cipher.encrypt(json.dumps(value,ensure_ascii=False)),key))
    def remove(self,key,revision):
        with self.connect() as db:
            cursor=db.execute('DELETE FROM work WHERE id=? AND revision=?',(key,revision))
            if cursor.rowcount!=1:raise ValueError('Wpis zmienił się. Odśwież kolejkę.')
    def export(self,target):
        from .files import transfer_file
        import tempfile
        target=Path(target)
        if target.suffix.lower()!='.csv' or target.exists():raise ValueError('Wybierz nowy plik CSV; istniejące pliki nie są nadpisywane.')
        data=io.StringIO();writer=csv.writer(data);writer.writerow(['Document','Status','Owner','Order','Type','Note','Updated'])
        for value in self.all():
            # Prevent spreadsheet formulas in data controlled by file names/users.
            row=[value[k] for k in ('path','status','owner','order','kind','note','updated')]
            writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in row])
        with tempfile.TemporaryDirectory(prefix='pdfmanager-queue-export-') as folder:
            tmp=Path(folder)/'export.csv';tmp.write_text(data.getvalue(),encoding='utf-8-sig');transfer_file(tmp,target)
