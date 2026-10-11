"""Okno zarządzania stronami PDF: miniatury, zmiana kolejności przez
przeciąganie, obrót, usuwanie, duplikowanie, wyodrębnianie, wstawianie
stron z innego pliku i podział dokumentu.

Każdy przycisk wywołuje natychmiast odpowiadającą operację z
`pdf_engine.page_ops` (zapis jest atomowy — patrz ten moduł), a potem
odświeża listę miniatur z dysku. To okno nigdy nie trzyma własnego,
długo żyjącego uchwytu `pymupdf.Document` — otwiera plik tylko na czas
wygenerowania miniatur i natychmiast go zamyka — dlatego wywołujący
(MainWindow) musi jedynie zwolnić uchwyt podglądu karty PRZED otwarciem
tego okna i otworzyć go ponownie PO jego zamknięciu (patrz
`PdfViewerWidget.release_document` / `reload_document`), żeby plik nie
był zablokowany na Windows.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from pdfmanager.i18n.translator import translator
from pdfmanager.pdf_engine import page_ops
from pdfmanager.pdf_engine.render import render_page_to_qimage

THUMBNAIL_ZOOM = 0.22
PAGE_INDEX_ROLE = Qt.ItemDataRole.UserRole


class PageManagerDialog(QDialog):
    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.setModal(True)
        self.resize(760, 580)

        self._list = QListWidget(self)
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setIconSize(QSize(120, 160))
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Snap)
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setSpacing(10)
        self._list.model().rowsMoved.connect(self._commit_current_order)

        self._btn_rotate_left = QPushButton(self)
        self._btn_rotate_right = QPushButton(self)
        self._btn_duplicate = QPushButton(self)
        self._btn_delete = QPushButton(self)
        self._btn_extract = QPushButton(self)
        self._btn_insert_from_file = QPushButton(self)
        self._btn_split = QPushButton(self)
        self._btn_close = QPushButton(self)

        self._btn_rotate_left.clicked.connect(lambda: self._rotate_selected(-90))
        self._btn_rotate_right.clicked.connect(lambda: self._rotate_selected(90))
        self._btn_duplicate.clicked.connect(self._duplicate_selected)
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_extract.clicked.connect(self._extract_selected)
        self._btn_insert_from_file.clicked.connect(self._insert_from_file)
        self._btn_split.clicked.connect(self._split_selected)
        self._btn_close.clicked.connect(self.accept)

        buttons_layout = QHBoxLayout()
        for btn in (
            self._btn_rotate_left,
            self._btn_rotate_right,
            self._btn_duplicate,
            self._btn_delete,
            self._btn_extract,
            self._btn_insert_from_file,
            self._btn_split,
        ):
            buttons_layout.addWidget(btn)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self._btn_close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(buttons_layout)

        self._retranslate()
        self._reload()

    # --------------------------------------------------------------- miniatury
    def _reload(self) -> None:
        self._list.clear()
        doc = pymupdf.open(str(self.path))
        try:
            for index in range(doc.page_count):
                image = render_page_to_qimage(doc[index], zoom=THUMBNAIL_ZOOM)
                pixmap = QPixmap.fromImage(image)
                item = QListWidgetItem(QIcon(pixmap), translator.tr("pages.page_label", number=index + 1))
                item.setData(PAGE_INDEX_ROLE, index)
                self._list.addItem(item)
        finally:
            doc.close()

    def _selected_page_indices(self) -> list[int]:
        indices = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.isSelected():
                indices.append(item.data(PAGE_INDEX_ROLE))
        return indices

    # ------------------------------------------------------------------ akcje
    def _commit_current_order(self, *_args: object) -> None:
        new_order = [self._list.item(row).data(PAGE_INDEX_ROLE) for row in range(self._list.count())]
        if len(set(new_order)) != len(new_order):
            return  # porządek jeszcze niekompletny (pośredni stan podczas przeciągania)
        try:
            page_ops.reorder_pages(self.path, new_order)
        except page_ops.PageOpError as exc:
            QMessageBox.warning(self, translator.tr("pages.error_title"), str(exc))
        self._reload()

    def _rotate_selected(self, degrees: int) -> None:
        indices = self._selected_page_indices()
        if not indices:
            return
        for index in indices:
            page_ops.rotate_page(self.path, index, degrees)
        self._reload()

    def _duplicate_selected(self) -> None:
        indices = self._selected_page_indices()
        if not indices:
            return
        for index in sorted(indices, reverse=True):
            page_ops.duplicate_page(self.path, index)
        self._reload()

    def _delete_selected(self) -> None:
        indices = self._selected_page_indices()
        if not indices:
            return
        if (
            QMessageBox.question(
                self,
                translator.tr("pages.confirm_delete_title"),
                translator.tr("pages.confirm_delete_message", count=len(indices)),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            for index in sorted(indices, reverse=True):
                page_ops.delete_page(self.path, index)
        except page_ops.PageOpError as exc:
            QMessageBox.warning(self, translator.tr("pages.error_title"), str(exc))
        self._reload()

    def _extract_selected(self) -> None:
        indices = self._selected_page_indices()
        if not indices:
            QMessageBox.information(self, translator.tr("pages.error_title"), translator.tr("pages.select_hint"))
            return
        output, _ = QFileDialog.getSaveFileName(self, translator.tr("pages.extract_dialog_title"), "", "PDF (*.pdf)")
        if not output:
            return
        page_ops.extract_pages(self.path, indices, Path(output))
        QMessageBox.information(self, translator.tr("pages.extract_dialog_title"), translator.tr("pages.extract_done", path=output))

    def _insert_from_file(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, translator.tr("pages.insert_dialog_title"), "", "PDF (*.pdf)")
        if not source:
            return
        indices = self._selected_page_indices()
        at_index = max(indices) + 1 if indices else self._list.count()
        page_ops.insert_pages_from(self.path, Path(source), at_index)
        self._reload()

    def _split_selected(self) -> None:
        indices = self._selected_page_indices()
        if not indices:
            QMessageBox.information(self, translator.tr("pages.error_title"), translator.tr("pages.split_select_hint"))
            return
        output_dir = QFileDialog.getExistingDirectory(self, translator.tr("pages.split_dialog_title"), "")
        if not output_dir:
            return
        parts = page_ops.split_at(self.path, indices, Path(output_dir), self.path.stem)
        QMessageBox.information(
            self,
            translator.tr("pages.split_dialog_title"),
            translator.tr("pages.split_done", count=len(parts), folder=output_dir),
        )

    # -------------------------------------------------------------------- i18n
    def _retranslate(self) -> None:
        self.setWindowTitle(translator.tr("pages.manager_title"))
        self._btn_rotate_left.setText(translator.tr("pages.rotate_left"))
        self._btn_rotate_right.setText(translator.tr("pages.rotate_right"))
        self._btn_duplicate.setText(translator.tr("pages.duplicate"))
        self._btn_delete.setText(translator.tr("pages.delete"))
        self._btn_extract.setText(translator.tr("pages.extract"))
        self._btn_insert_from_file.setText(translator.tr("pages.insert_from_file"))
        self._btn_split.setText(translator.tr("pages.split"))
        self._btn_close.setText(translator.tr("pages.close"))
