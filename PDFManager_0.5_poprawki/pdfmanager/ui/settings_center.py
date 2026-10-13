from pdfmanager.i18n.translator import translator
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import QDialog,QHBoxLayout,QVBoxLayout,QListWidget,QStackedWidget,QWidget,QFormLayout,QComboBox,QCheckBox,QSpinBox,QLineEdit,QDialogButtonBox,QLabel,QPushButton,QFileDialog
from pdfmanager.dms.preferences import Preferences
from pdfmanager.app_settings import settings
from .theme import apply_theme
from pdfmanager.i18n.bindings import current_source

class SettingsCenter(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.prefs=Preferences();self.setWindowTitle(translator.text('Ustawienia PDFManager'));self.resize(970,690)
        layout=QVBoxLayout(self);row=QHBoxLayout();self.navigation=QListWidget();self.navigation.setProperty("i18nItems",True);self.navigation.setFixedWidth(220);self.pages=QStackedWidget();row.addWidget(self.navigation);row.addWidget(self.pages,1);layout.addLayout(row);self.fields={}
        def page(name):
            self.navigation.addItem(name);widget=QWidget();form=QFormLayout(widget);form.setContentsMargins(22,16,22,16);form.setVerticalSpacing(14);title=QLabel(name);title.setObjectName('PageTitle');form.addRow(title);self.pages.addWidget(widget);return form
        def choice(form,key,label,options,default):
            box=QComboBox();box.addItems(options);box.setCurrentText(self.prefs.get(key,default));self.fields[key]=box;form.addRow(label,box);return box
        def check(form,key,label,default=False):
            box=QCheckBox(label);box.setChecked(self.prefs.get(key,default));self.fields[key]=box;form.addRow(box)
        general=page('Ogólne');choice(general,'startup_tab','Zakładka po uruchomieniu',['Start','Skrzynka','Organizuj','Edytor PDF','Edytor obrazu','Szukaj','Wydatki','Automatyzacja'],'Organizuj');check(general,'large_font','Większa czcionka interfejsu');check(general,'compact_ribbon','Kompaktowa wstążka',settings.compact_toolbar)
        theme=QComboBox();theme.addItems(['Jasny','Ciemny']);theme.setCurrentIndex(settings.theme=='dark');general.addRow('Motyw:',theme);self.theme=theme
        accent=QComboBox();accent.addItems(['Niebieski','Morski','Grafitowy','Zielony']);general.addRow('Kolor akcentu:',accent);self.accent=accent
        files=page('Dokumenty');files.addRow(QLabel('Szafki korzystają z katalogów Windows i dostępnych udziałów sieciowych.'))
        check(files,'show_preview','Podgląd PDF obok listy dokumentów',True)
        button=QPushButton('Szablony folderów…');button.clicked.connect(lambda:window._cabinet_tools.template());files.addRow(button)
        scan=page('Skanowanie i OCR');button=QPushButton('Profile skanowania…');button.clicked.connect(lambda:window._scan_profiles.show());scan.addRow(button)
        button=QPushButton('Folder skanera i automatyczny import…');button.clicked.connect(window._scan_automation.configure);scan.addRow(button)
        scan.addRow(QLabel('WIA korzysta ze sterownika Windows. Dla TWAIN można uruchomić aplikację producenta.'))
        search=page('Wyszukiwanie');check(search,'search_recursive','Domyślnie uwzględniaj podfoldery',True);check(search,'search_fulltext','Domyślnie przeszukuj treść PDF',False)
        search.addRow(QLabel('Tekst indeksu jest szyfrowany. Zmienione dokumenty są indeksowane ponownie.'))
        button=QPushButton('Wyczyść indeks');button.clicked.connect(window._search_page.clear_index);search.addRow(button)
        preview=page('Podgląd');choice(preview,'default_view','Widok dokumentu',['single','continuous','two','book','grid'],'single');zoom=QSpinBox();zoom.setRange(25,400);zoom.setSuffix(' %');zoom.setValue(self.prefs.get('default_zoom',100));self.fields['default_zoom']=zoom;preview.addRow('Powiększenie:',zoom)
        save=page('Zapis i otwieranie');save.addRow(QLabel('Edycja odbywa się w kopii roboczej. Zapis oryginału wymaga potwierdzenia.'))
        button=QPushButton('Odzyskaj dokument…');button.clicked.connect(window._recover_documents);save.addRow(button)
        button=QPushButton('Kopie zapasowe…');button.clicked.connect(window._open_backup);save.addRow(button)
        auto=page('Automatyzacja');auto.addRow(QLabel('Reguły mogą kierować dokumenty według tekstu lub kodu kreskowego.'))
        button=QPushButton('Otwórz reguły');button.clicked.connect(lambda:window._shell.tabs.setCurrentIndex(7));auto.addRow(button)
        codes=page('Kody i separatory');codes.addRow(QLabel('Obsługiwane są QR oraz kody 1D/2D rozpoznawane przez ZXing.'))
        button=QPushButton('Rozpoznaj kody w PDF…');button.clicked.connect(window._barcode_document);codes.addRow(button)
        split_button=QPushButton('Podziel dokument według kodów…');split_button.clicked.connect(window._split_by_codes);codes.addRow(split_button)
        integrations=page('Integracje');integrations.addRow(QLabel('Google Drive jest dostępny w menu Plik. Korekta językowa wymaga zgody na wysyłkę tekstu.'))
        button=QPushButton('Przygotuj paczkę do udostępnienia…');button.clicked.connect(window._share_package);integrations.addRow(button)
        security=page('Bezpieczeństwo');check(security,'defender_scan','Skanuj dokumenty przez Windows Defender przed przetwarzaniem',True)
        security.addRow(QLabel('Pliki wykonywalne i skróty są blokowane. PDF-y są przetwarzane w osobnych procesach z limitami.'))
        security.addRow(QLabel('Limity: 256 MB wejścia, 5000 stron, 20 mln pikseli na operację, 50 MB załącznika.'))
        migrate=QPushButton('Zaszyfruj starsze lokalne kopie…');migrate.clicked.connect(self.migrate_storage);security.addRow(migrate)
        security.addRow(QLabel('Procesy mają limit czasu i pamięci. Nie jest to pełny AppContainer ani program antywirusowy.'))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex);self.navigation.setCurrentRow(0)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.button(QDialogButtonBox.Save).setProperty('i18nText','Zapisz ustawienia');buttons.button(QDialogButtonBox.Save).setText(translator.text('Zapisz ustawienia'));buttons.button(QDialogButtonBox.Cancel).setText(translator.text('Anuluj'));buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def save(self):
        from PySide6.QtWidgets import QApplication
        for key,widget in self.fields.items():
            value=widget.isChecked() if isinstance(widget,QCheckBox) else widget.value() if isinstance(widget,QSpinBox) else current_source(widget);self.prefs.put(key,value)
        settings.theme='dark' if self.theme.currentIndex() else 'light';settings.compact_toolbar=self.fields['compact_ribbon'].isChecked();settings.title_color=['#234c70','#1d6877','#374857','#296853'][self.accent.currentIndex()]
        apply_theme(QApplication.instance(),settings.theme);self.window._shell.ribbon.setFixedHeight(78 if settings.compact_toolbar else 103)
        for button in self.window._shell.ribbon.findChildren(__import__('PySide6.QtWidgets',fromlist=['QToolButton']).QToolButton):button.setFixedHeight(46 if settings.compact_toolbar else 65);button.setIconSize(QSize(23,23) if settings.compact_toolbar else QSize(31,31))
        self.window._set_workspace_page(self.window._shell.tabs.currentIndex())
        self.window._search_page.recursive.setChecked(self.prefs.get('search_recursive',True));self.window._search_page.fulltext.setChecked(self.prefs.get('search_fulltext',False));self.accept()

    def migrate_storage(self):
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self,'Starsze kopie','Zamknij inne uruchomione wersje PDFManagera. Zaszyfrować starsze kopie zapasowe, kopie robocze i kosz?')!=QMessageBox.Yes:return
        from pdfmanager.security.cache import migrate_legacy_storage
        from .background_job import run_job
        def complete(result):
            count,errors=result;QMessageBox.information(self,'Ochrona danych',f'Zaszyfrowano plików: {count}. Błędy: {len(errors)}.\n'+'\n'.join(errors[:10]))
        run_job(self,'Zabezpieczanie starszych kopii',migrate_legacy_storage,complete)
