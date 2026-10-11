"""Windows WIA common dialog; TWAIN devices use their installed vendor application."""
from pathlib import Path
import sys
import tempfile
from pdfmanager.dms.jobs import run_process

WIA_SCRIPT=r'''
$Destination = $env:PDFMANAGER_WIA_DEST
$ErrorActionPreference = 'Stop'
try {
    $dialog = New-Object -ComObject WIA.CommonDialog
    $image = $dialog.ShowAcquireImage(1,0,0,'{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}',$false,$true,$false)
    if ($null -eq $image) { exit 3 }
    $image.SaveFile($Destination)
} catch { Write-Error $_; exit 1 }
'''

def acquire_wia(destination):
    if sys.platform!='win32':raise RuntimeError('Skanowanie WIA jest dostępne tylko w Windows.')
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError('Docelowy skan już istnieje.')
    import os
    powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    env=os.environ.copy();env['PDFMANAGER_WIA_DEST']=str(destination)
    # Fixed command text; paths are passed as data, not interpolated PowerShell code.
    result=run_process([str(powershell),'-NoProfile','-STA','-Command',WIA_SCRIPT],timeout=900,env=env)
    if result.returncode==3:return None
    if result.returncode or not destination.is_file():raise RuntimeError('Skanowanie WIA nie powiodło się. Sprawdź sterownik i dostępność urządzenia. '+result.stderr[-1000:])
    return destination
