"""Deduplicated scanner intake, optional OCR and predictable document names."""
from pathlib import Path
from datetime import datetime
import sqlite3
import tempfile
import uuid
from .recovery import data_dir,digest
from .scanning import import_scans,SUPPORTED
from .jobs import checkpoint,Cancelled
from .files import transfer_file

ALLOWED_FIELDS={'date','time','source','counter'}

def document_name(pattern,source,counter):
    import string
    for literal,field,spec,conversion in string.Formatter().parse(pattern):
        if field is not None and (field not in ALLOWED_FIELDS or spec or conversion):raise ValueError('Reguła obsługuje tylko {date}, {time}, {source}, {counter}.')
    now=datetime.now()
    result=pattern.format(date=now.strftime('%Y-%m-%d'),time=now.strftime('%H%M%S'),source=Path(source).stem,counter=str(counter))
    if not result.lower().endswith('.pdf'):result+='.pdf'
    from .cabinets import validate_relative
    relative=validate_relative(result)
    if len(relative.parts)!=1:raise ValueError('Reguła musi tworzyć pojedynczą nazwę pliku.')
    return relative.name

def process_scans(paths,destination,*,pattern='{date}_{source}_{counter}',ocr=False,language='pol',ledger=None):
    destination=Path(destination).resolve()
    if not destination.is_dir():raise ValueError('Folder docelowy jest niedostępny.')
    ledger=Path(ledger) if ledger else data_dir()/'scans.sqlite3'
    results=[]
    with sqlite3.connect(ledger) as db:
        db.execute('CREATE TABLE IF NOT EXISTS imported(target TEXT,hash TEXT,output TEXT,PRIMARY KEY(target,hash))')
        for i,value in enumerate(paths):
            source=Path(value)
            checkpoint(i,len(paths),'Import skanu: '+source.name)
            try:
                if not source.is_file() or source.suffix.lower() not in SUPPORTED:raise ValueError('Nieobsługiwany plik skanera.')
                checksum=digest(source);key=str(destination)
                old=db.execute('SELECT output FROM imported WHERE target=? AND hash=?',(key,checksum)).fetchone()
                if old and Path(old[0]).is_file():results.append((source,'duplicate',Path(old[0])));continue
                counter=db.execute('SELECT COUNT(*) FROM imported WHERE target=?',(key,)).fetchone()[0]+1
                name=document_name(pattern,source,counter);output=destination/name
                if output.exists():output=destination/(output.stem+'_'+uuid.uuid4().hex[:8]+'.pdf')
                with tempfile.TemporaryDirectory(prefix='pdfmanager-pipeline-') as temp:
                    temp=Path(temp);draft=import_scans([source],temp,'scan.pdf')
                    if ocr:
                        from pdfmanager.pdf_engine.workflows import ocr_document
                        recognized=temp/'ocr.pdf';ocr_document(draft,recognized,language=language);draft=recognized
                    if digest(source)!=checksum:raise ValueError('Plik skanera zmienił się podczas odczytu; ponów import po jego zakończeniu.')
                    checkpoint(i,len(paths),'Zapis skanu: '+source.name)
                    transfer_file(draft,output)
                with db:db.execute('INSERT OR REPLACE INTO imported VALUES(?,?,?)',(key,checksum,str(output)))
                results.append((source,'ok',output))
            except Cancelled:raise
            except Exception as exc:results.append((source,'error',str(exc)))
    return results

class StableFiles:
    """Wait for a scanner to stop changing size/mtime over multiple polls."""
    def __init__(self,required=2):self.seen={};self.required=required
    def ready(self,folder):
        current={};ready=[]
        for path in sorted(Path(folder).iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED:continue
            stat=path.stat();stamp=(stat.st_size,stat.st_mtime_ns)
            old,count=self.seen.get(path,(None,0));count=count+1 if stamp==old else 0
            current[path]=(stamp,count)
            if count>=self.required:ready.append(path)
        self.seen=current;return ready
