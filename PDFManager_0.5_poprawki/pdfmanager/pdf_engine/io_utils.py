"""Bezpieczny, atomowy zapis plików PDF — wspólny dla wszystkich silników.

Krytyczne dla Windows: nadpisanie pliku, który wciąż jest otwarty (ma aktywny
uchwyt) w tym samym procesie, zawodzi na Windows z błędem "plik jest używany
przez inny proces" (w przeciwieństwie do Linux/macOS, gdzie zwykle się to
udaje). Dlatego każda funkcja zapisu w tym module operuje na danych w
pamięci i nie wymaga, by wywołujący miał otwarty `pymupdf.Document` na
docelowej ścieżce w momencie zapisu — a warstwa UI (patrz `PdfViewerWidget`)
musi zamknąć swój własny uchwyt na plik PRZED wywołaniem funkcji silnika,
a otworzyć go ponownie PO zapisie.
"""
from __future__ import annotations

from pdfmanager.security.limits import safe_open

from pathlib import Path
from typing import Callable, TypeVar

import pymupdf

T = TypeVar("T")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Zapisuje `data` do `path` atomowo (plik tymczasowy + zamiana).

    Wywołujący powinien najpierw zserializować dokument do bajtów
    (``doc.tobytes(...)``) i ZAMKNĄĆ swój ``pymupdf.Document`` — dopiero
    potem wywołać tę funkcję. Patrz docstring modułu.
    """
    from pdfmanager.dms.jobs import checkpoint
    checkpoint()
    path = Path(path)
    import os
    import tempfile
    fd, name = tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    tmp_path=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)



def mutate_pdf_file(path: Path, mutate: Callable[[pymupdf.Document], T]) -> T:
    """Otwiera PDF z `path`, wywołuje `mutate(doc)`, zapisuje wynik atomowo.

    Standardowy wzorzec dla wszystkich operacji silnika PDF modyfikujących
    plik w miejscu (edycja tekstu, adnotacje, operacje na stronach):
    otwórz -> zmutuj w pamięci -> zserializuj -> ZAMKNIJ -> zapisz atomowo.
    """
    path = Path(path)
    doc = safe_open(str(path))
    try:
        result = mutate(doc)
        data = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
    atomic_write_bytes(path, data)
    return result


def new_pdf_file(path: Path, build: Callable[[pymupdf.Document], None]) -> None:
    """Tworzy nowy dokument PDF od zera, wypełnia go `build(doc)` i zapisuje atomowo."""
    doc = safe_open()
    try:
        build(doc)
        data = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()
    atomic_write_bytes(path, data)

def atomic_copy_file(source: Path,target: Path) -> None:
    """Atomic streamed copy avoids loading large documents solely for saving."""
    import tempfile,os,shutil
    from pdfmanager.dms.jobs import checkpoint
    checkpoint();target=Path(target)
    fd,name=tempfile.mkstemp(prefix=target.name+'.',suffix='.tmp',dir=target.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as output,Path(source).open('rb') as input_file:
            shutil.copyfileobj(input_file,output,1024*1024);output.flush();os.fsync(output.fileno())
        checkpoint();temporary.replace(target)
    finally:temporary.unlink(missing_ok=True)
