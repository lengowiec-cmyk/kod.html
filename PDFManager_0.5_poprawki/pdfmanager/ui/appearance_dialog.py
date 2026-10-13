"""Persistent, original appearance options for the document workspace."""
from pdfmanager.i18n.translator import translator
from PySide6.QtWidgets import QDialog,QFormLayout,QComboBox,QCheckBox,QDialogButtonBox,QApplication
from pdfmanager.app_settings import settings
from pdfmanager.ui.theme import apply_theme


class AppearanceDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.window=parent;self.setWindowTitle(translator.text('Wygląd'));form=QFormLayout(self)
        self.theme=QComboBox();self.theme.addItem('Jasny','light');self.theme.addItem('Ciemny','dark');self.theme.setCurrentIndex(max(0,self.theme.findData(settings.theme)));form.addRow('Motyw:',self.theme)
        self.title=QComboBox()
        for label,color in [('Niebieski','#2d5997'),('Grafit','#374151'),('Zielony','#2c735c'),('Fioletowy','#67529a'),('Morski','#226d80'),('Bordowy','#8c4051')]:self.title.addItem(label,color)
        self.title.setCurrentIndex(max(0,self.title.findData(settings.title_color)));form.addRow('Pasek tytułu:',self.title)
        self.toolbar=QComboBox();self.toolbar.addItem('Biały','#ffffff');self.toolbar.addItem('Jasnoszary','#eeeeee');self.toolbar.setCurrentIndex(max(0,self.toolbar.findData(settings.toolbar_color)));form.addRow('Wstążka:',self.toolbar)
        self.compact=QCheckBox('Mała wstążka');self.compact.setChecked(settings.compact_toolbar);form.addRow(self.compact)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);form.addRow(buttons)
    def save(self):
        settings.theme=self.theme.currentData();settings.title_color=self.title.currentData();settings.toolbar_color=self.toolbar.currentData();settings.compact_toolbar=self.compact.isChecked()
        apply_theme(QApplication.instance(),settings.theme)
        self.window._shell.ribbon.setFixedHeight(56 if settings.compact_toolbar else 76)
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QToolButton
        for button in self.window._shell.ribbon.findChildren(QToolButton):
            button.setFixedHeight(44 if settings.compact_toolbar else 63)
            button.setIconSize(QSize(22,22) if settings.compact_toolbar else QSize(30,30))
        self.accept()
