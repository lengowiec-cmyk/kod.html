"""Uwierzytelnianie Google OAuth dla Google Dysku (Workflow A).

Token dostępu/odświeżania jest przechowywany przez `keyring`, co oznacza
Menedżer poświadczeń Windows na Windows, Kluczyk (Keychain) na macOS albo
Secret Service na Linuksie — bez żadnego kodu specyficznego dla platformy
w tej aplikacji (zgodnie z wymogiem bezpiecznego przechowywania tokenów).

Aplikacja NIE zawiera własnych poświadczeń OAuth. Każde wdrożenie wymaga
własnego projektu w Google Cloud Console z włączonym Google Drive API i
utworzonym identyfikatorem klienta OAuth 2.0 typu „Desktop app” — ścieżkę
do pobranego pliku `client_secret.json` wskazuje użytkownik przy pierwszym
logowaniu. Zakres `drive` (pełny dostęp) jest konieczny, by aplikacja mogła
przeglądać dowolne foldery użytkownika, a nie tylko pliki przez nią
utworzone (węższy zakres `drive.file` by to ograniczył) — Google pokaże to
wprost na ekranie zgody.
"""
from __future__ import annotations

import json
from pathlib import Path

import keyring
import keyring.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]
KEYRING_SERVICE = "PDFManager-GoogleDrive"
KEYRING_USERNAME = "default"


class DriveAuthError(Exception):
    """Błąd uwierzytelniania Google Dysku."""


def _load_stored_credentials() -> Credentials | None:
    raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return None
    try:
        return Credentials.from_authorized_user_info(info, SCOPES)
    except ValueError:
        return None


def _store_credentials(creds: Credentials) -> None:
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, creds.to_json())


def clear_stored_credentials() -> None:
    """Wylogowuje — usuwa zapisany token (np. na żądanie użytkownika)."""
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass


def has_stored_credentials() -> bool:
    return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) is not None


def get_credentials(client_secret_path: Path | None = None, interactive: bool = True) -> Credentials:
    """Zwraca aktywne poświadczenia Google.

    Kolejność: (1) zapisany, wciąż ważny token; (2) zapisany token
    odświeżony przez refresh_token; (3) jeśli `interactive=True` i podano
    `client_secret_path` — pełny proces logowania w przeglądarce.
    Nigdy nie loguje w tle bez zgody — logowanie przeglądarkowe wymaga
    wyraźnego wywołania tej funkcji z `interactive=True` przez UI.
    """
    creds = _load_stored_credentials()
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _store_credentials(creds)
            return creds
        except Exception as exc:
            if not interactive:
                raise DriveAuthError(f"Nie udało się odświeżyć tokenu dostępu do Google Dysku: {exc}") from exc

    if not interactive:
        raise DriveAuthError("Brak zapisanych poświadczeń Google Dysku — wymagane jest zalogowanie.")

    if client_secret_path is None or not Path(client_secret_path).is_file():
        raise DriveAuthError(
            "Nie znaleziono pliku client_secret.json. Pobierz go z Google Cloud Console "
            "(identyfikator klienta OAuth 2.0 typu „Desktop app” z włączonym Google Drive API)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    new_creds = flow.run_local_server(port=0)
    _store_credentials(new_creds)
    return new_creds
