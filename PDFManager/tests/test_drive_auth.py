"""Testy uwierzytelniania Google Dysku — z atrapą `keyring` (bez realnego
magazynu systemowego) i bez realnego przepływu OAuth w przeglądarce."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials

from pdfmanager.drive.auth import (
    DriveAuthError,
    clear_stored_credentials,
    get_credentials,
    has_stored_credentials,
)


class _FakeKeyringStore:
    """Minimalna atrapa magazynu keyring — słownik w pamięci procesu testu."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._data[(service, username)] = password

    def get_password(self, service, username):
        return self._data.get((service, username))

    def delete_password(self, service, username):
        self._data.pop((service, username), None)


@pytest.fixture
def fake_keyring():
    store = _FakeKeyringStore()
    with patch("pdfmanager.drive.auth.keyring.set_password", store.set_password), \
         patch("pdfmanager.drive.auth.keyring.get_password", store.get_password), \
         patch("pdfmanager.drive.auth.keyring.delete_password", store.delete_password):
        yield store


def _valid_credentials() -> Credentials:
    return Credentials(token="access-token", refresh_token="refresh-token", token_uri="https://oauth2.googleapis.com/token",
                        client_id="client", client_secret="secret", scopes=["https://www.googleapis.com/auth/drive"])


def test_has_stored_credentials_false_initially(fake_keyring):
    assert has_stored_credentials() is False


def test_get_credentials_returns_stored_valid_token(fake_keyring):
    creds = _valid_credentials()
    with patch.object(Credentials, "valid", True):
        fake_keyring.set_password("PDFManager-GoogleDrive", "default", creds.to_json())
        result = get_credentials(interactive=False)
        assert result.token == "access-token"


def test_get_credentials_without_stored_token_and_non_interactive_raises(fake_keyring):
    with pytest.raises(DriveAuthError, match="wymagane jest zalogowanie"):
        get_credentials(interactive=False)


def test_get_credentials_missing_client_secret_raises(fake_keyring, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(DriveAuthError, match="client_secret.json"):
        get_credentials(client_secret_path=missing, interactive=True)


def test_get_credentials_runs_oauth_flow_and_stores_token(fake_keyring, tmp_path):
    client_secret = tmp_path / "client_secret.json"
    client_secret.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}))

    new_creds = _valid_credentials()
    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = new_creds

    with patch("pdfmanager.drive.auth.InstalledAppFlow.from_client_secrets_file", return_value=fake_flow):
        result = get_credentials(client_secret_path=client_secret, interactive=True)

    assert result is new_creds
    assert has_stored_credentials() is True


def test_clear_stored_credentials_removes_token(fake_keyring):
    fake_keyring.set_password("PDFManager-GoogleDrive", "default", "token-data")
    assert has_stored_credentials() is True
    clear_stored_credentials()
    assert has_stored_credentials() is False


def test_clear_stored_credentials_is_safe_when_nothing_stored(fake_keyring):
    clear_stored_credentials()  # nie powinno zgłosić wyjątku
