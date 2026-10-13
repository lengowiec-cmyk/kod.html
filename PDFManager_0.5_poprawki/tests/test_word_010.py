from pathlib import Path
from unittest.mock import patch
import time
import pytest,pymupdf
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QTextCursor,QTextCharFormat,QFont,QColor
from PySide6.QtWidgets import QApplication
from pdfmanager.ui.word_format import payload,SafeTextEdit
from pdfmanager.ui.responsive import run,busy
from pdfmanager.pdf_engine.rich_text import insert_rich_text
from pdfmanager.pdf_engine.font_resolver import system_font_file

def simple(path):
    with pymupdf.open() as doc:doc.new_page().insert_text((40,60),'Original text',fontsize=11);doc.save(path)

def test_qt_heartbeat_while_waiting_and_exception_preserved(qapp):
    ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(True));timer.start()
    def slow_work():
        deadline=time.monotonic()+2
        while len(ticks)<8 and time.monotonic()<deadline:time.sleep(.01)
        return 42
    assert run(slow_work)==42
    assert len(ticks)>=8 and not busy()
    def failed():time.sleep(.08);raise OSError('expected failure')
    with pytest.raises(OSError,match='expected failure'):run(failed)
    assert not busy();timer.stop()

def test_cancel_responsive_job_drains_thread(qapp):
    from pdfmanager.ui.background_job import BusyDialog
    from pdfmanager.dms.jobs import checkpoint,Cancelled
    def cancel():
        for widget in qapp.topLevelWidgets():
            if isinstance(widget,BusyDialog):widget.cancel()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(cancel);timer.start(50)
    def work():
        for _ in range(100):checkpoint();time.sleep(.02)
    with pytest.raises(Cancelled):run(work)
    assert not busy()

def test_system_font_variants_are_actual_files():
    for bold,italic in [(False,False),(True,False),(False,True),(True,True)]:
        path=system_font_file('DejaVu Sans',bold,italic);assert path and path.is_file()
    assert system_font_file('Not a real font 787343',False,False) is None

def test_rich_pdf_font_size_color_and_literal_markup(qapp,tmp_path):
    path=tmp_path/'out.pdf';simple(path);editor=SafeTextEdit();editor.setFont(QFont('DejaVu Sans',14));editor.setPlainText('Zażółć <script>tekst</script>')
    cursor=editor.textCursor();cursor.select(QTextCursor.Document)
    f=QTextCharFormat();f.setFontPointSize(18);f.setFontWeight(QFont.Bold);f.setForeground(QColor('#c42030'));f.setFontUnderline(True);cursor.mergeCharFormat(f)
    insert_rich_text(path,0,(40,100,540,180),payload(editor))
    with pymupdf.open(path) as doc:
        spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
        assert 'Zażółć <script>tekst</script>' in doc[0].get_text()
        rich=[s for s in spans if 'Zażółć' in s['text']][0];assert abs(rich['size']-18)<.1;assert rich['color']==0xc42030
        assert rich['flags']&16
        assert doc[0].get_drawings() # underlining is rendered into the PDF

def test_rich_overflow_rolls_back_original(tmp_path):
    path=tmp_path/'out.pdf';simple(path);before=path.read_bytes()
    data=[{'runs':[{'text':'Very large replacement','family':'DejaVu Sans','size':72,'color':(0,0,0)}]}]
    with pytest.raises(ValueError,match='mieści'):insert_rich_text(path,0,(40,40,50,50),data,original=(40,40,110,70))
    assert path.read_bytes()==before

def test_word_bar_changes_draft_and_pdf(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    path=tmp_path/'original.pdf';simple(path);win=MainWindow();win.open_document(str(path));viewer=win._current_viewer();panel=win._text_properties;bar=win._word_format
    from pdfmanager.pdf_engine.text_edit import get_default_text_edit_engine
    span=get_default_text_edit_engine().extract_spans(viewer.path,0)[0];panel.select_span(viewer,span)
    panel.editor.setPlainText('Tekst po zmianie');cursor=panel.editor.textCursor();cursor.select(QTextCursor.Document);panel.editor.setTextCursor(cursor)
    bar.family.setCurrentFont(QFont('DejaVu Sans'));bar.size.setCurrentText('16');bar.set_size();bar.buttons['bold'].click();bar.buttons['underline'].click();bar.buttons['center'].click();bar.buttons['border'].click()
    data=payload(panel.editor);assert data[0]['align']=='center' and data[0]['border'];assert data[0]['runs'][0]['bold'] and data[0]['runs'][0]['underline'];assert data[0]['runs'][0]['size']==16
    panel.width.setValue(300);panel.height.setValue(80)
    with patch('pdfmanager.ui.text_properties.QMessageBox.warning') as warning:panel.apply();assert not warning.called
    with pymupdf.open(viewer.path) as doc:assert 'Tekst po zmianie' in doc[0].get_text() and 'Original text' not in doc[0].get_text()
    assert 'Original text' in pymupdf.open(path)[0].get_text();assert viewer.can_undo
    viewer.undo();assert 'Original text' in pymupdf.open(viewer.path)[0].get_text();win.close()

def test_paragraph_lists_scripts_and_styles_are_serialized(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    win=MainWindow();panel=win._text_properties;bar=win._word_format
    panel.editor.setPlainText('Pierwszy\nDrugi');cursor=panel.editor.textCursor();cursor.select(QTextCursor.Document);panel.editor.setTextCursor(cursor)
    bar.list_format(True);bar.line_spacing(2);bar.indent(1);bar.style(2);data=payload(panel.editor)
    assert [p['prefix'] for p in data]==['1. ','2. '];assert all(p['spacing']==1.5 for p in data);assert data[0]['runs'][0]['size']==20
    path=tmp_path/'list.pdf';simple(path);insert_rich_text(path,0,(40,100,550,300),data)
    text=pymupdf.open(path)[0].get_text();assert 'Pierwszy' in text and 'Drugi' in text and '1.' in text
    win.close()

def test_cancelled_navigation_disables_stale_image_and_can_retry(qapp,tmp_path,monkeypatch):
    from pdfmanager.ui.viewer import PdfViewerWidget
    from pdfmanager.dms.jobs import Cancelled
    path=tmp_path/'two.pdf'
    with pymupdf.open() as doc:doc.new_page();doc.new_page();doc.save(path)
    viewer=PdfViewerWidget(path);original=viewer._doc.render_page
    def cancel(*args,**kwargs):raise Cancelled('cancelled render')
    monkeypatch.setattr(viewer._doc,'render_page',cancel);viewer.go_to_page(1)
    assert viewer.current_page==1 and not viewer._image_label.isEnabled()
    assert viewer._image_label.pixmap().isNull()
    monkeypatch.setattr(viewer._doc,'render_page',original);viewer.go_to_page(1)
    assert viewer._image_label.isEnabled() and not viewer._image_label.pixmap().isNull();viewer.close()

def test_large_document_thumbnail_icons_remain_bounded(qapp,tmp_path,monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from pdfmanager.pdf_engine.render import PdfDocument
    from pdfmanager.ui.viewer import PdfViewerWidget
    path=tmp_path/'large.pdf'
    with pymupdf.open() as doc:
        for _ in range(200):doc.new_page()
        doc.save(path)
    def fake_render(*args,**kwargs):
        image=QImage(20,30,QImage.Format_RGB888);image.fill(Qt.white);return image
    monkeypatch.setattr(PdfDocument,'render_page',fake_render)
    viewer=PdfViewerWidget(path);QTest.qWait(1800)
    assert viewer._thumbnails.count()==200
    assert 0<sum(not viewer._thumbnails.item(i).icon().isNull() for i in range(200))<=30
    viewer.go_to_page(199);QTest.qWait(1800)
    assert not viewer._thumbnails.item(199).icon().isNull()
    assert sum(not viewer._thumbnails.item(i).icon().isNull() for i in range(200))<=30
    viewer.close()

def test_background_preview_concurrency_is_bounded():
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from pdfmanager.ui.responsive import preview_work
    lock=threading.Lock();state={'current':0,'peak':0}
    def render():
        with lock:state['current']+=1;state['peak']=max(state['peak'],state['current'])
        time.sleep(.03)
        with lock:state['current']-=1
        return 1
    with ThreadPoolExecutor(max_workers=4) as pool:assert list(pool.map(lambda _:preview_work(render),range(8)))==[1]*8
    assert state['peak']==1
