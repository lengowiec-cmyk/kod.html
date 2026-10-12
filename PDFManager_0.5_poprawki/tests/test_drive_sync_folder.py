import sys
from unittest.mock import patch

from pdfmanager.drive.sync_folder import (
    FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS,
    is_online_only,
    looks_like_drive_desktop_folder,
)


def test_is_online_only_returns_none_on_non_windows(tmp_path):
    with patch("pdfmanager.drive.sync_folder.sys.platform", "linux"):
        assert is_online_only(tmp_path / "plik.pdf") is None


def test_is_online_only_detects_cloud_placeholder_flag(tmp_path):
    with patch("pdfmanager.drive.sync_folder.sys.platform", "win32"), \
         patch("pdfmanager.drive.sync_folder._get_file_attributes_windows", return_value=FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS):
        assert is_online_only(tmp_path / "plik.pdf") is True


def test_is_online_only_false_for_normal_downloaded_file(tmp_path):
    with patch("pdfmanager.drive.sync_folder.sys.platform", "win32"), \
         patch("pdfmanager.drive.sync_folder._get_file_attributes_windows", return_value=0x20):  # FILE_ATTRIBUTE_ARCHIVE
        assert is_online_only(tmp_path / "plik.pdf") is False


def test_is_online_only_none_on_invalid_attributes(tmp_path):
    with patch("pdfmanager.drive.sync_folder.sys.platform", "win32"), \
         patch("pdfmanager.drive.sync_folder._get_file_attributes_windows", return_value=0xFFFFFFFF):
        assert is_online_only(tmp_path / "plik.pdf") is None


def test_looks_like_drive_desktop_folder_by_name(tmp_path):
    drive_folder = tmp_path / "Mój Dysk"
    drive_folder.mkdir()
    assert looks_like_drive_desktop_folder(drive_folder) is True


def test_looks_like_drive_desktop_folder_by_marker_file(tmp_path):
    folder = tmp_path / "Dokumenty"
    folder.mkdir()
    (folder / ".tmp.drivedownload").write_text("")
    assert looks_like_drive_desktop_folder(folder) is True


def test_plain_folder_is_not_detected_as_drive_desktop(tmp_path):
    folder = tmp_path / "Dokumenty"
    folder.mkdir()
    (folder / "zwykly_plik.txt").write_text("")
    assert looks_like_drive_desktop_folder(folder) is False
