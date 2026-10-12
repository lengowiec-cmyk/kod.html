"""Adnotacje PDF: podświetlenia, notatki, tekst, kształty, obrazy/podpisy.

Każda funkcja jest samodzielna i atomowa: otwiera plik, dodaje/usuwa jedną
adnotację, zapisuje wynik (patrz `io_utils.mutate_pdf_file` — zamykamy
dokument przed zapisem na dysk, co jest konieczne dla poprawnego działania
na Windows, gdzie nadpisanie pliku z otwartym uchwytem kończy się błędem).
"""
from __future__ import annotations

from pdfmanager.security.limits import safe_open

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from pdfmanager.pdf_engine.io_utils import mutate_pdf_file

RGB = tuple[float, float, float]
RectTuple = tuple[float, float, float, float]


@dataclass(frozen=True)
class AnnotationInfo:
    xref: int
    page_index: int
    type_name: str
    rect: RectTuple
    content: str


def _as_rect(rect: RectTuple) -> pymupdf.Rect:
    r = pymupdf.Rect(*rect)
    r.normalize()
    return r


def _words_as_rects(page: pymupdf.Page, rect: pymupdf.Rect) -> list[pymupdf.Rect]:
    """Zwraca prostokąty poszczególnych słów przecinających `rect` — używane,
    by podświetlenie/podkreślenie/przekreślenie obejmowało realny tekst, a
    nie cały zaznaczony prostokąt (który zwykle jest wyższy niż litery)."""
    word_rects: list[pymupdf.Rect] = []
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        word_rect = pymupdf.Rect(x0, y0, x1, y1)
        if word_rect.intersects(rect):
            word_rects.append(word_rect)
    return word_rects


def _text_markup(path: Path, page_index: int, rect: RectTuple, annot_type: str) -> AnnotationInfo | None:
    def mutate(doc: pymupdf.Document) -> AnnotationInfo | None:
        page = doc[page_index]
        quads = _words_as_rects(page, _as_rect(rect))
        if not quads:
            return None
        if annot_type == "Highlight":
            annot = page.add_highlight_annot(quads)
            annot.set_blendmode("Multiply")
            annot.update()
        elif annot_type == "Underline":
            annot = page.add_underline_annot(quads)
        else:
            annot = page.add_strikeout_annot(quads)
        return AnnotationInfo(annot.xref, page_index, annot_type, tuple(annot.rect), "")

    return mutate_pdf_file(path, mutate)


def add_highlight(path: Path, page_index: int, rect: RectTuple) -> AnnotationInfo | None:
    return _text_markup(path, page_index, rect, "Highlight")


def add_underline(path: Path, page_index: int, rect: RectTuple) -> AnnotationInfo | None:
    return _text_markup(path, page_index, rect, "Underline")


def add_strikeout(path: Path, page_index: int, rect: RectTuple) -> AnnotationInfo | None:
    return _text_markup(path, page_index, rect, "StrikeOut")


def add_sticky_note(path: Path, page_index: int, point: tuple[float, float], text: str) -> AnnotationInfo:
    def mutate(doc: pymupdf.Document) -> AnnotationInfo:
        page = doc[page_index]
        annot = page.add_text_annot(point, text)
        return AnnotationInfo(annot.xref, page_index, "Text", tuple(annot.rect), text)

    return mutate_pdf_file(path, mutate)


def add_free_text(
    path: Path,
    page_index: int,
    rect: RectTuple,
    text: str,
    fontsize: float = 12.0,
    color: RGB = (0.0, 0.0, 0.0),
) -> AnnotationInfo:
    def mutate(doc: pymupdf.Document) -> AnnotationInfo:
        page = doc[page_index]
        annot = page.add_freetext_annot(_as_rect(rect), text, fontsize=fontsize, text_color=color)
        return AnnotationInfo(annot.xref, page_index, "FreeText", tuple(annot.rect), text)

    return mutate_pdf_file(path, mutate)


def add_rectangle(path: Path, page_index: int, rect: RectTuple, color: RGB = (0.0, 0.0, 0.0), width: float = 1.5) -> AnnotationInfo:
    def mutate(doc: pymupdf.Document) -> AnnotationInfo:
        page = doc[page_index]
        annot = page.add_rect_annot(_as_rect(rect))
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        return AnnotationInfo(annot.xref, page_index, "Square", tuple(annot.rect), "")

    return mutate_pdf_file(path, mutate)


def add_circle(path: Path, page_index: int, rect: RectTuple, color: RGB = (0.0, 0.0, 0.0), width: float = 1.5) -> AnnotationInfo:
    def mutate(doc: pymupdf.Document) -> AnnotationInfo:
        page = doc[page_index]
        annot = page.add_circle_annot(_as_rect(rect))
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        return AnnotationInfo(annot.xref, page_index, "Circle", tuple(annot.rect), "")

    return mutate_pdf_file(path, mutate)


def add_line(
    path: Path,
    page_index: int,
    start: tuple[float, float],
    end: tuple[float, float],
    color: RGB = (0.0, 0.0, 0.0),
    width: float = 1.5,
) -> AnnotationInfo:
    def mutate(doc: pymupdf.Document) -> AnnotationInfo:
        page = doc[page_index]
        annot = page.add_line_annot(start, end)
        annot.set_colors(stroke=color)
        annot.set_border(width=width)
        annot.update()
        return AnnotationInfo(annot.xref, page_index, "Line", tuple(annot.rect), "")

    return mutate_pdf_file(path, mutate)


def add_image_stamp(path: Path, page_index: int, rect: RectTuple, image_path: Path) -> AnnotationInfo:
    """Wstawia obraz (np. skan podpisu) jako znaczek w podanym prostokącie."""
    image_path = Path(image_path)

    from pdfmanager.security.limits import check_file,check_pixels
    from PIL import Image
    check_file(image_path)
    with Image.open(image_path) as image:check_pixels(image.width,image.height)
    def mutate(doc: pymupdf.Document) -> AnnotationInfo:
        page = doc[page_index]
        target = _as_rect(rect)
        page.insert_image(target, filename=str(image_path))
        return AnnotationInfo(xref=-1, page_index=page_index, type_name="stamp", rect=tuple(target), content=image_path.name)

    return mutate_pdf_file(path, mutate)


def list_annotations(path: Path, page_index: int) -> list[AnnotationInfo]:
    path = Path(path)
    doc = safe_open(str(path))
    try:
        page = doc[page_index]
        result = []
        for annot in page.annots():
            result.append(
                AnnotationInfo(
                    xref=annot.xref,
                    page_index=page_index,
                    type_name=annot.type[1],
                    rect=tuple(annot.rect),
                    content=annot.info.get("content", ""),
                )
            )
        return result
    finally:
        doc.close()


def delete_annotation(path: Path, page_index: int, xref: int) -> bool:
    def mutate(doc: pymupdf.Document) -> bool:
        page = doc[page_index]
        for annot in page.annots():
            if annot.xref == xref:
                page.delete_annot(annot)
                return True
        return False

    return mutate_pdf_file(path, mutate)


def add_arrow(path: Path, page_index: int, start: tuple, end: tuple) -> None:
    def mutate(doc):
        page=doc[page_index]
        annot=page.add_line_annot(start,end)
        annot.set_line_ends(0,5);annot.set_colors(stroke=(.8,.2,.2));annot.set_border(width=1.5);annot.update()
    mutate_pdf_file(path,mutate)


def add_polygon(path: Path, page_index: int, points: list[tuple]) -> None:
    def mutate(doc):
        page=doc[page_index]
        annot=page.add_polygon_annot(points)
        annot.set_colors(stroke=(.8,.2,.2));annot.set_border(width=1.5);annot.update()
    mutate_pdf_file(path,mutate)


def update_note(path: Path, page_index: int, xref: int, content: str) -> None:
    def mutate(doc):
        page=doc[page_index]
        annot=page.load_annot(xref)
        if annot is None:raise ValueError('Nie znaleziono notatki.')
        annot.set_info(content=content);annot.update()
    mutate_pdf_file(path,mutate)

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['add_highlight', 'add_underline', 'add_strikeout', 'add_sticky_note', 'add_free_text', 'add_rectangle', 'add_circle', 'add_line', 'add_image_stamp', 'list_annotations', 'delete_annotation', 'add_arrow', 'add_polygon', 'update_note']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
