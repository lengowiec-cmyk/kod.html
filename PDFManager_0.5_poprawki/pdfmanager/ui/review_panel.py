"""Local task queue: review status changes never edit the linked PDFs."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QLineEdit,QComboBox,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QDialog,QFormLayout,QTextEdit,QDialogButtonBox
from pdfmanager.i18n.translator import translator
from pdfmanager.dms.review_queue import ReviewQueue,STATES
LABELS=['Nowe','W trakcie','Do poprawy','Gotowe']
class ReviewPanel(QWidget):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.store=ReviewQueue();layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Kolejka weryfikacji dokumentów'))
        layout.addWidget(QLabel('Kolejka lokalna na tym komputerze. Zmiana statusu nie zmienia PDF. Raport CSV można udostępnić zespołowi.'))
        row=QHBoxLayout();self.query=QLineEdit();self.query.setPlaceholderText('Szukaj zlecenia, AWB, pracownika lub nazwy');row.addWidget(self.query);self.query.returnPressed.connect(self.refresh)
        self.filter=QComboBox();self.filter.addItems(['Wszystkie',*LABELS]);self.filter.currentIndexChanged.connect(self.refresh);row.addWidget(self.filter);layout.addLayout(row)
        row=QHBoxLayout()
        for name,slot in [('Dodaj PDF-y',self.add),('Edytuj zadanie',self.edit),('Otwórz dokument',self.open),('Odśwież',self.refresh),('Eksport CSV',self.export),('Usuń wpis',self.remove)]:
            button=QPushButton(name);button.clicked.connect(slot);row.addWidget(button)
        layout.addLayout(row);self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Dokument','Status','Pracownik','Zlecenie / AWB','Typ','Aktualizacja']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.doubleClicked.connect(self.edit);layout.addWidget(self.table)
        translator.language_changed.connect(self.on_language);self.refresh()
    def on_language(self,_):self.refresh()
    def refresh(self):
        try:
            query=self.query.text().casefold();state=self.filter.currentIndex()-1
            rows=[r for r in self.store.all() if (state<0 or r['status']==STATES[state]) and (not query or query in ' '.join(r[k] for k in ('path','owner','order','kind','note')).casefold())]
            self.rows=rows[:500];self.table.setRowCount(len(self.rows))
            for i,value in enumerate(self.rows):
                for j,text in enumerate([Path(value['path']).name,translator.text(LABELS[STATES.index(value['status'])]),value['owner'],value['order'],value['kind'],value['updated']]):self.table.setItem(i,j,QTableWidgetItem(text))
            self.table.resizeColumnsToContents()
        except Exception as exc:QMessageBox.warning(self,translator.text('Kolejka weryfikacji dokumentów'),str(exc))
    def selected(self):
        i=self.table.currentRow()
        return self.rows[i] if 0<=i<len(self.rows) else None
    def add(self):
        paths,_=QFileDialog.getOpenFileNames(self,translator.text('Dodaj PDF-y'),'','PDF (*.pdf)')
        try:
            for path in paths:self.store.add(path)
            self.refresh()
        except Exception as exc:QMessageBox.warning(self,'PDFManager',str(exc));self.refresh()
    def edit(self):
        value=self.selected()
        if not value:return
        dialog=QDialog(self);dialog.setWindowTitle('Edytuj zadanie');form=QFormLayout(dialog);state=QComboBox();state.addItems(LABELS);state.setCurrentIndex(STATES.index(value['status']));form.addRow('Status',state);fields={}
        for key,name in [('owner','Pracownik'),('order','Zlecenie / AWB'),('kind','Typ')]:
            widget=QLineEdit(value[key]);widget.setMaxLength(80 if key=='kind' else 120);fields[key]=widget;form.addRow(name,widget)
        note=QTextEdit();note.setAcceptRichText(False);note.setPlainText(value['note']);form.addRow('Uwagi',note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()!=QDialog.Accepted:return
        try:self.store.update(value['id'],value['revision'],status=STATES[state.currentIndex()],note=note.toPlainText(),**{k:w.text() for k,w in fields.items()});self.refresh()
        except Exception as exc:QMessageBox.warning(self,'PDFManager',str(exc));self.refresh()
    def open(self):
        value=self.selected()
        if value:self.window.open_document(value['path'])
    def remove(self):
        value=self.selected()
        if value and QMessageBox.question(self,'PDFManager',translator.text('Usunąć wpis? Dokument pozostanie na dysku.'))==QMessageBox.Yes:
            try:self.store.remove(value['id'],value['revision']);self.refresh()
            except Exception as exc:QMessageBox.warning(self,'PDFManager',str(exc))
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,translator.text('Eksport CSV'),'','CSV (*.csv)')
        if path:
            try:self.store.export(Path(path).with_suffix('.csv'))
            except Exception as exc:QMessageBox.warning(self,'PDFManager',str(exc))
