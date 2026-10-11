"""Okno korekty językowej (PL/EN/UK): zgoda na wysyłkę tekstu, sprawdzenie,
przegląd sugestii z możliwością zaznaczenia/odznaczenia każdej z nich,
zastosowanie zaakceptowanych poprawek przez prawdziwy silnik edycji tekstu.

Nic nie jest zapisywane do dokumentu, dopóki użytkownik nie kliknie
"Zastosuj zaznaczone" — a i wtedy tylko zaznaczone (zaakceptowane) sugestie.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pdfmanager.i18n.translator import SUPPORTED_LANGUAGES, translator
from pdfmanager.pdf_engine.text_edit import TextEditError, get_default_text_edit_engine
from pdfmanager.proofreading.language_tool_client import (
    LANGUAGE_CODES,
    PUBLIC_API_URL,
    LanguageToolClient,
    LanguageToolError,
)
from pathlib import Path

from pdfmanager.proofreading.workflow import ProofreadingSuggestion, check_document

LANGUAGE_LABEL_KEYS = {
    "pl": "menu.settings.language.pl",
    "en": "menu.settings.language.en",
    "uk": "menu.settings.language.uk",
}


class ProofreadingDialog(QDialog):
    def __init__(self, path: Path, page_count: int, parent=None) -> None:
        super().__init__(parent)
        self._path = Path(path)
        self._page_count = page_count
        self._engine = get_default_text_edit_engine()
        self._suggestions: list[ProofreadingSuggestion] = []
        self.setModal(True)
        self.resize(640, 520)

        self._stack = QStackedWidget(self)
        self._setup_page = self._build_setup_page()
        self._results_page = self._build_results_page()
        self._stack.addWidget(self._setup_page)
        self._stack.addWidget(self._results_page)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

        self._retranslate()

    # ------------------------------------------------------------- strona 1
    def _build_setup_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        self._language_label = QLabel(page)
        self._language_combo = QComboBox(page)
        for lang in SUPPORTED_LANGUAGES:
            self._language_combo.addItem(translator.tr(LANGUAGE_LABEL_KEYS[lang]), lang)
        self._language_combo.setCurrentIndex(SUPPORTED_LANGUAGES.index(translator.language))

        self._url_label = QLabel(page)
        self._url_edit = QLineEdit(PUBLIC_API_URL, page)

        self._hint_label = QLabel(page)
        self._hint_label.setWordWrap(True)

        self._consent_checkbox = QCheckBox(page)

        self._check_button = QPushButton(page)
        self._check_button.clicked.connect(self._run_check)

        layout.addWidget(self._language_label)
        layout.addWidget(self._language_combo)
        layout.addWidget(self._url_label)
        layout.addWidget(self._url_edit)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._consent_checkbox)
        layout.addStretch(1)
        layout.addWidget(self._check_button)
        return page

    # ------------------------------------------------------------- strona 2
    def _build_results_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        self._results_list = QListWidget(page)
        layout.addWidget(self._results_list)

        buttons = QHBoxLayout()
        self._back_button = QPushButton(page)
        self._back_button.clicked.connect(lambda: self._stack.setCurrentWidget(self._setup_page))
        self._apply_button = QPushButton(page)
        self._apply_button.clicked.connect(self._apply_selected)
        self._close_button = QPushButton(page)
        self._close_button.clicked.connect(self.accept)
        buttons.addWidget(self._back_button)
        buttons.addStretch(1)
        buttons.addWidget(self._apply_button)
        buttons.addWidget(self._close_button)
        layout.addLayout(buttons)
        return page

    # ------------------------------------------------------------------ logika
    def _run_check(self) -> None:
        if not self._consent_checkbox.isChecked():
            QMessageBox.warning(self, translator.tr("proofread.error_title"), translator.tr("proofread.consent_required"))
            return

        lang = self._language_combo.currentData()
        language_code = LANGUAGE_CODES[lang]
        client = LanguageToolClient(base_url=self._url_edit.text().strip() or PUBLIC_API_URL)

        try:
            self._suggestions = check_document(client, language_code, self._engine, self._path, self._page_count)
        except LanguageToolError as exc:
            QMessageBox.critical(self, translator.tr("proofread.error_title"), str(exc))
            return

        self._populate_results()
        self._stack.setCurrentWidget(self._results_page)

    def _populate_results(self) -> None:
        self._results_list.clear()
        if not self._suggestions:
            item = QListWidgetItem(translator.tr("proofread.no_issues_found"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._results_list.addItem(item)
            return

        for suggestion in self._suggestions:
            label = f"{suggestion.issue.short_message}: „{suggestion.span.text}” → „{suggestion.suggested_text}”"
            item = QListWidgetItem(label)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setToolTip(suggestion.issue.message)
            item.setData(Qt.ItemDataRole.UserRole, suggestion)
            self._results_list.addItem(item)

    def _apply_selected(self) -> None:
        accepted = []
        for row in range(self._results_list.count()):
            item = self._results_list.item(row)
            if item.checkState() == Qt.CheckState.Checked and item.data(Qt.ItemDataRole.UserRole) is not None:
                accepted.append(item.data(Qt.ItemDataRole.UserRole))

        if not accepted:
            self.accept()
            return

        all_warnings: list[str] = []
        applied = 0
        for suggestion in accepted:
            try:
                result = self._engine.apply_edit(self._path, suggestion.span, suggestion.suggested_text)
            except TextEditError as exc:
                all_warnings.append(str(exc))
                continue
            applied += 1
            all_warnings.extend(translator.tr(f"textedit.warning.{code}") for code in result.warnings)

        QMessageBox.information(
            self,
            translator.tr("proofread.dialog_title"),
            translator.tr("proofread.applied_summary", applied=applied, total=len(accepted)),
        )
        if all_warnings:
            QMessageBox.warning(self, translator.tr("proofread.apply_warnings_title"), "\n".join(all_warnings))

        self.accept()

    # ------------------------------------------------------------------- i18n
    def _retranslate(self) -> None:
        self.setWindowTitle(translator.tr("proofread.dialog_title"))
        self._language_label.setText(translator.tr("proofread.language_label"))
        self._url_label.setText(translator.tr("proofread.service_url_label"))
        self._hint_label.setText(translator.tr("proofread.public_api_hint"))
        self._consent_checkbox.setText(translator.tr("proofread.consent_checkbox"))
        self._check_button.setText(translator.tr("proofread.check_button"))
        self._back_button.setText(translator.tr("proofread.back_button"))
        self._apply_button.setText(translator.tr("proofread.apply_selected_button"))
        self._close_button.setText(translator.tr("proofread.close_button"))
