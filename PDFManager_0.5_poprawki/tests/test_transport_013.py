from pathlib import Path
from unittest.mock import patch
import json,pymupdf,pytest
from pdfmanager.dms.transport_templates import templates
from pdfmanager.dms.transport import create_order,missing_documents,read_checklist,save_checklist,render_tokens
from pdfmanager.dms.review_queue import ReviewQueue
from pdfmanager.dms.drafts import DraftStore
from pdfmanager.pdf_engine.transport_ops import mark

def pdf(path,pages=3):
    with pymupdf.open() as document:
        for _ in range(pages):document.new_page().insert_text((30,300),'Original')
        document.save(path)
    return path

def test_templates_have_same_ids_and_fields_in_three_languages():
    from string import Formatter
    fields=lambda value:{k for _,k,_,_ in Formatter().parse(value) if k is not None}
    for kind in ['stamps','snippets']:
        reference=templates('pl',kind)
        for lang in ['en','uk']:
            rows=templates(lang,kind);assert [r['id'] for r in rows]==[r['id'] for r in reference]
            for a,b in zip(reference,rows):assert fields(a['text'])==fields(b['text'])
    assert render_tokens('AWB: {awb}; {trasa}',awb='123-45678901',trasa='WAW → LHR')=='AWB: 123-45678901; WAW → LHR'

@pytest.mark.parametrize('language',['pl','en','uk'])
def test_unicode_stamps_only_selected_pages_and_keep_source(tmp_path,language):
    source=pdf(tmp_path/'source.pdf');before=source.read_bytes();output=tmp_path/'result.pdf'
    text=templates(language)[0]['text'];mark(source,output,text,{'x':30,'y':30,'width':350,'height':80,'size':12,'color':'#176c79','border':True},[0,2])
    with pymupdf.open(output) as document:
        assert text in document[0].get_text() and text not in document[1].get_text() and text in document[2].get_text()
    assert source.read_bytes()==before

def test_failed_multi_page_stamp_does_not_commit(tmp_path):
    source=pdf(tmp_path/'source.pdf');output=tmp_path/'out.pdf';output.write_bytes(b'existing');before=output.read_bytes()
    with pytest.raises(ValueError):mark(source,output,'COPY',{'x':30,'y':30,'width':350,'height':80,'size':12,'color':'#176c79'},[0,99])
    assert output.read_bytes()==before

def test_air_order_profile_and_manual_completeness(tmp_path):
    folder=create_order(tmp_path,'ZL-1','Alpha',profile='air');assert (folder/'02 AWB').is_dir() and (folder/'03 HAWB').is_dir()
    assert missing_documents(folder)==['AWB','Faktura handlowa','Lista pakunkowa','POD']
    value=read_checklist(folder);value['checks']={k:True for k in missing_documents(folder)};save_checklist(folder,value);assert not missing_documents(folder)

def test_queue_is_encrypted_detects_stale_revision_and_exports_safely(tmp_path):
    document=pdf(tmp_path/'AWB_customer.pdf');store=ReviewQueue(tmp_path/'private');key=store.add(document,owner='=HYPERLINK("bad")',order='SECRET-123')
    item=store.all()[0];store.update(key,item['revision'],status='ready',note='Reviewed')
    with pytest.raises(ValueError):store.update(key,item['revision'],status='new')
    assert b'SECRET-123' not in store.db.read_bytes()
    target=tmp_path/'tasks.csv';store.export(target);assert "'=HYPERLINK" in target.read_text(encoding='utf-8-sig')
    with pytest.raises(ValueError):store.export(target)
    assert document.exists();store.remove(key,store.all()[0]['revision']);assert not store.all()

def test_draft_cipher_tampering_is_rejected(tmp_path):
    store=DraftStore(tmp_path/'drafts');source=tmp_path/'source.pdf';data={'paragraphs':[{'runs':[{'text':'Zażółć — Київ — PRIVATE'}]}]}
    store.save(source,data);assert store.load(source)['paragraphs']==data['paragraphs'];file=next(store.root.glob('*.enc'));assert b'PRIVATE' not in file.read_bytes()
    file.write_text(file.read_text()[:-8]+'AAAAAAA=')
    with pytest.raises(Exception):store.load(source)

def test_ui_language_independent_stamp_range_favorites_and_air_profile(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.transport_center import TransportCenter
    from pdfmanager.i18n.translator import translator
    original=translator.language;translator.set_language('pl');source=pdf(tmp_path/'a.pdf');window=MainWindow();window.open_document(str(source));center=TransportCenter(window)
    center.content_language.setCurrentIndex(center.content_language.findData('uk'));center.use_factory(0)
    assert center.text.toPlainText()=='ПЕРЕВІРЕНО';translator.set_language('en');qapp.processEvents();assert center.text.toPlainText()=='ПЕРЕВІРЕНО' and center.content_language.currentData()=='uk'
    center.mark_scope.setCurrentIndex(2);center.mark_range.setText('1,3');assert center.selected_pages(window._current_viewer())==[0,2]
    center.add_template_favorite();center.text.setPlainText('different');center.use_favorite(0);assert center.text.toPlainText()=='ПЕРЕВІРЕНО'
    with patch('pdfmanager.ui.transport_center.QMessageBox.question',return_value=__import__('PySide6.QtWidgets',fromlist=['QMessageBox']).QMessageBox.Yes):center.apply_mark()
    viewer=window._current_viewer()
    with pymupdf.open(viewer.path) as document:assert 'ПЕРЕВІРЕНО' in document[0].get_text() and 'ПЕРЕВІРЕНО' not in document[1].get_text()
    viewer.undo();assert 'ПЕРЕВІРЕНО' not in pymupdf.open(viewer.path)[0].get_text();center.temp.cleanup();center.close();window.close();translator.set_language(original)

def test_draft_round_trip_keeps_unicode_styles_lists_and_original(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.word_format import payload,restore_payload,SafeTextEdit
    from PySide6.QtGui import QTextCursor
    source=pdf(tmp_path/'a.pdf');original=source.read_bytes();window=MainWindow();window.open_document(str(source));panel=window._text_properties;panel.new_text();panel.editor.setPlainText('Zażółć\nКиїв')
    cursor=panel.editor.textCursor();cursor.select(QTextCursor.Document);panel.editor.setTextCursor(cursor);window._word_format.list_format(True);window._word_format.change('bold',True)
    before=payload(panel.editor);restored=SafeTextEdit();restore_payload(restored,before);after=payload(restored)
    assert restored.toPlainText()=='Zażółć\nКиїв';assert [r['prefix'] for r in after]==['1. ','2. '];assert after[0]['runs'][0]['bold']
    panel.save_draft();panel.editor.setPlainText('temporary');panel.restore_draft();assert panel.editor.toPlainText()=='Zażółć\nКиїв' and panel.span is None
    assert source.read_bytes()==original;window.close()

def test_snapshot_history_is_encrypted_on_disk_and_rolls_back_failed_mutation(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.dms.undo_history import Snapshot
    source=pdf(tmp_path/'a.pdf');window=MainWindow();window.open_document(str(source));viewer=window._current_viewer();before=viewer.path.read_bytes()
    def failing():viewer.path.write_bytes(b'broken partial output');raise OSError('simulated failure')
    with pytest.raises(Exception):viewer._mutate_file(failing)
    assert viewer.path.read_bytes()==before
    viewer.add_note_at((30,100),'Note');snapshot=viewer._undo_stack[-1];assert isinstance(snapshot,Snapshot);assert snapshot.path.read_bytes().startswith(b'PDMENC1')
    viewer.undo();viewer.redo();assert viewer.can_undo;folder=viewer._history.root;window._close_tab(0);assert not folder.exists();window.close()

def test_save_detects_destination_change_during_copy(tmp_path):
    from pdfmanager.pdf_engine.io_utils import atomic_copy_file
    from pdfmanager.dms.recovery import digest
    source=pdf(tmp_path/'a.pdf');target=pdf(tmp_path/'b.pdf');baseline=digest(target);target.write_bytes(b'changed externally')
    with pytest.raises(ValueError):atomic_copy_file(source,target,expected_target_sha=baseline)
    assert target.read_bytes()==b'changed externally'

def test_cooperating_saves_do_not_silently_overwrite_each_other(tmp_path):
    from pdfmanager.dms.recovery import WorkingCopy
    source=pdf(tmp_path/'source.pdf');a=WorkingCopy(source,tmp_path/'recovery');b=WorkingCopy(source,tmp_path/'recovery');mark(a.path,a.path,'FIRST',{'x':30,'y':30,'width':300,'height':80,'size':12,'color':'#176c79'},[0]);a.changed();a.save()
    mark(b.path,b.path,'SECOND',{'x':30,'y':30,'width':300,'height':80,'size':12,'color':'#176c79'},[0]);b.changed()
    with pytest.raises(ValueError):b.save()
    assert 'FIRST' in pymupdf.open(source)[0].get_text() and 'SECOND' not in pymupdf.open(source)[0].get_text();a.close();b.close()

def test_close_metadata_failure_keeps_plain_working_copy_and_original(tmp_path):
    from pdfmanager.dms.recovery import WorkingCopy
    source=pdf(tmp_path/'original.pdf');copy=WorkingCopy(source,tmp_path/'recovery');original=source.read_bytes();mark(copy.path,copy.path,'MODIFIED',{'x':30,'y':30,'width':300,'height':80,'size':12,'color':'#176c79'},[0]);copy.changed();before=copy.path
    with patch.object(copy,'write_manifest',side_effect=OSError('disk full')):
        with pytest.raises(OSError):copy.close()
    assert copy.path==before and before.exists() and source.read_bytes()==original
    copy.close();assert copy.path.suffix=='.pdm'

def test_closing_tab_drains_worker_before_deletion(qapp,tmp_path):
    import time
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QCoreApplication,QEvent
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.background_job import Worker
    from pdfmanager.dms.jobs import checkpoint
    from shiboken6 import isValid
    source=pdf(tmp_path/'a.pdf');window=MainWindow();window.open_document(str(source));viewer=window._current_viewer()
    def work():
        while True:time.sleep(.01);checkpoint()
    worker=Worker(work,viewer);worker.start();QTest.qWait(20);window._close_tab(0)
    deadline=time.monotonic()+3
    while window._tabs.count() and time.monotonic()<deadline:QTest.qWait(20)
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    assert window._tabs.count()==0 and not isValid(viewer);window.close()

def test_deskew_is_conservative_and_scan_profile_keeps_original(tmp_path):
    from PIL import Image,ImageDraw
    from pdfmanager.pdf_engine.utilities import deskew_image,prepare_scan
    image=Image.new('RGB',(600,600),'white');draw=ImageDraw.Draw(image)
    for y in range(80,500,35):draw.rectangle((80,y,500,y+3),fill='black')
    tilted=image.rotate(3,expand=False,fillcolor='white');corrected=deskew_image(tilted)
    assert corrected.size[0]>tilted.size[0] # expansion retains page edges
    source=pdf(tmp_path/'scan.pdf',1);original=source.read_bytes();output=tmp_path/'prepared.pdf'
    prepare_scan(source,output,{'dpi':150,'color':'Szarość','rotation':90,'deskew':True,'omit_blank':True})
    assert source.read_bytes()==original
    with pymupdf.open(output) as result:assert len(result)==1 and result[0].rect.width>result[0].rect.height
