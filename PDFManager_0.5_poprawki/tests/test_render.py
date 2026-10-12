from pathlib import Path

import pymupdf
import pytest
from PySide6.QtGui import QImage

from pdfmanager.pdf_engine.render import PdfDocument


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Tworzy prosty, dwustronicowy PDF (A4) z osadzonym tekstem PL/UK."""
    doc = pymupdf.open()
    page1 = doc.new_page(width=595, height=842)  # A4 w punktach
    page1.insert_text((72, 72), "Zażółć gęślą jaźń — strona 1", fontsize=14)
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((72, 72), "Привіт, це тестова сторінка", fontsize=14)
    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_page_count(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        assert doc.page_count == 2


def test_render_page_returns_image_with_expected_aspect_ratio(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        image = doc.render_page(0, zoom=1.0)
        assert isinstance(image, QImage)
        assert image.width() > 0
        assert image.height() > 0
        width_pt, height_pt = doc.page_size_points(0)
        assert abs((image.width() / image.height()) - (width_pt / height_pt)) < 0.01


def test_render_page_zoom_scales_image(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        small = doc.render_page(0, zoom=1.0)
        large = doc.render_page(0, zoom=2.0)
        assert large.width() == pytest.approx(small.width() * 2, abs=2)


def test_invalid_page_index_raises(sample_pdf: Path):
    with PdfDocument(sample_pdf) as doc:
        with pytest.raises(IndexError):
            doc.render_page(99)
