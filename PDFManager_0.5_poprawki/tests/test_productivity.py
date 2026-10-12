from pathlib import Path
from dataclasses import replace
import sqlite3
import pymupdf
import pytest
from PIL import Image
from pdfmanager.dms.recovery import WorkingCopy,recoverable
from pdfmanager.dms.trash import Trash
from pdfmanager.dms.jobs import JobControl,Cancelled,execute
from pdfmanager.dms.scan_pipeline import process_scans,document_name,StableFiles
from pdfmanager.dms.search import search_files
from pdfmanager.pdf_engine.content import insert_content_at,inserted_objects,transform_inserted
from pdfmanager.pdf_engine.text_edit import TextSpan

def pdf(path,text='Original'):
    with pymupdf.open() as doc:
        doc.new_page().insert_text((30,40),text);doc.save(path)

def test_working_copy_recovery_conflict_and_backup(tmp_path):
    source=tmp_path/'source.pdf';pdf(source);before=source.read_bytes()
    copy=WorkingCopy(source,tmp_path/'recovery');pdf(copy.path,'Edited');copy.changed()
    assert source.read_bytes()==before
    assert recoverable(tmp_path/'recovery')[0][0]==copy.path
    pdf(source,'External edit')
    with pytest.raises(ValueError,match='poza aplikacją'):copy.save()
    assert 'External edit' in pymupdf.open(source)[0].get_text()
    target=tmp_path/'new.pdf';copy.save(target)
    assert 'Edited' in pymupdf.open(target)[0].get_text()
    copy.path.write_bytes(before);copy.changed();copy.save()
    assert len(list((tmp_path/'backups').glob('*.pdf')))==1
    assert recoverable(tmp_path/'recovery')==[]
    copy.close();assert not copy.folder.exists()

def test_backup_retention_prunes_oldest_copies_per_file(tmp_path):
    source=tmp_path/'source.pdf';pdf(source)
    copy=WorkingCopy(source,tmp_path/'recovery')
    for i in range(8):
        pdf(copy.path,f'Edit {i}');copy.changed();copy.save()
    backups=sorted((tmp_path/'backups').glob('*_source.pdf'))
    from pdfmanager.dms.recovery import MAX_BACKUPS_PER_FILE
    assert len(backups)==MAX_BACKUPS_PER_FILE
    copy.close()

def test_prune_backups_enforces_total_size_cap(tmp_path):
    import os,time
    from pdfmanager.dms.recovery import prune_backups
    for i in range(5):
        path=tmp_path/f'{i:02d}_doc.pdf';path.write_bytes(b'x'*1000)
        stamp=time.time()+i;os.utime(path,(stamp,stamp))
    prune_backups(tmp_path,'doc.pdf',max_per_file=100,max_total_bytes=3000)
    remaining=sorted(tmp_path.glob('*_doc.pdf'))
    assert sum(p.stat().st_size for p in remaining)<=3000
    assert (tmp_path/'04_doc.pdf').exists()
    assert not (tmp_path/'00_doc.pdf').exists()

def test_trash_restore_conflict_preserves_deleted_copy(tmp_path):
    source=tmp_path/'document.pdf';pdf(source);data=source.read_bytes()
    trash=Trash(tmp_path/'trash');folder=trash.put(source)
    assert not source.exists() and len(trash.entries())==1
    source.write_bytes(b'new')
    with pytest.raises(FileExistsError):trash.restore(folder)
    assert trash.entries()[0][2].read_bytes()==data
    target=tmp_path/'restored.pdf';trash.restore(folder,target)
    assert target.read_bytes()==data and source.read_bytes()==b'new' and trash.entries()==[]

def test_scanner_dedup_rules_and_source_changes(tmp_path):
    source=tmp_path/'scan.png';Image.new('RGB',(100,150),'red').save(source)
    output=tmp_path/'out';output.mkdir();ledger=tmp_path/'ledger.sqlite'
    first=process_scans([source],output,pattern='{source}_{counter}',ledger=ledger)
    assert first[0][1]=='ok' and first[0][2].name=='scan_1.pdf'
    assert process_scans([source],output,ledger=ledger)[0][1]=='duplicate'
    Image.new('RGB',(100,150),'blue').save(source)
    assert process_scans([source],output,ledger=ledger)[0][1]=='ok'
    assert len(list(output.glob('*.pdf')))==2
    assert source.exists()

@pytest.mark.parametrize('pattern',['{unknown}','../bad','{source.__class__}','{date!r}','{counter:02}'])
def test_reject_invalid_scan_patterns(pattern):
    with pytest.raises(ValueError):document_name(pattern,'scan.png',1)

def test_scanner_waits_until_size_stops_changing(tmp_path):
    source=tmp_path/'scan.png';source.write_bytes(b'part')
    tracker=StableFiles()
    assert tracker.ready(tmp_path)==[]
    assert tracker.ready(tmp_path)==[]
    source.write_bytes(b'completed')
    assert tracker.ready(tmp_path)==[]
    assert tracker.ready(tmp_path)==[]
    assert tracker.ready(tmp_path)==[source]

def test_index_reuses_text_and_refreshes_changed_pdf(tmp_path,monkeypatch):
    source=tmp_path/'invoice.pdf';pdf(source,'Old customer');index=tmp_path/'index.db'
    assert search_files(tmp_path,'Old',fulltext=True,index_path=index)[0][0][1]==0
    original=pymupdf.open
    def no_open(*args,**kwargs):raise AssertionError('Cached PDF was re-read')
    monkeypatch.setattr(pymupdf,'open',no_open)
    assert search_files(tmp_path,'Old',fulltext=True,index_path=index)[0]
    monkeypatch.setattr(pymupdf,'open',original);pdf(source,'New customer')
    assert search_files(tmp_path,'Old',fulltext=True,index_path=index)[0]==[]
    assert search_files(tmp_path,'New',fulltext=True,index_path=index)[0]
    source.unlink();assert search_files(tmp_path,'New',fulltext=True,index_path=index)[0]==[]

def test_cancel_prevents_index_and_scan_output(tmp_path):
    source=tmp_path/'source.pdf';pdf(source);control=JobControl();control.cancelled.set()
    with pytest.raises(Cancelled):execute(lambda:search_files(tmp_path,'Original',fulltext=True,index_path=tmp_path/'index.db'),control)
    folder=tmp_path/'out';folder.mkdir()
    with pytest.raises(Cancelled):execute(lambda:process_scans([source],folder,ledger=tmp_path/'ledger.db'),control)
    assert list(folder.iterdir())==[]

def test_move_and_scale_inserted_text_preserves_nearby_content(tmp_path):
    path=tmp_path/'document.pdf';pdf(path,'Nearby original')
    style=TextSpan(0,'','',(0,0,0,0),(0,0),'DejaVuSans',14,(0,0,0),False,False)
    object_id=insert_content_at(path,0,(30,100,300,180),text='Inserted text',style=style)
    assert inserted_objects(path,0)[0]['id']==object_id
    transform_inserted(path,0,object_id,(60,200,600-60,360))
    with pymupdf.open(path) as doc:
        spans=[s for block in doc[0].get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for s in line['spans']]
        original=next(s for s in spans if s['text']=='Nearby original')
        added=next(s for s in spans if s['text']=='Inserted text')
        assert original['bbox'][0]==30 and original['size']==11
        assert added['bbox'][0]==pytest.approx(60,.1) and added['size']>14
    before=path.read_bytes()
    with pytest.raises(ValueError):transform_inserted(path,0,object_id,(-10,20,100,200))
    assert path.read_bytes()==before

def test_safe_gui_edits_and_undo_keep_source(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    path=tmp_path/'document.pdf';pdf(path);before=path.read_bytes()
    win=MainWindow();win.open_document(str(path));viewer=win._current_viewer()
    viewer.add_note_at((80,80),'Test')
    assert path.read_bytes()==before and viewer.working_copy.dirty
    viewer.undo();assert path.read_bytes()==before
    win.close();assert viewer.working_copy.path.exists()

def test_wia_is_explicitly_windows_only(tmp_path,monkeypatch):
    import pdfmanager.windows.scanner as scanner
    monkeypatch.setattr(scanner.sys,'platform','linux')
    with pytest.raises(RuntimeError,match='Windows'):scanner.acquire_wia(tmp_path/'scan.png')

def test_wia_paths_are_data_not_interpolated_code(tmp_path,monkeypatch):
    import pdfmanager.windows.scanner as scanner
    from subprocess import CompletedProcess
    monkeypatch.setattr(scanner.sys,'platform','win32')
    target=tmp_path/'OBrien $value scan.png'
    def fake(command,timeout,env):
        assert str(target) not in command[-1]
        assert env['PDFMANAGER_WIA_DEST']==str(target.resolve())
        target.write_bytes(b'image')
        return CompletedProcess(command,0,'','')
    monkeypatch.setattr(scanner,'run_process',fake)
    assert scanner.acquire_wia(target)==target

def test_worker_cancellation_does_not_call_success(qapp):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QWidget
    from pdfmanager.ui.background_job import run_job,Worker
    from pdfmanager.dms.jobs import checkpoint
    import time
    from unittest.mock import patch
    results=[];parent=QWidget()
    original=Worker.run
    def cancel_run(worker):
        worker.control.cancelled.set();original(worker)
    with patch.object(Worker,'run',cancel_run):
        run_job(parent,'Cancel test',lambda:checkpoint(),results.append)
    assert results==[]
    parent.close()

def test_mouse_place_move_and_undo(qapp,tmp_path):
    from PySide6.QtCore import QPoint
    from pdfmanager.ui.viewer import PdfViewerWidget
    path=tmp_path/'document.pdf';pdf(path)
    viewer=PdfViewerWidget(str(path))
    viewer.pending_content={'text':'Mouse placed','style':TextSpan(0,'','',(0,0,0,0),(0,0),'DejaVuSans',14,(0,0,0),False,False)}
    viewer.set_active_tool('place_content');scale=viewer._effective_zoom_matrix_scale()
    point=lambda x,y:QPoint(round(x*scale),round(y*scale))
    viewer._on_image_drag_finished(point(30,100),point(300,180))
    objects=inserted_objects(path,0);assert len(objects)==1 and viewer.pending_content is None
    viewer.set_active_tool('move_content');viewer._on_image_drag_finished(point(40,110),point(70,140))
    assert inserted_objects(path,0)[0]['rect'][0]==pytest.approx(60,.1)
    viewer.undo();assert inserted_objects(path,0)[0]['rect'][0]==pytest.approx(30,.1)
    viewer.close()

def test_panel_applies_font_size_without_changing_source(qapp,tmp_path):
    from PySide6.QtWidgets import QDialogButtonBox
    from pdfmanager.ui.main_window import MainWindow
    path=tmp_path/'document.pdf';pdf(path);before=path.read_bytes()
    win=MainWindow();win.show();win.open_document(str(path));viewer=win._current_viewer()
    span=viewer._text_engine.extract_spans(viewer.path,0)[0]
    win._text_properties.show();win._on_edit_span_requested(viewer,span)
    editor=win._text_properties.widget();editor.size.setValue(22)
    editor.findChild(QDialogButtonBox).accepted.emit()
    assert viewer._text_engine.extract_spans(viewer.path,0)[0].font_size==22
    assert path.read_bytes()==before
    win.close()

def test_recovery_detects_commit_before_manifest_update(tmp_path):
    source=tmp_path/'original.pdf';pdf(source)
    copy=WorkingCopy(source,tmp_path/'recovery');pdf(copy.path,'Crash happened')
    assert not copy.dirty
    assert recoverable(tmp_path/'recovery')[0][0]==copy.path
    copy.close();assert copy.path.exists()

@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_inserted_object_move_on_rotated_and_cropped_page(tmp_path,rotation):
    path=tmp_path/'cropped.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page(width=600,height=800);page.set_cropbox(pymupdf.Rect(20,30,580,770));page.set_rotation(rotation);doc.save(path)
    style=TextSpan(0,'','',(0,0,0,0),(0,0),'DejaVuSans',14,(255,0,0),False,False)
    with pymupdf.open(path) as doc:display=pymupdf.Rect(50,100,250,180)*doc[0].rotation_matrix
    object_id=insert_content_at(path,0,tuple(display),text='Movable',style=style)
    transform_inserted(path,0,object_id,(80,130,280,210))
    with pymupdf.open(path) as doc:
        box=doc[0].search_for('Movable')[0]
        assert box.x0==pytest.approx(80,abs=.1)
        assert 125<box.y0<150

def test_preview_has_memory_limit():
    from pdfmanager.pdf_engine.render import safe_render_scale
    scale=safe_render_scale(10000,10000,5)
    assert 10000*10000*scale*scale<=20_000_001

def test_automatic_ocr_scans_create_searchable_pdf(tmp_path):
    import shutil
    if not shutil.which('tesseract'):pytest.skip('Tesseract required')
    from PIL import ImageDraw,ImageFont
    source=tmp_path/'scan.png';image=Image.new('RGB',(1200,500),'white')
    font=ImageFont.truetype(str(Path(__file__).resolve().parents[1]/'pdfmanager/resources/fonts/DejaVuSans.ttf'),48)
    ImageDraw.Draw(image).text((60,80),'Invoice number 123',font=font,fill='black');image.save(source)
    before=source.read_bytes();folder=tmp_path/'out';folder.mkdir()
    result=process_scans([source],folder,ocr=True,language='eng',ledger=tmp_path/'ledger.db')
    assert result[0][1]=='ok',result
    with pymupdf.open(result[0][2]) as doc:assert 'Invoice' in doc[0].get_text()
    assert source.read_bytes()==before

def test_export_cannot_overwrite_original_of_safe_viewer(qapp,tmp_path):
    from unittest.mock import patch
    from pdfmanager.ui.main_window import MainWindow
    path=tmp_path/'document.pdf';pdf(path);before=path.read_bytes()
    win=MainWindow();win.open_document(str(path))
    with patch('pdfmanager.ui.document_tools.QFileDialog.getSaveFileName',return_value=(str(path),'')),patch('pdfmanager.ui.document_tools.QMessageBox.warning') as warning:
        assert win._tools.output('Export') is None
        assert warning.called
    assert path.read_bytes()==before;win.close()

def test_cancellation_terminates_running_subprocess():
    import sys,time
    from pdfmanager.dms.jobs import run_process
    control=JobControl();control.cancelled.set();start=time.monotonic()
    with pytest.raises(Cancelled):execute(lambda:run_process([sys.executable,'-c','import time; time.sleep(10)']),control)
    assert time.monotonic()-start<2

def test_different_custom_fonts_do_not_reuse_old_font(tmp_path):
    path=tmp_path/'document.pdf';pdf(path)
    fonts=Path(__file__).resolve().parents[1]/'pdfmanager/resources/fonts'
    style=TextSpan(0,'','',(0,0,0,0),(0,0),'DejaVuSans',14,(0,0,0),False,False)
    insert_content_at(path,0,(30,100,300,170),text='Regular custom',style=style,font_file=fonts/'DejaVuSans.ttf')
    insert_content_at(path,0,(30,200,300,270),text='Bold custom',style=style,font_file=fonts/'DejaVuSans-Bold.ttf')
    with pymupdf.open(path) as doc:
        spans=[s for b in doc[0].get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        regular=next(s for s in spans if s['text']=='Regular custom')
        bold=next(s for s in spans if s['text']=='Bold custom')
        assert regular['font']!=bold['font'] and 'Bold' in bold['font']
