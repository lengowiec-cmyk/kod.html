"""Testy prototypu edycji istniejącego tekstu w PDF (Etap 2).

Pokrywają kategorie dokumentów wymagane w specyfikacji projektu: proste
czcionki standardowe, czcionki osadzone, znaki PL/UK, ryzyko nałożenia się
tekstu (układ wielokolumnowy / tabelaryczny), strony bez tekstu (skan),
dokumenty wielostronicowe i dokumenty z adnotacjami.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from pdfmanager.pdf_engine.text_edit import (
    PyMuPDFTextEditBackend,
    TextEditError,
    WARNING_FALLBACK_FONT,
    WARNING_LAYOUT_MAY_OVERLAP,
)

FALLBACK_FONT_PATH = Path(__file__).resolve().parent.parent / "pdfmanager" / "resources" / "fonts" / "DejaVuSans.ttf"


@pytest.fixture
def engine() -> PyMuPDFTextEditBackend:
    return PyMuPDFTextEditBackend()


def _save(doc: "pymupdf.Document", tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return path


# ---------------------------------------------------------------- proste czcionki standardowe
def test_simple_standard_font_edit_roundtrips_text(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Original invoice text", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "simple.pdf")

    spans = engine.extract_spans(path, 0)
    assert len(spans) == 1
    target = spans[0]
    assert target.text == "Original invoice text"

    result = engine.apply_edit(path, target, "Corrected invoice text")
    assert result.success
    # Standardowa czcionka "helv" nie jest osadzona w pliku -> zawsze fallback.
    assert WARNING_FALLBACK_FONT in result.warnings

    reopened = engine.extract_spans(path, 0)
    assert any(s.text == "Corrected invoice text" for s in reopened)
    assert not any(s.text == "Original invoice text" for s in reopened)


# ---------------------------------------------------------------- czcionki osadzone + PL/UK
def test_embedded_font_covering_polish_and_ukrainian_is_reused_without_fallback(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="Embedded", fontfile=str(FALLBACK_FONT_PATH))
    page.insert_text((72, 72), "Zażółć gęślą jaźń", fontname="Embedded", fontsize=14)
    path = _save(doc, tmp_path, "embedded.pdf")

    spans = engine.extract_spans(path, 0)
    target = spans[0]

    new_text = "Привіт, це поправлений текст із ąśżź"
    result = engine.apply_edit(path, target, new_text)
    assert result.success
    assert WARNING_FALLBACK_FONT not in result.warnings  # oryginalna czcionka pokrywa PL+UK

    reopened = engine.extract_spans(path, 0)
    assert any(s.text == new_text for s in reopened)


# ---------------------------------------------------------------- PL/UK na niestandardowej (nieosadzonej) czcionce
def test_polish_ukrainian_characters_use_fallback_and_roundtrip_correctly(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Plain ascii text", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "plukr.pdf")

    target = engine.extract_spans(path, 0)[0]
    new_text = "Łąka, źrebię, wiśnia — Привіт, українська мова"
    result = engine.apply_edit(path, target, new_text)
    assert result.success
    assert WARNING_FALLBACK_FONT in result.warnings

    reopened_text = pymupdf.open(path)[0].get_text()
    assert new_text in reopened_text


# ---------------------------------------------------------------- ryzyko nałożenia (tabela / wiele kolumn)
def test_overflowing_replacement_in_tight_layout_warns_about_overlap(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    # Dwie "komórki tabeli" na tej samej linii bazowej, blisko siebie.
    page.insert_text((72, 100), "A1", fontname="helv", fontsize=12)
    page.insert_text((110, 100), "B1", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "table.pdf")

    spans = engine.extract_spans(path, 0)
    left_cell = next(s for s in spans if s.text == "A1")

    result = engine.apply_edit(path, left_cell, "A very long overflowing value")
    assert result.success
    assert WARNING_LAYOUT_MAY_OVERLAP in result.warnings


def test_short_replacement_in_tight_layout_does_not_warn_about_overlap(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "A1", fontname="helv", fontsize=12)
    page.insert_text((110, 100), "B1", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "table_ok.pdf")

    spans = engine.extract_spans(path, 0)
    left_cell = next(s for s in spans if s.text == "A1")

    result = engine.apply_edit(path, left_cell, "A2")
    assert WARNING_LAYOUT_MAY_OVERLAP not in result.warnings


# ---------------------------------------------------------------- strona zeskanowana (brak tekstu)
def test_image_only_page_has_no_extractable_spans(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100))
    pix.set_rect(pix.irect, (200, 200, 200))
    page.insert_image(pymupdf.Rect(50, 50, 500, 500), pixmap=pix)
    path = _save(doc, tmp_path, "scanned.pdf")

    spans = engine.extract_spans(path, 0)
    assert spans == []


# ---------------------------------------------------------------- dokument wielostronicowy
def test_editing_one_page_does_not_affect_other_pages(tmp_path, engine):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Page one text", fontname="helv", fontsize=12)
    doc.new_page(width=595, height=842).insert_text((72, 72), "Page two text", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "multipage.pdf")

    page0_span = engine.extract_spans(path, 0)[0]
    engine.apply_edit(path, page0_span, "Page one EDITED")

    reopened = pymupdf.open(path)
    assert "Page one EDITED" in reopened[0].get_text()
    assert "Page two text" in reopened[1].get_text()
    reopened.close()


# ---------------------------------------------------------------- dokument z adnotacjami
def test_annotation_survives_nearby_text_edit(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 200), "Highlighted phrase here", fontname="helv", fontsize=12)
    highlight_rect = pymupdf.Rect(300, 300, 400, 320)
    page.add_highlight_annot(highlight_rect)
    path = _save(doc, tmp_path, "annotated.pdf")

    reopened = pymupdf.open(path)
    assert len(list(reopened[0].annots())) == 1
    reopened.close()

    target = engine.extract_spans(path, 0)[0]
    result = engine.apply_edit(path, target, "Edited phrase here")
    assert result.success

    final = pymupdf.open(path)
    assert len(list(final[0].annots())) == 1
    assert "Edited phrase here" in final[0].get_text()
    final.close()


# ---------------------------------------------------------------- zapis atomowy / integralność danych
def test_apply_edit_leaves_no_temporary_file_behind(tmp_path, engine):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Some text", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "atomic.pdf")

    target = engine.extract_spans(path, 0)[0]
    engine.apply_edit(path, target, "Some other text")

    tmp_file = path.with_name(path.name + ".tmp")
    assert not tmp_file.exists()
    assert path.exists()


def test_empty_replacement_text_is_rejected(tmp_path, engine):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Some text", fontname="helv", fontsize=12)
    path = _save(doc, tmp_path, "empty.pdf")

    target = engine.extract_spans(path, 0)[0]
    with pytest.raises(TextEditError):
        engine.apply_edit(path, target, "")
