from pathlib import Path
from unittest.mock import patch

import pymupdf

from pdfmanager.drive.api_client import DriveApiClient, DriveFile
from pdfmanager.ui.main_window import DriveTabInfo, MainWindow


def _make_pdf(path: Path, text: str = "Lokalny dokument") -> None:
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), text, fontname="helv", fontsize=12)
    doc.save(str(path))
    doc.close()


def test_save_as_action_disabled_without_open_document(qapp):
    win = MainWindow()
    assert win._action_save_as_local.isEnabled() is False
    win.close()


def test_save_as_action_enabled_after_opening_document(qapp, tmp_path):
    win = MainWindow()
    local_path = tmp_path / "doc.pdf"
    _make_pdf(local_path)
    win.open_document(str(local_path))

    assert win._action_save_as_local.isEnabled() is True
    win.close()


def test_save_as_local_copies_file_and_switches_active_path(qapp, tmp_path):
    win = MainWindow()
    source = tmp_path / "original.pdf"
    _make_pdf(source, "Original document content")
    win.open_document(str(source))

    target = tmp_path / "kopia.pdf"
    with patch("pdfmanager.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(target), "")):
        win._save_as_local()

    assert target.exists()
    viewer = win._current_viewer()
    assert viewer.source_path == target
    assert viewer.path != target
    index = win._tabs.indexOf(viewer)
    assert win._tabs.tabText(index) == "kopia.pdf"

    final_text = pymupdf.open(str(target))[0].get_text()
    assert "Original document content" in final_text
    win.close()


def test_save_as_local_adds_pdf_extension_if_missing(qapp, tmp_path):
    win = MainWindow()
    source = tmp_path / "original.pdf"
    _make_pdf(source)
    win.open_document(str(source))

    target_without_ext = tmp_path / "kopia_bez_rozszerzenia"
    with patch(
        "pdfmanager.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(target_without_ext), "")
    ):
        win._save_as_local()

    expected = target_without_ext.with_suffix(".pdf")
    assert expected.exists()
    win.close()


def test_save_as_local_clears_drive_association(qapp, tmp_path):
    win = MainWindow()
    source = tmp_path / "from_drive.pdf"
    _make_pdf(source)
    win.open_document(str(source))

    viewer = win._current_viewer()
    drive_file = DriveFile(
        id="id1", name="from_drive.pdf", mime_type="application/pdf",
        modified_time="2026-01-01T00:00:00Z", size=10, md5_checksum="chk", parents=("root",),
    )
    from unittest.mock import MagicMock

    viewer.drive_info = DriveTabInfo(file_id="id1", baseline=drive_file, client=MagicMock(spec=DriveApiClient))
    win._update_drive_actions()
    assert win._action_drive_save.isEnabled() is True

    target = tmp_path / "local_copy.pdf"
    with patch("pdfmanager.ui.main_window.QFileDialog.getSaveFileName", return_value=(str(target), "")):
        win._save_as_local()

    assert viewer.drive_info is None
    assert win._action_drive_save.isEnabled() is False
    win.close()


def test_open_document_above_threshold_builds_copy_in_background(qapp, tmp_path, monkeypatch):
    win = MainWindow()
    monkeypatch.setattr(MainWindow, "_ASYNC_OPEN_THRESHOLD_BYTES", 0)  # wymuś ścieżkę run_job nawet dla małego pliku
    source = tmp_path / "duzy_skan.pdf"
    _make_pdf(source, "Tresc skopiowana w tle")
    win.open_document(str(source))

    viewer = win._current_viewer()
    assert viewer is not None and viewer.is_loaded
    assert viewer.working_copy is not None and viewer.working_copy.path.is_file()
    assert "Tresc skopiowana w tle" in pymupdf.open(str(viewer.path))[0].get_text()
    win.close()


def test_open_document_cancelled_background_copy_opens_nothing(qapp, tmp_path, monkeypatch):
    win = MainWindow()
    monkeypatch.setattr(MainWindow, "_ASYNC_OPEN_THRESHOLD_BYTES", 0)
    monkeypatch.setattr(
        "pdfmanager.ui.background_job.run_job",
        lambda parent, title, function, on_success=None: None,
    )
    source = tmp_path / "anulowany.pdf"
    _make_pdf(source)
    win.open_document(str(source))
    assert win._current_viewer() is None
    win.close()


def test_save_as_local_cancelled_dialog_does_nothing(qapp, tmp_path):
    win = MainWindow()
    source = tmp_path / "original.pdf"
    _make_pdf(source)
    win.open_document(str(source))
    viewer = win._current_viewer()
    original_path = viewer.path

    with patch("pdfmanager.ui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
        win._save_as_local()

    assert viewer.path == original_path
    win.close()
