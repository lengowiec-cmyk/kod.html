"""Testy klienta Google Drive API — wszystkie z atrapą `service`, bez sieci."""
from __future__ import annotations

from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from pdfmanager.drive.api_client import (
    DriveApiClient,
    DriveApiError,
    DriveConflictError,
    DriveFile,
    FOLDER_MIME_TYPE,
)

RAW_FOLDER = {"id": "f1", "name": "Dokumenty", "mimeType": FOLDER_MIME_TYPE, "modifiedTime": "2026-01-01T00:00:00Z"}
RAW_PDF = {
    "id": "p1",
    "name": "umowa.pdf",
    "mimeType": "application/pdf",
    "modifiedTime": "2026-01-02T00:00:00Z",
    "size": "12345",
    "md5Checksum": "abc123",
    "parents": ["f1"],
}


def _client_with_execute(return_value=None, side_effect=None) -> tuple[DriveApiClient, MagicMock]:
    service = MagicMock()
    execute = service.files.return_value.list.return_value.execute
    if side_effect is not None:
        execute.side_effect = side_effect
    else:
        execute.return_value = return_value
    return DriveApiClient(service), service


def test_list_folder_parses_files_and_folders():
    client, service = _client_with_execute({"files": [RAW_FOLDER, RAW_PDF]})
    files = client.list_folder("root")

    assert len(files) == 2
    assert files[0].is_folder is True
    assert files[1].name == "umowa.pdf"
    assert files[1].md5_checksum == "abc123"
    assert files[1].parents == ("f1",)

    service.files.return_value.list.assert_called_once()
    _, kwargs = service.files.return_value.list.call_args
    assert "'root' in parents" in kwargs["q"]


def test_search_escapes_quotes_in_query():
    client, service = _client_with_execute({"files": [RAW_PDF]})
    results = client.search("O'Brien's umowa")

    assert len(results) == 1
    _, kwargs = service.files.return_value.list.call_args
    assert "O\\'Brien\\'s umowa" in kwargs["q"]


def test_list_folder_wraps_http_error():
    http_error = HttpError(httplib2.Response({"status": 404}), b"not found")
    client, _ = _client_with_execute(side_effect=http_error)
    with pytest.raises(DriveApiError):
        client.list_folder("root")


def test_get_metadata_parses_file():
    service = MagicMock()
    service.files.return_value.get.return_value.execute.return_value = RAW_PDF
    client = DriveApiClient(service)

    result = client.get_metadata("p1")
    assert result.name == "umowa.pdf"
    assert result.size == 12345


def test_upload_new_revision_succeeds_when_no_conflict():
    service = MagicMock()
    service.files.return_value.get.return_value.execute.return_value = RAW_PDF
    updated = {**RAW_PDF, "modifiedTime": "2026-01-03T00:00:00Z"}
    service.files.return_value.update.return_value.execute.return_value = updated
    client = DriveApiClient(service)

    baseline = DriveFile(
        id="p1", name="umowa.pdf", mime_type="application/pdf",
        modified_time="2026-01-02T00:00:00Z", size=12345, md5_checksum="abc123", parents=("f1",),
    )

    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 fake content")
        tmp_path = Path(tmp.name)

    try:
        result = client.upload_new_revision("p1", tmp_path, baseline)
        assert result.modified_time == "2026-01-03T00:00:00Z"
    finally:
        tmp_path.unlink()


def test_upload_new_revision_raises_conflict_when_remote_checksum_changed():
    service = MagicMock()
    remote_changed = {**RAW_PDF, "md5Checksum": "different-checksum"}
    service.files.return_value.get.return_value.execute.return_value = remote_changed
    client = DriveApiClient(service)

    baseline = DriveFile(
        id="p1", name="umowa.pdf", mime_type="application/pdf",
        modified_time="2026-01-02T00:00:00Z", size=12345, md5_checksum="abc123", parents=("f1",),
    )

    from pathlib import Path

    with pytest.raises(DriveConflictError):
        client.upload_new_revision("p1", Path("/tmp/does_not_matter.pdf"), baseline)

    service.files.return_value.update.assert_not_called()


def test_upload_new_file_sets_parent_folder():
    service = MagicMock()
    service.files.return_value.create.return_value.execute.return_value = RAW_PDF
    client = DriveApiClient(service)

    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"%PDF-1.4 fake content")
        tmp_path = Path(tmp.name)

    try:
        client.upload_new_file(tmp_path, "nowy.pdf", parent_folder_id="f1")
    finally:
        tmp_path.unlink()

    _, kwargs = service.files.return_value.create.call_args
    assert kwargs["body"] == {"name": "nowy.pdf", "parents": ["f1"]}
