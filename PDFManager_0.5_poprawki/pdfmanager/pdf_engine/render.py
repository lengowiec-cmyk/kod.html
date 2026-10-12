"""Renderowanie stron PDF do podglądu (PyMuPDF).

Ten moduł odpowiada wyłącznie za odczyt i renderowanie — nie modyfikuje
dokumentu. Edycja istniejącego tekstu zostanie dodana w Etapie 2 jako
osobny moduł (``pdf_engine/text_edit.py``), zgodnie z przyjętą architekturą
(silnik edycji ma być wymienny, patrz ocena silników PDF).
"""
from __future__ import annotations

from pdfmanager.security.limits import pixmap as limited_pixmap

from pdfmanager.security.limits import safe_open

from pathlib import Path

import pymupdf
from PySide6.QtGui import QImage

DEFAULT_DPI = 96


def safe_render_scale(width,height,zoom):
    import math
    if not all(math.isfinite(float(v)) and float(v)>0 for v in (width,height,zoom)):raise ValueError('Nieprawidłowy rozmiar strony lub skala.')
    return min(zoom,math.sqrt(20_000_000/(width*height)),16384/max(width,height))

def render_page_to_qimage(page: "pymupdf.Page", zoom: float = 1.0) -> QImage:
    """Renderuje pojedynczą stronę PyMuPDF do QImage. ``zoom``=1.0 to DEFAULT_DPI.

    Współdzielone przez `PdfDocument` (podgląd) i okno zarządzania stronami
    (miniatury), żeby konwersja Pixmap -> QImage istniała w jednym miejscu.
    """
    zoom=safe_render_scale(page.rect.width,page.rect.height,zoom)
    matrix = pymupdf.Matrix(zoom, zoom)
    pix = limited_pixmap(page,matrix=matrix, dpi=None)
    fmt = QImage.Format.Format_RGB888 if pix.n == 3 else QImage.Format.Format_RGBA8888
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
    # Kopia, bo bufor `pix.samples` zwalniany jest po wyjściu z funkcji.
    return image.copy()


def validated_png(data):
    import struct
    if len(data)<24 or data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Proces PDF zwrócił nieprawidłowy obraz.')
    width,height=struct.unpack('>II',data[16:24])
    from pdfmanager.security.limits import check_pixels
    check_pixels(width,height)
    if max(width,height)>16384:raise ValueError('Obraz przekracza limit wymiarów.')
    image=QImage.fromData(data,'PNG')
    if image.isNull():raise ValueError('Nie można odczytać obrazu strony.')
    return image

class PdfDocument:
    """PDF metadata/raster proxy. Native parsing runs in resource-limited workers."""
    def __init__(self,path):
        from pdfmanager.security.isolation import call
        self.path=Path(path);self._info=call('document.info',self.path);self._closed=False;self._thumbnail_cache={}
        if self._info['protected']:raise ValueError('PDF wymaga hasła.')
    @property
    def page_count(self):return self._info['pages']
    def close(self):self._closed=True
    def render_page(self,page_index,zoom=1.0):
        from pdfmanager.security.isolation import call
        if self._closed:raise RuntimeError('Dokument jest zamknięty.')
        if not 0<=page_index<self.page_count:raise IndexError('Nieprawidłowa strona.')
        width,height=self.page_size_points(page_index);zoom=safe_render_scale(width,height,zoom)
        if zoom<=.26:
            key=(page_index,round(zoom,4))
            if key not in self._thumbnail_cache:
                for index,data in call('document.thumbnail_batch',self.path,page_index,zoom):self._thumbnail_cache[(index,round(zoom,4))]=data
                while len(self._thumbnail_cache)>160:self._thumbnail_cache.pop(next(iter(self._thumbnail_cache)))
            return validated_png(self._thumbnail_cache[key])
        return validated_png(call('document.render',self.path,page_index,zoom))
    def page_size_points(self,index):
        x0,y0,x1,y1=self._info['sizes'][index];return x1-x0,y1-y0
    def rotation_matrix(self,index):return pymupdf.Matrix(self._info['rotations'][index])
    def unrotate_point(self,index,x,y):
        point=pymupdf.Point(x,y)*~self.rotation_matrix(index);return point.x,point.y
    def search_rects(self,index,query):
        from pdfmanager.security.isolation import call
        return call('document.search',self.path,index,query)
    def links(self,index):
        from pdfmanager.security.isolation import call
        return call('document.links',self.path,index)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
