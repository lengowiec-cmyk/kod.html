"""Real clicks on formatting controls, separate from connection inventory."""
from unittest.mock import patch
from PySide6.QtGui import QTextCursor,QColor
from PySide6.QtCore import Qt

def test_formatting_buttons_act_on_selected_text(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.word_format import payload
    import pymupdf
    source=tmp_path/'original.pdf'
    with pymupdf.open() as doc:doc.new_page();doc.save(source)
    before=source.read_bytes();window=MainWindow();window.open_document(str(source));panel=window._text_properties;panel.new_text();bar=window._word_format;editor=panel.editor
    def select(text='Alpha\nBeta'):
        editor.setPlainText(text);cursor=editor.textCursor();cursor.select(QTextCursor.Document);editor.setTextCursor(cursor)
    def run():return payload(editor)[0]['runs'][0]
    for key,field in [('bold','bold'),('italic','italic'),('underline','underline'),('strike','strike')]:
        select();bar.buttons[key].setChecked(False);bar.buttons[key].click();assert run()[field]
    for key,value in [('sub','sub'),('super','super')]:
        select();bar.buttons[key].setChecked(False);bar.buttons[key].click();assert run()['script']==value
    select();bar.size.setCurrentText('11');bar.set_size();bar.buttons['grow'].click();assert run()['size']==12;bar.buttons['shrink'].click();assert run()['size']==11
    for key,align in [('left','left'),('center','center'),('right','right'),('justify','justify')]:
        select();bar.buttons[key].click();assert payload(editor)[0]['align']==align
    for key,prefix in [('numbers','1. '),('bullets','• ')]:
        select();bar.buttons[key].click();assert payload(editor)[0]['prefix']==prefix
    select();bar.buttons['more_indent'].click();assert payload(editor)[0]['indent']==1;bar.buttons['less_indent'].click();assert payload(editor)[0]['indent']==0
    select('Zulu\nAlpha');bar.buttons['sort'].click();assert editor.toPlainText()=='Alpha\nZulu'
    select();bar.buttons['show_marks'].click();assert editor.document().defaultTextOption().flags()
    for key,field in [('color','color'),('highlight','background')]:
        select()
        with patch('pdfmanager.ui.word_format.QColorDialog.getColor',return_value=QColor('#123456')):bar.buttons[key].click()
        assert tuple(run()[field])==(18,52,86)
    select()
    with patch('pdfmanager.ui.word_format.QColorDialog.getColor',return_value=QColor('#123456')):bar.buttons['paragraph_color'].click()
    assert tuple(payload(editor)[0]['background'])==(18,52,86)
    bar.buttons['border'].setChecked(False);bar.buttons['border'].click();assert payload(editor)[0]['border']
    for i,size in enumerate([11,11,20,16,28,14]):select();bar.style_tiles[i].click();assert run()['size']==size
    select('Zażółć Київ');bar.buttons['copy'].click();assert qapp.clipboard().text()=='Zażółć Київ';bar.buttons['cut'].click();assert editor.toPlainText()=='';bar.buttons['paste'].click();assert editor.toPlainText()=='Zażółć Київ'
    select();bar.buttons['painter'].click();assert bar.painter_format is not None;bar.buttons['painter'].click();assert bar.painter_format is None
    bar.buttons['clear'].click();assert not run()['bold'];bar.case(1);assert editor.toPlainText()=='ALPHA\nBETA'
    assert source.read_bytes()==before;window.close()

def test_deleted_stock_scan_profile_is_not_recreated():
    from pdfmanager.dms.profiles import ScanProfiles
    class Memory:
        def __init__(self):self.data={}
        def get(self,key,default=None):return self.data.get(key,default)
        def put(self,key,value):self.data[key]=value
    store=ScanProfiles();store.prefs=Memory();assert 'Transport pol+eng' in store.all();store.remove('Transport pol+eng');assert 'Transport pol+eng' not in store.all();assert 'Transport ukr+eng' in store.all()

def test_repeated_transport_and_settings_dialogs_are_released(qapp,monkeypatch):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.transport_center import TransportCenter
    from pdfmanager.ui.settings_center import SettingsCenter
    from PySide6.QtWidgets import QDialog
    from PySide6.QtCore import QCoreApplication,QEvent
    monkeypatch.setattr(TransportCenter,'exec',lambda self:QDialog.Rejected)
    monkeypatch.setattr(SettingsCenter,'exec',lambda self:QDialog.Rejected)
    window=MainWindow()
    for _ in range(12):
        window._open_transport_center();window._show_appearance_settings();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        assert not window.findChildren(TransportCenter) and not window.findChildren(SettingsCenter)
    window.close()

def test_page_and_proofreading_dialogs_release_objects(qapp,tmp_path,monkeypatch):
    import pymupdf
    from pdfmanager.ui.main_window import MainWindow,PageManagerDialog,ProofreadingDialog
    from PySide6.QtWidgets import QDialog
    from PySide6.QtCore import QCoreApplication,QEvent
    source=tmp_path/'source.pdf'
    with pymupdf.open() as doc:doc.new_page();doc.save(source)
    monkeypatch.setattr(PageManagerDialog,'exec',lambda self:QDialog.Rejected);monkeypatch.setattr(ProofreadingDialog,'exec',lambda self:QDialog.Rejected)
    window=MainWindow();window.open_document(str(source))
    for _ in range(3):
        window._open_page_manager();window._open_proofreading();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        assert not window.findChildren(PageManagerDialog) and not window.findChildren(ProofreadingDialog)
        assert window._current_viewer().is_loaded and not window._current_viewer().can_undo
    window.close()
