"""Persistent page-text index; changed PDFs are refreshed and broken files reported."""
from pathlib import Path
import sqlite3
import pymupdf
from .recovery import data_dir
from .jobs import checkpoint

def search_files(folder,query,*,recursive=True,fulltext=False,index_path=None):
    folder=Path(folder)
    if not folder.is_dir() or not query.strip():raise ValueError('Wybierz folder i wpisz tekst.')
    paths=sorted(p for p in (folder.rglob('*') if recursive else folder.iterdir()) if p.is_file())
    results=[];errors=[]
    db=sqlite3.connect(str(index_path or data_dir()/'search.sqlite3'))
    try:
        db.execute('CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, stamp TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS pages(path TEXT,page INTEGER,text TEXT,PRIMARY KEY(path,page))')
        for n,path in enumerate(paths):
            checkpoint(n,len(paths),f'Wyszukiwanie: {path.name}')
            try:
                if query.casefold() in path.name.casefold():results.append((path,-1,1))
                if not fulltext or path.suffix.lower()!='.pdf':continue
                key=str(path.resolve());stat=path.stat();stamp=f'{stat.st_mtime_ns}:{stat.st_size}'
                cached=db.execute('SELECT stamp FROM documents WHERE path=?',(key,)).fetchone()
                if not cached or cached[0]!=stamp:
                    rows=[]
                    with pymupdf.open(path) as doc:
                        if doc.needs_pass:raise ValueError('Dokument wymaga hasła.')
                        for page in doc:
                            checkpoint(n,len(paths),f'Indeksowanie {path.name}: strona {page.number+1}/{len(doc)}')
                            rows.append((key,page.number,page.get_text(sort=True).casefold()))
                    with db:
                        db.execute('DELETE FROM pages WHERE path=?',(key,))
                        db.executemany('INSERT INTO pages VALUES(?,?,?)',rows)
                        db.execute('INSERT OR REPLACE INTO documents VALUES(?,?)',(key,stamp))
                for page,text in db.execute('SELECT page,text FROM pages WHERE path=? ORDER BY page',(key,)):
                    count=text.count(query.casefold())
                    if count:results.append((path,page,count))
            except (OSError,ValueError,RuntimeError) as exc:errors.append(f'{path.name}: {exc}')
        checkpoint(len(paths),len(paths),'Wyszukiwanie zakończone')
    finally:db.close()
    return results,errors

def clear_index():
    path=data_dir()/'search.sqlite3'
    if path.exists():
        with sqlite3.connect(path) as db:
            db.execute('DELETE FROM pages');db.execute('DELETE FROM documents')
