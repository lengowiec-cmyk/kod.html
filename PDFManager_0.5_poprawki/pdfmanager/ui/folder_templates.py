from pdfmanager.i18n.translator import translator
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QHBoxLayout,QVBoxLayout,QListWidget,QTreeWidget,QTreeWidgetItem,QPushButton,QInputDialog,QMessageBox,QLabel,QDialogButtonBox
from pdfmanager.dms.cabinets import CabinetStore,validate_relative

class FolderTemplatesDialog(QDialog):
    def __init__(self,parent,root=None):
        super().__init__(parent);self.setWindowTitle(translator.text('Biblioteka struktur folderów'));self.resize(850,590);self.store=CabinetStore();self.root=Path(root) if root else None
        layout=QVBoxLayout(self);layout.addWidget(QLabel('Powtarzalne struktury dla klientów, projektów i spraw'))
        actions=QHBoxLayout()
        for label,callback in [('Dodaj',lambda:self.edit()),('Edytuj',self.edit_selected),('Usuń',self.remove)]:
            button=QPushButton(label);button.clicked.connect(callback);actions.addWidget(button)
        actions.addStretch();layout.addLayout(actions)
        row=QHBoxLayout();self.list=QListWidget();self.tree=QTreeWidget();self.tree.setHeaderLabels(['Podgląd folderów']);row.addWidget(self.list,1);row.addWidget(self.tree,2);layout.addLayout(row)
        self.list.currentTextChanged.connect(self.preview)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        apply=QPushButton('Utwórz klienta z szablonu');apply.setEnabled(bool(root));apply.clicked.connect(self.apply);layout.addWidget(apply);self.refresh()
    def refresh(self):
        current=self.list.currentItem().text() if self.list.currentItem() else '';self.list.clear();self.list.addItems(sorted(self.store.templates()))
        items=self.list.findItems(current,Qt.MatchExactly)
        if items:self.list.setCurrentItem(items[0])
        elif self.list.count():self.list.setCurrentRow(0)
    def preview(self,name):
        self.tree.clear();nodes={}
        for path in self.store.templates().get(name,[]):
            parts=path.replace('\\','/').split('/');parent=None
            for level,part in enumerate(parts):
                key='/'.join(parts[:level+1])
                if key not in nodes:
                    item=QTreeWidgetItem([part]);nodes[key]=item
                    parent.addChild(item) if parent else self.tree.addTopLevelItem(item)
                parent=nodes[key]
        self.tree.expandAll()
    def edit_selected(self):
        if self.list.currentItem():self.edit(self.list.currentItem().text())
    def edit(self,name=None):
        if not name:
            name,ok=QInputDialog.getText(self,'Nowy szablon',translator.text('Nazwa:'))
            if not ok:return
        text,ok=QInputDialog.getMultiLineText(self,'Struktura folderów','Jeden folder na linię; podfoldery oddzielaj /:', '\n'.join(self.store.templates().get(name,[])))
        if not ok:return
        try:self.store.save_template(name,[line.strip() for line in text.splitlines() if line.strip()]);self.refresh()
        except Exception as exc:QMessageBox.warning(self,'Szablon',str(exc))
    def remove(self):
        item=self.list.currentItem()
        if item and QMessageBox.question(self,'Usuń szablon','Usunąć szablon? Utworzone foldery pozostaną bez zmian.')==QMessageBox.Yes:
            import json
            templates=self.store.templates();templates.pop(item.text());self.store.settings.setValue('dms/templates',json.dumps(templates,ensure_ascii=False));self.refresh()
    def apply(self):
        item=self.list.currentItem()
        if not item:return
        name,ok=QInputDialog.getText(self,translator.text('Nowy klient'),'Nazwa nowego folderu klienta:')
        if not ok:return
        try:
            path=self.store.create_client(self.root,name,item.text());QMessageBox.information(self,'Struktura utworzona',str(path))
        except Exception as exc:QMessageBox.warning(self,'Struktura folderów',str(exc))
