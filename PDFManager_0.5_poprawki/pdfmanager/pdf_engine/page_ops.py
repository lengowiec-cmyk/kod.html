"""Operacje na stronach PDF: obrót, usuwanie, duplikowanie, kolejność,
wstawianie z innego pliku, ekstrakcja, podział i scalanie.

Jak w `annotations.py` — każda operacja otwiera plik, mutuje w pamięci i
zapisuje atomowo (patrz `io_utils.mutate_pdf_file` / `new_pdf_file`), co
jest wymagane dla poprawnego działania na Windows.
"""
from __future__ import annotations

from pdfmanager.security.limits import safe_open

from pathlib import Path

import pymupdf

from pdfmanager.pdf_engine.io_utils import mutate_pdf_file, new_pdf_file


class PageOpError(Exception):
    """Błąd podczas operacji na stronach PDF."""


def rotate_page(path: Path, page_index: int, degrees: int) -> None:
    """Obraca stronę względnie o `degrees` (musi być wielokrotnością 90)."""
    if degrees % 90 != 0:
        raise PageOpError("Obrót musi być wielokrotnością 90 stopni.")

    def mutate(doc: pymupdf.Document) -> None:
        page = doc[page_index]
        page.set_rotation((page.rotation + degrees) % 360)

    mutate_pdf_file(path, mutate)


def delete_page(path: Path, page_index: int) -> None:
    def mutate(doc: pymupdf.Document) -> None:
        if doc.page_count <= 1:
            raise PageOpError("Nie można usunąć ostatniej pozostałej strony dokumentu.")
        doc.delete_page(page_index)

    mutate_pdf_file(path, mutate)


def duplicate_page(path: Path, page_index: int) -> None:
    """Wstawia kopię strony `page_index` bezpośrednio po niej."""

    def mutate(doc: pymupdf.Document) -> None:
        doc.fullcopy_page(page_index, page_index)

    mutate_pdf_file(path, mutate)


def move_page(path: Path, from_index: int, to_index: int) -> None:
    """Przenosi stronę `from_index` na pozycję PRZED stroną, która przed
    operacją miała indeks `to_index` (semantyka PyMuPDF `Document.move_page`).

    Przykład: strony [A, B, C, D], `move_page(0, 2)` -> [B, A, C, D]
    (A trafia przed to, co było C). `to_index=-1` oznacza "na koniec, po
    ostatniej stronie". Warstwa UI musi przeliczyć docelowy indeks z
    kontekstu "upuszczono między pozycją X i Y" na ten parametr.
    """

    def mutate(doc: pymupdf.Document) -> None:
        doc.move_page(from_index, to_index)

    mutate_pdf_file(path, mutate)


def reorder_pages(path: Path, new_order: list[int]) -> None:
    """Ustawia nową kolejność stron (np. po przeciągnięciu w Menedżerze stron).

    `new_order` to pełna permutacja indeksów 0..page_count-1 — np. [2,0,1,3]
    oznacza, że dotychczasowa strona 2 staje się pierwsza, strona 0 — druga.
    """

    def mutate(doc: pymupdf.Document) -> None:
        if sorted(new_order) != list(range(doc.page_count)):
            raise PageOpError("Nowa kolejność stron musi zawierać każdą stronę dokumentu dokładnie raz.")
        doc.select(new_order)

    mutate_pdf_file(path, mutate)


def insert_pages_from(
    path: Path,
    source_path: Path,
    at_index: int,
    page_range: tuple[int, int] | None = None,
) -> None:
    """Wstawia strony z `source_path` do `path`, zaczynając od `at_index`.

    `page_range`, jeśli podany, to (pierwsza, ostatnia) strona źródła
    (indeksy od 0, włącznie) do wstawienia; domyślnie wszystkie strony.
    """
    source_path = Path(source_path)

    def mutate(doc: pymupdf.Document) -> None:
        src = safe_open(str(source_path))
        try:
            from_page, to_page = page_range if page_range else (0, src.page_count - 1)
            doc.insert_pdf(src, from_page=from_page, to_page=to_page, start_at=at_index)
        finally:
            src.close()

    mutate_pdf_file(path, mutate)


def extract_pages(path: Path, indices: list[int], output_path: Path) -> None:
    """Zapisuje wybrane strony (indeksy od 0, w podanej kolejności) jako nowy PDF."""
    if not indices:
        raise PageOpError("Nie wybrano żadnych stron do wyodrębnienia.")
    path = Path(path)

    def build(new_doc: pymupdf.Document) -> None:
        src = safe_open(str(path))
        try:
            for index in indices:
                new_doc.insert_pdf(src, from_page=index, to_page=index)
        finally:
            src.close()

    new_pdf_file(Path(output_path), build)


def split_at(path: Path, split_after_pages: list[int], output_dir: Path, base_name: str) -> list[Path]:
    """Dzieli dokument na części. `split_after_pages` to lista numerów stron
    (indeksy od 0) PO których następuje podział, np. [2, 5] dla dokumentu
    10-stronicowego da części: strony 0-2, 3-5, 6-9."""
    path = Path(path)
    output_dir = Path(output_dir)
    src = safe_open(str(path))
    try:
        page_count = src.page_count
    finally:
        src.close()

    boundaries = sorted(set(split_after_pages))
    ranges: list[tuple[int, int]] = []
    start = 0
    for boundary in boundaries:
        if 0 <= boundary < page_count - 1:
            ranges.append((start, boundary))
            start = boundary + 1
    ranges.append((start, page_count - 1))

    output_paths: list[Path] = []
    for part_no, (first, last) in enumerate(ranges, start=1):
        output_path = output_dir / f"{base_name}_part{part_no}.pdf"

        def build(new_doc: pymupdf.Document, first=first, last=last) -> None:
            src_doc = safe_open(str(path))
            try:
                new_doc.insert_pdf(src_doc, from_page=first, to_page=last)
            finally:
                src_doc.close()

        new_pdf_file(output_path, build)
        output_paths.append(output_path)

    return output_paths


def merge_documents(paths: list[Path], output_path: Path) -> None:
    if not paths:
        raise PageOpError("Nie wybrano żadnych plików do scalenia.")
    paths = [Path(p) for p in paths]
    if any(p.resolve()==Path(output_path).resolve() for p in paths):
        raise PageOpError('Wybierz plik docelowy inny niż pliki źródłowe.')

    def build(new_doc: pymupdf.Document) -> None:
        for source_path in paths:
            src = safe_open(str(source_path))
            try:
                new_doc.insert_pdf(src)
            finally:
                src.close()

    new_pdf_file(Path(output_path), build)

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['rotate_page', 'delete_page', 'duplicate_page', 'move_page', 'reorder_pages', 'insert_pages_from', 'extract_pages', 'split_at', 'merge_documents']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
