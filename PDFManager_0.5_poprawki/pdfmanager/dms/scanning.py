"""Scanner file intake: no deletion, no overwrites, staged PDF output."""
from pathlib import Path
import tempfile
import os
from datetime import datetime
from pdfmanager.pdf_engine.workflows import merge_inputs

SUPPORTED={'.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'}

def import_scans(inputs,folder,name=None):
    folder=Path(folder)
    if not folder.is_dir():raise ValueError('Wybierz dostępny folder docelowy.')
    paths=[Path(p) for p in inputs]
    if not paths or any(not p.is_file() or p.suffix.lower() not in SUPPORTED for p in paths):raise ValueError('Wybierz pliki PDF lub obrazy ze skanera.')
    from .cabinets import validate_relative
    name=name or datetime.now().strftime('Skan_%Y%m%d_%H%M%S_%f.pdf')
    relative=validate_relative(name)
    if len(relative.parts)!=1 or relative.suffix.lower()!='.pdf':raise ValueError('Podaj nazwę pliku z rozszerzeniem .pdf.')
    output=folder/relative
    if output.exists():raise FileExistsError('Plik docelowy już istnieje.')
    with tempfile.TemporaryDirectory(prefix='pdfmanager-scan-',dir=folder) as temp:
        staged=Path(temp)/'scan.pdf';merge_inputs(paths,staged)
        # Exclusive creation prevents concurrent scanner imports overwriting a file.
        with output.open('xb') as dest:
            try:
                with staged.open('rb') as source:
                    import shutil
                    shutil.copyfileobj(source,dest)
                dest.flush();os.fsync(dest.fileno())
            except Exception:
                dest.close();output.unlink(missing_ok=True);raise
    return output
