"""Lokalny katalog podręczny na pliki PDF pobrane z Google Dysku do edycji.

Używa standardowej, zależnej od systemu lokalizacji danych aplikacji
(Qt `QStandardPaths`) — na Windows to zwykle
``%LOCALAPPDATA%\\PDFManager\\cache\\drive_files``, na Linuksie
``~/.cache/PDFManager/drive_files`` — nigdy nie zapisujemy do
zahardkodowanych ścieżek uniksowych ani katalogów systemowych.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QStandardPaths

_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")


def cache_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    if not base:
        base = str(Path.home() / ".pdfmanager_cache")
    path = Path(base) / "drive_files"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_path_for(file_id: str, name: str) -> Path:
    """Ścieżka lokalnego pliku podręcznego dla pliku Google Dysku `file_id`.

    Nazwa zawiera identyfikator pliku (unikalność — dwa pliki na Dysku
    mogą mieć tę samą nazwę wyświetlaną) oraz oczyszczoną nazwę oryginalną
    (bez znaków niedozwolonych w nazwach plików na Windows).
    """
    safe_name = _UNSAFE_CHARS_RE.sub("_", name).strip("_") or "dokument.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    return cache_dir() / f"{file_id}_{safe_name}"
