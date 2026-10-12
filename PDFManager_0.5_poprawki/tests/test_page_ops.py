from pathlib import Path

import pymupdf
import pytest

from pdfmanager.pdf_engine.page_ops import (
    PageOpError,
    delete_page,
    duplicate_page,
    extract_pages,
    insert_pages_from,
    merge_documents,
    move_page,
    reorder_pages,
    rotate_page,
    split_at,
)


def _make_pdf(path: Path, labels: list[str]) -> Path:
    doc = pymupdf.open()
    for label in labels:
        doc.new_page(width=300, height=300).insert_text((72, 72), label, fontname="helv", fontsize=20)
    doc.save(str(path))
    doc.close()
    return path


def _labels(path: Path) -> list[str]:
    doc = pymupdf.open(str(path))
    try:
        return [page.get_text().strip() for page in doc]
    finally:
        doc.close()


@pytest.fixture
def four_page_pdf(tmp_path: Path) -> Path:
    return _make_pdf(tmp_path / "four.pdf", ["A", "B", "C", "D"])


def test_rotate_page_changes_rotation(four_page_pdf):
    rotate_page(four_page_pdf, 0, 90)
    doc = pymupdf.open(str(four_page_pdf))
    assert doc[0].rotation == 90
    doc.close()


def test_rotate_rejects_non_multiple_of_90(four_page_pdf):
    with pytest.raises(PageOpError):
        rotate_page(four_page_pdf, 0, 45)


def test_delete_page_removes_correct_page(four_page_pdf):
    delete_page(four_page_pdf, 1)
    assert _labels(four_page_pdf) == ["A", "C", "D"]


def test_delete_last_remaining_page_is_rejected(tmp_path):
    path = _make_pdf(tmp_path / "single.pdf", ["A"])
    with pytest.raises(PageOpError):
        delete_page(path, 0)


def test_duplicate_page_inserts_adjacent_copy(four_page_pdf):
    duplicate_page(four_page_pdf, 1)
    assert _labels(four_page_pdf) == ["A", "B", "B", "C", "D"]


def test_move_page_reorders_correctly(four_page_pdf):
    move_page(four_page_pdf, 0, 2)
    assert _labels(four_page_pdf) == ["B", "A", "C", "D"]


def test_reorder_pages_applies_full_permutation(four_page_pdf):
    reorder_pages(four_page_pdf, [2, 0, 1, 3])
    assert _labels(four_page_pdf) == ["C", "A", "B", "D"]


def test_reorder_pages_rejects_incomplete_permutation(four_page_pdf):
    with pytest.raises(PageOpError):
        reorder_pages(four_page_pdf, [0, 1, 2])


def test_insert_pages_from_another_document(tmp_path, four_page_pdf):
    source = _make_pdf(tmp_path / "source.pdf", ["X", "Y"])
    insert_pages_from(four_page_pdf, source, at_index=2)
    assert _labels(four_page_pdf) == ["A", "B", "X", "Y", "C", "D"]


def test_insert_pages_from_partial_range(tmp_path, four_page_pdf):
    source = _make_pdf(tmp_path / "source.pdf", ["X", "Y", "Z"])
    insert_pages_from(four_page_pdf, source, at_index=0, page_range=(1, 1))
    assert _labels(four_page_pdf) == ["Y", "A", "B", "C", "D"]


def test_extract_pages_creates_new_document_in_order(tmp_path, four_page_pdf):
    output = tmp_path / "extracted.pdf"
    extract_pages(four_page_pdf, [2, 0], output)
    assert _labels(output) == ["C", "A"]
    # Oryginał pozostaje nienaruszony.
    assert _labels(four_page_pdf) == ["A", "B", "C", "D"]


def test_extract_pages_requires_at_least_one_index(tmp_path, four_page_pdf):
    with pytest.raises(PageOpError):
        extract_pages(four_page_pdf, [], tmp_path / "empty.pdf")


def test_split_at_produces_expected_parts(tmp_path):
    source = _make_pdf(tmp_path / "ten.pdf", [str(i) for i in range(10)])
    output_dir = tmp_path / "parts"
    output_dir.mkdir()
    parts = split_at(source, [2, 5], output_dir, "ten")
    assert len(parts) == 3
    assert _labels(parts[0]) == ["0", "1", "2"]
    assert _labels(parts[1]) == ["3", "4", "5"]
    assert _labels(parts[2]) == ["6", "7", "8", "9"]


def test_merge_documents_concatenates_in_order(tmp_path):
    first = _make_pdf(tmp_path / "first.pdf", ["A", "B"])
    second = _make_pdf(tmp_path / "second.pdf", ["C", "D"])
    output = tmp_path / "merged.pdf"
    merge_documents([first, second], output)
    assert _labels(output) == ["A", "B", "C", "D"]


def test_merge_documents_requires_at_least_one_path(tmp_path):
    with pytest.raises(PageOpError):
        merge_documents([], tmp_path / "out.pdf")


def test_rotate_page_leaves_no_temp_file(four_page_pdf):
    rotate_page(four_page_pdf, 0, 90)
    tmp_file = four_page_pdf.with_name(four_page_pdf.name + ".tmp")
    assert not tmp_file.exists()
