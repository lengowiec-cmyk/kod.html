"""Testy integracyjne: narzędzia adnotacji i historia undo/redo w podglądzie."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QPoint

from pdfmanager.pdf_engine.annotations import list_annotations
from pdfmanager.ui.viewer import PdfViewerWidget, TOOL_DELETE_ANNOTATION, TOOL_HIGHLIGHT, TOOL_NOTE, TOOL_RECTANGLE


def _make_pdf(path, text="Highlight this important phrase please"):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 100), text, fontname="helv", fontsize=12)
    doc.save(str(path))
    doc.close()


def _word_pixel_rect(viewer: PdfViewerWidget) -> tuple[QPoint, QPoint]:
    doc = pymupdf.open(str(viewer.path))
    try:
        x0, y0, x1, y1 = doc[0].get_text("words")[0][:4]
    finally:
        doc.close()
    scale = viewer._effective_zoom_matrix_scale()
    return QPoint(int((x0 - 1) * scale), int((y0 - 1) * scale)), QPoint(int((x1 + 1) * scale), int((y1 + 1) * scale))


def test_drag_with_highlight_tool_creates_annotation(qapp, tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)
    viewer = PdfViewerWidget(str(path))
    viewer.set_active_tool(TOOL_HIGHLIGHT)

    start, end = _word_pixel_rect(viewer)
    viewer._on_image_drag_finished(start, end)

    assert len(list_annotations(path, 0)) == 1
    viewer.close()


def test_tiny_drag_is_ignored(qapp, tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)
    viewer = PdfViewerWidget(str(path))
    viewer.set_active_tool(TOOL_RECTANGLE)

    viewer._on_image_drag_finished(QPoint(100, 100), QPoint(100, 100))

    assert list_annotations(path, 0) == []
    viewer.close()


def test_undo_removes_last_annotation_and_redo_restores_it(qapp, tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)
    viewer = PdfViewerWidget(str(path))
    viewer.set_active_tool(TOOL_RECTANGLE)

    viewer._on_image_drag_finished(QPoint(50, 50), QPoint(150, 150))
    assert len(list_annotations(path, 0)) == 1
    assert viewer.can_undo is True
    assert viewer.can_redo is False

    viewer.undo()
    assert list_annotations(path, 0) == []
    assert viewer.can_undo is False
    assert viewer.can_redo is True

    viewer.redo()
    assert len(list_annotations(path, 0)) == 1
    assert viewer.can_redo is False
    viewer.close()


def test_delete_annotation_tool_removes_clicked_annotation(qapp, tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)
    viewer = PdfViewerWidget(str(path))
    viewer.set_active_tool(TOOL_RECTANGLE)
    viewer._on_image_drag_finished(QPoint(50, 50), QPoint(150, 150))
    assert len(list_annotations(path, 0)) == 1

    viewer.set_active_tool(TOOL_DELETE_ANNOTATION)
    viewer._on_image_clicked(QPoint(100, 100))

    assert list_annotations(path, 0) == []
    viewer.close()


def test_note_tool_emits_signal_instead_of_mutating_directly(qapp, tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path)
    viewer = PdfViewerWidget(str(path))
    viewer.set_active_tool(TOOL_NOTE)

    captured = []
    viewer.note_requested.connect(lambda point: captured.append(point))
    viewer._on_image_clicked(QPoint(100, 100))

    assert len(captured) == 1
    assert list_annotations(path, 0) == []  # jeszcze nic nie zapisano — czeka na tekst notatki
    viewer.close()


def test_release_and_reload_document_picks_up_external_change(qapp, tmp_path):
    path = tmp_path / "doc.pdf"
    _make_pdf(path, text="Before")
    viewer = PdfViewerWidget(str(path))
    assert viewer.page_count == 1

    viewer.release_document()
    _make_pdf(path, text="After")  # symuluje zewnętrzną modyfikację (np. przez Menedżera stron)
    viewer.reload_document()

    doc = pymupdf.open(str(viewer.path))
    assert "After" in doc[0].get_text()
    doc.close()
    viewer.close()
