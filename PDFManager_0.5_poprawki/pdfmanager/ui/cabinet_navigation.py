from pdfmanager.i18n.translator import translator
from pdfmanager.i18n.bindings import SOURCE_ROLE
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QComboBox,QLineEdit,QListWidget,QListWidgetItem,QLabel,QPushButton
from pdfmanager.dms.cabinets import CabinetStore
from .vector_icons import vector_icon

class CabinetNavigation(QWidget):
    root_selected=Signal(str);folder_selected=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('CabinetNavigation');layout=QVBoxLayout(self);layout.setContentsMargins(8,10,8,8);layout.setSpacing(7)
        title=QLabel('SZAFKI');title.setObjectName('PanelEyebrow');layout.addWidget(title)
        self.cabinets=QComboBox();self.cabinets.setProperty("i18nSkip",True);layout.addWidget(self.cabinets)
        self.filter=QLineEdit();self.filter.setPlaceholderText(translator.text('Filtruj szuflady…'));layout.addWidget(self.filter)
        self.drawers=QListWidget();self.drawers.setObjectName('DrawersList');layout.addWidget(self.drawers)
        self.filter.textChanged.connect(self.filter_items);self.cabinets.currentIndexChanged.connect(self.select_root);self.drawers.itemClicked.connect(lambda item:self.folder_selected.emit(item.data(Qt.UserRole)))
        self.refresh()
    def refresh(self):
        selected=self.cabinets.currentData();self.cabinets.blockSignals(True);self.cabinets.clear()
        for entry in CabinetStore().read():self.cabinets.addItem(entry['name'],entry['root'])
        if selected:self.cabinets.setCurrentIndex(max(0,self.cabinets.findData(selected)))
        self.cabinets.blockSignals(False)
    def select_root(self,index):
        root=self.cabinets.currentData()
        if root:self.set_root(root);self.root_selected.emit(root)
    def set_root(self,root):
        root=Path(root);self.drawers.clear()
        if not root.is_dir():return
        try:children=sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink())[:5000]
        except OSError:
            self.drawers.addItem('Folder jest chwilowo niedostępny.');return
        for path in [root,*children]:
            item=QListWidgetItem(vector_icon('cabinet'),'Wszystkie dokumenty' if path==root else path.name);item.setData(Qt.UserRole,str(path));
            if path==root:item.setData(SOURCE_ROLE,'Wszystkie dokumenty');item.setText(translator.text('Wszystkie dokumenty'))
            self.drawers.addItem(item)
        self.filter_items(self.filter.text())
    def filter_items(self,text):
        for i in range(self.drawers.count()):self.drawers.item(i).setHidden(text.casefold() not in self.drawers.item(i).text().casefold())
