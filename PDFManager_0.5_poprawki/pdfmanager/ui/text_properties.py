from pdfmanager.i18n.translator import translator
from PySide6.QtCore import Qt,QTimer,QSignalBlocker
from PySide6.QtGui import QFont,QColor,QTextCharFormat,QTextCursor
from PySide6.QtWidgets import QDockWidget,QWidget,QVBoxLayout,QLabel,QPushButton,QFormLayout,QDoubleSpinBox,QMessageBox
from pdfmanager.ui.word_format import SafeTextEdit,payload

class TextProperties(QDockWidget):
    def __init__(self,window):
        super().__init__('Edycja tekstu',window);self.window=window;self.viewer=None;self.span=None
        body=QWidget();layout=QVBoxLayout(body);self.message=QLabel('Włącz edycję tekstu i kliknij fragment PDF albo wpisz nowy tekst.');self.message.setWordWrap(True);layout.addWidget(self.message)
        self.editor=SafeTextEdit();self.editor.setFont(QFont('DejaVu Sans',11));self.editor.setMinimumHeight(160);layout.addWidget(self.editor)
        form=QFormLayout();layout.addLayout(form);self.width=QDoubleSpinBox();self.height=QDoubleSpinBox()
        for box in (self.width,self.height):box.setRange(1,10000)
        self.width.setValue(250);self.height.setValue(100);form.addRow('Szerokość pola (pkt):',self.width);form.addRow('Wysokość pola (pkt):',self.height)
        apply=QPushButton('Zastosuj do PDF');apply.clicked.connect(self.apply);layout.addWidget(apply)
        restore=QPushButton('Przywróć zapisany szkic');restore.clicked.connect(self.restore_draft);layout.addWidget(restore)
        self._draft_loading=False;self._draft_source=None;self._draft_dirty=False
        self._draft_timer=QTimer(self);self._draft_timer.setSingleShot(True);self._draft_timer.setInterval(3000);self._draft_timer.timeout.connect(self.save_draft)
        self.editor.textChanged.connect(self.draft_changed)
        self.setWidget(body);self.setMinimumWidth(300);self.hide()
    def draft_changed(self):
        if self._draft_loading:return
        if self.viewer and self.viewer.working_copy:
            self._draft_source=self.viewer.working_copy.source;self._draft_dirty=True;self._draft_timer.start()
    def save_draft(self):
        if not self._draft_dirty or not self._draft_source or not self.editor.toPlainText().strip():return
        try:
            from pdfmanager.dms.drafts import DraftStore
            DraftStore().save(self._draft_source,{'paragraphs':payload(self.editor),'width':self.width.value(),'height':self.height.value()});self._draft_dirty=False
        except Exception as exc:self.window.statusBar().showMessage(str(exc),10000)
    def restore_draft(self):
        viewer=self.window._current_viewer()
        if not viewer or not viewer.working_copy:return
        try:
            from pdfmanager.dms.drafts import DraftStore
            from pdfmanager.ui.word_format import restore_payload
            value=DraftStore().load(viewer.working_copy.source)
            if not value:self.message.setText(translator.text('Brak zapisanego szkicu dla tego dokumentu.'));return
            self._draft_loading=True;self.viewer=viewer;self.span=None;self._draft_source=viewer.working_copy.source
            restore_payload(self.editor,value['paragraphs']);self.width.setValue(value['width']);self.height.setValue(value['height']);self.show()
            self.message.setText(translator.text('Przywrócono szkic. Sprawdź tekst i wybierz miejsce wstawienia; PDF nie został zmieniony.'))
        except Exception as exc:QMessageBox.warning(self.window,'PDFManager',str(exc))
        finally:self._draft_loading=False;self._draft_dirty=False
    def clear_draft(self):
        self._draft_timer.stop();self._draft_dirty=False
        if self._draft_source:
            from pdfmanager.dms.drafts import DraftStore
            DraftStore().clear(self._draft_source)
    def edit_pdf(self):
        self.viewer=self.window._current_viewer()
        if self.viewer:self.viewer.set_edit_mode(True);self.show();self.message.setText(translator.text('Kliknij fragment tekstu na stronie. Formatuj szkic paskiem nad dokumentem.'))
    def new_text(self):
        self.save_draft();self._draft_timer.stop();self._draft_loading=True;self.viewer=self.window._current_viewer();self.span=None;self.editor.clear();self._draft_loading=False;self._draft_dirty=False;self.show();self.message.setText(translator.text('Wpisz tekst, ustaw format, kliknij Zastosuj i przeciągnij pole na stronie.'))
    def select_span(self,viewer,span):
        self.save_draft();self._draft_timer.stop();self._draft_loading=True;self.viewer=viewer;self.span=span;self.editor.setPlainText(span.text)
        f=QTextCharFormat();f.setFontFamilies([span.font_name]);f.setFontPointSize(span.font_size);f.setFontWeight(QFont.Bold if span.bold else QFont.Normal);f.setFontItalic(span.italic);f.setForeground(QColor(*span.color_rgb))
        cursor=self.editor.textCursor();cursor.select(QTextCursor.Document);cursor.setCharFormat(f);cursor.clearSelection();self.editor.setTextCursor(cursor);self.editor.setCurrentCharFormat(f)
        self._draft_loading=False;self._draft_dirty=False;self._draft_source=viewer.working_copy.source if viewer.working_copy else None
        self.width.setValue(span.bbox[2]-span.bbox[0]+20);self.height.setValue(max(30,span.bbox[3]-span.bbox[1]+8));self.message.setText(translator.text('Edytujesz wybrany fragment. Oryginał na dysku zmieni się dopiero po zapisaniu dokumentu.'));self.show()
    def apply(self):
        viewer=self.window._current_viewer()
        if viewer is None:return
        if not self.editor.toPlainText().strip():self.message.setText(translator.text('Najpierw wpisz tekst.'));self.show();return
        data=payload(self.editor)
        if self.span is None:
            viewer.pending_content={'rich':data};viewer.set_active_tool('place_content');self.message.setText(translator.text('Przeciągnij na stronie prostokąt dla tekstu.'));return
        if viewer is not self.viewer:self.message.setText(translator.text('Wybierz fragment w bieżącym dokumencie.'));return
        if viewer.current_page!=self.span.page_index:self.message.setText(translator.text('Wróć do strony edytowanego fragmentu albo wybierz nowy tekst.'));return
        import pymupdf
        from pdfmanager.pdf_engine.rich_text import insert_rich_text
        box=pymupdf.Rect(self.span.bbox)*viewer._doc.rotation_matrix(self.span.page_index);w,h=viewer._doc.page_size_points(self.span.page_index)
        rect=(box.x0,box.y0,min(w,box.x0+self.width.value()),min(h,box.y0+self.height.value()))
        try:
            result=viewer._mutate_file(lambda:insert_rich_text(viewer.path,self.span.page_index,rect,data,original=self.span.bbox))
            if result.get('fallback_fonts'):self.window.statusBar().showMessage('Użyto czcionki zastępczej dla: '+', '.join(result['fallback_fonts']),10000)
            self.clear_draft();self.span=None;self.message.setText(translator.text('Zmieniono kopię roboczą. Sprawdź układ i kliknij Zapisz. Ponownie zaznacz fragment przed kolejną zmianą.'))
        except Exception as exc:QMessageBox.warning(self.window,translator.text('Edycja tekstu'),str(exc))
