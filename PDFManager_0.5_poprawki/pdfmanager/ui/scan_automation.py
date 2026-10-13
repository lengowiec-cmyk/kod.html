from pdfmanager.i18n.translator import translator
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtCore import QTimer,QProcess
from PySide6.QtWidgets import (QDialog,QFormLayout,QLineEdit,QPushButton,QCheckBox,QComboBox,QDialogButtonBox,QFileDialog,QMessageBox,QLabel)
from pdfmanager.dms.preferences import Preferences
from pdfmanager.dms.scan_pipeline import process_scans,StableFiles,document_name
from .background_job import Worker,run_job

class ScanAutomation:
    def __init__(self,window):
        self.window=window;self.worker=None;self.stable=StableFiles();self.failed_stamps={}
        self.prefs=Preferences();self.config=self.prefs.get('scan_config',{})
        self.timer=QTimer(window);self.timer.setInterval(3000);self.timer.timeout.connect(self.poll)
        # Configuration persists; automatic intake requires an explicit start each session.
    def configure(self):
        dialog=QDialog(self.window);dialog.setWindowTitle('Automatyczny import skanów');form=QFormLayout(dialog)
        fields={}
        for key,label in [('input','Folder skanera'),('output','Folder PDF')]:
            edit=QLineEdit(self.config.get(key,''));fields[key]=edit
            choose=QPushButton('Wybierz…')
            def pick(checked=False,e=edit):
                folder=QFileDialog.getExistingDirectory(dialog,'Folder')
                if folder:e.setText(folder)
            choose.clicked.connect(pick);form.addRow(label,edit);form.addRow(choose)
        pattern=QLineEdit(self.config.get('pattern','{date}_{source}_{counter}'));form.addRow('Reguła nazwy:',pattern)
        form.addRow(QLabel('Pola: {date}, {time}, {source}, {counter}. Duplikaty sprawdzane po zawartości.'))
        ocr=QCheckBox('OCR po imporcie');ocr.setChecked(self.config.get('ocr',False));form.addRow(ocr)
        routing=QCheckBox('Zastosuj reguły kierowania — utwórz kopie w docelowych szafkach');routing.setChecked(self.config.get('routing',False));form.addRow(routing)
        lang=QComboBox();lang.addItems(['pol','eng','ukr']);lang.setCurrentText(self.config.get('language','pol'));form.addRow('Język OCR:',lang)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if not dialog.exec():return
        config={key:edit.text() for key,edit in fields.items()};config.update(pattern=pattern.text(),ocr=ocr.isChecked(),language=lang.currentText(),routing=routing.isChecked())
        try:
            source=Path(config['input']).resolve();target=Path(config['output']).resolve()
            if not source.is_dir() or not target.is_dir():raise ValueError('Wybierz istniejące katalogi.')
            if source==target or source in target.parents:raise ValueError('Folder wynikowy musi znajdować się poza folderem skanera.')
            document_name(config['pattern'],Path('scan.png'),1)
            if config['ocr']:
                from pdfmanager.pdf_engine.workflows import ocr_languages
                if config['language'] not in ocr_languages():raise ValueError('Zainstaluj wybrany model OCR.')
            if config['routing']:
                from pdfmanager.dms.automation import Rules
                if not Rules().all():raise ValueError('Utwórz przynajmniej jedną regułę w zakładce Automatyzacja.')
            self.config=config;self.prefs.put('scan_config',config);self.stable=StableFiles();self.failed_stamps.clear()
        except Exception as exc:QMessageBox.warning(self.window,translator.text('Import skanów'),str(exc))
    def toggle(self):
        if self.timer.isActive():self.timer.stop();self.window.statusBar().showMessage('Obserwowanie folderu skanera wyłączone.',4000);return
        if not self.config:self.configure()
        if self.config:self.timer.start();self.window.statusBar().showMessage('Obserwowanie folderu skanera aktywne co 3 sekundy.',5000)
    def poll(self):
        if self.worker:return
        try:
            paths=self.stable.ready(self.config['input'])
            paths=[p for p in paths if self.failed_stamps.get(p)!=(p.stat().st_size,p.stat().st_mtime_ns)]
            if not paths:return
            config=dict(self.config)
            self.worker=Worker(lambda:self.process(paths,config),self.window)
            self.worker.succeeded.connect(self.complete)
            self.worker.failed.connect(lambda error:self.window.statusBar().showMessage('Import skanów: '+error,7000))
            self.worker.finished.connect(self.finished);self.worker.start()
        except Exception as exc:self.timer.stop();self.window.statusBar().showMessage('Obserwowanie zatrzymane: '+str(exc),7000)
    @staticmethod
    def process(paths,config):
        results=process_scans(paths,config['output'],pattern=config['pattern'],ocr=config['ocr'],language=config['language'])
        if config.get('routing'):
            from pdfmanager.dms.automation import Rules,route_documents
            updated=[]
            for source,status,value in results:
                if status=='ok':
                    rows=route_documents([Path(value)],Rules().all(),pattern='{source}')
                    if rows[0][1]=='Błąd':updated.append((source,'error',rows[0][2]));continue
                    if rows[0][2]:value=Path(rows[0][2])
                updated.append((source,status,value))
            results=updated
        return results
    def complete(self,results):
        errors=[];added=0
        from pdfmanager.logging_setup import get_logger
        logger=get_logger(__name__)
        for source,status,value in results:
            if status=='error':
                errors.append(f'{source.name}: {value}');logger.error('Import skanu %s: %s',source,value)
            if status=='ok':added+=1
            self.failed_stamps[source]=(source.stat().st_size,source.stat().st_mtime_ns) if source.exists() else None
        if added or errors:self.window.statusBar().showMessage(f'Skany: dodano {added}. '+ '; '.join(errors),10000)
    def finished(self):self.worker.deleteLater();self.worker=None
    def stop(self):
        self.timer.stop()
        if self.worker:
            self.worker.control.cancelled.set();self.worker.wait();self.worker.deleteLater();self.worker=None
    def wia(self):
        folder=QFileDialog.getExistingDirectory(self.window,'Folder zapisu PDF ze skanera')
        if not folder:return
        from pdfmanager.windows.scanner import acquire_wia
        from pdfmanager.dms.scanning import import_scans
        with TemporaryDirectory(prefix='pdfmanager-wia-') as temporary:
            source=Path(temporary)/'scan.png'
            def work():
                result=acquire_wia(source)
                return import_scans([result],folder) if result else None
            run_job(self.window,'Skanowanie WIA',work,lambda result:self.window.open_document(str(result)) if result else None)
    def vendor(self):
        executable=self.prefs.get('scanner_application','')
        if not executable or not Path(executable).is_file():
            executable,_=QFileDialog.getOpenFileName(self.window,'Aplikacja producenta skanera (TWAIN)','','Program Windows (*.exe)')
            if not executable:return
            self.prefs.put('scanner_application',executable)
        ok,pid=QProcess.startDetached(executable,[])
        if not ok:QMessageBox.warning(self.window,'Skaner','Nie można uruchomić aplikacji skanera.')
