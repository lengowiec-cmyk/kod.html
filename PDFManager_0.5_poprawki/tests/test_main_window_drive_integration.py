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


def test_save_to_drive_queues_encrypted_snapshot(qapp, tmp_path):
    from pdfmanager.drive.teamwork import Outbox
    from pdfmanager.dms.preferences import Preferences
    from pdfmanager.ui.main_window import DriveTabInfo
    win=MainWindow();source=tmp_path/'cached.pdf';_make_local_pdf(source);win.open_document(str(source))
    client=MagicMock(spec=DriveApiClient);client._team_account_id='account';viewer=win._current_viewer();viewer.drive_info=DriveTabInfo('file123',_drive_file(),client)
    Preferences().put('transport_employee','Anna');outbox=Outbox(tmp_path/'outbox')
    with patch('pdfmanager.drive.teamwork.Outbox',return_value=outbox):job=win._save_to_drive()
    assert job;assert outbox.items()[0]['state']=='Oczekuje na wysłanie';client.upload_new_revision.assert_not_called()
    restored=tmp_path/'restored.pdf';outbox.recover(job,restored);assert restored.read_bytes()==viewer.path.read_bytes();win.close()


def test_save_to_drive_failure_warns_and_retains_document(qapp,tmp_path):
    from pdfmanager.dms.preferences import Preferences
    from pdfmanager.ui.main_window import DriveTabInfo
    win=MainWindow();source=tmp_path/'cached.pdf';_make_local_pdf(source);win.open_document(str(source))
    client=MagicMock(spec=DriveApiClient);client._team_account_id='account';viewer=win._current_viewer();viewer.drive_info=DriveTabInfo('file123',_drive_file(),client);Preferences().put('transport_employee','Anna')
    with patch('pdfmanager.drive.teamwork.Outbox.enqueue',side_effect=OSError('disk full')),patch('pdfmanager.ui.main_window.QMessageBox.warning') as warning:
        assert win._save_to_drive() is False;warning.assert_called_once()
    assert viewer.path.exists();client.upload_new_revision.assert_not_called();win.close()


def test_local_tab_has_no_drive_actions_enabled(qapp, tmp_path):
    win = MainWindow()
    local_path = tmp_path / "local.pdf"
    _make_local_pdf(local_path)
    win.open_document(str(local_path))

    assert win._action_drive_save.isEnabled() is False
    assert win._action_drive_save_as_new.isEnabled() is False
    win.close()
