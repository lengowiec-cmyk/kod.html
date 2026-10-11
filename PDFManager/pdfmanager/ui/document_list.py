"""Lista dokumentów PDF w wybranym folderze — panel centralny."""
from __future__ import annotations

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtWidgets import QFileSystemModel, QTreeView, QAbstractItemView, QMenu, QFileDialog, QInputDialog, QMessageBox

from pdfmanager.i18n.translator import translator

# Domyślne kolumny QFileSystemModel: 0 Nazwa, 1 Rozmiar, 2 Typ, 3 Data modyfikacji.
COLUMN_TYPE = 2


class DocumentListView(QTreeView):
    document_activated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.is_open_document = lambda path: False
        self._model = QFileSystemModel(self)
        self._model.setFilter(QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self._model.setNameFilters([])
        self._model.setNameFilterDisables(False)
        self._model.setRootPath("")
        self.setColumnWidth(0,240)
        self.setModel(self._model)
        self.hideColumn(COLUMN_TYPE)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.doubleClicked.connect(self._on_double_clicked)
        translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def show_folder(self, path: str) -> None:
        index = self._model.setRootPath(path)
        self.setRootIndex(index)

    def _on_double_clicked(self, index) -> None:
        path = self._model.filePath(index)
        if not self._model.isDir(index):
            if path.lower().endswith('.pdf'):
                self.document_activated.emit(path)
            else:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def retranslate_ui(self) -> None:
        self._model.setHeaderData(0, Qt.Orientation.Horizontal, translator.tr("column.name"))
        self._model.setHeaderData(1, Qt.Orientation.Horizontal, translator.tr("column.size"))
        self._model.setHeaderData(3, Qt.Orientation.Horizontal, translator.tr("column.modified"))

    def selected_paths(self):
        from pathlib import Path
        return [Path(self._model.filePath(i)) for i in self.selectionModel().selectedRows(0)]

    def _context_menu(self, position):
        menu=QMenu(self)
        for label,callback in [('Kopiuj do folderu…',lambda:self._transfer(False)),('Przenieś do folderu…',lambda:self._transfer(True)),('Zmień nazwę…',self._rename),('Przenieś do kosza PDFManager',self._trash)]:
            menu.addAction(label,callback)
        menu.exec(self.viewport().mapToGlobal(position))

    def _rename(self):
        paths=self.selected_paths()
        if len(paths)!=1:return
        name,ok=QInputDialog.getText(self,'Zmień nazwę','Nowa nazwa pliku:',text=paths[0].name)
        if not ok:return
        try:
            if self.is_open_document(paths[0]):raise ValueError("Zamknij kartę dokumentu przed zmianą nazwy.")
            from pdfmanager.dms.cabinets import validate_relative
            relative=validate_relative(name)
            if len(relative.parts)!=1 :raise ValueError('Podaj pojedynczą nazwę pliku.')
            from pdfmanager.dms.files import transfer_file
            transfer_file(paths[0],paths[0].parent/relative,move=True)
        except Exception as exc:QMessageBox.critical(self,'Zmiana nazwy',str(exc))

    def _transfer(self,move):
        paths=self.selected_paths()
        if not paths:return
        folder=QFileDialog.getExistingDirectory(self,'Folder docelowy')
        if not folder:return
        from pathlib import Path
        from pdfmanager.dms.files import transfer_file
        from .background_job import run_job
        opened={p for p in paths if self.is_open_document(p)}
        def work():
            errors=[]
            for path in paths:
                try:
                    if move and path in opened:raise ValueError('Zamknij kartę dokumentu przed przeniesieniem.')
                    transfer_file(path,Path(folder)/path.name,move=move)
                except Exception as exc:errors.append(f'{path.name}: {exc}')
            return errors
        def complete(errors):
            if errors:QMessageBox.warning(self,'Operacje na plikach','\n'.join(errors))
        run_job(self,'Przenoszenie' if move else 'Kopiowanie',work,complete)

    def _trash(self):
        from pdfmanager.dms.trash import Trash
        paths=self.selected_paths()
        if not paths:return
        if QMessageBox.question(self,'Kosz PDFManager',f'Przenieść {len(paths)} plików do kosza aplikacji? Można je później przywrócić.')!=QMessageBox.Yes:return
        errors=[]
        for path in paths:
            try:
                if self.is_open_document(path):raise ValueError('Zamknij kartę dokumentu przed przeniesieniem do kosza.')
                Trash().put(path)
            except Exception as exc:errors.append(f'{path.name}: {exc}')
        if errors:QMessageBox.warning(self,'Kosz','\n'.join(errors))
