from pathlib import Path
import pytest
import pymupdf
from pdfmanager.pdf_engine.extended_ops import search_text, export_images, stamp_document, flatten_document

@pytest.fixture
def source(tmp_path):
    path = tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        for text in ['Hello PDF', 'Second Hello']:
            page = doc.new_page()
            page.insert_text((50, 80), text)
        doc.save(path)
    return path


def test_search(source):
    assert search_text(source, 'Hello') == [(0, 1), (1, 1)]
    assert search_text(source, 'missing') == []

@pytest.mark.parametrize('fmt', ['png', 'jpg'])
def test_export_images(source, tmp_path, fmt):
    files = export_images(source, tmp_path/'images', [1], 72, fmt)
    pix = pymupdf.Pixmap(str(files[0]))
    assert pix.width == 595 and pix.height == 842
    with pytest.raises(ValueError):
        export_images(source, tmp_path/'images', [1], 72, fmt)


def test_stamps_preserve_source(source, tmp_path):
    before = source.read_bytes()
    out = tmp_path/'stamped.pdf'
    stamp_document(source, out, 'DRAFT', True)
    assert source.read_bytes() == before
    with pymupdf.open(out) as doc:
        assert len(doc) == 2
        assert 'DRAFT' in doc[0].get_text()
        assert '2 / 2' in doc[1].get_text()
    with pytest.raises(ValueError):
        stamp_document(source, source, 'DRAFT')


def test_flatten(source, tmp_path):
    out = tmp_path/'flattened.pdf'
    flatten_document(source, out, 72)
    with pymupdf.open(out) as doc:
        assert len(doc) == 2
        assert doc[0].get_text() == ''
        assert len(doc[0].get_images()) == 1
    assert search_text(source, 'Hello')


def test_unicode_watermark_preserves_bookmarks_and_metadata(source, tmp_path):
    with pymupdf.open(source) as doc:
        doc.set_toc([[1, 'Chapter', 1]])
        doc.set_metadata({'title': 'Original title'})
        data = doc.tobytes()
    source.write_bytes(data)
    out = tmp_path/'unicode.pdf'
    stamp_document(source, out, 'ZAŻÓŁĆ GĘŚLĄ JAŹŃ')
    with pymupdf.open(out) as doc:
        assert 'ZAŻÓŁĆ GĘŚLĄ JAŹŃ' in doc[0].get_text()
        assert doc.metadata['title'] == 'Original title'
        assert doc.get_toc() == [[1, 'Chapter', 1]]
