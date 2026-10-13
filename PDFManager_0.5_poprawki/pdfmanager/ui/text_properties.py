from PySide6.QtCore import Qt
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
        self.setWidget(body);self.setMinimumWidth(300);self.hide()
    def edit_pdf(self):
        self.viewer=self.window._current_viewer()
        if self.viewer:self.viewer.set_edit_mode(True);self.show();self.message.setText('Kliknij fragment tekstu na stronie. Formatuj szkic paskiem nad dokumentem.')
    def new_text(self):
        self.viewer=self.window._current_viewer();self.span=None;self.editor.clear();self.show();self.message.setText('Wpisz tekst, ustaw format, kliknij Zastosuj i przeciągnij pole na stronie.')
    def select_span(self,viewer,span):
        self.viewer=viewer;self.span=span;self.editor.setPlainText(span.text)
        f=QTextCharFormat();f.setFontFamilies([span.font_name]);f.setFontPointSize(span.font_size);f.setFontWeight(QFont.Bold if span.bold else QFont.Normal);f.setFontItalic(span.italic);f.setForeground(QColor(*span.color_rgb))
        cursor=self.editor.textCursor();cursor.select(QTextCursor.Document);cursor.setCharFormat(f);cursor.clearSelection();self.editor.setTextCursor(cursor);self.editor.setCurrentCharFormat(f)
        self.width.setValue(span.bbox[2]-span.bbox[0]+20);self.height.setValue(max(30,span.bbox[3]-span.bbox[1]+8));self.message.setText('Edytujesz wybrany fragment. Oryginał na dysku zmieni się dopiero po zapisaniu dokumentu.');self.show()
    def apply(self):
        viewer=self.window._current_viewer()
        if viewer is None:return
        if not self.editor.toPlainText().strip():self.message.setText('Najpierw wpisz tekst.');self.show();return
        data=payload(self.editor)
        if self.span is None:
            viewer.pending_content={'rich':data};viewer.set_active_tool('place_content');self.message.setText('Przeciągnij na stronie prostokąt dla tekstu.');return
        if viewer is not self.viewer:self.message.setText('Wybierz fragment w bieżącym dokumencie.');return
        if viewer.current_page!=self.span.page_index:self.message.setText('Wróć do strony edytowanego fragmentu albo wybierz nowy tekst.');return
        import pymupdf
        from pdfmanager.pdf_engine.rich_text import insert_rich_text
        box=pymupdf.Rect(self.span.bbox)*viewer._doc.rotation_matrix(self.span.page_index);w,h=viewer._doc.page_size_points(self.span.page_index)
        rect=(box.x0,box.y0,min(w,box.x0+self.width.value()),min(h,box.y0+self.height.value()))
        try:
            result=viewer._mutate_file(lambda:insert_rich_text(viewer.path,self.span.page_index,rect,data,original=self.span.bbox))
            if result.get('fallback_fonts'):self.window.statusBar().showMessage('Użyto czcionki zastępczej dla: '+', '.join(result['fallback_fonts']),10000)
            self.span=None;self.message.setText('Zmieniono kopię roboczą. Sprawdź układ i kliknij Zapisz. Ponownie zaznacz fragment przed kolejną zmianą.')
        except Exception as exc:QMessageBox.warning(self.window,'Edycja tekstu',str(exc))
