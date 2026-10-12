from pathlib import Path
import tempfile
from PySide6.QtWidgets import QDialog,QFormLayout,QComboBox,QSpinBox,QCheckBox,QPushButton,QHBoxLayout,QInputDialog,QMessageBox,QFileDialog,QDialogButtonBox
from pdfmanager.dms.profiles import ScanProfiles
from .background_job import run_job

class ScanProfilesDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.store=ScanProfiles();self.setWindowTitle('Profile skanowania i importu');self.resize(630,500);form=QFormLayout(self)
        self.names=QComboBox();self.names.addItems(self.store.all());form.addRow('Profil:',self.names)
        self.dpi=QSpinBox();self.dpi.setRange(72,600);form.addRow('Rozdzielczość DPI:',self.dpi)
        self.color=QComboBox();self.color.addItems(['Kolor','Szarość','Czerń i biel']);form.addRow('Kolor:',self.color)
        self.rotation=QComboBox();self.rotation.addItems(['0','90','180','270']);form.addRow('Obrót:',self.rotation)
        self.ocr=QCheckBox('Utwórz przeszukiwalny PDF przez OCR');form.addRow(self.ocr)
        self.language=QComboBox();self.language.addItems(['pol','eng','ukr']);form.addRow('Język:',self.language)
        self.blank=QCheckBox('Pomijaj niemal białe, puste strony');form.addRow(self.blank)
        row=QHBoxLayout()
        for label,callback in [('Nowy',self.new),('Zapisz profil',self.save),('Usuń',self.remove)]:
            button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
        form.addRow(row);import_button=QPushButton('Importuj skany według profilu…');import_button.clicked.connect(self.import_scans);form.addRow(import_button)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);buttons.rejected.connect(self.reject);form.addRow(buttons)
        self.names.currentTextChanged.connect(self.load);self.load(self.names.currentText())
    def load(self,name):
        p=self.store.all().get(name)
        if p:self.dpi.setValue(p['dpi']);self.color.setCurrentText(p['color']);self.rotation.setCurrentText(str(p.get('rotation',0)));self.ocr.setChecked(p['ocr']);self.language.setCurrentText(p['language']);self.blank.setChecked(p.get('omit_blank',False))
    def profile(self):return {'dpi':self.dpi.value(),'color':self.color.currentText(),'rotation':int(self.rotation.currentText()),'ocr':self.ocr.isChecked(),'language':self.language.currentText(),'omit_blank':self.blank.isChecked()}
    def save(self):self.store.save(self.names.currentText(),self.profile())
    def new(self):
        name,ok=QInputDialog.getText(self,'Nowy profil','Nazwa:')
        if ok and name.strip():self.store.save(name,self.profile());self.names.addItem(name);self.names.setCurrentText(name)
    def remove(self):
        try:self.store.remove(self.names.currentText());self.names.removeItem(self.names.currentIndex())
        except Exception as exc:QMessageBox.warning(self,'Profil',str(exc))
    def import_scans(self):
        files,_=QFileDialog.getOpenFileNames(self,'Wybierz skany','','Skany (*.pdf *.tif *.tiff *.png *.jpg *.jpeg)')
        if not files:return
        output,_=QFileDialog.getSaveFileName(self,'Wynik profilu','','PDF (*.pdf)')
        if not output:return
        output=str(Path(output).with_suffix('.pdf'))
        if Path(output).exists() and QMessageBox.question(self,'Wynik profilu','Nadpisać istniejący plik wynikowy?')!=QMessageBox.Yes:return
        if any(Path(output).resolve()==Path(f).resolve() for f in files):QMessageBox.warning(self,'Profil','Wybierz nowy plik wynikowy.');return
        profile=self.profile()
        def work():
            from pdfmanager.pdf_engine.workflows import merge_inputs,ocr_document
            from pdfmanager.pdf_engine.utilities import prepare_scan
            with tempfile.TemporaryDirectory(prefix='pdfmanager-profile-') as temp:
                temp=Path(temp);merged=temp/'input.pdf';prepared=temp/'prepared.pdf';merge_inputs([Path(f) for f in files],merged);prepare_scan(merged,prepared,profile)
                if profile['ocr']:ocr_document(prepared,Path(output),profile['language'],dpi=profile['dpi'])
                else:
                    from pdfmanager.pdf_engine.io_utils import atomic_copy_file
                    atomic_copy_file(prepared,Path(output))
        run_job(self,'Import według profilu',work,lambda _:self.window.open_document(output))
