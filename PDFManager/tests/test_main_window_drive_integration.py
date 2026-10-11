"""Test integracyjny: menu Plik -> Google Dysk (Workflow A) w MainWindow.

Uwierzytelnianie i wywołania sieciowe są podstawione (atrapy) — nie mamy
w tym środowisku prawdziwych poświadczeń Google Cloud. Weryfikujemy
rzeczywiste okablowanie: wybór pliku w przeglądarce Dysku -> pobranie do
lokalnego cache -> otwarcie karty -> oznaczenie jej jako „z Dysku” ->
wskaźnik w pasku stanu -> zapis z wykrywaniem konfliktu wersji.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pymupdf
from PySide6.QtWidgets import QDialog

from pdfmanager.drive.api_client import DriveApiClient, DriveConflictError, DriveFile
from pdfmanager.ui.main_window import MainWindow


def _make_local_pdf(path: Path) -> None:
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Treść z Google Dysku", fontname="helv", fontsize=12)
    doc.save(str(path))
    doc.close()


def _drive_file(**overrides) -> DriveFile:
    base = dict(
        id="file123", name="umowa.pdf", mime_type="application/pdf",
        modified_time="2026-01-01T00:00:00Z", size=100, md5_checksum="chk1", parents=("root",),
    )
    base.update(overrides)
    return DriveFile(**base)


def test_connect_drive_downloads_and_opens_document(qapp, tmp_path):
    win = MainWindow()
    drive_file = _drive_file()
    fake_client = MagicMock(spec=DriveApiClient)
    fake_client.download.side_effect = lambda file_id, dest: _make_local_pdf(Path(dest))

    with patch("pdfmanager.ui.main_window.MainWindow._ensure_drive_client", return_value=fake_client), \
         patch("pdfmanager.ui.main_window.DriveBrowserDialog") as mock_dialog_cls:
        mock_dialog = mock_dialog_cls.return_value
        mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
        mock_dialog.selected_file = drive_file

        win._connect_drive()

    viewer = win._current_viewer()
    assert viewer is not None
    assert viewer.drive_info is not None
    assert viewer.drive_info.file_id == "file123"
    assert win._action_drive_save.isEnabled() is True
    assert "umowa.pdf" in win._status_folder_label.text()
    win.close()


def test_save_to_drive_uploads_new_revision(qapp, tmp_path):
    win = MainWindow()
    local_path = tmp_path / "cached.pdf"
    _make_local_pdf(local_path)
    win.open_document(str(local_path))

    viewer = win._current_viewer()
    fake_client = MagicMock(spec=DriveApiClient)
    updated = _drive_file(modified_time="2026-01-02T00:00:00Z")
    fake_client.upload_new_revision.return_value = updated

    from pdfmanager.ui.main_window import DriveTabInfo
    viewer.drive_info = DriveTabInfo(file_id="file123", baseline=_drive_file(), client=fake_client)

    with patch("pdfmanager.ui.main_window.QMessageBox.information") as mock_info:
        win._save_to_drive()
        mock_info.assert_called_once()

    fake_client.upload_new_revision.assert_called_once_with("file123", viewer.path, _drive_file())
    assert viewer.drive_info.baseline.modified_time == "2026-01-02T00:00:00Z"
    win.close()


def test_save_to_drive_shows_conflict_warning(qapp, tmp_path):
    win = MainWindow()
    local_path = tmp_path / "cached.pdf"
    _make_local_pdf(local_path)
    win.open_document(str(local_path))

    viewer = win._current_viewer()
    fake_client = MagicMock(spec=DriveApiClient)
    remote_now = _drive_file(md5_checksum="changed-on-drive")
    fake_client.upload_new_revision.side_effect = DriveConflictError("file123", remote_now)

    from pdfmanager.ui.main_window import DriveTabInfo
    viewer.drive_info = DriveTabInfo(file_id="file123", baseline=_drive_file(), client=fake_client)

    with patch("pdfmanager.ui.main_window.QMessageBox.warning") as mock_warning:
        win._save_to_drive()
        mock_warning.assert_called_once()

    win.close()


def test_local_tab_has_no_drive_actions_enabled(qapp, tmp_path):
    win = MainWindow()
    local_path = tmp_path / "local.pdf"
    _make_local_pdf(local_path)
    win.open_document(str(local_path))

    assert win._action_drive_save.isEnabled() is False
    assert win._action_drive_save_as_new.isEnabled() is False
    win.close()
