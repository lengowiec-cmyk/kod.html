"""Optional explicit Microsoft Defender scan; no automatic file remediation."""
from pathlib import Path
import os,sqlite3,time,hashlib
from .limits import check_file

def executable():
    candidates=[]
    platform=Path(os.environ.get('ProgramData',r'C:\ProgramData'))/'Microsoft/Windows Defender/Platform'
    if platform.is_dir():candidates.extend(sorted(platform.glob('*/MpCmdRun.exe'),reverse=True))
    candidates.append(Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Windows Defender/MpCmdRun.exe')
    return next((p for p in candidates if p.is_file()),None)

_trusted_paths={}

def scan(path):
    if os.name!='nt':return 'Unavailable on this platform'
    from pdfmanager.dms.preferences import Preferences
    if not Preferences().get('defender_scan',True):return 'Disabled by user'
    path=Path(path)
    if not path.is_file():return 'Not a file'
    check_file(path)
    tool=executable()
    if tool is None:raise ValueError('Nie znaleziono Windows Defender. Sprawdź ochronę antywirusową lub zmień ustawienie skanowania w sekcji Bezpieczeństwo.')
    from pdfmanager.dms.recovery import data_dir
    resolved=path.resolve();private=resolved.is_relative_to(data_dir()/'recovery');stat=path.stat();stamp=(stat.st_mtime_ns,stat.st_size)
    if private and _trusted_paths.get(resolved)==stamp:return 'Checked working copy'
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    key=digest.hexdigest()
    from pdfmanager.dms.recovery import data_dir
    with sqlite3.connect(data_dir()/'defender-cache.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS checked(hash TEXT PRIMARY KEY,time REAL)')
        previous=db.execute('SELECT time FROM checked WHERE hash=?',(key,)).fetchone()
        if previous and time.time()-previous[0]<600:
            if private:_trusted_paths[resolved]=stamp
            return 'Recently checked'
        from pdfmanager.dms.jobs import run_process
        result=run_process([str(tool),'-Scan','-ScanType','3','-File',str(path.resolve()),'-DisableRemediation'],timeout=180)
        if result.returncode:raise ValueError('Skan antywirusowy nie potwierdził bezpieczeństwa pliku lub wykrył zagrożenie. Otwieranie zostało zablokowane. Sprawdź historię ochrony Windows.')
        db.execute('INSERT OR REPLACE INTO checked VALUES(?,?)',(key,time.time()));db.execute('DELETE FROM checked WHERE time<?',(time.time()-86400,))
        if private:_trusted_paths[resolved]=stamp
        return 'Scanned'

def scan_arguments(args):
    from .isolation import WORKER_MODE
    if WORKER_MODE or os.name!='nt':return
    def visit(value):
        if isinstance(value,Path) and value.suffix.lower() in {'.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp','.zip'} and value.is_file():scan(value)
        elif isinstance(value,(list,tuple)):
            for item in value:visit(item)
    visit(args)
