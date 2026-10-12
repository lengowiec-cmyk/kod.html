"""Run on the user's Windows PC: python tools/check_windows.py [--wia]."""
from pathlib import Path
import argparse
import json
import platform
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--wia',action='store_true',help='List WIA scanner availability without acquiring a scan');args=parser.parse_args()
    report={'platform':platform.platform(),'python':sys.version.split()[0],'checks':{}}
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtPrintSupport import QPrinterInfo
        from PySide6.QtCore import QStandardPaths
        import pymupdf
        app=QApplication.instance() or QApplication([])
        report['checks']['printers']=[p.printerName() for p in QPrinterInfo.availablePrinters()]
        with tempfile.TemporaryDirectory(prefix='PDFManager-sprawdzenie-') as temporary:
            source=Path(temporary)/'Zażółć gęślą jaźń.pdf'
            with pymupdf.open() as doc:doc.new_page().insert_text((30,40),'PDFManager');doc.save(source)
            from pdfmanager.ui.viewer import PdfViewerWidget
            viewer=PdfViewerWidget(str(source),safe_edit=True)
            assert viewer.is_loaded and viewer.page_count==1
            viewer.add_note_at((60,60),'Test');assert not list(pymupdf.open(source)[0].annots() or [])
            output=Path(temporary)/'Zapis.pdf';viewer.working_copy.save(output);assert output.is_file()
            viewer.close();report['checks']['unicode_paths_and_safe_save']='OK'
        from pdfmanager.pdf_engine.workflows import ocr_languages
        try:report['checks']['ocr_languages']=ocr_languages()
        except Exception as exc:report['checks']['ocr_languages']=str(exc)
        if args.wia:
            if sys.platform!='win32':report['checks']['wia']='Windows required'
            else:
                import os
                powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
                command="$m=New-Object -ComObject WIA.DeviceManager; @($m.DeviceInfos | Where-Object {$_.Type -eq 1}).Count"
                result=subprocess.run([str(powershell),'-NoProfile','-Command',command],capture_output=True,text=True,timeout=30)
                report['checks']['wia_scanner_count']=result.stdout.strip() if result.returncode==0 else result.stderr.strip()
        report['licensing']='Closed-source distribution requires resolving PyMuPDF licensing; see LICENSING.md.'
    except Exception as exc:
        report['error']=str(exc)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if 'error' in report else 0
if __name__=='__main__':raise SystemExit(main())
