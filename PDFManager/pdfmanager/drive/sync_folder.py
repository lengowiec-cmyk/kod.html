"""Workflow B: pliki PDF w folderze zsynchronizowanym przez Google Drive
for desktop — widoczne w systemie jako normalne pliki lokalne.

W trybie „tylko w chmurze” (stream) Google Drive for desktop oznacza
pliki jeszcze nie pobrane na dysk specjalnym atrybutem systemu plików
(na Windows: `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` / `FILE_ATTRIBUTE_OFFLINE`
na punkcie zmiany przeznaczenia). Otwarcie takiego pliku wywołuje
automatyczne pobranie przez usługę Google Drive w tle — ta funkcja tylko
wykrywa ten stan PRZED otwarciem, żeby interfejs mógł ostrzec użytkownika
(może to chwilę potrwać albo się nie powiedzie bez połączenia z siecią),
zamiast ciche zawieszenie się aplikacji przy odczycie.
"""
from __future__ import annotations

import sys
from pathlib import Path

FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
FILE_ATTRIBUTE_OFFLINE = 0x00001000
_CLOUD_PLACEHOLDER_MASK = FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | FILE_ATTRIBUTE_OFFLINE
_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

_DRIVE_DESKTOP_MARKERS = (".tmp.drivedownload", ".tmp.driveupload")
_DRIVE_DESKTOP_NAME_HINTS = ("my drive", "mój dysk", "google drive")


def _get_file_attributes_windows(path: Path) -> int:
    """Cienka otoczka na WinAPI `GetFileAttributesW` — wyodrębniona, żeby
    logikę interpretacji bitów dało się testować również poza Windows."""
    import ctypes

    return ctypes.windll.kernel32.GetFileAttributesW(str(path))  # type: ignore[attr-defined]


def is_online_only(path: Path) -> bool | None:
    """True = plik jest „tylko w chmurze” (nie pobrany lokalnie),
    False = pobrany na dysk, None = nie można ustalić (system inny niż
    Windows albo błąd odczytu atrybutów)."""
    if sys.platform != "win32":
        return None
    try:
        attrs = _get_file_attributes_windows(Path(path))
    except Exception:
        return None
    if attrs == _INVALID_FILE_ATTRIBUTES:
        return None
    return bool(attrs & _CLOUD_PLACEHOLDER_MASK)


def looks_like_drive_desktop_folder(path: Path) -> bool:
    """Heurystyka (nie pewnik!): czy folder wygląda na katalog
    zsynchronizowany przez Google Drive for desktop — obecność plików
    tymczasowych charakterystycznych dla tej aplikacji albo typowa nazwa
    głównego folderu. Nie zweryfikowano na rzeczywistej instalacji Google
    Drive for desktop na Windows — do potwierdzenia/dopracowania przy
    pierwszym realnym teście na docelowym systemie."""
    path = Path(path)
    if any(hint in path.name.lower() for hint in _DRIVE_DESKTOP_NAME_HINTS):
        return True
    try:
        entries = {entry.name.lower() for entry in path.iterdir()}
    except OSError:
        return False
    return any(marker in entries for marker in _DRIVE_DESKTOP_MARKERS)
