"""Drzewo folderów (lokalny system plików) — panel po lewej stronie.

Na tym etapie obsługuje tylko lokalny system plików. Google Dysk (Workflow A)
zostanie dodany w kolejnym etapie jako odrębne źródło/korzeń drzewa — patrz
ocena architektury: integracja nie powinna wymuszać przebudowy tego widoku.
"""
from __future__ import annotations

from PySide6.QtCore import QDir, Signal
from PySide6.QtWidgets import QFileSystemModel, QTreeView

from pdfmanager.i18n.translator import translator


class FolderTreeView(QTreeView):
    folder_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model = QFileSystemModel(self)
        self._model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        self._model.setRootPath("")
        self.setModel(self._model)
        self.setRootIndex(self._model.index(QDir.rootPath()))
        # Pokazujemy tylko nazwę folderu, resztę kolumn (rozmiar, typ, data)
        # chowamy — nie są tu przydatne.
        for column in range(1, self._model.columnCount()):
            self.hideColumn(column)
        self.setHeaderHidden(True)
        self.clicked.connect(self._on_clicked)
        translator.language_changed.connect(self.retranslate_ui)

    def set_cabinet_root(self, path: str) -> None:
        index = self._model.setRootPath(path)
        self.setRootIndex(index)

    def set_current_folder(self, path: str) -> None:
        index = self._model.index(path)
        if index.isValid():
            self.setCurrentIndex(index)
            self.expand(index)
            self.scrollTo(index)

    def _on_clicked(self, index) -> None:
        path = self._model.filePath(index)
        self.folder_selected.emit(path)

    def retranslate_ui(self) -> None:
        # Nagłówek jest ukryty; metoda zachowana dla spójności wzorca
        # retranslate_ui stosowanego w całym interfejsie.
        pass
