from pdfmanager.i18n.translator import translator
from pathlib import Path
from PySide6.QtCore import Signal,Qt,QDate
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QTableWidget,QTableWidgetItem,QLabel,QDialog,QFormLayout,QLineEdit,QDateEdit,QComboBox,QCheckBox,QFileDialog,QDialogButtonBox,QMessageBox,QSplitter
from pdfmanager.dms.receipts import ReceiptStore
from .viewer import PdfViewerWidget

class ReceiptsPanel(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.store=ReceiptStore();layout=QVBoxLayout(self)
        heading=QLabel('Paragony i wydatki');heading.setObjectName('PageTitle');layout.addWidget(heading)
        row=QHBoxLayout()
        for label,callback in [('Dodaj wydatek',lambda:self.edit()),('Edytuj',self.edit_selected),('Usuń',self.remove),('Eksport CSV',self.export)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch();layout.addLayout(row)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Data','Sprzedawca','Kwota','Waluta','Kategoria','Płatność','Do zwrotu']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.doubleClicked.connect(lambda:self.edit_selected());layout.addWidget(self.table)
        translator.language_changed.connect(lambda _:self.refresh());self.total=QLabel();layout.addWidget(self.total);self.refresh()
    def refresh(self):
        from decimal import Decimal
        rows=self.store.all();self.table.setRowCount(len(rows));totals={}
        for row,(identifier,data) in enumerate(rows):
            for column,key in enumerate(('date','payee','amount','currency','category','payment','reimbursable')):
                value=data.get(key,'');item=QTableWidgetItem(translator.text('Tak' if value else 'Nie') if key=='reimbursable' else str(value));item.setData(Qt.UserRole,identifier);self.table.setItem(row,column,item)
            currency=data.get('currency','PLN');totals[currency]=totals.get(currency,Decimal(0))+Decimal(data['amount'])
        self.total.setText(translator.text('Suma: ')+ ' • '.join(f'{v:.2f} {k}' for k,v in totals.items()));self.table.resizeColumnsToContents()
    def selected(self):
        row=self.table.currentRow()
        if row<0:return None
        identifier=self.table.item(row,0).data(Qt.UserRole)
        return next((i,r) for i,r in self.store.all() if i==identifier)
    def edit_selected(self):
        item=self.selected()
        if item:self.edit(*item)
    def edit(self,identifier=None,record=None):
        record=record or {};dialog=QDialog(self);dialog.setWindowTitle('Wydatek — dokument i dane');dialog.resize(1000,650)
        layout=QHBoxLayout(dialog);preview=QWidget();pv=QVBoxLayout(preview);empty=QLabel('Wybierz PDF paragonu, aby zobaczyć podgląd.');pv.addWidget(empty);layout.addWidget(preview,3)
        form_widget=QWidget();form=QFormLayout(form_widget);layout.addWidget(form_widget,2);fields={}
        date_edit=QDateEdit();date_edit.setCalendarPopup(True);date_edit.setDate(QDate.fromString(record.get('date',QDate.currentDate().toString('yyyy-MM-dd')),'yyyy-MM-dd'));form.addRow('Data:',date_edit)
        for key,label,default in [('payee','Sprzedawca',''),('amount','Kwota','0.00'),('currency','Waluta','PLN'),('category','Kategoria','Zakupy'),('payment','Płatność','Karta'),('description','Opis','')]:
            edit=QLineEdit(str(record.get(key,default)));form.addRow(label+':',edit);fields[key]=edit
        refundable=QCheckBox('Wydatek do zwrotu');refundable.setChecked(record.get('reimbursable',False));form.addRow(refundable)
        document=QLineEdit(record.get('document',''));form.addRow('Dokument PDF:',document)
        viewers=[]
        def load(path):
            if not path or not Path(path).is_file():return
            for viewer in viewers:pv.removeWidget(viewer);viewer.close();viewer.deleteLater()
            viewers.clear()
            try:
                viewer=PdfViewerWidget(path)
                if not viewer.is_loaded:
                    error=viewer.load_error;viewer.close();viewer.deleteLater();raise ValueError(error or 'Nie można wyświetlić dokumentu.')
                pv.addWidget(viewer);viewers.append(viewer);empty.hide();viewer.fit_width()
            except Exception as exc:QMessageBox.warning(dialog,translator.text('Podgląd'),str(exc))
        def choose():
            path,_=QFileDialog.getOpenFileName(dialog,'Dokument paragonu','','PDF (*.pdf)')
            if path:document.setText(path);load(path)
        button=QPushButton('Wybierz PDF');button.clicked.connect(choose);form.addRow(button)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        def save():
            try:self.store.save({k:v.text() for k,v in fields.items()}|{'date':date_edit.date().toString('yyyy-MM-dd'),'reimbursable':refundable.isChecked(),'document':document.text()},identifier);dialog.accept()
            except Exception as exc:QMessageBox.warning(dialog,'Wydatek',str(exc))
        buttons.accepted.connect(save);load(document.text());dialog.exec()
        for viewer in viewers:viewer.close()
        self.refresh()
    def remove(self):
        item=self.selected()
        if item and QMessageBox.question(self,'Usuń wydatek','Usunąć wpis? Plik dokumentu pozostanie na dysku.')==QMessageBox.Yes:self.store.remove(item[0]);self.refresh()
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Eksport wydatków','','CSV (*.csv)')
        if path:self.store.export(path)
