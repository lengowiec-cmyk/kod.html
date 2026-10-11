"""Pasek nagłówka: nazwa aplikacji, informacja o prawach autorskich i
szybki przełącznik języka (ikony flag). Jeden, trwały element interfejsu
widoczny niezależnie od tego, która karta dokumentu jest aktywna."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from pdfmanager.i18n.translator import SUPPORTED_LANGUAGES, translator
from pdfmanager.ui.flag_icons import flag_icon

COPYRIGHT_TEXT = "Copyright (c) 2026 Artur B"
LOGO_PATH = Path(__file__).resolve().parent.parent / "resources" / "branding" / "logo_full.png"
LOGO_HEIGHT = 30


class HeaderBar(QWidget):
    language_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(52)

        self._logo_label = QLabel(self)
        logo_pixmap = QPixmap(str(LOGO_PATH)) if LOGO_PATH.is_file() else QPixmap()
        if not logo_pixmap.isNull():
            self._logo_label.setPixmap(
                logo_pixmap.scaledToHeight(LOGO_HEIGHT, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._logo_label.setVisible(False)

        self._title_label = QLabel(self)
        self._title_label.setStyleSheet("font-weight: 600; font-size: 11pt;")

        self._copyright_label = QLabel(COPYRIGHT_TEXT, self)
        self._copyright_label.setObjectName("HeaderCopyrightLabel")

        self._flag_buttons: dict[str, QToolButton] = {}
        flags_layout = QHBoxLayout()
        flags_layout.setSpacing(4)
        for lang in SUPPORTED_LANGUAGES:
            button = QToolButton(self)
            button.setIcon(flag_icon(lang))
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(lang.upper())
            button.clicked.connect(lambda checked, selected=lang: self._on_flag_clicked(selected))
            flags_layout.addWidget(button)
            self._flag_buttons[lang] = button

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.addWidget(self._logo_label)
        layout.addSpacing(8)
        layout.addWidget(self._title_label)
        layout.addStretch(1)
        layout.addWidget(self._copyright_label)
        layout.addSpacing(16)
        layout.addLayout(flags_layout)

        translator.language_changed.connect(self._on_language_changed)
        self._retranslate()
        self._update_checked_flag(translator.language)

    def _on_flag_clicked(self, lang: str) -> None:
        self.language_selected.emit(lang)

    def _on_language_changed(self, lang: str) -> None:
        self._retranslate()
        self._update_checked_flag(lang)

    def _update_checked_flag(self, lang: str) -> None:
        for code, button in self._flag_buttons.items():
            button.setChecked(code == lang)

    def _retranslate(self) -> None:
        self._title_label.setText(translator.tr("app.title"))
