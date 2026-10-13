"""Complete transport workspace with real actions, editable templates and Drive outbox."""
from pdfmanager.i18n.translator import translator
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,QWidget,QPushButton,QLabel,QLineEdit,QTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QListWidget,QFileDialog,QInputDialog,QMessageBox,QColorDialog,QTableWidget,QTableWidgetItem,QAbstractItemView,QScrollArea)
from pdfmanager.dms.transport import Library,filename,render_tokens,create_order,read_checklist,save_checklist,missing_documents
from pdfmanager.dms.preferences import Preferences
from pdfmanager.pdf_engine import transport_ops
from pdfmanager.ui.background_job import run_job
from pdfmanager.drive.teamwork import TeamDrive,Outbox

def button(layout,text,slot):
    b=QPushButton(text);b.clicked.connect(slot)
    if text.startswith(('Wstaw na','Utwórz','Zapisz','Wyślij')):b.setObjectName('TransportPrimary')
    layout.addWidget(b);return b

def field(form,label,widget):form.addRow(label,widget);return widget

class TransportCenter(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle(translator.text('PDFManager — centrum spedycji'));self.resize(1080,780)
        self.setStyleSheet("""
            QDialog { background: #f2f6fa; }
            QLabel { color: #334155; }
            QLabel#TransportHeading { color: #125b6b; font-size: 19px; font-weight: 600; padding: 8px 0; }
            QTabWidget::pane { border: 1px solid #d4dde8; background: white; border-radius: 6px; }
            QTabBar::tab { background: #e8eef5; padding: 10px 16px; color: #334155; border: 0; }
            QTabBar::tab:selected { background: #176c79; color: white; font-weight: 600; }
            QScrollArea { border: 0; background: white; }
            QScrollArea > QWidget > QWidget { background: white; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QListWidget, QTableWidget { background: white; color: #1e293b; border: 1px solid #d4dde8; border-radius: 4px; padding: 4px; }
            QPushButton { background: #f7f9fc; color: #334155; border: 1px solid #cbd5e1; border-radius: 5px; padding: 8px 12px; }
            QPushButton:hover { border-color: #176c79; background: #e7f4f5; }
            QPushButton#TransportPrimary { color: white; background: #176c79; border-color: #176c79; }
            QPushButton#TransportPrimary:hover { background: #125b6b; }
        """)
        self.library=Library();self.data=self.library.read();self.folder=None;self.checkdata=None;self.temp=TemporaryDirectory(prefix='pdfmanager-transport-')
        root=QVBoxLayout(self);heading=QLabel('Centrum spedycji');heading.setObjectName('TransportHeading');root.addWidget(heading);root.addWidget(QLabel('Dokumenty transportowe • szablony • praca zespołowa'))
        self.tabs=QTabWidget();root.addWidget(self.tabs)
        self._library_page();self._order_page();self._batch_page();self._drive_page();self._quick_page()
        button(root,'Zamknij',self.accept)
    def page(self,name):
        w=QWidget();layout=QVBoxLayout(w);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame);scroll.setWidget(w);self.tabs.addTab(scroll,name);return layout
    def error(self,error):QMessageBox.warning(self,translator.text('Centrum spedycji'),str(error))
    def viewer(self):
        v=self.window._current_viewer()
        if not v or not v.is_loaded:raise ValueError('Najpierw otwórz dokument PDF.')
        return v
    def _library_page(self):
        layout=self.page('Stemple i teksty');form=QFormLayout();layout.addLayout(form)
        self.employee=field(form,'Pracownik:',QLineEdit(Preferences().get('transport_employee','')))
        self.order=field(form,'Numer zlecenia:',QLineEdit());self.contractor=field(form,'Kontrahent:',QLineEdit())
        self.profile=field(form,'Profil dokumentu:',QComboBox());self.profile.setProperty('i18nSkip',True);self.profile.addItems(self.data['profiles']);self.profile.currentTextChanged.connect(self.load_profile)
        self.kind=field(form,'Biblioteka:',QComboBox());self.kind.addItems(['Stemple','Bloki tekstu'])
        self.entry=field(form,'Wzór:',QComboBox());self.entry.setProperty('i18nSkip',True);self.kind.currentIndexChanged.connect(self.refresh_entries);self.entry.currentTextChanged.connect(self.load_entry)
        self.text=QTextEdit();layout.addWidget(self.text)
        layout.addWidget(QLabel('Pola automatyczne: {data}, {godzina}, {pracownik}, {zlecenie}, {kontrahent}.'))
        row=QHBoxLayout();layout.addLayout(row)
        button(row,'Wstaw obraz / logo',self.insert_image);button(row,'Nowy wzór',self.add_entry);button(row,'Zapisz wzór',self.save_entry);button(row,'Usuń wzór',self.delete_entry)
        positions=QFormLayout();layout.addLayout(positions)
        self.x=field(positions,'Pozycja X (punkty PDF):',QDoubleSpinBox());self.y=field(positions,'Pozycja Y:',QDoubleSpinBox())
        self.width=field(positions,'Szerokość:',QDoubleSpinBox());self.height=field(positions,'Wysokość:',QDoubleSpinBox())
        for w in (self.x,self.y,self.width,self.height):w.setRange(0,10000)
        self.size=field(positions,'Rozmiar czcionki:',QSpinBox());self.size.setRange(5,72)
        self.color='#176c79';self.fontfile='';row=QHBoxLayout();layout.addLayout(row)
        self.colorbutton=button(row,'Kolor tekstu',self.choose_color);self.fontbutton=button(row,'Czcionka Unicode / wybierz TTF',self.choose_font)
        self.border=QCheckBox('Ramka stempla');self.border.setChecked(True);row.addWidget(self.border)
        self.metadata=QCheckBox('Dodaj datę, godzinę i pracownika');self.metadata.setChecked(True);layout.addWidget(self.metadata)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Zapisz profil pozycji',self.save_profile);button(row,'Nowy profil',self.new_profile)
        button(row,'Podgląd na bieżącej stronie',self.preview_mark);button(row,'Wstaw na bieżącej stronie',self.apply_mark)
        self.load_profile(self.profile.currentText());self.refresh_entries()
    def insert_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Obraz pieczątki lub logo','','Obrazy (*.png *.jpg *.jpeg)')
        if not path:return
        try:
            v=self.viewer();v.stamp_image_path=Path(path);v.set_active_tool('stamp');self.accept();self.window._shell.tabs.setCurrentIndex(3)
        except Exception as exc:self.error(exc)
    def choose_color(self):
        color=QColorDialog.getColor(QColor(self.color),self)
        if color.isValid():self.color=color.name();self.colorbutton.setText('Kolor '+self.color)
    def choose_font(self):
        path,_=QFileDialog.getOpenFileName(self,'Czcionka z obsługą polskich znaków','','Czcionki (*.ttf *.otf)')
        if path:self.fontfile=path;self.fontbutton.setText(Path(path).name)
    def load_profile(self,name):
        if not hasattr(self,'x'):return
        data=self.data['profiles'].get(name,{})
        for key,w in [('x',self.x),('y',self.y),('width',self.width),('height',self.height),('size',self.size)]:w.setValue(data.get(key,12 if key=='size' else 24))
        self.color=data.get('color','#176c79');self.fontfile=data.get('fontfile','')
    def options(self):return {'x':self.x.value(),'y':self.y.value(),'width':self.width.value(),'height':self.height.value(),'size':self.size.value(),'color':self.color,'fontfile':self.fontfile,'border':self.border.isChecked()}
    def save_profile(self):
        self.data['profiles'][self.profile.currentText()]=self.options();self.library.save(self.data)
    def new_profile(self):
        name,ok=QInputDialog.getText(self,'Profil',translator.text('Nazwa:'))
        if ok and name.strip():self.data['profiles'][name.strip()]=self.options();self.library.save(self.data);self.profile.addItem(name.strip());self.profile.setCurrentText(name.strip())
    def refresh_entries(self):
        self.entry.clear();self.entry.addItems(self.data['stamps'] if self.kind.currentIndex()==0 else self.data['snippets'])
        self.load_entry(self.entry.currentText())
    def load_entry(self,name):self.text.setPlainText(name if self.kind.currentIndex()==0 else self.data['snippets'].get(name,''))
    def save_entry(self):
        value=self.text.toPlainText().strip();name=self.entry.currentText()
        if not value:return
        if self.kind.currentIndex()==0:
            if name in self.data['stamps']:self.data['stamps'][self.data['stamps'].index(name)]=value
            elif value not in self.data['stamps']:self.data['stamps'].append(value)
        else:self.data['snippets'][name or value[:40]]=value
        self.library.save(self.data);self.refresh_entries()
    def add_entry(self):
        name,ok=QInputDialog.getText(self,translator.text('Nowy wzór'),'Nazwa / tekst stempla:')
        if ok and name.strip():
            if self.kind.currentIndex()==0:self.data['stamps'].append(name.strip())
            else:self.data['snippets'][name.strip()]=name.strip()
            self.library.save(self.data);self.refresh_entries();self.entry.setCurrentText(name.strip())
    def delete_entry(self):
        name=self.entry.currentText()
        if not name:return
        if self.kind.currentIndex()==0:self.data['stamps'].remove(name)
        else:self.data['snippets'].pop(name,None)
        self.library.save(self.data);self.refresh_entries()
    def resolved_text(self):
        Preferences().put('transport_employee',self.employee.text().strip())
        text=render_tokens(self.text.toPlainText(),self.order.text(),self.contractor.text(),self.employee.text())
        if self.metadata.isChecked():text+='\n'+render_tokens('{data} {godzina} • {pracownik}',employee=self.employee.text())
        return text
    def preview_mark(self):
        try:
            v=self.viewer();path=Path(self.temp.name)/'preview.pdf';transport_ops.mark(v.path,path,self.resolved_text(),self.options(),[v.current_page])
            from pdfmanager.ui.viewer import PdfViewerWidget
            d=QDialog(self);d.setWindowTitle('Podgląd — dokument nie został zmieniony');d.resize(750,800);layout=QVBoxLayout(d);viewer=PdfViewerWidget(str(path),d);layout.addWidget(viewer);QTimer.singleShot(300,lambda:viewer.go_to_page(v.current_page));d.exec();viewer.release_document()
        except Exception as exc:self.error(exc)
    def apply_mark(self):
        try:
            v=self.viewer();text=self.resolved_text();options=self.options();v._mutate_file(lambda:transport_ops.mark(v.path,v.path,text,options,[v.current_page]));self.window.statusBar().showMessage('Wstawiono element. Dostępne Cofnij; zapisz dokument.',4000)
        except Exception as exc:self.error(exc)
    def _order_page(self):
        layout=self.page('Teczki zleceń');form=QFormLayout();layout.addLayout(form)
        self.order_root=field(form,'Katalog zleceń:',QLineEdit());button(layout,'Wybierz katalog',lambda:self.choose_directory(self.order_root))
        self.project_order=field(form,'Numer zlecenia:',QLineEdit());self.project_client=field(form,'Kontrahent:',QLineEdit());button(layout,'Utwórz teczkę ze strukturą folderów',self.new_order)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Otwórz teczkę zlecenia',self.open_order);button(row,'Ostatnie foldery',self.recent_folder)
        self.project_label=QLabel('Wybierz teczkę zlecenia.');layout.addWidget(self.project_label);self.checks={}
        for name in ('Podpisany CMR','POD','Faktura'):
            row=QHBoxLayout();layout.addLayout(row);box=QCheckBox(name+' — sprawdzono');self.checks[name]=box;row.addWidget(box);button(row,'Dołącz dokument',lambda checked=False,n=name:self.attach_order(n))
        button(layout,'Zapisz listę kontrolną',self.save_order);self.missing=QLabel('');layout.addWidget(self.missing)
        button(layout,'Sprawdź braki we wszystkich teczkach',self.check_orders)
        self.naming=QComboBox();self.naming.setProperty("i18nSkip",True);self.naming.addItems(['CMR','POD','Zlecenie','Faktura']);form.addRow('Typ dokumentu do nazwy:',self.naming)
        button(layout,'Podpowiedz dane z tekstu / OCR',self.suggest_data);button(layout,'Zapisz bieżący PDF z automatyczną nazwą',self.named_copy);layout.addStretch()
    def choose_directory(self,edit):
        value=QFileDialog.getExistingDirectory(self,'Katalog',edit.text())
        if value:edit.setText(value);Preferences().recent(value)
    def new_order(self):
        try:self.folder=create_order(self.order_root.text(),self.project_order.text(),self.project_client.text());self.load_order()
        except Exception as exc:self.error(exc)
    def open_order(self):
        path=QFileDialog.getExistingDirectory(self,'Teczka zlecenia',self.order_root.text())
        if path:self.folder=Path(path);self.load_order()
    def recent_folder(self):
        items=Preferences().get('recent',[])
        if not items:return
        path,ok=QInputDialog.getItem(self,translator.text('Ostatnie foldery'),'Wybierz:',items,0,False)
        if ok:self.order_root.setText(path)
    def load_order(self):
        try:
            self.checkdata=read_checklist(self.folder);self.project_label.setText(str(self.folder));self.project_order.setText(self.checkdata['order']);self.project_client.setText(self.checkdata['contractor']);Preferences().recent(self.folder)
            for name,box in self.checks.items():box.setChecked(bool(self.checkdata.get('checks',{}).get(name)))
            self.missing.setText('Brakuje: '+', '.join(missing_documents(self.folder)))
        except Exception as exc:self.checkdata=None;self.error(exc)
    def attach_order(self,name):
        if not self.folder or not self.checkdata:self.error('Wybierz teczkę.');return
        path,_=QFileDialog.getOpenFileName(self,'Dokument PDF','','PDF (*.pdf)')
        if not path:return
        from pdfmanager.pdf_engine.io_utils import atomic_copy_file
        try:
            sub={'Podpisany CMR':'02 CMR','POD':'03 POD','Faktura':'04 Faktury'}[name];target=self.folder/sub/Path(path).name
            if target.exists():raise FileExistsError('Dokument już istnieje. Zmień nazwę przed dołączeniem.')
            atomic_copy_file(path,target);self.checkdata.setdefault('documents',{})[name]=str(target.relative_to(self.folder));self.save_order()
        except Exception as exc:self.error(exc)
    def save_order(self):
        if not self.folder or not self.checkdata:return
        try:
            self.checkdata['checks']={n:b.isChecked() for n,b in self.checks.items()};save_checklist(self.folder,self.checkdata);self.missing.setText('Brakuje: '+(', '.join(missing_documents(self.folder)) or 'brak — komplet sprawdzony'))
        except Exception as exc:self.error(exc)
    def check_orders(self):
        try:
            root=Path(self.order_root.text());results=[]
            for folder in sorted(root.iterdir()):
                if folder.is_dir() and (folder/'zlecenie.pdfmanager.json').is_file():results.append(folder.name+': '+(', '.join(missing_documents(folder)) or 'komplet'))
            QMessageBox.information(self,'Brakujące dokumenty','\n'.join(results[:1000]) or 'Brak teczek.')
        except Exception as exc:self.error(exc)
    def suggest_data(self):
        import re
        try:v=self.viewer()
        except Exception as exc:self.error(exc);return
        source=v.path;result=Path(self.temp.name)/'ocr_suggestion.pdf'
        def collect():
            from pdfmanager.pdf_engine.render import PdfDocument
            from pdfmanager.security.isolation import call
            text='\n'.join(call('document.texts',source))
            if not text.strip():
                from pdfmanager.pdf_engine.workflows import ocr_document
                ocr_document(source,result,language='pol+eng')
                text='\n'.join(call('document.texts',result))
            match=re.search(r'(?:zlecenie|order|ZL)[\s:#-]*(?:nr[.:]?\s*)?([A-Z0-9][A-Z0-9/._-]{2,40})',text,re.IGNORECASE)
            return match.group(1) if match else ''
        def apply(value):
            if value:self.project_order.setText(value);self.order.setText(value)
            QMessageBox.information(self,'Podpowiedź OCR',('Numer zlecenia: '+value+'. Sprawdź poprawność przed zapisem.') if value else 'Nie znaleziono pewnego numeru zlecenia. Wpisz dane ręcznie.')
        run_job(self,'Podpowiadanie numeru zlecenia',collect,apply)
    def named_copy(self):
        try:
            v=self.viewer();name=filename(self.project_order.text(),self.naming.currentText(),self.project_client.text());folder=QFileDialog.getExistingDirectory(self,'Folder zapisu',str(self.folder or ''))
            if not folder:return
            target=Path(folder)/name
            if target.exists():raise FileExistsError('Plik istnieje; nie został nadpisany.')
            from pdfmanager.pdf_engine.io_utils import atomic_copy_file
            atomic_copy_file(v.path,target);Preferences().recent(folder);QMessageBox.information(self,'Zapis','Zapisano lokalną kopię: '+str(target))
        except Exception as exc:self.error(exc)
    def _batch_page(self):
        layout=self.page('Pakiety i operacje zbiorcze');self.files=QListWidget();self.files.setDragDropMode(QAbstractItemView.InternalMove);self.files.setSelectionMode(QAbstractItemView.ExtendedSelection);layout.addWidget(self.files)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Dodaj PDF-y',self.add_files);button(row,'Usuń z listy',self.remove_files);button(row,'Wyczyść',self.files.clear)
        layout.addWidget(QLabel('Przeciągnij wiersze, aby ustawić kolejność stron pakietu. Źródła pozostają bez zmian.'))
        self.package_title=QLineEdit('Pakiet dokumentów transportowych');layout.addWidget(self.package_title)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Utwórz pakiet z okładką i numeracją',self.build_package);button(row,'Porównaj dwa pierwsze pliki',self.compare_files)
        self.batch_kind=QComboBox();self.batch_kind.addItems(['Stempel / tekst z biblioteki','Numeracja stron','Obrót 90°','Obrót 180°','Obrót 270°','Kompresja bez rasteryzacji','Kopie z automatycznymi nazwami']);layout.addWidget(self.batch_kind)
        button(layout,'Przetwórz listę do nowego folderu',self.batch_files)
        button(layout,'Trwale usuń poufne dane w bieżącym PDF',self.redact)
        layout.addWidget(QLabel('Redakcja usuwa treść; po jej wykonaniu sprawdź eksport tekstu i podgląd dokumentu.'))
    def paths(self):return [Path(self.files.item(i).text()) for i in range(self.files.count())]
    def add_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'Dokumenty do pakietu','','PDF (*.pdf)');existing={str(p) for p in self.paths()};self.files.addItems([p for p in files if p not in existing])
    def remove_files(self):
        for item in self.files.selectedItems():self.files.takeItem(self.files.row(item))
    def build_package(self):
        output,_=QFileDialog.getSaveFileName(self,'Nowy pakiet','','PDF (*.pdf)')
        if not output:return
        output=Path(output).with_suffix('.pdf')
        if output.exists():self.error('Wybierz nową nazwę; pakiet nie nadpisuje plików.');return
        paths=self.paths();title=self.package_title.text();run_job(self,'Tworzenie pakietu',lambda:transport_ops.package(paths,output,title),lambda _:self.window.open_document(str(output)))
    def compare_files(self):
        paths=self.paths()
        if len(paths)<2:self.error('Dodaj dwie wersje dokumentu.');return
        output,_=QFileDialog.getSaveFileName(self,'Raport różnic','','PDF (*.pdf)')
        if not output:return
        output=Path(output).with_suffix('.pdf')
        if output.exists():self.error('Wybierz nową nazwę.');return
        run_job(self,'Porównanie z zaznaczeniem różnic',lambda:transport_ops.comparison_pdf(paths[0],paths[1],output),lambda _:self.window.open_document(str(output)))
    def batch_files(self):
        import tempfile
        from pdfmanager.dms.jobs import checkpoint
        from pdfmanager.pdf_engine.io_utils import atomic_copy_file
        parent=QFileDialog.getExistingDirectory(self,'Katalog wyników')
        if not parent:return
        paths=self.paths();kind=self.batch_kind.currentIndex();text=self.resolved_text();options=self.options();order=self.order.text();client=self.contractor.text();doc_type=self.profile.currentText()
        def process():
            target=Path(tempfile.mkdtemp(prefix='PDFManager_wyniki_',dir=parent));results=[]
            for i,path in enumerate(paths):
                checkpoint(i,len(paths),'Przetwarzanie '+path.name)
                name=filename(order,doc_type,client) if kind==6 else path.name
                output=target/f'{i+1:03d}_{name}'
                try:
                    if kind==0:transport_ops.mark(path,output,text,options)
                    elif kind==6:atomic_copy_file(path,output)
                    else:transport_ops.batch_transform(path,output,rotation={2:90,3:180,4:270}.get(kind,0),compress=kind==5,number=kind==1)
                    results.append(path.name+': OK')
                except Exception as exc:results.append(path.name+': '+str(exc))
            return str(target)+'\n'+'\n'.join(results)
        run_job(self,'Operacje zbiorcze',process,lambda result:QMessageBox.information(self,'Raport operacji',result))
    def redact(self):
        if QMessageBox.question(self,'Trwała redakcja','Usunąć treść zaznaczonego obszaru? Oryginał i starsze kopie nadal mogą zawierać dane. Zapisz i udostępniaj wyłącznie sprawdzony wynik.')!=QMessageBox.Yes:return
        self.accept();self.window._activate_extended_tool('redact');self.window._shell.tabs.setCurrentIndex(3)
    def _drive_page(self):
        layout=self.page('Google Drive — zespół');layout.addWidget(QLabel('Bezpieczne wersje są osobnymi plikami. Oryginał nie jest nadpisywany.\nRezerwacje są ostrzeżeniem dla PDFManagera; inne programy mogą je ominąć.'))
        row=QHBoxLayout();layout.addLayout(row);button(row,'Zarezerwuj / odnów na 15 minut',self.reserve);button(row,'Zwolnij rezerwację',self.release);button(row,'Sprawdź, kto edytuje',self.show_reservation)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Dodaj bieżący PDF do kolejki',self.enqueue);button(row,'Wyślij / ponów kolejkę',self.send_queue);button(row,'Odśwież',self.refresh_queue)
        self.queue=QTableWidget(0,4);self.queue.setHorizontalHeaderLabels(['Dokument','Stan zapisu','Pracownik','Błąd / informacja']);self.queue.setSelectionBehavior(QAbstractItemView.SelectRows);self.queue.setEditTriggers(QAbstractItemView.NoEditTriggers);layout.addWidget(self.queue)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Zachowaj lokalną kopię wpisu',self.recover_queue);button(row,'Usuń wybrany wpis',self.remove_queue)
        row=QHBoxLayout();layout.addLayout(row);button(row,'Historia wersji PDFManagera',self.version_history);button(row,'Historia zmian oryginału Drive',self.revision_history)
        self.automatic=QCheckBox('Automatycznie ponawiaj kolejkę co minutę przy otwartym dokumencie Drive');self.automatic.setChecked(Preferences().get('transport_auto_send',True));layout.addWidget(self.automatic)
        self.automatic.toggled.connect(lambda value:Preferences().put('transport_auto_send',value));self.timer=QTimer(self);self.timer.setInterval(60000);self.timer.timeout.connect(self.auto_send);self.sending=False;self.refresh_queue()
    def drive(self):
        v=self.viewer();info=getattr(v,'drive_info',None)
        if not info:raise ValueError('Otwórz dokument przez połączenie Google Drive API, nie tylko folder synchronizowany.')
        return v,info,TeamDrive(info.client)
    def account(self,team):
        cached=getattr(team.client,'_team_account_id','')
        if isinstance(cached,str) and cached:return cached
        data=team.service.about().get(fields='user(permissionId)').execute()
        value=data.get('user',{}).get('permissionId')
        if not value:raise ValueError('Nie można potwierdzić konta Google.')
        team.client._team_account_id=value
        return value
    def token(self):
        import secrets
        if not hasattr(self.window,'_transport_lease_token'):self.window._transport_lease_token=secrets.token_hex(4)
        return self.window._transport_lease_token
    def reserve(self):
        try:
            _,info,team=self.drive();owner=self.employee.text().strip()
            if not owner:raise ValueError('Podaj pracownika w zakładce Stemple i teksty.')
            lease=team.reserve(info.file_id,owner,self.token());self.window._transport_leases[info.file_id]=(team,owner,self.token());QMessageBox.information(self,'Rezerwacja','Zarezerwowano do '+lease['until'])
        except Exception as exc:self.error(exc)
    def release(self):
        try:_,info,team=self.drive();team.release(info.file_id,self.token());self.window._transport_leases.pop(info.file_id,None);QMessageBox.information(self,'Rezerwacja','Zwolniono własną rezerwację, jeśli nadal była aktywna.')
        except Exception as exc:self.error(exc)
    def show_reservation(self):
        try:_,info,team=self.drive();item=team.reservation(info.file_id);QMessageBox.information(self,'Rezerwacja',str(item or 'Brak aktywnej rezerwacji.'))
        except Exception as exc:self.error(exc)
    def enqueue(self):
        try:
            v,info,team=self.drive();Outbox().enqueue(v.path,info.baseline,self.employee.text().strip(),self.account(team));self.window.statusBar().showMessage('Zapisano zaszyfrowaną kopię lokalną. Oczekuje na wysłanie do Google Drive.',6000);self.refresh_queue()
        except Exception as exc:self.error(exc)
    def send_queue(self):
        if self.sending:return
        try:_,_,team=self.drive();account=self.account(team)
        except Exception as exc:self.error(exc);return
        self.sending=True
        try:run_job(self,'Wysyłanie bez nadpisywania oryginałów',lambda:Outbox().process(team,account),lambda _:self.refresh_queue())
        finally:self.sending=False
    def auto_send(self):
        if self.automatic.isChecked() and self.isVisible() and not self.sending:self.send_queue()
    def refresh_queue(self):
        try:
            self.queue_items=Outbox().items();self.queue.setRowCount(len(self.queue_items))
            for i,item in enumerate(self.queue_items):
                for j,text in enumerate([item['baseline']['name'],item['state'],item['owner'],item.get('error','')]):self.queue.setItem(i,j,QTableWidgetItem(text))
            self.queue.resizeColumnsToContents()
        except Exception as exc:self.error(exc)
    def selected_queue(self):
        row=self.queue.currentRow()
        if row<0:raise ValueError('Wybierz wpis kolejki.')
        return self.queue_items[row]
    def recover_queue(self):
        try:
            item=self.selected_queue();path,_=QFileDialog.getSaveFileName(self,'Kopia do porównania / nowego wysłania',item['baseline']['name'],'PDF (*.pdf)')
            if path:Outbox().recover(item['job'],Path(path).with_suffix('.pdf'))
        except Exception as exc:self.error(exc)
    def remove_queue(self):
        try:
            item=self.selected_queue()
            if QMessageBox.question(self,'Usuń wpis','Usunąć lokalny wpis i zaszyfrowaną kopię? Nie usuwa to wersji z Google Drive.')==QMessageBox.Yes:Outbox().remove(item['job']);self.refresh_queue()
        except Exception as exc:self.error(exc)
    def version_history(self):
        try:
            _,info,team=self.drive();entries=team.versions(info.file_id)
            if not entries:raise ValueError('Brak wersji utworzonych przez PDFManager.')
            labels=[e['name']+' — '+e.get('appProperties',{}).get('pdfmanagerOwner','')+' — '+e.get('modifiedTime','') for e in entries]
            label,ok=QInputDialog.getItem(self,'Historia — pobierz wcześniejszą wersję','Wersja:',labels,0,False)
            if not ok:return
            entry=entries[labels.index(label)];path,_=QFileDialog.getSaveFileName(self,'Pobierz wersję jako nowy plik',entry['name'],'PDF (*.pdf)')
            if not path:return
            target=Path(path).with_suffix('.pdf')
            if target.exists():raise FileExistsError('Wybierz nową nazwę.')
            run_job(self,'Pobieranie wcześniejszej wersji',lambda:team.client.download(entry['id'],target),lambda _:self.window.open_document(str(target)))
        except Exception as exc:self.error(exc)
    def revision_history(self):
        try:
            _,info,team=self.drive();entries=team.revisions(info.file_id)
            if not entries:raise ValueError('Brak dostępnych rewizji oryginału.')
            labels=[e['id']+' — '+e.get('modifiedTime','')+' — '+e.get('lastModifyingUser',{}).get('displayName','') for e in entries]
            label,ok=QInputDialog.getItem(self,'Rewizje Drive — dostępność zależy od retencji Google','Pobierz:',labels,0,False)
            if not ok:return
            entry=entries[labels.index(label)];path,_=QFileDialog.getSaveFileName(self,'Przywróć jako nową lokalną kopię','','PDF (*.pdf)')
            if not path:return
            target=Path(path).with_suffix('.pdf')
            if target.exists():raise FileExistsError('Wybierz nową nazwę.')
            run_job(self,'Pobieranie rewizji',lambda:team.download_revision(info.file_id,entry['id'],target),lambda _:self.window.open_document(str(target)))
        except Exception as exc:self.error(exc)
    def _quick_page(self):
        layout=self.page('Ulubione i skróty');layout.addWidget(QLabel('Ctrl+Shift+T — centrum spedycji\nCtrl+Alt+N — zapisz i otwórz następny PDF w tym folderze\nCtrl+S — zapis; dokumenty API Drive trafiają do bezpiecznej kolejki.'))
        self.favorite_actions=QListWidget();self.favorite_actions.setSelectionMode(QAbstractItemView.MultiSelection)
        stored=Preferences().get('transport_quick_actions',['transport_center','save_next'])
        self.action_choices=[('transport_center','Centrum spedycji'),('save_next','Zapisz i następny'),('transport_send','Wyślij kolejkę'),('transport_queue','Dodaj do kolejki')]
        for key,label in self.action_choices:
            self.favorite_actions.addItem(label)
            if key in stored:self.favorite_actions.item(self.favorite_actions.count()-1).setSelected(True)
        layout.addWidget(self.favorite_actions);button(layout,'Zapisz ulubione narzędzia na pasku',self.save_favorites)
        button(layout,'Otwórz ostatni folder',self.open_recent);layout.addStretch()
    def save_favorites(self):
        keys=[key for i,(key,_) in enumerate(self.action_choices) if self.favorite_actions.item(i).isSelected()];Preferences().put('transport_quick_actions',keys);self.window._refresh_transport_quick()
    def open_recent(self):
        paths=Preferences().get('recent',[])
        if not paths:return
        path,ok=QInputDialog.getItem(self,translator.text('Ostatnie foldery'),translator.text('Folder:'),paths,0,False)
        if ok:self.window._on_folder_selected(path);self.accept()
