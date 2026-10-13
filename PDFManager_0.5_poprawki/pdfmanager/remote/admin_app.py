"""Separate owner GUI. Employees receive a complete, already paired package."""
from pathlib import Path
import json
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,QListWidget,QSpinBox,QMessageBox,QFileDialog,QInputDialog,QLabel,QPlainTextEdit,QScrollArea,QGroupBox
from PySide6.QtCore import QStandardPaths,QTimer,Qt
from pdfmanager.remote.admin_backend import AdminWorkspace,serve
from pdfmanager.remote.deployment import automatic_unlock,remember_password,attach_shared_folder,ingest_hellos,prepare_package,SETTINGS
from pdfmanager.ui.background_job import Worker,run_job

class AdminWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('PDFManager — centrum właściciela');self.resize(900,850)
        self.workspace=None;self.server=None;self.password=None;self.config=None;self.poll_worker=None;self.closing=False
        body=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);self.setCentralWidget(scroll);layout=QVBoxLayout(body)
        title=QLabel('PDFManager • dostęp i aktualizacje');title.setStyleSheet('font-size:24px;font-weight:600;color:#225a91;');layout.addWidget(title)
        note=QLabel('Przygotuj firmową paczkę przed przekazaniem programu pracownikom.\nPracownik rozpakowuje cały folder i uruchamia PDFManager.exe.');note.setWordWrap(True);layout.addWidget(note)
        def button(text,slot,target=layout):
            b=QPushButton(text);b.setMinimumHeight(36);b.clicked.connect(lambda:self.perform(slot));target.addWidget(b);return b
        button('1. Połącz z firmowym folderem Google Drive',self.connect_shared)
        button('2. Przygotuj gotową paczkę PDFManager dla pracowników',self.package)
        self.status=QLabel('Klucz prywatny pozostaje na tym komputerze. Dokumenty firmy są poza kanałem połączenia.');self.status.setWordWrap(True);layout.addWidget(self.status)
        layout.addWidget(QLabel('Zgłoszone komputery'));self.devices=QListWidget();self.devices.setMinimumHeight(120);self.devices.setMaximumHeight(180);layout.addWidget(self.devices)
        button('Zmień opis wybranego komputera',self.rename)
        form=QFormLayout();layout.addLayout(form);self.reason=QLineEdit('Wpisz nowy kod dostępu otrzymany od administratora.');form.addRow('Komunikat blokady:',self.reason)
        button('Zablokuj wybrany komputer — pokaż okno kodu',lambda:self.command(True));button('Cofnij zdalną blokadę',lambda:self.command(False))
        self.days=QSpinBox();self.days.setRange(1,3650);self.days.setValue(180);form.addRow('Nowy dostęp (dni):',self.days)
        button('Wystaw jednorazowy kod dla wybranego komputera',self.grant);self.code=QPlainTextEdit();self.code.setMaximumHeight(80);self.code.setReadOnly(True);layout.addWidget(self.code)
        self.version=QLineEdit('0.13.1');form.addRow('Wersja instalatora aktualizacji:',self.version)
        button('Wyślij podpisaną aktualizację EXE',self.update)
        toggle=button('Ustawienia zaawansowane ▾',lambda:self.advanced.setVisible(not self.advanced.isVisible()))
        self.advanced=QGroupBox('Zaawansowane / dotychczasowe połączenie HTTPS');advanced=QVBoxLayout(self.advanced);layout.addWidget(self.advanced);self.advanced.hide()
        extra=QFormLayout();advanced.addLayout(extra)
        self.location=QLineEdit(str(Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'PDFManagerAdmin'));extra.addRow('Prywatny katalog właściciela:',self.location)
        self.url=QLineEdit('https://192.168.1.10:8443');extra.addRow('Opcjonalny adres HTTPS:',self.url)
        button('Odblokuj istniejący klucz hasłem',self.unlock,advanced)
        button('Wybierz ponownie folder połączenia',lambda:self.connect_shared(True),advanced)
        button('Utwórz certyfikat HTTPS dla sieci lokalnej',self.tls,advanced)
        button('Eksportuj publiczną konfigurację HTTPS',self.export,advanced)
        button('Odśwież komputery',self.refresh,advanced);button('Dodaj instalację ręcznie',self.register,advanced)
        self.port=QSpinBox();self.port.setRange(1024,65535);self.port.setValue(8443);extra.addRow('Port serwera HTTPS:',self.port)
        button('Uruchom serwer HTTPS',self.start_server,advanced);button('Zatrzymaj serwer HTTPS',self.stop_server,advanced)
        self.timer=QTimer(self);self.timer.setInterval(5000);self.timer.timeout.connect(self.poll);self.timer.start();QTimer.singleShot(0,self.restore)
    def perform(self,slot):
        try:slot()
        except Exception as exc:QMessageBox.warning(self,'Centrum właściciela',str(exc))
    def require(self):
        if not self.workspace or not self.workspace.key:raise ValueError('Najpierw uruchom połączenie lub odblokuj istniejący klucz.')
        return self.workspace
    def restore(self):
        if self.closing:return
        folder=Path(self.location.text())
        if not (folder/'automatic-key.enc').exists() or not (folder/SETTINGS).exists():return
        try:self.connect_shared()
        except Exception as exc:self.status.setText('Połączenie czeka: '+str(exc))
    def connect_shared(self,choose=False):
        if self.poll_worker and self.poll_worker.isRunning():raise ValueError('Poczekaj na zakończenie odczytu kanału.')
        workspace=self.workspace or AdminWorkspace(self.location.text())
        if not workspace.key:self.password=automatic_unlock(workspace)
        self.workspace=workspace
        parent=None
        if choose or not (workspace.folder/SETTINGS).exists():
            parent=QFileDialog.getExistingDirectory(self,'Wybierz folder Google Drive dostępny pracownikom')
            if not parent:return
        self.config=attach_shared_folder(workspace,parent)
        self.stop_server();self.refresh();self.status.setText('Połączenie przygotowane: '+self.config['folder_hint']+' • Teraz utwórz paczkę dla pracowników.');self.poll()
    def package(self):
        workspace=self.require()
        if not self.config or self.config.get('transport')!='shared_folder':raise ValueError('Najpierw przygotuj połączenie Google Drive.')
        source=QFileDialog.getExistingDirectory(self,'Wybierz cały zbudowany folder dist/PDFManager')
        if not source:return
        destination,_=QFileDialog.getSaveFileName(self,'Gotowa paczka dla pracowników','PDFManager-firmowy.zip','ZIP (*.zip)')
        if not destination:return
        config=self.config.copy();key=workspace.key
        run_job(self,'Przygotowywanie firmowej paczki',lambda:prepare_package(source,destination,config,key),lambda path:self.status.setText('Gotowa paczka: '+str(path)+' • Przekaż pracownikom cały ZIP.'))
    def unlock(self):
        password,ok=QInputDialog.getText(self,'Klucz właściciela','Hasło istniejącego klucza (minimum 12 znaków):',QLineEdit.Password)
        if not ok:return
        workspace=AdminWorkspace(self.location.text());workspace.unlock(password);remember_password(workspace,password);self.workspace=workspace;self.password=password;self.refresh();self.status.setText('Klucz odblokowany i zabezpieczony lokalnie. Nie udostępniaj prywatnego katalogu.')
    def poll(self):
        if self.closing or not self.config or self.config.get('transport')!='shared_folder' or (self.poll_worker and self.poll_worker.isRunning()):return
        workspace=self.workspace;self.poll_worker=Worker(lambda:ingest_hellos(workspace),self)
        self.poll_worker.succeeded.connect(lambda _:self.refresh());self.poll_worker.failed.connect(lambda error:self.status.setText('Kanał połączenia: '+error));self.poll_worker.finished.connect(self.poll_worker.deleteLater);self.poll_worker.finished.connect(lambda:setattr(self,'poll_worker',None));self.poll_worker.start()
    def refresh(self):
        selected=self.devices.currentItem().data(Qt.UserRole) if self.devices.currentItem() else None
        self.devices.clear()
        if self.workspace:
            for device,row in self.workspace.devices().items():
                self.devices.addItem(row['label']+' | '+device+(' | BLOKADA' if row['blocked'] else '')+' | '+row.get('version','brak zgłoszenia'))
                item=self.devices.item(self.devices.count()-1);item.setData(Qt.UserRole,device)
                if device==selected:self.devices.setCurrentItem(item)
    def selected(self):
        if not self.devices.currentItem():raise ValueError('Wybierz komputer.')
        return self.devices.currentItem().data(Qt.UserRole)
    def rename(self):
        workspace=self.require();device=self.selected();label,ok=QInputDialog.getText(self,'Opis komputera','Nazwa pracownika lub stanowiska:')
        if ok:
            with workspace.lock:
                rows=workspace.devices();rows[device]['label']=label.strip()[:100] or device;workspace.save_devices(rows)
            self.refresh()
    def register(self):
        workspace=self.require();device,ok=QInputDialog.getText(self,'Nowa instalacja','Identyfikator instalacji:')
        if not ok:return
        label,ok=QInputDialog.getText(self,'Pracownik / komputer','Opis lokalny:')
        if ok:workspace.register(device,label);self.refresh()
    def command(self,blocked):
        workspace=self.require();device=self.selected()
        if QMessageBox.question(self,'Potwierdź polecenie','Zablokować dostęp?' if blocked else 'Cofnąć blokadę? Nie przedłuża to wygasłego dostępu.')!=QMessageBox.Yes:return
        workspace.command(device,blocked,self.reason.text() if blocked else '');self.refresh();self.status.setText('Polecenie podpisane. Dotarcie zależy od synchronizacji Drive i połączenia komputera pracownika.')
    def grant(self):self.code.setPlainText(self.require().grant(self.selected(),self.days.value()))
    def export(self):
        config=self.require().configuration(self.url.text());path,_=QFileDialog.getSaveFileName(self,'Publiczna konfiguracja HTTPS','management.json','JSON (*.json)')
        if path:Path(path).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');self.status.setText('Wyeksportowano tylko klucz publiczny i adres połączenia.')
    def tls(self):self.require().create_tls(self.url.text(),self.password);self.status.setText('Certyfikat LAN gotowy. Wyeksportuj konfigurację z CA.')
    def update(self):
        workspace=self.require();device=self.selected();path,_=QFileDialog.getOpenFileName(self,'Instalator Inno Setup PDFManager','','Instalator (*.exe)')
        if not path:return
        if QMessageBox.question(self,'Aktualizacja','Podpisać ten instalator do automatycznej instalacji po bezpiecznym zamknięciu PDFManagera? Instalator musi pochodzić z Twojego zaufanego buildu.')!=QMessageBox.Yes:return
        url=self.config['base_url'] if self.config else self.url.text()
        def publish():
            release=workspace.release(path,self.version.text(),url)
            with workspace.lock:return workspace.command(device,workspace.devices()[device]['blocked'],'',release)
        run_job(self,'Publikowanie aktualizacji',publish,lambda _:self.status.setText('Podpisana aktualizacja opublikowana. Przed uruchomieniem klient sprawdzi podpis, SHA-256 i Defendera.'));self.refresh()
    def start_server(self):
        workspace=self.require()
        if self.config and self.config.get('transport')=='shared_folder':raise ValueError('Połączenie Drive nie wymaga serwera HTTPS.')
        if self.server:raise ValueError('Serwer już działa.')
        self.server=serve(workspace,self.port.value(),str(workspace.folder/'tls-server.crt'),str(workspace.folder/'tls-server.key'),self.password);self.status.setText('HTTPS uruchomiony. Adres i zapora wymagają konfiguracji w sieci.')
    def stop_server(self):
        if self.server:self.server.shutdown();self.server.server_close();self.server=None
    def closeEvent(self,event):
        self.closing=True;self.timer.stop()
        # Do not destroy running QThreads, including a package progress dialog.
        running=[w for w in self.findChildren(Worker) if w.isRunning()]
        if running:
            event.ignore()
            for worker in running:
                worker.control.cancelled.set();worker.finished.connect(self.close)
            return
        self.stop_server();super().closeEvent(event)

def main():
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app=QApplication([]);app.setOrganizationName('PDFManagerAdmin');app.setApplicationName('PDFManagerAdmin')
    from pdfmanager.ui.theme import apply_theme
    apply_theme(app,'light');window=AdminWindow();window.show();return app.exec()
if __name__=='__main__':raise SystemExit(main())
