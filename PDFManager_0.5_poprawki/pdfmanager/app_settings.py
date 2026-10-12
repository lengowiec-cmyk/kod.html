"""Trwałe ustawienia aplikacji (QSettings) — język, geometria okna, historia."""
from __future__ import annotations

from PySide6.QtCore import QSettings

ORG_NAME = "PDFManager"
APP_NAME = "PDFManager"


class AppSettings:
    def __init__(self) -> None:
        self._settings = QSettings(ORG_NAME, APP_NAME)

    @property
    def language(self) -> str:
        # Domyślny język przy pierwszym uruchomieniu: angielski.
        return self._settings.value("ui/language", "en", type=str)

    @language.setter
    def language(self, value: str) -> None:
        self._settings.setValue("ui/language", value)

    @property
    def theme(self) -> str:
        return self._settings.value("ui/theme", "light", type=str)

    @theme.setter
    def theme(self, value: str) -> None:
        self._settings.setValue("ui/theme", value)

    @property
    def title_color(self) -> str:
        return self._settings.value('ui/title_color', '#2d5997', type=str)

    @title_color.setter
    def title_color(self, value: str) -> None:
        self._settings.setValue('ui/title_color', value)

    @property
    def toolbar_color(self) -> str:
        return self._settings.value('ui/toolbar_color', '#ffffff', type=str)

    @toolbar_color.setter
    def toolbar_color(self, value: str) -> None:
        self._settings.setValue('ui/toolbar_color', value)

    @property
    def compact_toolbar(self) -> bool:
        return self._settings.value('ui/compact_toolbar', False, type=bool)

    @compact_toolbar.setter
    def compact_toolbar(self, value: bool) -> None:
        self._settings.setValue('ui/compact_toolbar', value)

    @property
    def last_folder(self) -> str:
        return self._settings.value("browser/last_folder", "", type=str)

    @last_folder.setter
    def last_folder(self, value: str) -> None:
        self._settings.setValue("browser/last_folder", value)

    def window_geometry(self):
        return self._settings.value("window/geometry")

    def set_window_geometry(self, geometry) -> None:
        self._settings.setValue("window/geometry", geometry)

    @property
    def drive_client_secret_path(self) -> str:
        """Ścieżka do pliku client_secret.json (Google Cloud Console, OAuth
        2.0 Client ID typu „Desktop app”) — nie jest to sam token, tylko
        identyfikator aplikacji; bezpieczny token logowania przechowuje
        `pdf_engine.drive.auth` przez `keyring`, nie tutaj."""
        return self._settings.value("drive/client_secret_path", "", type=str)

    @drive_client_secret_path.setter
    def drive_client_secret_path(self, value: str) -> None:
        self._settings.setValue("drive/client_secret_path", value)


settings = AppSettings()
