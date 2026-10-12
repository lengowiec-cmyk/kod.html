from pathlib import Path

import pymupdf
import pytest

from pdfmanager.pdf_engine.annotations import (
    add_circle,
    add_free_text,
    add_highlight,
    add_image_stamp,
    add_line,
    add_rectangle,
    add_sticky_note,
    add_strikeout,
    add_underline,
    delete_annotation,
    list_annotations,
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Highlight this important phrase please", fontname="helv", fontsize=12)
    path = tmp_path / "annotate.pdf"
    doc.save(str(path))
    doc.close()
    return path


def _word_rect_on_page(path: Path, page_index: int = 0) -> tuple[float, float, float, float]:
    doc = pymupdf.open(str(path))
    try:
        words = doc[page_index].get_text("words")
        x0, y0, x1, y1 = words[0][:4]
        return (x0 - 1, y0 - 1, x1 + 1, y1 + 1)
    finally:
        doc.close()


def test_highlight_covers_intersecting_words(sample_pdf):
    rect = _word_rect_on_page(sample_pdf)
    info = add_highlight(sample_pdf, 0, rect)
    assert info is not None
    assert info.type_name == "Highlight"

    annots = list_annotations(sample_pdf, 0)
    assert len(annots) == 1
    assert annots[0].type_name == "Highlight"


def test_highlight_on_empty_area_returns_none(sample_pdf):
    info = add_highlight(sample_pdf, 0, (72, 700, 500, 750))
    assert info is None
    assert list_annotations(sample_pdf, 0) == []


def test_underline_and_strikeout(sample_pdf):
    rect = _word_rect_on_page(sample_pdf)
    add_underline(sample_pdf, 0, rect)
    add_strikeout(sample_pdf, 0, rect)
    annots = list_annotations(sample_pdf, 0)
    types = {a.type_name for a in annots}
    assert types == {"Underline", "StrikeOut"}


def test_sticky_note_has_content(sample_pdf):
    info = add_sticky_note(sample_pdf, 0, (300, 300), "Sprawdź ten akapit — ąęćżź")
    assert info.type_name == "Text"

    annots = list_annotations(sample_pdf, 0)
    assert len(annots) == 1
    assert annots[0].content == "Sprawdź ten akapit — ąęćżź"


def test_free_text_annotation(sample_pdf):
    info = add_free_text(sample_pdf, 0, (100, 400, 300, 440), "Komentarz redakcyjny")
    assert info.type_name == "FreeText"
    annots = list_annotations(sample_pdf, 0)
    assert annots[0].type_name == "FreeText"


def test_rectangle_circle_and_line_shapes(sample_pdf):
    add_rectangle(sample_pdf, 0, (50, 500, 200, 550), color=(1, 0, 0))
    add_circle(sample_pdf, 0, (220, 500, 320, 550), color=(0, 1, 0))
    add_line(sample_pdf, 0, (50, 600), (300, 600), color=(0, 0, 1))

    types = {a.type_name for a in list_annotations(sample_pdf, 0)}
    assert types == {"Square", "Circle", "Line"}


def test_image_stamp_inserts_image(sample_pdf, tmp_path):
    image_path = tmp_path / "znaczek.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50))
    pix.set_rect(pix.irect, (10, 20, 30))
    pix.save(str(image_path))

    info = add_image_stamp(sample_pdf, 0, (400, 700, 460, 750), image_path)
    assert info.type_name == "stamp"

    reopened = pymupdf.open(sample_pdf)
    assert len(reopened[0].get_images()) >= 1
    reopened.close()


def test_delete_annotation_by_xref(sample_pdf):
    rect = _word_rect_on_page(sample_pdf)
    info = add_highlight(sample_pdf, 0, rect)
    assert len(list_annotations(sample_pdf, 0)) == 1

    deleted = delete_annotation(sample_pdf, 0, info.xref)
    assert deleted is True
    assert list_annotations(sample_pdf, 0) == []


def test_delete_unknown_xref_returns_false(sample_pdf):
    assert delete_annotation(sample_pdf, 0, 99999) is False


def test_atomic_save_leaves_no_temp_file(sample_pdf):
    rect = _word_rect_on_page(sample_pdf)
    add_highlight(sample_pdf, 0, rect)
    tmp_file = sample_pdf.with_name(sample_pdf.name + ".tmp")
    assert not tmp_file.exists()
