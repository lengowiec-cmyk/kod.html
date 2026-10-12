"""Edycja istniejącego tekstu w PDF — warstwa abstrakcji + implementacja PyMuPDF.

Warstwa abstrakcji (`TextEditEngine`) jest celowo oddzielona od konkretnej
implementacji, żeby domyślny, open-source'owy silnik oparty na PyMuPDF
(AGPL-3.0) można było później zastąpić silnikiem komercyjnym (np.
Aspose.PDF) bez zmian w resztcie aplikacji — patrz decyzja architektoniczna
zapisana w pamięci projektu (ocena silników PDF, Etap 0).

Metoda PyMuPDF: redakcja oryginalnego fragmentu (z dopasowanym kolorem tła)
i ponowne wstawienie tekstu w tym samym miejscu, tą samą czcionką, rozmiarem
i kolorem. To NIE jest prawdziwy "reflow" — każda operacja kończy się
listą ostrzeżeń (`EditResult.warnings`), gdy zachowanie układu nie jest
gwarantowane (patrz `KNOWN LIMITATIONS` poniżej).
"""
from __future__ import annotations

from pdfmanager.security.limits import pixmap as limited_pixmap

from pdfmanager.security.limits import safe_open
from uuid import uuid4
from pdfmanager.security.isolation import engine_method

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from pdfmanager.pdf_engine.font_resolver import ResolvedFont, resolve_font
from pdfmanager.pdf_engine.io_utils import mutate_pdf_file

# Bity pola "flags" w PyMuPDF get_text("dict"): 0=superscript, 1=italic,
# 2=serifed, 3=monospaced, 4=bold.
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4

# Kody ostrzeżeń — tłumaczone w UI przez translator.tr(f"textedit.warning.{code}")
WARNING_FALLBACK_FONT = "fallback_font_used"
WARNING_BACKGROUND_APPROXIMATED = "background_approximated"
WARNING_LAYOUT_MAY_OVERLAP = "layout_may_overlap"

_BACKGROUND_CONFIDENCE_THRESHOLD = 0.7
_OVERFLOW_TOLERANCE = 1.15  # 15% szerokości dodatkowego miejsca uznajemy za bezpieczne
_MAX_BACKGROUND_SAMPLES = 4000


@dataclass(frozen=True)
class TextSpan:
    """Jeden fragment tekstu na stronie, tak jak go widzi silnik PDF."""

    page_index: int
    span_id: str
    text: str
    bbox: tuple[float, float, float, float]
    origin: tuple[float, float]
    font_name: str
    font_size: float
    color_rgb: tuple[int, int, int]
    bold: bool
    italic: bool


@dataclass(frozen=True)
class EditResult:
    success: bool
    warnings: tuple[str, ...] = ()


class TextEditError(Exception):
    """Błąd podczas edycji istniejącego tekstu PDF."""


class TextEditEngine(ABC):
    """Interfejs silnika edycji istniejącego tekstu — patrz docstring modułu."""

    @abstractmethod
    @engine_method
    def extract_spans(self, path: Path, page_index: int) -> list[TextSpan]:
        """Zwraca wszystkie fragmenty tekstu na danej stronie."""

    @abstractmethod
    @engine_method
    def apply_edit(self, path: Path, span: TextSpan, new_text: str, *, style: TextSpan | None = None, font_file: Path | None = None) -> EditResult:
        """Zamienia tekst fragmentu `span` na `new_text` i zapisuje dokument."""


class PyMuPDFTextEditBackend(TextEditEngine):
    @engine_method
    def extract_spans(self, path: Path, page_index: int) -> list[TextSpan]:
        path = Path(path)
        doc = safe_open(str(path))
        try:
            page = doc[page_index]
            data = page.get_text("dict")
            spans: list[TextSpan] = []
            for block_no, block in enumerate(data["blocks"]):
                if block.get("type") != 0:  # tylko bloki tekstowe, nie obrazy
                    continue
                for line_no, line in enumerate(block["lines"]):
                    for span_no, span in enumerate(line["spans"]):
                        if not span["text"].strip():
                            continue
                        flags = span["flags"]
                        color_int = span["color"]
                        spans.append(
                            TextSpan(
                                page_index=page_index,
                                span_id=f"{block_no}-{line_no}-{span_no}",
                                text=span["text"],
                                bbox=tuple(span["bbox"]),
                                origin=tuple(span["origin"]),
                                font_name=span["font"],
                                font_size=span["size"],
                                color_rgb=(
                                    (color_int >> 16) & 255,
                                    (color_int >> 8) & 255,
                                    color_int & 255,
                                ),
                                bold=bool(flags & _FLAG_BOLD),
                                italic=bool(flags & _FLAG_ITALIC),
                            )
                        )
            return spans
        finally:
            doc.close()

    @engine_method
    def apply_edit(self, path: Path, span: TextSpan, new_text: str, *, style: TextSpan | None = None, font_file: Path | None = None) -> EditResult:
        path = Path(path)
        if not new_text:
            raise TextEditError("Nowy tekst nie może być pusty — użyj usuwania fragmentu (inny tryb).")

        def mutate(doc: pymupdf.Document) -> EditResult:
            page = doc[span.page_index]
            rect = pymupdf.Rect(*span.bbox)

            target = style or span
            resolved = resolve_font(page, target.font_name, new_text, target.bold, target.italic)
            if font_file is not None:
                from pdfmanager.pdf_engine.font_resolver import _font_covers_text
                buffer = Path(font_file).read_bytes()
                if not _font_covers_text(buffer, new_text):
                    raise TextEditError("Wybrana czcionka nie obsługuje wszystkich znaków tekstu.")
                resolved = ResolvedFont("custom_"+uuid4().hex, None, buffer, False)
            neighbor_gap = self._distance_to_next_span_on_line(page, span)
            bg_color, bg_confident = self._detect_background_color(page, rect)

            page.add_redact_annot(rect, fill=bg_color)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=0)

            if resolved.fontbuffer is not None:
                page.insert_font(fontname=resolved.fontname, fontbuffer=resolved.fontbuffer)
            else:
                page.insert_font(fontname=resolved.fontname, fontfile=str(resolved.fontfile))

            color_fraction = tuple(c / 255 for c in target.color_rgb)
            page.insert_text(
                span.origin,
                new_text,
                fontname=resolved.fontname,
                fontsize=target.font_size,
                color=color_fraction,
            )

            warnings: list[str] = []
            if resolved.is_fallback:
                warnings.append(WARNING_FALLBACK_FONT)
            if not bg_confident:
                warnings.append(WARNING_BACKGROUND_APPROXIMATED)
            if self._overflow_risk(resolved, new_text, target, neighbor_gap):
                warnings.append(WARNING_LAYOUT_MAY_OVERLAP)

            return EditResult(success=True, warnings=tuple(warnings))

        return mutate_pdf_file(path, mutate)

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _measure_text_width(resolved: ResolvedFont, text: str, fontsize: float) -> float:
        if resolved.fontbuffer is not None:
            font = pymupdf.Font(fontbuffer=resolved.fontbuffer)
        else:
            font = pymupdf.Font(fontfile=str(resolved.fontfile))
        return font.text_length(text, fontsize=fontsize)

    def _overflow_risk(
        self,
        resolved: ResolvedFont,
        new_text: str,
        span: TextSpan,
        neighbor_gap: float | None,
    ) -> bool:
        new_width = self._measure_text_width(resolved, new_text, span.font_size)
        original_width = span.bbox[2] - span.bbox[0]
        if neighbor_gap is not None:
            return new_width > original_width + neighbor_gap
        return new_width > original_width * _OVERFLOW_TOLERANCE

    @staticmethod
    def _distance_to_next_span_on_line(page, span: TextSpan) -> float | None:
        data = page.get_text("dict")
        best_gap: float | None = None
        for block in data["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for other in line["spans"]:
                    same_line = abs(other["origin"][1] - span.origin[1]) < 1.0
                    to_the_right = other["bbox"][0] >= span.bbox[2] - 0.5
                    is_self = abs(other["bbox"][0] - span.bbox[0]) < 0.1 and abs(other["bbox"][2] - span.bbox[2]) < 0.1
                    if same_line and to_the_right and not is_self:
                        gap = other["bbox"][0] - span.bbox[2]
                        if best_gap is None or gap < best_gap:
                            best_gap = gap
        return best_gap

    @staticmethod
    def _detect_background_color(page, rect: "pymupdf.Rect", zoom: float = 3.0) -> tuple[tuple[float, float, float], bool]:
        try:
            pix = limited_pixmap(page,matrix=pymupdf.Matrix(zoom, zoom), clip=rect)
        except Exception:
            return (1.0, 1.0, 1.0), False

        width, height = pix.width, pix.height
        total_pixels = width * height
        if total_pixels == 0:
            return (1.0, 1.0, 1.0), False

        step = max(1, round((total_pixels / _MAX_BACKGROUND_SAMPLES) ** 0.5))
        counts: dict[tuple[int, int, int], int] = {}
        sampled = 0
        for y in range(0, height, step):
            for x in range(0, width, step):
                pixel = pix.pixel(x, y)[:3]
                counts[pixel] = counts.get(pixel, 0) + 1
                sampled += 1
        if sampled == 0:
            return (1.0, 1.0, 1.0), False

        best_pixel, best_count = max(counts.items(), key=lambda kv: kv[1])
        confidence = best_count / sampled
        normalized = tuple(c / 255 for c in best_pixel)
        return normalized, confidence >= _BACKGROUND_CONFIDENCE_THRESHOLD

def get_default_text_edit_engine() -> TextEditEngine:
    """Punkt rozszerzenia: tu podłącza się alternatywny (płatny) silnik edycji."""
    return PyMuPDFTextEditBackend()
