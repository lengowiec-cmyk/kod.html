"""Prosty system i18n oparty na plikach JSON (bez narzędzi Qt Linguist).

Wybór ten jest świadomy: aplikacja potrzebuje natychmiastowej zmiany języka
w czasie działania oraz łatwej edycji tłumaczeń bez kroku kompilacji .qm.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

LOCALES_DIR = Path(__file__).parent / "locales"
SUPPORTED_LANGUAGES = ("pl", "en", "uk")
DEFAULT_LANGUAGE = "en"  # domyślny język interfejsu przy pierwszym uruchomieniu
FALLBACK_LANGUAGE = "en"


class Translator(QObject):
    """Przechowuje teksty interfejsu dla wszystkich obsługiwanych języków.

    Komponenty UI nasłuchują sygnału ``language_changed`` i w reakcji na
    niego ponownie ustawiają swoje teksty (wzorzec ``retranslate_ui``).
    """

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._strings: dict[str, dict[str, str]] = {}
        self._language = DEFAULT_LANGUAGE
        self._ui_strings = {}
        self._sources = {}
        for lang in SUPPORTED_LANGUAGES:
            path = LOCALES_DIR / f"{lang}.json"
            with path.open("r", encoding="utf-8") as fh:
                self._strings[lang] = json.load(fh)
            self._ui_strings[lang] = json.loads((LOCALES_DIR / f"ui_{lang}.json").read_text(encoding="utf-8"))
        for lang in SUPPORTED_LANGUAGES:
            for source, value in self._ui_strings[lang].items():
                self._sources.setdefault(value, source)

    def source(self, value: str) -> str | None:
        if value in self._ui_strings["pl"]:
            return value
        return self._sources.get(value)

    def text(self, source: str, **kwargs: object) -> str:
        value = self._ui_strings[self._language].get(source, source)
        return value.format(**kwargs) if kwargs else value

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Nieobsługiwany język: {language}")
        if language == self._language:
            return
        self._language = language
        self.language_changed.emit(language)

    def tr(self, key: str, **kwargs: object) -> str:
        """Zwraca przetłumaczony tekst dla danego klucza.

        Jeśli klucz nie istnieje w wybranym języku, próbuje języka
        zapasowego (en), a w ostateczności zwraca sam klucz — to ułatwia
        wykrycie brakujących tłumaczeń podczas rozwoju.
        """
        text = self._strings.get(self._language, {}).get(key)
        if text is None:
            text = self._strings.get(FALLBACK_LANGUAGE, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text


# Jedna współdzielona instancja używana w całej aplikacji.
translator = Translator()
