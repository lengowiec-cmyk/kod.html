"""Renderowanie stron PDF do podglądu (PyMuPDF).

Ten moduł odpowiada wyłącznie za odczyt i renderowanie — nie modyfikuje
dokumentu. Edycja istniejącego tekstu zostanie dodana w Etapie 2 jako
osobny moduł (``pdf_engine/text_edit.py``), zgodnie z przyjętą architekturą
(silnik edycji ma być wymienny, patrz ocena silników PDF).
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtGui import QImage

DEFAULT_DPI = 96


def safe_render_scale(width,height,zoom):
    import math
    if width<=0 or height<=0:raise ValueError('Nieprawidłowy rozmiar strony.')
    return min(zoom,math.sqrt(20_000_000/(width*height)),16384/max(width,height))

def render_page_to_qimage(page: "pymupdf.Page", zoom: float = 1.0) -> QImage:
    """Renderuje pojedynczą stronę PyMuPDF do QImage. ``zoom``=1.0 to DEFAULT_DPI.

    Współdzielone przez `PdfDocument` (podgląd) i okno zarządzania stronami
    (miniatury), żeby konwersja Pixmap -> QImage istniała w jednym miejscu.
    """
    zoom=safe_render_scale(page.rect.width,page.rect.height,zoom)
    matrix = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, dpi=None)
    fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
    # Kopia, bo bufor `pix.samples` zwalniany jest po wyjściu z funkcji.
    return image.copy()


class PdfDocument:
    """Lekka otoczka na ``pymupdf.Document`` używana przez widok podglądu."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._doc = pymupdf.open(str(self.path))

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def close(self) -> None:
        self._doc.close()

    def render_page(self, page_index: int, zoom: float = 1.0) -> QImage:
        if not (0 <= page_index < self.page_count):
            raise IndexError(f"Nieprawidłowy numer strony: {page_index}")
        return render_page_to_qimage(self._doc[page_index], zoom)

    def page_size_points(self, page_index: int) -> tuple[float, float]:
        page = self._doc[page_index]
        rect = page.rect
        return rect.width, rect.height

    def unrotate_point(self,page_index,x,y):
        point=pymupdf.Point(x,y)*self._doc[page_index].derotation_matrix
        return point.x,point.y

    def search_rects(self,page_index,query):
        page=self._doc[page_index]
        return [tuple(rect*page.rotation_matrix) for rect in page.search_for(query)]

    def links(self,page_index):
        page=self._doc[page_index]
        result=[]
        for link in page.get_links():
            entry=dict(link)
            entry['from']=tuple(link['from']*page.derotation_matrix)
            result.append(entry)
        return result

    def __enter__(self) -> "PdfDocument":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
