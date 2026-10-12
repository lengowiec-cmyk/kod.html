"""Logowanie do pliku (log.txt) — kluczowe dla wersji .exe bez okna konsoli:
bez tego awaria aplikacji po prostu "znika" bez żadnego śladu, którym
można by się kierować przy diagnozowaniu problemu.

Plik zapisywany jest w katalogu danych aplikacji użytkownika (zapisywalny
bez uprawnień administratora niezależnie od tego, gdzie zainstalowano
program — np. w Program Files), nie obok samego .exe.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QStandardPaths

LOG_FILE_NAME = "log.txt"
MAX_LOG_BYTES = 2_000_000
BACKUP_COUNT = 3

_logger = logging.getLogger("pdfmanager")


def log_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = str(Path.home() / ".pdfmanager")
    path = Path(base) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file_path() -> Path:
    return log_dir() / LOG_FILE_NAME


def configure_logging() -> None:
    """Wołane raz, na samym początku main() — zanim cokolwiek innego się wykona."""
    handler = RotatingFileHandler(
        log_file_path(), maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    _logger.info("=== Uruchomienie aplikacji ===")

    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        _logger.critical("Nieobsłużony wyjątek", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_uncaught_exception


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"pdfmanager.{name}")
