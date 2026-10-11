"""Testy okna Menedżera stron: miniatury, operacje, zmiana kolejności."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pymupdf
from PySide6.QtWidgets import QMessageBox

from pdfmanager.ui.page_manager_dialog import PAGE_INDEX_ROLE, PageManagerDialog


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


def _select_rows(dialog: PageManagerDialog, rows: list[int]) -> None:
    dialog._list.clearSelection()
    for row in rows:
        dialog._list.item(row).setSelected(True)


def test_loads_one_item_per_page(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B", "C"])
    dialog = PageManagerDialog(path)
    assert dialog._list.count() == 3
    assert [dialog._list.item(i).data(PAGE_INDEX_ROLE) for i in range(3)] == [0, 1, 2]


def test_rotate_selected_page(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B"])
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [1])
    dialog._rotate_selected(90)

    doc = pymupdf.open(str(path))
    assert doc[1].rotation == 90
    doc.close()


def test_duplicate_selected_page(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B"])
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [0])
    dialog._duplicate_selected()

    assert _labels(path) == ["A", "A", "B"]
    assert dialog._list.count() == 3


def test_delete_selected_page_with_confirmation(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B", "C"])
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [1])

    with patch("pdfmanager.ui.page_manager_dialog.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        dialog._delete_selected()

    assert _labels(path) == ["A", "C"]


def test_delete_cancelled_by_user_keeps_pages(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B"])
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [0])

    with patch("pdfmanager.ui.page_manager_dialog.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        dialog._delete_selected()

    assert _labels(path) == ["A", "B"]


def test_extract_selected_pages_to_new_file(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B", "C"])
    output = tmp_path / "out.pdf"
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [0, 2])

    with patch("pdfmanager.ui.page_manager_dialog.QFileDialog.getSaveFileName", return_value=(str(output), "")), \
         patch("pdfmanager.ui.page_manager_dialog.QMessageBox.information"):
        dialog._extract_selected()

    assert _labels(output) == ["A", "C"]
    assert _labels(path) == ["A", "B", "C"]  # oryginał nienaruszony


def test_insert_from_file_adds_pages_after_selection(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B"])
    source = _make_pdf(tmp_path / "source.pdf", ["X"])
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [0])

    with patch("pdfmanager.ui.page_manager_dialog.QFileDialog.getOpenFileName", return_value=(str(source), "")):
        dialog._insert_from_file()

    assert _labels(path) == ["A", "X", "B"]


def test_split_selected_pages_creates_parts(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B", "C", "D"])
    output_dir = tmp_path / "parts"
    output_dir.mkdir()
    dialog = PageManagerDialog(path)
    _select_rows(dialog, [1])

    with patch("pdfmanager.ui.page_manager_dialog.QFileDialog.getExistingDirectory", return_value=str(output_dir)), \
         patch("pdfmanager.ui.page_manager_dialog.QMessageBox.information"):
        dialog._split_selected()

    parts = sorted(output_dir.glob("*.pdf"))
    assert len(parts) == 2
    assert _labels(parts[0]) == ["A", "B"]
    assert _labels(parts[1]) == ["C", "D"]


def test_commit_current_order_persists_drag_drop_reorder(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf", ["A", "B", "C", "D"])
    dialog = PageManagerDialog(path)

    # Symulujemy wynik przeciągnięcia: strona z indeksem 2 (C) trafia na początek.
    item = dialog._list.takeItem(2)
    dialog._list.insertItem(0, item)

    dialog._commit_current_order()

    assert _labels(path) == ["C", "A", "B", "D"]
    assert [dialog._list.item(i).data(PAGE_INDEX_ROLE) for i in range(4)] == [0, 1, 2, 3]
