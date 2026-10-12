"""Folder PDF content search with results and explicit per-file failures."""
from pathlib import Path
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QPushButton,QTreeWidget,QTreeWidgetItem,QLabel,QSplitter,QFileDialog,QCheckBox,QDateEdit,QComboBox)
from pdfmanager.pdf_engine.extended_ops import search_text
from .background_job import run_job


class SearchPanel(QWidget):
    open_requested=Signal(str,int)
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=QHBoxLayout(self);layout.setContentsMargins(5,5,5,5)
        options=QWidget();options.setMaximumWidth(330);form=QFormLayout(options)
        form.addRow(QLabel('Opcje wyszukiwania'))
        self.query=QLineEdit();form.addRow('Szukaj tekstu:',self.query)
        self.folder=QLineEdit();form.addRow('Folder:',self.folder)
        choose=QPushButton('Wybierz folder');choose.clicked.connect(self.choose_folder);form.addRow(choose)
        self.fulltext=QCheckBox('Szukaj także w treści PDF');form.addRow(self.fulltext)
        self.recursive=QCheckBox('Uwzględnij podfoldery');form.addRow(self.recursive)
        clear=QPushButton('Wyczyść indeks PDF');clear.clicked.connect(self.clear_index);form.addRow(clear)
        self.types=QComboBox();self.types.addItems(['Wszystkie pliki','PDF','Obrazy','Dokumenty biurowe']);form.addRow('Typ pliku:',self.types)
        self.dates=QCheckBox('Filtruj datę modyfikacji');form.addRow(self.dates)
        self.from_date=QDateEdit();self.to_date=QDateEdit();self.from_date.setCalendarPopup(True);self.to_date.setCalendarPopup(True)
        from PySide6.QtCore import QDate
        self.from_date.setDate(QDate.currentDate().addMonths(-12));self.to_date.setDate(QDate.currentDate());form.addRow('Od:',self.from_date);form.addRow('Do:',self.to_date)
        self.button=QPushButton('Szukaj');self.button.clicked.connect(self.search);form.addRow(self.button)
        self.status=QLabel();self.status.setWordWrap(True);form.addRow(self.status)
        self.results=QTreeWidget();self.results.setHeaderLabels(['Nazwa','Lokalizacja','Strona','Trafienia'])
        self.results.itemDoubleClicked.connect(self.open_result)
        split=QSplitter();split.addWidget(options);split.addWidget(self.results);split.setSizes([320,1200]);layout.addWidget(split)
    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Folder wyszukiwania')
        if folder:self.folder.setText(folder)
    def search(self):
        folder=Path(self.folder.text());query=self.query.text().strip();recursive=self.recursive.isChecked();fulltext=self.fulltext.isChecked()
        if not folder.is_dir() or not query:self.status.setText('Wybierz folder i wpisz tekst.');return
        extensions=[None,{'.pdf'},{'.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'},{'.docx','.xlsx','.pptx','.odt','.ods','.rtf','.txt','.csv'}][self.types.currentIndex()]
        after=self.from_date.date().toPython() if self.dates.isChecked() else None;before=self.to_date.date().toPython() if self.dates.isChecked() else None
        def work():
            from pdfmanager.dms.search import search_files
            return search_files(folder,query,recursive=recursive,fulltext=fulltext,extensions=extensions,modified_after=after,modified_before=before)
        def complete(data):
            results,errors=data;self.results.clear()
            for path,page,count in results:
                item=QTreeWidgetItem([path.name,str(path.parent),str(page+1) if page>=0 else 'Nazwa pliku',str(count)])
                item.setData(0,Qt.ItemDataRole.UserRole,(str(path),page));self.results.addTopLevelItem(item)
            self.status.setText(f'Wyniki: {len(results)}. Błędy: {len(errors)}.'+ ('\n'+'\n'.join(errors[:10]) if errors else ''))
        run_job(self,'Wyszukiwanie PDF',work,complete)
    def open_result(self,item,column):
        path,page=item.data(0,Qt.ItemDataRole.UserRole)
        if Path(path).suffix.lower()=='.pdf':self.open_requested.emit(path,max(0,page))
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            __import__("pdfmanager.security.opening",fromlist=["open_document_file"]).open_document_file(self,path)

    def clear_index(self):
        from pdfmanager.dms.search import clear_index
        run_job(self,'Czyszczenie indeksu',clear_index,lambda _:self.status.setText('Indeks wyczyszczony; zostanie odbudowany przy wyszukiwaniu treści.'))
