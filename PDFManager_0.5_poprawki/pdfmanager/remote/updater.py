"""Separate Windows helper: waits for GUI exit and runs a verified Inno installer."""
from pathlib import Path
import json,os,sys,time,subprocess
from pdfmanager.remote.protocol import verify,origin,version
from pdfmanager.remote.client import digest
from pdfmanager.remote.storage import load_config,RemoteState
from pdfmanager.remote import APP_VERSION
from pdfmanager.dms.recovery import data_dir
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

def validate_plan(plan,config,device):
    payload=verify(plan['envelope'],config['public_key'],device)
    update=payload.get('update')
    if payload['sequence']<RemoteState().read()['sequence']:raise ValueError('Aktualizacja została zastąpiona nowszym poleceniem administratora.')
    if not update or version(update['version'])<=version(APP_VERSION) or origin(update['url'])!=origin(config['base_url']):raise ValueError('Nieprawidłowa lub starsza aktualizacja.')
    installer=Path(plan['installer']).resolve();root=Path(plan['root']).resolve()
    if not installer.is_file() or installer.suffix.lower()!='.exe' or installer.stat().st_size!=update['size'] or digest(installer)!=update['sha256']:raise ValueError('Instalator nie odpowiada podpisanej aktualizacji.')
    if not root.is_dir() or not (root/'PDFManager.exe').is_file():raise ValueError('Nie znaleziono instalacji PDFManager.')
    if type(plan.get('pid')) is not int or plan['pid']<=0:raise ValueError('Nieprawidłowy proces oczekiwania.')
    return installer,root,update

def wait_windows(pid,timeout=180):
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x100000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return # Already exited.
        raise OSError('Nie można potwierdzić zamknięcia programu.')
    try:
        if kernel.WaitForSingleObject(handle,timeout*1000)!=0:raise TimeoutError('PDFManager nie zakończył działania; aktualizacja została odłożona.')
    finally:kernel.CloseHandle(handle)

def apply(plan,config,device,*,wait=wait_windows,run=subprocess.run,restart=subprocess.Popen):
    installer,root,update=validate_plan(plan,config,device);wait(plan['pid'])
    # Reverify after the wait to detect tampering while the application closes.
    validate_plan(plan,config,device)
    with installer.open('rb') as stream:
        if stream.read(2)!=b'MZ':raise ValueError('Plik nie jest instalatorem Windows.')
    result=run([str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/DIR='+str(root)],timeout=600,check=False)
    if result.returncode not in (0,3010):raise RuntimeError('Instalator zakończył się błędem '+str(result.returncode))
    restart([str(root/'PDFManager.exe')],cwd=str(root));return update['version']

def main(argv=None):
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication(['PDFManagerUpdater']);app.setOrganizationName('PDFManager');app.setApplicationName('PDFManager')
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('plan',type=Path);args=parser.parse_args(argv)
    if sys.platform!='win32':return 2
    output=data_dir()/'update-result.json'
    try:
        if args.plan.stat().st_size>100000:raise ValueError('Plan aktualizacji jest zbyt duży.')
        config=load_config()
        if not config:raise ValueError('Brak zaufanej konfiguracji administratora.')
        release=apply(json.loads(args.plan.read_text(encoding='utf-8')),config,RemoteState().device())
        atomic_write_bytes(output,json.dumps({'ok':True,'version':release}).encode());return 0
    except Exception as exc:
        atomic_write_bytes(output,json.dumps({'ok':False,'error':str(exc)[:1000]}).encode());return 1
if __name__=='__main__':raise SystemExit(main())
