"""Okna systemu licencjonowania: wprowadzanie klucza aktywacyjnego,
ostrzeżenie o kończącej się licencji, blokada po wygaśnięciu."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout

from pdfmanager.i18n.translator import translator
from pdfmanager.licensing.license_key import LicenseKeyError
from pdfmanager.licensing.license_manager import LicenseManager


class ActivationDialog(QDialog):
    """Okno wprowadzania klucza aktywacyjnego.

    `allow_cancel=False` blokuje zamknięcie okna bez wprowadzenia
    prawidłowego klucza — używane, gdy okres próbny/licencja już wygasły
    i program ma pozostać zablokowany do aktywacji.
    """

    def __init__(
        self,
        manager: LicenseManager,
        parent=None,
        allow_cancel: bool = True,
        message_key: str = "license.activation_message",
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._allow_cancel = allow_cancel
        self._message_key = message_key
        self.setModal(True)
        self.setMinimumWidth(480)

        self._message_label = QLabel(self)
        self._message_label.setWordWrap(True)

        self._key_edit = QPlainTextEdit(self)
        self._key_edit.setFixedHeight(90)

        self._activate_button = QPushButton(self)
        self._activate_button.clicked.connect(self._on_activate)
        self._cancel_button = QPushButton(self)
        if allow_cancel:
            self._cancel_button.clicked.connect(self.reject)
        else:
            # Nie można po prostu "zamknąć" tego okna bez aktywacji (program
            # jest zablokowany) — ale użytkownik musi mieć możliwość
            # zakończenia APLIKACJI, żeby nie został w niej uwięziony.
            self._cancel_button.clicked.connect(self._quit_application)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_button)
        buttons.addWidget(self._activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._message_label)
        layout.addWidget(self._key_edit)
        layout.addLayout(buttons)

        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(translator.tr("license.activation_title"))
        self._message_label.setText(translator.tr(self._message_key))
        self._key_edit.setPlaceholderText(translator.tr("license.key_placeholder"))
        self._activate_button.setText(translator.tr("license.activate_button"))
        self._cancel_button.setText(
            translator.tr("license.cancel_button") if self._allow_cancel else translator.tr("license.exit_button")
        )

    def closeEvent(self, event) -> None:
        if not self._allow_cancel:
            event.ignore()
        else:
            super().closeEvent(event)

    def _quit_application(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
        self.reject()

    def _on_activate(self) -> None:
        key = self._key_edit.toPlainText().strip()
        if not key:
            return
        try:
            self._manager.activate(key)
        except LicenseKeyError as exc:
            QMessageBox.critical(self, translator.tr("license.error_title"), str(exc))
            return
        QMessageBox.information(
            self, translator.tr("license.activation_title"), translator.tr("license.activation_success")
        )
        self.accept()


class ExpiryWarningDialog(QDialog):
    """Ostrzeżenie pokazywane, gdy do końca okresu próbnego/licencji
    zostało niewiele dni. `enter_key_requested` mówi wywołującemu, czy
    po zamknięciu należy otworzyć `ActivationDialog`."""

    def __init__(self, days_remaining: int, parent=None) -> None:
        super().__init__(parent)
        self.days_remaining = days_remaining
        self.enter_key_requested = False
        self.setModal(True)
        self.setMinimumWidth(420)

        self._message_label = QLabel(self)
        self._message_label.setWordWrap(True)

        self._enter_key_button = QPushButton(self)
        self._enter_key_button.clicked.connect(self._on_enter_key)
        self._remind_later_button = QPushButton(self)
        self._remind_later_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._remind_later_button)
        buttons.addWidget(self._enter_key_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._message_label)
        layout.addLayout(buttons)

        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(translator.tr("license.warning_title"))
        self._message_label.setText(translator.tr("license.warning_message", days=self.days_remaining))
        self._enter_key_button.setText(translator.tr("license.enter_new_key_button"))
        self._remind_later_button.setText(translator.tr("license.remind_later_button"))

    def _on_enter_key(self) -> None:
        self.enter_key_requested = True
        self.accept()
