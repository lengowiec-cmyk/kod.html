"""Test integracyjny: kliknięcie na tekst w trybie edycji -> dialog -> zapis.

Dialog Qt (`TextStyleDialog.exec`) jest modalny i w środowisku headless
(bez pętli zdarzeń z realną interakcją) zablokowałby test w nieskończoność,
więc podstawiamy go (monkeypatch) — tak jak zrobiłby to użyk, wpisując
nowy tekst i klikając OK.
"""
from __future__ import annotations

from unittest.mock import patch

import pymupdf
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from pdfmanager.ui.main_window import MainWindow


def _make_simple_pdf(path, text="Original clickable text"):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), text, fontname="helv", fontsize=14)
    doc.save(str(path))
    doc.close()


def test_click_in_edit_mode_opens_dialog_and_applies_edit(qapp, tmp_path):
    path = tmp_path / "click.pdf"
    _make_simple_pdf(path)

    win = MainWindow()
    win.open_document(str(path))
    viewer = win._current_viewer()
    viewer.set_edit_mode(True)

    scale = viewer._effective_zoom_matrix_scale()
    click_point = QPoint(int(75 * scale), int(68 * scale))

    with patch("pdfmanager.ui.content_editor.TextStyleDialog.exec", new=lambda dialog: (dialog.text.setPlainText("Changed clickable text"), 1)[1]), \
         patch("pdfmanager.ui.main_window.QMessageBox.warning"):
        # "helv" nie jest osadzona w pliku, więc edycja użyje czcionki zastępczej
        # i wywoła ostrzeżenie — mockujemy je tutaj, bo nie jest przedmiotem tego testu.
        viewer._on_image_clicked(click_point)

    final_text = pymupdf.open(viewer.path)[0].get_text()
    assert "Original clickable text" in pymupdf.open(path)[0].get_text()
    assert "Changed clickable text" in final_text
    assert "Original clickable text" not in final_text
    win.close()


def test_click_outside_edit_mode_does_nothing(qapp, tmp_path):
    path = tmp_path / "noclick.pdf"
    _make_simple_pdf(path)

    win = MainWindow()
    win.open_document(str(path))
    viewer = win._current_viewer()
    # edit_mode pozostaje wyłączony (domyślnie)

    scale = viewer._effective_zoom_matrix_scale()
    click_point = QPoint(int(75 * scale), int(68 * scale))

    with patch("pdfmanager.ui.content_editor.TextStyleDialog.exec") as mock_dialog:
        viewer._on_image_clicked(click_point)
        mock_dialog.assert_not_called()
    win.close()


def test_warning_dialog_shown_when_fallback_font_used(qapp, tmp_path):
    path = tmp_path / "warn.pdf"
    _make_simple_pdf(path)

    win = MainWindow()
    win.open_document(str(path))
    viewer = win._current_viewer()
    viewer.set_edit_mode(True)

    scale = viewer._effective_zoom_matrix_scale()
    click_point = QPoint(int(75 * scale), int(68 * scale))

    with patch("pdfmanager.ui.content_editor.TextStyleDialog.exec", new=lambda dialog: (dialog.text.setPlainText("Zażółć gęślą jaźń"), 1)[1]), \
         patch("pdfmanager.ui.main_window.QMessageBox.warning") as mock_warning:
        viewer._on_image_clicked(click_point)
        assert mock_warning.called  # czcionka "helv" nie jest osadzona -> ostrzeżenie o foncie zastępczym
    win.close()
