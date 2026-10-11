"""Dialogs connecting advanced document workflows to the existing viewer."""
from pathlib import Path
import json
import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog,QInputDialog,QMessageBox,QDialog,QVBoxLayout,QFormLayout,
                              QLineEdit,QComboBox,QCheckBox,QButtonGroup,QDialogButtonBox,QApplication,QScrollArea,QWidget)
from pdfmanager.pdf_engine import workflows as ops
from .background_job import run_job


class DocumentTools:
    def __init__(self, window):self.window=window
    def viewer(self):return self.window._current_viewer()
    def output(self, title, suffix='.pdf'):
        viewer=self.viewer()
        default=str(viewer.source_path.with_name(viewer.source_path.stem+'_export'+suffix)) if viewer else ''
        path,_=QFileDialog.getSaveFileName(self.window,title,default,'PDF (*.pdf)' if suffix=='.pdf' else 'All files (*)')
        if not path:return None
        result=Path(path)
        if result.suffix.lower()!=suffix:result=result.with_suffix(suffix)
        if viewer and result.resolve() in (viewer.path.resolve(),viewer.source_path.resolve()):
            QMessageBox.warning(self.window,title,'Wybierz nowy plik; oryginał zostanie zachowany.');return None
        # Added extension may point at an existing file not checked by the native dialog.
        if result.exists() and QMessageBox.question(self.window,title,'Plik istnieje. Nadpisać?')!=QMessageBox.StandardButton.Yes:return None
        return result
    def export(self,title,fn,suffix='.pdf'):
        viewer=self.viewer()
        if not viewer:return
        output=self.output(title,suffix)
        if not output:return
        source=viewer.path
        run_job(self.window,title,lambda:fn(source,output),lambda _:self.window.open_document(str(output)) if suffix=='.pdf' else QMessageBox.information(self.window,title,str(output)))
    def text(self,title,prompt,default=''):
        value,ok=QInputDialog.getText(self.window,title,prompt,text=default)
        return value if ok else None
    def extract_text(self):self.export('Eksport tekstu',ops.export_text,'.txt')
    def ocr(self,text_only=False,region=None):
        try:languages=ops.ocr_languages()
        except Exception as exc:QMessageBox.warning(self.window,'OCR',str(exc));return
        lang,ok=QInputDialog.getItem(self.window,'OCR','Język OCR:',languages,0,False)
        if not ok:return
        viewer=self.viewer()
        if not viewer:return
        scope,ok=QInputDialog.getItem(self.window,'OCR','Zakres:',['Wszystkie strony','Bieżąca strona'],0,False)
        if not ok:return
        indices=[viewer.current_page] if scope=='Bieżąca strona' or region else None
        if text_only:
            destination,ok=QInputDialog.getItem(self.window,'OCR','Wynik:', ['Plik TXT','Schowek'],0,False)
            if not ok:return
            if destination=='Schowek':
                from tempfile import TemporaryDirectory
                with TemporaryDirectory(prefix='pdfmanager-ocr-text-') as folder:
                    output=Path(folder)/'ocr.txt'
                    def work():
                        ops.ocr_document(viewer.path,output,lang,text_only=True,indices=indices,region=region)
                        return output.read_text(encoding='utf-8')
                    def complete(text):
                        QApplication.clipboard().setText(text)
                        QMessageBox.information(self.window,'OCR','Skopiowano rozpoznany tekst do schowka.')
                    run_job(self.window,'OCR',work,complete)
                return
        self.export('OCR',lambda src,out:ops.ocr_document(src,out,lang,text_only=text_only,indices=indices,region=region),'.txt' if text_only else '.pdf')
    def install_ocr_language(self):
        from pdfmanager.pdf_engine.ocr_models import download_model
        lang,ok=QInputDialog.getItem(self.window,'Modele OCR','Pobierz oficjalny model tessdata_fast (Apache-2.0):',['pol','eng','ukr'],0,False)
        if ok:run_job(self.window,'Pobieranie modelu OCR',lambda:download_model(lang),lambda path:QMessageBox.information(self.window,'OCR','Zainstalowano i zweryfikowano model '+lang))

    def crop(self):
        viewer=self.viewer()
        if not viewer:return
        margins=self.text('Przytnij','Marginesy w punktach: lewy,górny,prawy,dolny','20,20,20,20')
        if margins is None:return
        try:
            values=tuple(float(s) for s in margins.split(','))
            if len(values)!=4:raise ValueError
        except ValueError:QMessageBox.warning(self.window,'Przytnij','Wpisz cztery liczby.');return
        expression=self.text('Przytnij','Strony, np. 1-3,5 lub *','*')
        if expression is None:return
        try:indices=ops.parse_pages(expression,viewer.page_count)
        except Exception as exc:QMessageBox.warning(self.window,'Przytnij',str(exc));return
        self.export('Przytnij',lambda src,out:ops.crop_document(src,out,indices,values))
    def resize(self):
        value=self.text('Rozmiar strony','Szerokość,wysokość w punktach (A4: 595,842)','595,842')
        if value is None:return
        try:width,height=map(float,value.split(','))
        except ValueError:QMessageBox.warning(self.window,'Rozmiar strony','Wpisz dwie liczby.');return
        self.export('Rozmiar strony',lambda src,out:ops.resize_document(src,out,width,height))
    def transform(self,operation):
        if QMessageBox.question(self.window,'Przekształcenie skanu','Utworzyć kopię wszystkich stron jako obrazy? Formularze, tekst i podpisy nie będą zachowane.')!=QMessageBox.StandardButton.Yes:return
        value=0
        if operation in ('rotate','deskew'):
            value,ok=QInputDialog.getDouble(self.window,'Obrót / prostowanie','Kąt (stopnie):',0,-180,180,2)
            if not ok:return
        elif operation=='levels':
            raw=self.text('Poziomy','Czerń,biel,gamma','0,255,1')
            if raw is None:return
            try:
                value=tuple(map(float,raw.split(',')))
                if len(value)!=3:raise ValueError
            except ValueError:QMessageBox.warning(self.window,'Poziomy','Wpisz trzy liczby.');return
        elif operation=='perspective':
            raw=self.text('Perspektywa','Narożniki jako proporcje obrazu 0–1: LG;PG;PD;LD','0,0;1,0;1,1;0,1')
            if raw is None:return
            try:
                points=[tuple(map(float,p.split(','))) for p in raw.split(';')]
                if len(points)!=4 or any(len(p)!=2 or any(v<0 or v>1 for v in p) for p in points):raise ValueError
            except ValueError:QMessageBox.warning(self.window,'Perspektywa','Nieprawidłowe narożniki.');return
            # Normalize independently for each rendered page, including varying page dimensions.
            self.export('Perspektywa',lambda src,out:ops.transform_pdf(src,out,'perspective_normalized',points));return
        self.export('Przekształcenie skanu',lambda src,out:ops.transform_pdf(src,out,operation,value))
    def protect(self):
        password,ok=QInputDialog.getText(self.window,'Hasło PDF','Nowe hasło:',QLineEdit.EchoMode.Password)
        if ok and password:self.export('Hasło PDF',lambda src,out:ops.resave(src,out,new_password=password))
    def decrypt(self):self.export('Usuń hasło',ops.resave)
    def repair(self):self.export('Napraw / optymalizuj',ops.resave)
    def forms(self):
        viewer=self.viewer()
        if not viewer:return
        try:fields=ops.form_fields(viewer.path)
        except Exception as exc:QMessageBox.warning(self.window,'Formularz',str(exc));return
        if not fields:QMessageBox.information(self.window,'Formularz','Brak pól formularza.');return
        dialog=QDialog(self.window);dialog.setWindowTitle('Wypełnij formularz');dialog.resize(600,450)
        layout=QVBoxLayout(dialog);scroll=QScrollArea(dialog);scroll.setWidgetResizable(True)
        container=QWidget();form=QFormLayout(container);controls={};radio_groups={}
        for field in fields:
            if field.kind in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE,pymupdf.PDF_WIDGET_TYPE_BUTTON):continue
            if field.kind in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX,pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                control=QCheckBox()
                if field.kind==pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    if field.name not in radio_groups:radio_groups[field.name]=QButtonGroup(dialog)
                    radio_groups[field.name].addButton(control)
                control.setChecked(str(field.value) not in ('Off','False','', 'None'))
            elif field.choices:
                control=QComboBox();control.addItems([str(v) for v in field.choices]);control.setCurrentText(str(field.value or ''))
            else:
                control=QLineEdit(str(field.value or ''))
                if field.kind==pymupdf.PDF_WIDGET_TYPE_TEXT:control.setMaxLength(10000)
            form.addRow(f'{field.name} (strona {field.page+1})',control);controls[field.xref]=(field,control)
        scroll.setWidget(container);layout.addWidget(scroll)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        values={}
        for xref,(field,control) in controls.items():
            if isinstance(control,QCheckBox):values[xref]=field.on_value if control.isChecked() else 'Off'
            elif isinstance(control,QComboBox):values[xref]=control.currentText()
            else:values[xref]=control.text()
        self.export('Formularz',lambda src,out:ops.fill_form(src,out,values))
    def bookmarks(self):
        viewer=self.viewer()
        if not viewer:return
        try:toc=ops.bookmarks(viewer.path)
        except Exception as exc:QMessageBox.warning(self.window,'Zakładki',str(exc));return
        labels=[f'{"  "*(level-1)}{title} — {page}' for level,title,page in toc]
        choices=['Dodaj zakładkę',*labels]
        choice,ok=QInputDialog.getItem(self.window,'Zakładki','Przejdź do zakładki lub dodaj:',choices,0,False)
        if not ok:return
        if choice!='Dodaj zakładkę':viewer.go_to_page(toc[labels.index(choice)][2]-1);return
        title=self.text('Zakładka','Nazwa:')
        if title: self.export('Zakładka',lambda src,out:ops.set_bookmarks(src,out,toc+[[1,title,viewer.current_page+1]]))
    def compare(self):
        viewer=self.viewer()
        if not viewer:return
        other,_=QFileDialog.getOpenFileName(self.window,'Porównaj z PDF','','PDF (*.pdf)')
        if not other:return
        def complete(rows):
            report='\n'.join(f"Strona {r['page']}: {r['status']} ({r['difference']}% zmienionych pikseli)" for r in rows)
            dialog=QMessageBox(self.window);dialog.setWindowTitle('Porównanie wizualne');dialog.setText(f'Porównano {len(rows)} stron; zmienionych: {sum(r["status"]!="same" for r in rows)}.');dialog.setDetailedText(report);dialog.exec()
            self.window.open_document(other);self.window._toggle_compare_pane()
        run_job(self.window,'Porównanie PDF',lambda:ops.compare_documents(viewer.path,Path(other)),complete)
    def attach(self):
        file,_=QFileDialog.getOpenFileName(self.window,'Dodaj załącznik')
        if file:self.export('Dodaj załącznik',lambda src,out:ops.add_attachment(src,out,Path(file)))
    def extract_attachment(self):
        viewer=self.viewer()
        if not viewer:return
        try:names=ops.attachment_names(viewer.path)
        except Exception as exc:QMessageBox.warning(self.window,'Załączniki',str(exc));return
        if not names:QMessageBox.information(self.window,'Załączniki','Brak załączników.');return
        name,ok=QInputDialog.getItem(self.window,'Załączniki','Wybierz:',names,0,False)
        if not ok:return
        output,_=QFileDialog.getSaveFileName(self.window,'Zapisz załącznik',Path(name).name)
        if output:run_job(self.window,'Załącznik',lambda:ops.extract_attachment(viewer.path,name,Path(output)))
    def sign(self):
        cert,_=QFileDialog.getOpenFileName(self.window,'Certyfikat podpisu','','PKCS#12 (*.pfx *.p12)')
        if not cert:return
        password,ok=QInputDialog.getText(self.window,'Podpis','Hasło certyfikatu:',QLineEdit.EchoMode.Password)
        if ok:self.export('Podpis cyfrowy',lambda src,out:ops.sign_pkcs12(src,out,Path(cert),password))
    def verify(self):
        viewer=self.viewer()
        if not viewer:return
        def complete(rows):
            message='\n'.join(f"{r['field']}: integralność={r['intact']}, poprawność kryptograficzna={r['valid']}, zaufanie={r['trusted']}" for r in rows) or 'Brak podpisów.'
            QMessageBox.information(self.window,'Podpisy — weryfikacja lokalna',message+'\nBez internetowego sprawdzenia unieważnień OCSP/CRL.')
        run_job(self.window,'Weryfikacja podpisów',lambda:ops.verify_signatures(viewer.path),complete)
    def batch(self):
        folder=QFileDialog.getExistingDirectory(self.window,'Folder źródłowy')
        if not folder:return
        output=QFileDialog.getExistingDirectory(self.window,'Pusty folder docelowy')
        if output:run_job(self.window,'Przetwarzanie zbiorcze',lambda:ops.batch_resave(Path(folder),Path(output)),lambda rows:QMessageBox.information(self.window,'Przetwarzanie zbiorcze',f'OK: {sum(status=="OK" for _,status in rows)} / {len(rows)}. Szczegóły w report.csv.'))
    def merge(self):
        files,_=QFileDialog.getOpenFileNames(self.window,'Scal PDF, obrazy lub ZIP','','Dokumenty (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.zip)')
        if not files:return
        output=self.output('Scal dokumenty')
        if output:run_job(self.window,'Scalanie',lambda:ops.merge_inputs([Path(f) for f in files],output),lambda _:self.window.open_document(str(output)))
