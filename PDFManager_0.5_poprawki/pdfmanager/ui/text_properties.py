from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget,QDialogButtonBox,QLabel,QMessageBox
from .content_editor import TextStyleDialog

class TextProperties(QDockWidget):
    def __init__(self,window):
        super().__init__('Tekst i czcionka',window);self.window=window
        self.setWidget(QLabel('Włącz edycję tekstu i kliknij fragment na stronie.'));self.hide()
    def select_span(self,viewer,span):
        editor=TextStyleDialog(self,span);editor.setWindowFlags(Qt.Widget)
        buttons=editor.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.Ok).setText('Zastosuj')
        buttons.button(QDialogButtonBox.Cancel).setText('Anuluj')
        buttons.accepted.disconnect();buttons.rejected.disconnect()
        def apply():
            text,style=editor.result_style()
            try:
                result=viewer.apply_text_edit(span,text,style=style,font_file=editor.font_file)
                if result.warnings:self.window.statusBar().showMessage('Zmieniono tekst. Sprawdź układ i dopasowanie czcionki.',6000)
                self.setWidget(QLabel('Zastosowano. Kliknij ponownie tekst, aby kontynuować edycję.'))
            except Exception as exc:QMessageBox.warning(self.window,'Edycja tekstu',str(exc))
        buttons.accepted.connect(apply);buttons.rejected.connect(lambda:self.setWidget(QLabel('Wybierz tekst na stronie.')))
        self.setWidget(editor)
