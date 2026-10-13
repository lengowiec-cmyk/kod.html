"""
Moduł logowania — zapisuje logi jednocześnie do pliku i (przez callback)
do interfejsu GUI. Jeden obiekt AppLogger współdzielony przez wszystkie moduły.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


def _get_app_directory() -> str:
    """
    Zwraca katalog, w którym faktycznie znajduje się plik programu — trwały,
    NIE folder tymczasowy PyInstalera (_MEIPASS), bo ten jest usuwany zaraz
    po zamknięciu programu, co sprawiłoby, że logi znikałyby natychmiast.
    - Po spakowaniu do .exe: katalog zawierający plik .exe (sys.executable).
    - Jako skrypt .py: katalog bieżącego katalogu roboczego.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


# Alias publiczny — inne moduły (np. main.py) mogą potrzebować tego samego
# trwałego katalogu programu do zapisu plików innych niż logi (np. raportów
# diagnostycznych).
get_app_directory = _get_app_directory


class AppLogger:
    """
    Centralny logger aplikacji. Pisze do:
      - pliku logs/config_YYYYMMDD_HHMMSS.log
      - konsoli (dla debugowania z terminala)
      - dowolnego callbacku GUI podpiętego przez set_gui_callback()
    """

    def __init__(self, log_dir: str = None):
        if log_dir is None:
            log_dir = Path(_get_app_directory()) / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"config_{timestamp}.log"

        self._logger = logging.getLogger("RicohScannerConfig")
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers.clear()

        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                               datefmt="%H:%M:%S")
        )
        self._logger.addHandler(file_handler)

        self._gui_callback = None

    def set_gui_callback(self, callback):
        """Podpina funkcję GUI, która otrzyma każdy zalogowany komunikat."""
        self._gui_callback = callback

    def _emit(self, level: str, msg: str):
        getattr(self._logger, level.lower())(msg)
        if self._gui_callback:
            prefix = {
                "info": "",
                "warning": "⚠ ",
                "error": "✖ ",
                "debug": "",
            }.get(level.lower(), "")
            self._gui_callback(f"{prefix}{msg}")

    def info(self, msg: str):
        self._emit("info", msg)

    def warning(self, msg: str):
        self._emit("warning", msg)

    def error(self, msg: str):
        self._emit("error", msg)

    def debug(self, msg: str):
        self._emit("debug", msg)

    def section(self, title: str):
        """Nagłówek sekcji w logu — dla czytelności raportu."""
        line = "─" * 50
        self._emit("info", f"\n{line}\n{title}\n{line}")

    def get_log_path(self) -> str:
        return str(self.log_file)


# Singleton — jedna instancja loggera na cały czas życia aplikacji
_logger_instance = None


def get_logger() -> AppLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AppLogger()
    return _logger_instance
