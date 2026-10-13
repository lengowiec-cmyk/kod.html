"""Independent text formatting and positioned clipboard insertion."""
from pdfmanager.i18n.translator import translator
from dataclasses import replace
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor,QFont
from PySide6.QtWidgets import (QApplication, QDialog, QFormLayout, QTextEdit, QComboBox,
 QFontComboBox, QDoubleSpinBox, QCheckBox, QPushButton, QColorDialog, QDialogButtonBox, QFileDialog, QMessageBox)
from pdfmanager.pdf_engine.text_edit import TextSpan
from pdfmanager.pdf_engine.content import insert_content_at

class TextStyleDialog(QDialog):
    def __init__(self, parent, span=None):
        super().__init__(parent)
        self.setWindowTitle('Tekst i czcionka'); self.resize(540,420)
        self.span=span or TextSpan(0,'','',(0,0,0,0),(0,0),'DejaVuSans',12,(0,0,0),False,False)
        layout=QFormLayout(self)
        self.text=QTextEdit();self.text.setMinimumHeight(100);self.text.setMaximumHeight(180); self.text.setPlainText(self.span.text); layout.addRow('Tekst (obsługuje wklejanie):',self.text)
        self.font_file=None
        font_button=QPushButton('Wybierz własną czcionkę TTF / OTF…');font_button.clicked.connect(self.pick_font);layout.addRow(font_button)
        self.family=QFontComboBox();self.family.setCurrentFont(QFont(self.span.font_name));self._original_family=self.family.currentText();layout.addRow('Czcionka:',self.family)
        self.size=QDoubleSpinBox(); self.size.setRange(1,300);self.size.setValue(self.span.font_size);layout.addRow('Rozmiar w punktach:',self.size)
        self.bold=QCheckBox();self.bold.setChecked(self.span.bold);layout.addRow('Pogrubienie:',self.bold)
        self.italic=QCheckBox();self.italic.setChecked(self.span.italic);layout.addRow('Kursywa:',self.italic)
        self.color=QColor(*self.span.color_rgb);button=QPushButton('Wybierz kolor');button.clicked.connect(self.choose_color);layout.addRow('Kolor:',button)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addRow(buttons)
    def pick_font(self):
        name,_=QFileDialog.getOpenFileName(self,translator.text('Czcionka'),'','Czcionki (*.ttf *.otf)')
        if name:self.font_file=Path(name)
    def choose_color(self):
        selected=QColorDialog.getColor(self.color,self)
        if selected.isValid():self.color=selected
    def result_style(self):
        return self.text.toPlainText(),replace(self.span,font_name=self.span.font_name if self.family.currentText()==self._original_family and self.bold.isChecked()==self.span.bold and self.italic.isChecked()==self.span.italic else 'system:'+self.family.currentFont().family(),font_size=self.size.value(),bold=self.bold.isChecked(),italic=self.italic.isChecked(),color_rgb=(self.color.red(),self.color.green(),self.color.blue()))

def insert_content(parent,viewer,clipboard=False):
    if viewer is None:return
    dialog=TextStyleDialog(parent)
    dialog.setWindowTitle('Wstaw zawartość — pozycja i rozmiar w punktach PDF')
    layout=dialog.layout()
    values=[]
    for label,default in [('X',40),('Y',40),('Szerokość',250),('Wysokość',120)]:
        box=QDoubleSpinBox();box.setRange(0 if label in ('X','Y') else 1,10000);box.setValue(default);layout.insertRow(layout.rowCount()-1,label,box);values.append(box)
    use_mouse=QCheckBox('Umieść na stronie myszą — przeciągnij obszar');use_mouse.setChecked(True)
    layout.insertRow(layout.rowCount()-1,use_mouse)
    image_data=None
    if clipboard:
        clip=QApplication.clipboard()
        if clip.mimeData().hasImage():
            buffer=QBuffer();buffer.open(QIODevice.WriteOnly);clip.image().save(buffer,'PNG');image_data=bytes(buffer.data())
            dialog.text.setPlainText('[Obraz ze schowka — proporcje zostaną zachowane]');dialog.text.setReadOnly(True)
        else:dialog.text.setPlainText(clip.text())
    else:
        button=QPushButton('Wybierz obraz PNG / JPG / TIFF…');layout.insertRow(layout.rowCount()-1,button)
        def pick():
            nonlocal image_data
            name,_=QFileDialog.getOpenFileName(parent,'Obraz','','Obrazy (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)')
            if name:
                from pdfmanager.security.limits import check_file
                check_file(name)
                if Path(name).stat().st_size>32*1024*1024:QMessageBox.warning(dialog,'Obraz','Obraz przekracza limit 32 MB.');return
                image_data=Path(name).read_bytes();dialog.text.setPlainText('[Obraz: '+Path(name).name+']');dialog.text.setReadOnly(True)
        button.clicked.connect(pick)
    if not dialog.exec():return
    text,style=dialog.result_style();x,y,w,h=[v.value() for v in values]
    if use_mouse.isChecked():
        viewer.pending_content={'text':text,'style':style,'image':image_data,'font_file':dialog.font_file}
        viewer.set_active_tool('place_content')
        parent.statusBar().showMessage('Przeciągnij na stronie obszar dla wstawianej zawartości.',7000)
        return
    try:
        viewer._mutate_file(lambda:insert_content_at(viewer.path,viewer.current_page,(x,y,x+w,y+h),text=text,style=style,image=image_data,font_file=dialog.font_file))
    except Exception as exc:QMessageBox.critical(parent,'Nie można wstawić zawartości',str(exc))
