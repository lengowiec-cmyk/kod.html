from pathlib import Path
from PySide6.QtWidgets import QInputDialog,QFileDialog,QMessageBox,QDialog,QVBoxLayout,QListWidget,QPushButton,QDialogButtonBox
from pdfmanager.dms.cabinets import CabinetStore
from pdfmanager.dms.scanning import import_scans
from .background_job import run_job

class CabinetTools:
    def __init__(self,window):
        self.window=window;self.store=CabinetStore();self.active=None
        from pdfmanager.app_settings import settings
        folder=Path(settings.last_folder).resolve() if settings.last_folder else None
        if folder:
            for entry in self.store.read():
                if folder.is_relative_to(Path(entry['root']).resolve()):self.active=entry;self.window._folder_tree.set_cabinet_root(entry['root']);break
    def error(self,exc):QMessageBox.critical(self.window,'Szafki i skany',str(exc))
    def select(self):
        entries=self.store.read()
        if not entries:self.add();return
        name,ok=QInputDialog.getItem(self.window,'Szafki','Wybierz szafkę:',[e['name'] for e in entries],0,False)
        if ok:
            entry=next(e for e in entries if e['name']==name)
            if not Path(entry['root']).is_dir():self.error('Folder szafki jest niedostępny.');return
            self.active=entry;self.window._folder_tree.set_cabinet_root(entry['root']);self.window._on_folder_selected(entry['root'])
    def add(self):
        root=QFileDialog.getExistingDirectory(self.window,'Katalog szafki')
        if not root:return
        name,ok=QInputDialog.getText(self.window,'Nowa szafka','Nazwa szafki:')
        if not ok:return
        try:self.store.add(name,root);self.active={'name':name.strip(),'root':root};self.window._folder_tree.set_cabinet_root(root);self.window._on_folder_selected(root)
        except Exception as exc:self.error(exc)
    def client(self):
        if not self.active:self.select()
        if not self.active:return
        name,ok=QInputDialog.getText(self.window,'Nowy klient / projekt','Nazwa folderu:')
        if not ok:return
        template,ok=QInputDialog.getItem(self.window,'Szablon folderów','Szablon:',list(self.store.templates()),0,False)
        if not ok:return
        try:path=self.store.create_client(self.active['root'],name,template);self.window._on_folder_selected(str(path))
        except Exception as exc:self.error(exc)
    def template(self):
        from .folder_templates import FolderTemplatesDialog
        FolderTemplatesDialog(self.window,self.active['root'] if self.active else None).exec()
    def scans(self):
        inputs,_=QFileDialog.getOpenFileNames(self.window,'Pliki ze skanera','','Skany (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)')
        if not inputs:return
        # Explicit page ordering rather than the file dialog's unspecified selection order.
        dialog=QDialog(self.window);dialog.setWindowTitle('Kolejność skanów — przeciągnij pliki');layout=QVBoxLayout(dialog)
        listing=QListWidget();listing.addItems(inputs);listing.setDragDropMode(QListWidget.DragDropMode.InternalMove);layout.addWidget(listing)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if not dialog.exec():return
        inputs=[listing.item(i).text() for i in range(listing.count())]
        folder=QFileDialog.getExistingDirectory(self.window,'Folder zapisu skanu',self.window._search_page.folder.text())
        if not folder:return
        run_job(self.window,'Import skanów do PDF',lambda:import_scans(inputs,folder),lambda path:self.window.open_document(str(path)))
    def scanner_folder(self):
        source=QFileDialog.getExistingDirectory(self.window,'Folder wejściowy skanera')
        if not source:return
        from pdfmanager.dms.scanning import SUPPORTED
        paths=sorted(p for p in Path(source).iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
        if not paths:self.error('W folderze nie ma obsługiwanych skanów.');return
        folder=QFileDialog.getExistingDirectory(self.window,'Folder zapisu zbiorczego PDF')
        if not folder:return
        if QMessageBox.question(self.window,'Import folderu',f'Połączyć {len(paths)} plików w jeden PDF? Kolejność alfabetyczna. Pliki źródłowe pozostaną w folderze.')!=QMessageBox.Yes:return
        run_job(self.window,'Import folderu skanera',lambda:import_scans(paths,folder),lambda path:self.window.open_document(str(path)))
    def search_cabinet(self):
        if not self.active:self.select()
        if not self.active:return
        self.window._shell.tabs.setCurrentIndex(5);self.window._search_page.folder.setText(self.active['root']);self.window._search_page.recursive.setChecked(True)

    def batch_split(self):
        inputs,_=QFileDialog.getOpenFileNames(self.window,'Wsadowe dzielenie PDF','','PDF (*.pdf)')
        if not inputs:return
        pages,ok=QInputDialog.getInt(self.window,'Podział PDF','Liczba stron w części:',1,1,10000)
        if not ok:return
        folder=QFileDialog.getExistingDirectory(self.window,'Folder wynikowy')
        if not folder:return
        from pdfmanager.dms.files import batch_split
        def complete(results):
            errors=[f'{p.name}: {error}' for p,outputs,error in results if error]
            count=sum(len(outputs) for p,outputs,error in results)
            QMessageBox.information(self.window,'Podział PDF',f'Utworzono części: {count}. Błędy: {len(errors)}.\n'+'\n'.join(errors))
        run_job(self.window,'Wsadowe dzielenie PDF',lambda:batch_split(inputs,folder,pages),complete)

    def restore_trash(self):
        from pdfmanager.dms.trash import Trash
        trash=Trash();entries=trash.entries()
        if not entries:self.error('Kosz aplikacji jest pusty.');return
        labels=[f'{source} — {folder.name[:8]}' for folder,source,item in entries]
        label,ok=QInputDialog.getItem(self.window,'Kosz PDFManager','Przywróć plik:',labels,0,False)
        if not ok:return
        folder,source,item=entries[labels.index(label)]
        target=None
        if source.exists():
            name,_=QFileDialog.getSaveFileName(self.window,'Oryginalna nazwa jest zajęta — wybierz nową',str(source))
            if not name:return
            target=Path(name)
        try:trash.restore(folder,target);QMessageBox.information(self.window,'Kosz','Przywrócono plik.')
        except Exception as exc:self.error(exc)
    def favorite(self):
        if not self.active:self.select()
        if self.active:
            from pdfmanager.dms.preferences import Preferences
            Preferences().favorite(self.active)
    def favorites(self):
        from pdfmanager.dms.preferences import Preferences
        entries=Preferences().get('favorites',[])
        if not entries:self.error('Dodaj szafkę do ulubionych.');return
        label,ok=QInputDialog.getItem(self.window,'Ulubione szafki','Szafka:',[e['name'] for e in entries],0,False)
        if ok:
            entry=next(e for e in entries if e['name']==label)
            if not Path(entry['root']).is_dir():self.error('Folder jest niedostępny.');return
            self.active=entry;self.window._folder_tree.set_cabinet_root(entry['root']);self.window._on_folder_selected(entry['root'])
