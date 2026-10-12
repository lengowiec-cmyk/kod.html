from pathlib import Path
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QComboBox,QFileDialog,QSplitter,QMessageBox
from .document_list import DocumentListView
from pdfmanager.dms.cabinets import CabinetStore
from pdfmanager.dms.files import transfer_file
from pdfmanager.dms.preferences import Preferences
from pdfmanager.security.opening import ALLOWED

class DropDocuments(DocumentListView):
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.target=None;self.setAcceptDrops(True);self.setDragEnabled(True)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):event.acceptProposedAction()
    def dragMoveEvent(self,event):self.dragEnterEvent(event)
    def dropEvent(self,event):
        if not self.target:return
        errors=[]
        for url in event.mimeData().urls():
            path=Path(url.toLocalFile())
            try:
                if not path.is_file() or path.suffix.lower() not in ALLOWED|{'.pdf'}:raise ValueError('Nieobsługiwany lub niebezpieczny typ pliku.')
                transfer_file(path,Path(self.target)/path.name)
            except Exception as exc:errors.append(f'{path.name}: {exc}')
        if errors:QMessageBox.warning(self,'Import dokumentów','\n'.join(errors))
        event.acceptProposedAction();self.changed.emit()

class InboxPanel(QWidget):
    open_requested=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.source='';layout=QVBoxLayout(self);layout.setContentsMargins(12,10,12,10)
        heading=QLabel('Skrzynka dokumentów');heading.setObjectName('PageTitle');layout.addWidget(heading)
        controls=QHBoxLayout();choose=QPushButton('Folder przychodzący');choose.clicked.connect(self.choose);controls.addWidget(choose)
        self.source_label=QLabel('Wybierz folder skanów lub dokumentów przychodzących.');controls.addWidget(self.source_label,1)
        self.cabinets=QComboBox();self.cabinets.currentIndexChanged.connect(self.destination);controls.addWidget(self.cabinets)
        target=QPushButton('Folder docelowy…');target.clicked.connect(self.choose_target);controls.addWidget(target)
        copy=QPushButton('Kopiuj zaznaczone →');copy.clicked.connect(self.copy);controls.addWidget(copy);layout.addLayout(controls)
        split=QSplitter();self.incoming=DocumentListView();self.incoming.setDragEnabled(True);self.outgoing=DropDocuments()
        split.addWidget(self.incoming);split.addWidget(self.outgoing);layout.addWidget(split)
        note=QLabel('Przeciągnij dokument z lewej listy na prawą. Import kopiuje plik — oryginał pozostaje w skrzynce.');note.setObjectName('MutedLabel');layout.addWidget(note)
        self.incoming.document_activated.connect(self.open_requested);self.outgoing.document_activated.connect(self.open_requested)
        self.refresh();source=Preferences().get('inbox_folder','')
        if source and Path(source).is_dir():self.set_source(source)
    def refresh(self):
        self.cabinets.blockSignals(True);self.cabinets.clear()
        for entry in CabinetStore().read():self.cabinets.addItem(entry['name'],entry['root'])
        self.cabinets.blockSignals(False);self.destination()
    def set_source(self,folder):self.source=folder;self.source_label.setText(folder);self.incoming.show_folder(folder);Preferences().put('inbox_folder',folder)
    def choose(self):
        folder=QFileDialog.getExistingDirectory(self,'Folder przychodzący',self.source)
        if folder:self.set_source(folder)
    def destination(self,*args):
        folder=self.cabinets.currentData()
        if folder:self.outgoing.target=folder;self.outgoing.show_folder(folder)
    def choose_target(self):
        folder=QFileDialog.getExistingDirectory(self,'Folder docelowy')
        if folder:self.outgoing.target=folder;self.outgoing.show_folder(folder)
    def copy(self):
        if not self.outgoing.target:return
        errors=[]
        for path in self.incoming.selected_paths():
            try:
                if path.suffix.lower() not in ALLOWED|{'.pdf'}:raise ValueError('Niebezpieczny lub nieobsługiwany typ pliku.')
                transfer_file(path,Path(self.outgoing.target)/path.name)
            except Exception as exc:errors.append(str(exc))
        if errors:QMessageBox.warning(self,'Kopiowanie','\n'.join(errors))
