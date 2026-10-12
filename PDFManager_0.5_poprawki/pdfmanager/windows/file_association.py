"""Rejestracja aplikacji jako programu do obsługi plików .pdf w Windows.

Od Windows 8 wybór domyślnej aplikacji dla typu pliku jest chroniony
skrótem („UserChoice") zapisanym w rejestrze — żadna aplikacja trzecia
NIE MOŻE go ustawić programowo (to świadome zabezpieczenie przed
„przejmowaniem" skojarzeń plików bez zgody użytkownika). Jedyna właściwa
droga to: (1) zarejestrować aplikację i jej „możliwości" (Capabilities)
w rejestrze, żeby pojawiła się jako opcja, (2) poprowadzić użytkownika do
systemowego ekranu Ustawienia > Aplikacje > Aplikacje domyślne, gdzie on
SAM potwierdza wybór, (3) zweryfikować rzeczywisty efekt odczytem
rejestru — nigdy nie zakładać sukcesu z góry.

Rejestracja odbywa się w `HKEY_CURRENT_USER` (nie wymaga uprawnień
administratora i dotyczy tylko zalogowanego użytkownika).

Moduł jest importowalny na każdym systemie (żeby reszta aplikacji, pisana
i testowana też poza Windows, mogła go bezpiecznie importować), ale
funkcje rejestru działają tylko na Windows — na innych systemach zgłaszają
`FileAssociationError`. Zależność od `winreg` jest wstrzykiwana przez
`_registry`, żeby dało się to przetestować atrapą rejestru także poza
Windows (patrz testy).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import winreg as _real_winreg
else:
    _real_winreg = None

_registry: Any = _real_winreg

PROG_ID = "PDFManager.Document"
APP_REGISTERED_NAME = "PDFManager"
CAPABILITIES_KEY = r"Software\PDFManager\Capabilities"
REGISTERED_APPS_KEY = r"Software\RegisteredApplications"
USER_CHOICE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice"
DEFAULT_APPS_SETTINGS_URI = "ms-settings:defaultapps"


class FileAssociationError(Exception):
    """Błąd podczas rejestrowania skojarzenia z plikami PDF."""


def _require_registry() -> Any:
    if _registry is None:
        raise FileAssociationError(
            "Skojarzenie z plikami PDF w systemie Windows jest dostępne tylko w systemie Windows."
        )
    return _registry


def register_application(exe_path: Path) -> None:
    """Rejestruje aplikację i ProgID `.pdf` w HKEY_CURRENT_USER.

    Nie ustawia aplikacji jako domyślnej (Windows to blokuje) — tylko
    zgłasza ją jako dostępną opcję na liście „Aplikacje domyślne" i w
    menu „Otwórz za pomocą".
    """
    reg = _require_registry()
    exe_path = Path(exe_path)
    open_command = f'"{exe_path}" "%1"'

    with reg.CreateKey(reg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}") as key:
        reg.SetValueEx(key, None, 0, reg.REG_SZ, "Dokument PDF (Menedżer PDF)")
    with reg.CreateKey(reg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}\shell\open\command") as key:
        reg.SetValueEx(key, None, 0, reg.REG_SZ, open_command)
    with reg.CreateKey(reg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}\DefaultIcon") as key:
        reg.SetValueEx(key, None, 0, reg.REG_SZ, f'"{exe_path}",0')

    with reg.CreateKey(reg.HKEY_CURRENT_USER, CAPABILITIES_KEY) as key:
        reg.SetValueEx(key, "ApplicationName", 0, reg.REG_SZ, "Menedżer PDF")
        reg.SetValueEx(key, "ApplicationDescription", 0, reg.REG_SZ, "Przeglądanie, edycja i zarządzanie dokumentami PDF")
    with reg.CreateKey(reg.HKEY_CURRENT_USER, rf"{CAPABILITIES_KEY}\FileAssociations") as key:
        reg.SetValueEx(key, ".pdf", 0, reg.REG_SZ, PROG_ID)

    with reg.CreateKey(reg.HKEY_CURRENT_USER, REGISTERED_APPS_KEY) as key:
        reg.SetValueEx(key, APP_REGISTERED_NAME, 0, reg.REG_SZ, CAPABILITIES_KEY)


def unregister_application() -> None:
    """Usuwa rejestrację (np. przy odinstalowaniu). Najlepszy wysiłek —
    nie zgłasza błędu, jeśli dane klucze już nie istnieją."""
    reg = _require_registry()
    for key_path in (
        rf"Software\Classes\{PROG_ID}\shell\open\command",
        rf"Software\Classes\{PROG_ID}\shell\open",
        rf"Software\Classes\{PROG_ID}\shell",
        rf"Software\Classes\{PROG_ID}\DefaultIcon",
        rf"Software\Classes\{PROG_ID}",
        rf"{CAPABILITIES_KEY}\FileAssociations",
        CAPABILITIES_KEY,
    ):
        try:
            reg.DeleteKey(reg.HKEY_CURRENT_USER, key_path)
        except OSError:
            pass
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, REGISTERED_APPS_KEY, 0, reg.KEY_SET_VALUE) as key:
            reg.DeleteValue(key, APP_REGISTERED_NAME)
    except OSError:
        pass


def is_registered_as_default() -> bool:
    """Sprawdza FAKTYCZNY stan: czy ta aplikacja jest bieżącym programem
    domyślnym dla plików .pdf (odczyt klucza UserChoice ustawianego przez
    Windows po potwierdzeniu wyboru przez użytkownika). Zwraca False, gdy
    nie jest domyślna LUB gdy nie można tego ustalić — nigdy nie zgaduje."""
    reg = _require_registry()
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, USER_CHOICE_KEY) as key:
            prog_id, _ = reg.QueryValueEx(key, "ProgId")
    except OSError:
        return False
    return prog_id == PROG_ID


def open_default_apps_settings() -> None:
    """Otwiera systemowy ekran Ustawienia > Aplikacje domyślne.

    Windows nie pozwala ustawić domyślnej aplikacji programowo — to
    jedyny sposób, by poprowadzić tam użytkownika, który sam dokończy
    wybór.
    """
    _require_registry()
    os.startfile(DEFAULT_APPS_SETTINGS_URI)  # type: ignore[attr-defined]
