from pathlib import Path
import math
MAX_INPUT_BYTES=256*1024*1024
MAX_PAGES=5000
MAX_PIXELS=20_000_000
MAX_ATTACHMENT_BYTES=50*1024*1024

class DocumentLimitError(ValueError):pass

def check_file(path):
    if Path(path).stat().st_size>MAX_INPUT_BYTES:raise DocumentLimitError('Plik przekracza limit 256 MB. Podziel dokument na mniejsze części.')

def check_pixels(width,height,dpi=72):
    values=(width,height,dpi)
    if not all(math.isfinite(float(v)) and float(v)>0 for v in values):raise DocumentLimitError('Nieprawidłowy rozmiar strony lub DPI.')
    if width*height*(dpi/72)**2>MAX_PIXELS:raise DocumentLimitError('Operacja przekroczyłaby limit 20 milionów pikseli. Zmniejsz DPI lub rozmiar strony.')

def safe_open(*args,**kwargs):
    import pymupdf
    if args and isinstance(args[0],(str,Path)) and Path(args[0]).is_file():check_file(args[0])
    data=kwargs.get('stream')
    if data is not None and len(data)>MAX_INPUT_BYTES:raise DocumentLimitError('Zbyt duży dokument w pamięci.')
    doc=pymupdf.open(*args,**kwargs)
    if len(doc)>MAX_PAGES:
        doc.close();raise DocumentLimitError('Dokument przekracza limit 5000 stron.')
    return doc

def pixmap(page,*args,**kwargs):
    dpi=kwargs.get('dpi')
    if dpi:check_pixels(page.rect.width,page.rect.height,dpi)
    else:
        matrix=kwargs.get('matrix')
        if matrix:
            rect=page.rect*matrix;check_pixels(rect.width,rect.height)
        else:check_pixels(page.rect.width,page.rect.height)
    return page.get_pixmap(*args,**kwargs)
