from pathlib import Path
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QPushButton,QDialog,QFormLayout,QLineEdit,QComboBox,QCheckBox,QFileDialog,QDialogButtonBox,QMessageBox
from pdfmanager.dms.automation import Rules,route_documents
from .background_job import run_job

class AutomationPanel(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rules=Rules();layout=QVBoxLayout(self);heading=QLabel('Automatyzacja dokumentów');heading.setObjectName('PageTitle');layout.addWidget(heading)
        layout.addWidget(QLabel('Reguły kierowania według nazwy, treści PDF albo kodów. Pierwsza pasująca reguła wygrywa.'))
        row=QHBoxLayout()
        for text,callback in [('Nowa reguła',lambda:self.edit()),('Edytuj',self.edit_selected),('Usuń',self.remove),('Przetwórz dokumenty…',self.run)]:
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();layout.addLayout(row)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Reguła','Warunek','Szukana fraza','Folder docelowy','Aktywna']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);layout.addWidget(self.table)
        self.ocr=QCheckBox('Przed kierowaniem wykonaj OCR (skany)');layout.addWidget(self.ocr);self.lang=QComboBox();self.lang.addItems(['pol','eng','ukr']);layout.addWidget(self.lang)
        self.report=QTableWidget(0,3);self.report.setHorizontalHeaderLabels(['Dokument','Wynik','Lokalizacja / komunikat']);layout.addWidget(self.report);self.refresh()
    def refresh(self):
        rules=self.rules.all();self.table.setRowCount(len(rules))
        for row,r in enumerate(rules):
            for col,key in enumerate(('name','kind','match','target','enabled')):self.table.setItem(row,col,QTableWidgetItem(str(r.get(key,''))))
        self.table.resizeColumnsToContents()
    def edit_selected(self):
        index=self.table.currentRow()
        if index>=0:self.edit(index)
    def edit(self,index=None):
        value=self.rules.all()[index] if index is not None else {};dialog=QDialog(self);dialog.setWindowTitle('Reguła kierowania dokumentów');dialog.resize(650,330);form=QFormLayout(dialog)
        name=QLineEdit(value.get('name',''));form.addRow('Nazwa:',name);kind=QComboBox();kind.addItems(['Nazwa','Tekst PDF','Kod kreskowy']);kind.setCurrentText(value.get('kind','Tekst PDF'));form.addRow('Warunek:',kind)
        match=QLineEdit(value.get('match',''));form.addRow('Zawiera frazę:',match);target=QLineEdit(value.get('target',''));form.addRow('Folder docelowy:',target)
        def choose():
            folder=QFileDialog.getExistingDirectory(dialog,'Folder docelowy')
            if folder:target.setText(folder)
        button=QPushButton('Wybierz folder…');button.clicked.connect(choose);form.addRow(button);enabled=QCheckBox('Reguła aktywna');enabled.setChecked(value.get('enabled',True));form.addRow(enabled)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        def save():
            try:self.rules.save({'name':name.text(),'kind':kind.currentText(),'match':match.text(),'target':target.text(),'enabled':enabled.isChecked()},index);dialog.accept()
            except Exception as exc:QMessageBox.warning(dialog,'Reguła',str(exc))
        buttons.accepted.connect(save);dialog.exec();self.refresh()
    def remove(self):
        index=self.table.currentRow()
        if index>=0 and QMessageBox.question(self,'Usuń regułę','Usunąć zaznaczoną regułę?')==QMessageBox.Yes:self.rules.remove(index);self.refresh()
    def run(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Dokumenty do kierowania','','Dokumenty (*.pdf *.png *.jpg *.jpeg *.tif *.tiff)')
        if not paths:return
        rules=self.rules.all();ocr=self.ocr.isChecked();language=self.lang.currentText()
        def complete(rows):
            self.report.setRowCount(len(rows))
            for row,values in enumerate(rows):
                for col,value in enumerate(values):self.report.setItem(row,col,QTableWidgetItem(str(value)))
            self.report.resizeColumnsToContents()
        run_job(self,'Kierowanie dokumentów',lambda:route_documents([Path(p) for p in paths],rules,ocr=ocr,language=language),complete)
