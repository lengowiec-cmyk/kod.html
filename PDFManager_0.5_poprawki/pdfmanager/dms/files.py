
from pdfmanager.security.limits import safe_open
"""Batch split without source modifications or overwriting outputs."""
from pathlib import Path
import tempfile
import pymupdf
from pdfmanager.pdf_engine.page_ops import split_at

def batch_split(paths,output_folder,pages_per_part=1):
    folder=Path(output_folder)
    if not folder.is_dir() or pages_per_part<1:raise ValueError('Wybierz folder i dodatnią liczbę stron na część.')
    results=[]
    from .jobs import checkpoint
    for position,value in enumerate(paths):
        checkpoint(position,len(paths),'Dzielenie: '+Path(value).name)
        source=Path(value)
        try:
            from pdfmanager.security.isolation import call
            info=call('document.info',source)
            if info['protected']:raise ValueError('Dokument wymaga hasła.')
            count=info['pages']
            # Unique per-source folder keeps similarly named inputs and prior runs intact.
            destination=Path(tempfile.mkdtemp(prefix=source.stem+'_split_',dir=folder))
            try:outputs=split_at(source,list(range(pages_per_part-1,count-1,pages_per_part)),destination,source.stem)
            except Exception:
                import shutil
                shutil.rmtree(destination);raise
            results.append((source,outputs,None))
        except Exception as exc:results.append((source,[],str(exc)))
    return results

def transfer_file(source,destination,*,move=False):
    import shutil
    source=Path(source);destination=Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Plik źródłowy i docelowy są takie same.')
    # Exclusive copy works across Windows drives; source is removed only after success.
    with destination.open('xb') as target:
        try:
            with source.open('rb') as original:shutil.copyfileobj(original,target)
        except Exception:
            target.close();destination.unlink(missing_ok=True);raise
    try:shutil.copystat(source,destination)
    except OSError:pass
    if __import__('os').name=='nt':
        # Preserve Windows download provenance when copying an existing document.
        try:
            zone=Path(str(source)+':Zone.Identifier').read_bytes()
            if len(zone)<=16384:Path(str(destination)+':Zone.Identifier').write_bytes(zone)
        except FileNotFoundError:pass
        except OSError:
            import logging
            logging.getLogger(__name__).warning('Nie udało się zachować oznaczenia pobrania pliku z Internetu.')
    if move:source.unlink()
    return destination
