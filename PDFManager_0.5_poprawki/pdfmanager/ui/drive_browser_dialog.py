"""Okno przeglądania Google Dysku (Workflow A): foldery, wyszukiwanie,
wybór pliku PDF do otwarcia. Nie pobiera niczego samo — zwraca wybrany
`DriveFile`, pobranie i otwarcie obsługuje wywołujący (`MainWindow`).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from pdfmanager.drive.api_client import DriveApiClient, DriveApiError, DriveFile
from pdfmanager.i18n.translator import translator

ROOT_FOLDER_ID = "root"
ROOT_FOLDER_LABEL = "Mój Dysk"


class DriveBrowserDialog(QDialog):
    def __init__(self, client: DriveApiClient, parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._folder_stack: list[tuple[str, str]] = [(ROOT_FOLDER_ID, ROOT_FOLDER_LABEL)]
        self.selected_file: DriveFile | None = None

        self.setModal(True)
        self.resize(560, 480)

        self._breadcrumb_label = QLabel(self)
        self._back_button = QPushButton(self)
        self._back_button.clicked.connect(self._go_back)

        self._search_edit = QLineEdit(self)
        self._search_button = QPushButton(self)
        self._search_button.clicked.connect(self._run_search)

        self._list = QListWidget(self)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._open_button = QPushButton(self)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._cancel_button = QPushButton(self)
        self._cancel_button.clicked.connect(self.reject)

        top_row = QHBoxLayout()
        top_row.addWidget(self._back_button)
        top_row.addWidget(self._breadcrumb_label, 1)

        search_row = QHBoxLayout()
        search_row.addWidget(self._search_edit, 1)
        search_row.addWidget(self._search_button)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(self._cancel_button)
        bottom_row.addWidget(self._open_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addLayout(search_row)
        layout.addWidget(self._list)
        layout.addLayout(bottom_row)

        self._retranslate()
        self._load_current_folder()

    # ------------------------------------------------------------- nawigacja
    def _load_current_folder(self) -> None:
        folder_id, _ = self._folder_stack[-1]
        try:
            files = self._client.list_folder(folder_id)
        except DriveApiError as exc:
            QMessageBox.critical(self, translator.tr("drive.error_title"), str(exc))
            files = []
        self._populate_list(files)
        self._update_breadcrumb()

    def _populate_list(self, files: list[DriveFile]) -> None:
        self._list.clear()
        for drive_file in files:
            if not drive_file.is_folder and drive_file.mime_type != "application/pdf":
                continue
            icon_prefix = "📁 " if drive_file.is_folder else "📄 "
            item = QListWidgetItem(icon_prefix + drive_file.name)
            item.setData(Qt.ItemDataRole.UserRole, drive_file)
            self._list.addItem(item)

    def _update_breadcrumb(self) -> None:
        self._breadcrumb_label.setText(" / ".join(name for _, name in self._folder_stack))
        self._back_button.setEnabled(len(self._folder_stack) > 1)

    def _go_back(self) -> None:
        if len(self._folder_stack) > 1:
            self._folder_stack.pop()
            self._load_current_folder()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        drive_file: DriveFile = item.data(Qt.ItemDataRole.UserRole)
        if drive_file.is_folder:
            self._folder_stack.append((drive_file.id, drive_file.name))
            self._load_current_folder()
        else:
            self.selected_file = drive_file
            self.accept()

    def _on_open_clicked(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        drive_file: DriveFile = item.data(Qt.ItemDataRole.UserRole)
        if drive_file.is_folder:
            self._folder_stack.append((drive_file.id, drive_file.name))
            self._load_current_folder()
        else:
            self.selected_file = drive_file
            self.accept()

    # -------------------------------------------------------------- wyszukiwanie
    def _run_search(self) -> None:
        query = self._search_edit.text().strip()
        if not query:
            self._load_current_folder()
            return
        try:
            files = [f for f in self._client.search(query) if f.is_folder or f.mime_type == "application/pdf"]
        except DriveApiError as exc:
            QMessageBox.critical(self, translator.tr("drive.error_title"), str(exc))
            return
        self._populate_list(files)

    # ------------------------------------------------------------------- i18n
    def _retranslate(self) -> None:
        self.setWindowTitle(translator.tr("drive.browser_title"))
        self._back_button.setText(translator.tr("drive.back_button"))
        self._search_edit.setPlaceholderText(translator.tr("drive.search_placeholder"))
        self._search_button.setText(translator.tr("drive.search_button"))
        self._open_button.setText(translator.tr("drive.open_button"))
        self._cancel_button.setText(translator.tr("drive.cancel_button"))
