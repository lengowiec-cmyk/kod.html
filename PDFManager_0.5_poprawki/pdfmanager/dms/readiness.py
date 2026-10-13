"""Read-only workstation diagnostics: no credentials, document reads or scans."""
import shutil,sys
from pathlib import Path

def checks():
    from .recovery import data_dir
    rows=[];root=data_dir();free=shutil.disk_usage(root).free
    rows.append(('Dysk lokalny','OK' if free>=1024**3 else 'UWAGA',f'{free//1024**2} MB'))
    exe=shutil.which('tesseract')
    if not exe:
        for path in ['C:/Program Files/Tesseract-OCR/tesseract.exe','C:/Program Files (x86)/Tesseract-OCR/tesseract.exe']:
            if Path(path).is_file():exe=path;break
    rows.append(('Tesseract OCR','OK' if exe else 'BRAK','OCR wymaga Tesseract 5; podstawowa edycja PDF działa bez niego.'))
    if exe:
        try:
            from pdfmanager.pdf_engine.workflows import ocr_languages
            available=ocr_languages()
            for code in ['pol','eng','ukr']:rows.append(('OCR '+code,'OK' if code in available else 'BRAK','Model językowy'))
        except Exception as exc:rows.append(('Modele OCR','UWAGA',str(exc)[:200]))
    font=Path(__file__).parents[1]/'resources/fonts/DejaVuSans.ttf'
    rows.append(('Czcionka Unicode','OK' if font.is_file() else 'BRAK','Polskie znaki i cyrylica'))
    rows.append(('Skanowanie WIA','DO TESTU' if sys.platform=='win32' else 'WINDOWS','Wymaga skanera i sterownika na Windows.'))
    rows.append(('Synchronizacja Google Drive','DO TESTU','Sprawdź na komputerze firmowym. Diagnostyka nie zapisuje na Dysku Google.'))
    return rows
