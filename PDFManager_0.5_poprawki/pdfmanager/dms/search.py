
from pdfmanager.security.limits import safe_open
"""Persistent page-text index; changed PDFs are refreshed and broken files reported."""
from pathlib import Path
import sqlite3
import pymupdf
from .recovery import data_dir
from .jobs import checkpoint

def search_files(folder,query,*,recursive=True,fulltext=False,index_path=None,extensions=None,modified_after=None,modified_before=None,max_results=10000):
    folder=Path(folder)
    if not folder.is_dir() or not query.strip():raise ValueError('Wybierz folder i wpisz tekst.')
    import itertools
    from datetime import datetime
    candidates=itertools.islice((p for p in (folder.rglob('*') if recursive else folder.iterdir()) if p.is_file()),50001)
    paths=sorted(candidates)
    limited=len(paths)>50000;paths=paths[:50000]
    results=[];errors=['Ograniczono przegląd do 50 000 plików. Zawęź folder.'] if limited else []
    index=Path(index_path) if index_path else data_dir()/'search.sqlite3'
    from pdfmanager.security.cache import CacheCipher
    cipher=CacheCipher(index.parent)
    db=sqlite3.connect(str(index))
    db.execute('PRAGMA secure_delete=ON')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, stamp TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS pages(path TEXT,page INTEGER,text TEXT,PRIMARY KEY(path,page))')
        if db.execute("SELECT 1 FROM pages WHERE text NOT LIKE 'enc:v1:%' LIMIT 1").fetchone():
            with db:db.execute('DELETE FROM pages');db.execute('DELETE FROM documents')
            db.execute('VACUUM')
        for n,path in enumerate(paths):
            checkpoint(n,len(paths),f'Wyszukiwanie: {path.name}')
            try:
                if extensions and path.suffix.lower() not in extensions:continue
                modified=datetime.fromtimestamp(path.stat().st_mtime).date()
                if modified_after and modified<modified_after:continue
                if modified_before and modified>modified_before:continue
                if len(results)>=max_results:errors.append('Ograniczono liczbę wyników. Zawęź wyszukiwanie.');break
                if query.casefold() in path.name.casefold():results.append((path,-1,1))
                if not fulltext or path.suffix.lower()!='.pdf':continue
                key=str(path.resolve());stat=path.stat();stamp=f'{stat.st_mtime_ns}:{stat.st_size}'
                cached=db.execute('SELECT stamp FROM documents WHERE path=?',(key,)).fetchone()
                if not cached or cached[0]!=stamp:
                    rows=[]
                    from pdfmanager.security.isolation import call
                    for number,text in enumerate(call('document.texts',path)):
                        checkpoint(n,len(paths),f'Indeksowanie {path.name}: strona {number+1}')
                        rows.append((key,number,cipher.encrypt(text.casefold())))
                    with db:
                        db.execute('DELETE FROM pages WHERE path=?',(key,))
                        db.executemany('INSERT INTO pages VALUES(?,?,?)',rows)
                        db.execute('INSERT OR REPLACE INTO documents VALUES(?,?)',(key,stamp))
                for page,text in db.execute('SELECT page,text FROM pages WHERE path=? ORDER BY page',(key,)):
                    count=cipher.decrypt(text).count(query.casefold())
                    if count:results.append((path,page,count))
            except (OSError,ValueError,RuntimeError) as exc:errors.append(f'{path.name}: {exc}')
        checkpoint(len(paths),len(paths),'Wyszukiwanie zakończone')
    finally:db.close()
    return results,errors

def clear_index():
    path=data_dir()/'search.sqlite3'
    if path.exists():
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM pages');db.execute('DELETE FROM documents');db.commit();db.execute('VACUUM')
