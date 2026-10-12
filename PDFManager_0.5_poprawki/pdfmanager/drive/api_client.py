"""Klient Google Drive API (Workflow A): przeglądanie, wyszukiwanie,
pobieranie, zapis z powrotem do oryginalnego pliku (z wykrywaniem
konfliktu wersji), zapis jako nowy plik.

`DriveApiClient` przyjmuje już zbudowany obiekt `service` (wynik
`googleapiclient.discovery.build`) — dzięki temu jest w pełni testowalny
bez sieci (wstrzyknięcie atrapy `service`). Rzeczywiste użycie przechodzi
przez `DriveApiClient.from_credentials(...)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
PDF_MIME_TYPE = "application/pdf"
DRIVE_FIELDS = "id, name, mimeType, modifiedTime, size, md5Checksum, parents, trashed"
LIST_FIELDS = f"files({DRIVE_FIELDS})"


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    modified_time: str
    size: int | None
    md5_checksum: str | None
    parents: tuple[str, ...]

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME_TYPE


class DriveApiError(Exception):
    """Błąd komunikacji z Google Drive API."""


class DriveConflictError(DriveApiError):
    """Zdalna wersja pliku zmieniła się na Dysku od czasu otwarcia go do edycji."""

    def __init__(self, file_id: str, remote: DriveFile) -> None:
        super().__init__(
            f"Plik „{remote.name}” (id={file_id}) został zmieniony na Google Dysku od czasu otwarcia. "
            "Zapis został zatrzymany, żeby nie nadpisać cudzych zmian."
        )
        self.file_id = file_id
        self.remote = remote


def _parse_file(data: dict) -> DriveFile:
    return DriveFile(
        id=data["id"],
        name=data["name"],
        mime_type=data.get("mimeType", ""),
        modified_time=data.get("modifiedTime", ""),
        size=int(data["size"]) if data.get("size") else None,
        md5_checksum=data.get("md5Checksum"),
        parents=tuple(data.get("parents", ())),
    )


class DriveApiClient:
    def __init__(self, service) -> None:
        self._service = service

    @classmethod
    def from_credentials(cls, credentials) -> "DriveApiClient":
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        client=cls(build("drive", "v3", http=AuthorizedHttp(credentials,http=httplib2.Http(timeout=30)), cache_discovery=False))
        client._credentials=credentials
        return client

    def for_thread(self):
        """httplib2 clients must not be shared between network worker threads."""
        return self.from_credentials(self._credentials) if hasattr(self,'_credentials') else self

    def list_folder(self, folder_id: str = "root") -> list[DriveFile]:
        result=[];token=None
        safe_id=folder_id.replace("\\","\\\\").replace("'","\\'")
        try:
            for _ in range(50):
                kwargs=dict(q=f"'{safe_id}' in parents and trashed = false",fields='nextPageToken,'+LIST_FIELDS,orderBy='folder, name',pageSize=200,supportsAllDrives=True,includeItemsFromAllDrives=True)
                if token:kwargs['pageToken']=token
                data=self._service.files().list(**kwargs).execute()
                result.extend(_parse_file(f) for f in data.get('files',[]));token=data.get('nextPageToken')
                if not token:return result
            raise DriveApiError('Folder przekracza limit 10 000 wpisów.')
        except HttpError as exc:
            raise DriveApiError(f"Nie udało się pobrać zawartości folderu: {exc}") from exc

    def search(self, query_text: str) -> list[DriveFile]:
        safe_query = query_text.replace("\\", "\\\\").replace("'", "\\'")
        try:
            result = (
                self._service.files()
                .list(q=f"name contains '{safe_query}' and trashed = false", fields=LIST_FIELDS, pageSize=100)
                .execute()
            )
        except HttpError as exc:
            raise DriveApiError(f"Wyszukiwanie na Google Dysku nie powiodło się: {exc}") from exc
        return [_parse_file(f) for f in result.get("files", [])]

    def get_metadata(self, file_id: str) -> DriveFile:
        try:
            data = self._service.files().get(fileId=file_id, fields=DRIVE_FIELDS,supportsAllDrives=True).execute()
        except HttpError as exc:
            raise DriveApiError(f"Nie udało się odczytać metadanych pliku: {exc}") from exc
        return _parse_file(data)

    def download(self, file_id: str, destination: Path) -> None:
        request=self._service.files().get_media(fileId=file_id,supportsAllDrives=True)
        download_request(request,destination)

    def upload_new_revision(self, file_id: str, local_path: Path, baseline: DriveFile) -> DriveFile:
        """Zapisuje zawartość `local_path` jako nową wersję pliku `file_id`.

        `baseline` to metadane zapamiętane w momencie otwarcia pliku do
        edycji. Przed zapisem porównujemy je ze AKTUALNYMI metadanymi z
        Dysku: jeśli suma kontrolna się różni, ktoś inny zmienił plik w
        międzyczasie — zgłaszamy `DriveConflictError` i NIC nie nadpisujemy.
        """
        current = self.get_metadata(file_id)
        if baseline.md5_checksum and current.md5_checksum and baseline.md5_checksum != current.md5_checksum:
            raise DriveConflictError(file_id, current)

        local_path = Path(local_path)
        media = MediaFileUpload(str(local_path), mimetype=PDF_MIME_TYPE, resumable=True)
        try:
            data = self._service.files().update(fileId=file_id, media_body=media, fields=DRIVE_FIELDS).execute()
        except HttpError as exc:
            raise DriveApiError(f"Nie udało się zapisać pliku na Google Dysku: {exc}") from exc
        return _parse_file(data)

    def upload_new_file(self, local_path: Path, name: str, parent_folder_id: str | None = None) -> DriveFile:
        local_path = Path(local_path)
        metadata: dict = {"name": name}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        media = MediaFileUpload(str(local_path), mimetype=PDF_MIME_TYPE, resumable=True)
        try:
            data = self._service.files().create(body=metadata, media_body=media, fields=DRIVE_FIELDS).execute()
        except HttpError as exc:
            raise DriveApiError(f"Nie udało się zapisać nowego pliku na Google Dysku: {exc}") from exc
        return _parse_file(data)


def download_request(request,destination):
    """Download with a finite size budget; failures never replace a good file."""
    import os,tempfile
    from pdfmanager.dms.jobs import checkpoint
    destination=Path(destination)
    fd,name=tempfile.mkstemp(prefix='pdfmanager-drive-',suffix='.tmp',dir=destination.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as stream:
            downloader=MediaIoBaseDownload(stream,request,chunksize=1024*1024)
            done=False
            while not done:
                checkpoint();_,done=downloader.next_chunk()
                if stream.tell()>256*1024*1024:raise DriveApiError('Pobierany dokument przekracza limit 256 MB.')
            stream.flush();os.fsync(stream.fileno())
        checkpoint();temporary.replace(destination)
    except HttpError as exc:
        raise DriveApiError('Nie udało się pobrać dokumentu z Google Drive.') from exc
    finally:temporary.unlink(missing_ok=True)
