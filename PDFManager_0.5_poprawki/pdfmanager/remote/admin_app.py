"""Operator GUI; run python -m pdfmanager.remote.admin_app on owner's computer."""
from pathlib import Path
import json
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,QListWidget,QSpinBox,QMessageBox,QFileDialog,QInputDialog,QLabel,QPlainTextEdit,QScrollArea
from PySide6.QtCore import QStandardPaths
from pdfmanager.remote.admin_backend import AdminWorkspace,serve

class AdminWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('PDFManager Administrator — dostęp i aktualizacje');self.resize(900,780);self.workspace=None;self.server=None;self.password=None
        body=QWidget();scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(body);self.setCentralWidget(scroll);layout=QVBoxLayout(body);layout.addWidget(QLabel('Panel administratora PDFManager • podpisane polecenia'))
        form=QFormLayout();layout.addLayout(form);self.url=QLineEdit('https://192.168.1.10:8443');form.addRow('Adres HTTPS widoczny dla pracowników:',self.url)
        self.location=QLineEdit(str(Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'PDFManagerAdmin'));form.addRow('Prywatny katalog administratora:',self.location)
        def button(text,slot):b=QPushButton(text);b.clicked.connect(lambda:self.perform(slot));layout.addWidget(b)
        button('Utwórz / odblokuj klucz administratora',self.unlock)
        button('Utwórz certyfikat HTTPS dla sieci lokalnej',self.tls)
        button('Eksportuj konfigurację do wbudowania w PDFManager',self.export)
        self.devices=QListWidget();layout.addWidget(self.devices);button('Odśwież zgłoszone instalacje',self.refresh);button('Dodaj instalację ręcznie',self.register)
        self.reason=QLineEdit('Wpisz nowy kod dostępu otrzymany od administratora.');form.addRow('Komunikat blokady:',self.reason)
        button('Zablokuj wybraną instalację — pokaż okno kodu',lambda:self.command(True));button('Cofnij zdalną blokadę',lambda:self.command(False))
        self.days=QSpinBox();self.days.setRange(1,3650);self.days.setValue(180);form.addRow('Ważność nowego dostępu (dni):',self.days)
        button('Wystaw jednorazowy kod dla wybranej instalacji',self.grant);self.code=QPlainTextEdit();self.code.setMaximumHeight(110);self.code.setReadOnly(True);layout.addWidget(self.code)
        self.version=QLineEdit('0.8.1');form.addRow('Wersja publikowanego instalatora:',self.version)
        button('Opublikuj aktualizację EXE dla wybranej instalacji',self.update)
        self.port=QSpinBox();self.port.setRange(1024,65535);self.port.setValue(8443);form.addRow('Port serwera HTTPS:',self.port)
        button('Uruchom serwer HTTPS',self.start_server);button('Zatrzymaj serwer',self.stop_server);self.status=QLabel('Klucz prywatny pozostaje wyłącznie na komputerze administratora.');layout.addWidget(self.status)
    def perform(self,slot):
        try:slot()
        except Exception as exc:QMessageBox.warning(self,'Administrator',str(exc))
    def require(self):
        if not self.workspace or not self.workspace.key:raise ValueError('Odblokuj klucz administratora.')
        return self.workspace
    def unlock(self):
        password,ok=QInputDialog.getText(self,'Klucz administratora','Hasło szyfrujące klucz (co najmniej 12 znaków):',QLineEdit.Password)
        if not ok:return
        workspace=AdminWorkspace(self.location.text());workspace.unlock(password);self.workspace=workspace;self.password=password;self.refresh();self.status.setText('Klucz odblokowany. Nie udostępniaj katalogu prywatnego ani hasła.')
    def refresh(self):
        self.devices.clear()
        if self.workspace:
            for device,row in self.workspace.devices().items():self.devices.addItem(row['label']+' | '+device+(' | BLOKADA' if row['blocked'] else '')+' | '+row.get('version','brak zgłoszenia'))
    def selected(self):
        if not self.devices.currentItem():raise ValueError('Wybierz instalację.')
        return self.devices.currentItem().text().split(' | ')[1]
    def register(self):
        workspace=self.require();device,ok=QInputDialog.getText(self,'Nowa instalacja','Identyfikator instalacji:')
        if not ok:return
        label,ok=QInputDialog.getText(self,'Pracownik / komputer','Opis lokalny:')
        if ok:workspace.register(device,label);self.refresh()
    def command(self,blocked):
        workspace=self.require();device=self.selected()
        if QMessageBox.question(self,'Potwierdź polecenie','Zablokować dostęp?' if blocked else 'Cofnąć zdalną blokadę? Nie przedłuża to wygasłej licencji.')!=QMessageBox.Yes:return
        workspace.command(device,blocked,self.reason.text() if blocked else '');self.refresh();self.status.setText('Podpisane polecenie gotowe. Klient pobierze je przy działającym połączeniu.')
    def grant(self):self.code.setPlainText(self.require().grant(self.selected(),self.days.value()))
    def export(self):
        config=self.require().configuration(self.url.text());path,_=QFileDialog.getSaveFileName(self,'Publiczna konfiguracja administratora','management.json','JSON (*.json)')
        if path:Path(path).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');self.status.setText('Wyeksportowano tylko klucz publiczny i adres połączenia.')
    def tls(self):self.require().create_tls(self.url.text(),self.password);self.status.setText('Utworzono certyfikat LAN. Wyeksportuj ponownie publiczną konfigurację z CA.')
    def update(self):
        workspace=self.require();device=self.selected();path,_=QFileDialog.getOpenFileName(self,'Instalator Inno Setup PDFManager','','Instalator (*.exe)')
        if not path:return
        release=workspace.release(path,self.version.text(),self.url.text())
        if QMessageBox.question(self,'Publikacja aktualizacji','Podpisać ten instalator do automatycznego zainstalowania po bezpiecznym zamknięciu PDFManagera?')!=QMessageBox.Yes:return
        workspace.command(device,workspace.devices()[device]['blocked'],'',release);self.refresh();self.status.setText('Podpisany instalator opublikowany. Oryginalne dokumenty nie są częścią aktualizacji.')
    def start_server(self):
        workspace=self.require()
        if self.server:raise ValueError('Serwer już działa.')
        self.server=serve(workspace,self.port.value(),str(workspace.folder/'tls-server.crt'),str(workspace.folder/'tls-server.key'),self.password);self.status.setText('Serwer HTTPS działa. Dostępność adresu i zaporę trzeba skonfigurować w sieci.')
    def stop_server(self):
        if self.server:self.server.shutdown();self.server.server_close();self.server=None;self.status.setText('Serwer zatrzymany.')
    def closeEvent(self,event):self.stop_server();super().closeEvent(event)

def main():
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import Qt
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app=QApplication([]);app.setOrganizationName('PDFManagerAdmin');app.setApplicationName('PDFManagerAdmin')
    from pdfmanager.ui.theme import apply_theme
    apply_theme(app,'light');window=AdminWindow();window.show();return app.exec()
if __name__=='__main__':raise SystemExit(main())
