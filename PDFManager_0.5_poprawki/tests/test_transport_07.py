from pathlib import Path
from unittest.mock import MagicMock,patch
from dataclasses import asdict
import json
import pytest
import pymupdf
from pdfmanager.dms.transport import filename,render_tokens,create_order,missing_documents,read_checklist,save_checklist
from pdfmanager.pdf_engine.transport_ops import mark,package,batch_transform,comparison_pdf
from pdfmanager.drive.api_client import DriveApiClient,DriveFile,DriveConflictError
from pdfmanager.drive.teamwork import TeamDrive,Outbox,LEASE_KEY

def make_pdf(path,text='Original'):
    with pymupdf.open() as doc:doc.new_page().insert_text((80,200),text);doc.save(path)
    return path

def baseline(checksum='original',modified='2026-10-12T00:00:00Z'):
    return DriveFile('id1','CMR.pdf','application/pdf',modified,500,checksum,('folder1',))

def raw(file):
    return {'id':file.id,'name':file.name,'mimeType':file.mime_type,'modifiedTime':file.modified_time,'size':str(file.size),'md5Checksum':file.md5_checksum,'parents':list(file.parents)}

def test_names_and_tokens():
    assert filename('ZL/42','CMR','Łódź','2026-10-12')=='2026-10-12_ZL_42_CMR_Łódź.pdf'
    assert 'Anna' in render_tokens('{pracownik} {zlecenie}',order='ZL42',employee='Anna')
    with pytest.raises(ValueError):filename('CON','CMR','Firma')
    with pytest.raises(ValueError):filename('ZL42','CMR','Firma','wrong')

def test_transport_folder_and_checklist(tmp_path):
    folder=create_order(tmp_path,'ZL42','Firma')
    assert (folder/'02 CMR').is_dir();assert len(missing_documents(folder))==3
    data=read_checklist(folder);data['checks']={'Podpisany CMR':True,'POD':True};save_checklist(folder,data)
    assert missing_documents(folder)==['Faktura']
    with pytest.raises(FileExistsError):create_order(tmp_path,'ZL42','Firma')

def test_marks_are_unicode_and_do_not_modify_original(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');before=source.read_bytes();out=tmp_path/'out.pdf'
    mark(source,out,'OPŁACONO — Łódź',{'x':20,'y':20,'width':350,'height':80,'size':16,'border':True})
    with pymupdf.open(out) as doc:assert 'OPŁACONO — Łódź' in doc[0].get_text()
    assert source.read_bytes()==before

def test_marks_reject_overflow_and_outside_page(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');out=tmp_path/'out.pdf'
    with pytest.raises(ValueError):mark(source,out,'long '*100,{'width':20,'height':10,'size':12})
    assert not out.exists()
    with pytest.raises(ValueError):mark(source,out,'TEST',{'x':1000,'width':100,'height':100,'size':12})
    assert not out.exists()

def test_package_order_cover_bookmarks_and_numbers(tmp_path):
    a=make_pdf(tmp_path/'CMR.pdf','CMR content');b=make_pdf(tmp_path/'POD.pdf','POD content');out=tmp_path/'pakiet.pdf'
    package([b,a],out,'Zlecenie Łódź')
    with pymupdf.open(out) as doc:
        assert len(doc)==3;assert 'Zlecenie Łódź' in doc[0].get_text();assert 'POD content' in doc[1].get_text();assert 'CMR content' in doc[2].get_text();assert '3 / 3' in doc[2].get_text();assert doc.get_toc()[0][2]==2

def test_batch_rotation_compression_and_numbers(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');out=tmp_path/'b.pdf';batch_transform(source,out,rotation=90,compress=True,number=True)
    with pymupdf.open(out) as doc:assert doc[0].rotation==90;assert 'Original' in doc[0].get_text();assert '1 / 1' in doc[0].get_text()

def test_difference_report_highlights_changed_page(tmp_path):
    a=make_pdf(tmp_path/'a.pdf');b=make_pdf(tmp_path/'b.pdf','Different');out=tmp_path/'diff.pdf'
    result=comparison_pdf(a,b,out);assert result[0]['difference']>0
    with pymupdf.open(out) as doc:assert len(doc)==1;assert 'różnice' in doc[0].get_text();assert len(doc[0].get_images())==3

def test_identical_difference_is_zero(tmp_path):
    a=make_pdf(tmp_path/'a.pdf');result=comparison_pdf(a,a,tmp_path/'diff.pdf');assert result[0]['difference']==0

def test_redaction_removes_text_not_just_rectangle(tmp_path):
    from pdfmanager.pdf_engine.workflows import redact
    a=make_pdf(tmp_path/'a.pdf','CONFIDENTIAL')
    with pymupdf.open(a) as doc:rect=tuple(doc[0].search_for('CONFIDENTIAL')[0])
    redact(a,0,rect)
    with pymupdf.open(a) as doc:assert 'CONFIDENTIAL' not in doc[0].get_text()
    assert b'CONFIDENTIAL' not in a.read_bytes()

def test_outbox_survives_offline_and_is_encrypted(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');outbox=Outbox(tmp_path/'outbox');job=outbox.enqueue(source,baseline(),'Anna','account')
    assert b'CMR.pdf' not in (outbox.folder/f'{job}.json').read_bytes();assert b'%PDF' not in (outbox.folder/f'{job}.pdm').read_bytes()
    fake=MagicMock();fake.publish.side_effect=OSError('offline');results=outbox.process(fake,'account')
    assert results[0]['state']=='Oczekuje na wysłanie';assert 'offline' in results[0]['error']
    recovered=tmp_path/'recovered.pdf';Outbox(outbox.folder).recover(job,recovered);assert recovered.read_bytes()==source.read_bytes()

def test_queue_wrong_account_never_sends(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');outbox=Outbox(tmp_path/'outbox');outbox.enqueue(source,baseline(),'Anna','account1');fake=MagicMock();assert outbox.process(fake,'account2')==[];fake.publish.assert_not_called()

def test_queue_conflict_is_retained_and_not_retried(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');outbox=Outbox(tmp_path/'outbox');job=outbox.enqueue(source,baseline(),'Anna','account');fake=MagicMock();fake.publish.side_effect=DriveConflictError('id1',baseline('changed'))
    results=outbox.process(fake,'account');assert results[0]['state']=='Konflikt';assert outbox.process(fake,'account')==[];assert fake.publish.call_count==1;assert (outbox.folder/f'{job}.pdm').exists()

def test_queue_success_not_repeated(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');outbox=Outbox(tmp_path/'outbox');outbox.enqueue(source,baseline(),'Anna','account');fake=MagicMock();fake.publish.return_value=baseline('new')
    assert outbox.process(fake,'account')[0]['state']=='Zapisano na Google Drive';assert outbox.process(fake,'account')==[];assert fake.publish.call_count==1

def test_publish_creates_immutable_version_never_updates_original(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');service=MagicMock();service.files().list().execute.return_value={'files':[]};service.files().get().execute.return_value=raw(baseline());service.files().create().execute.return_value=raw(baseline('new'));team=TeamDrive(DriveApiClient(service))
    result=team.publish(source,baseline(),'Anna','12345678-1234-1234-1234-123456789012')
    assert result.md5_checksum=='new';service.files().update.assert_not_called()
    body=service.files().create.call_args.kwargs['body'];assert body['appProperties']['pdfmanagerOrigin']=='id1';assert body['parents']==['folder1'];assert 'wersja_' in body['name']

def test_publish_checksumless_conflict_uses_modified_time(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');service=MagicMock();service.files().list().execute.return_value={'files':[]};service.files().get().execute.return_value=raw(baseline(None,'changed'));team=TeamDrive(DriveApiClient(service))
    with pytest.raises(DriveConflictError):team.publish(source,baseline(None),'Anna','job')
    service.files().create.assert_not_called();service.files().update.assert_not_called()

def test_publish_retry_finds_already_created_version(tmp_path):
    service=MagicMock();service.files().list().execute.return_value={'files':[raw(baseline('new'))]};team=TeamDrive(DriveApiClient(service));assert team.publish(tmp_path/'not-needed.pdf',baseline(),'Anna','job').md5_checksum=='new';service.files().create.assert_not_called()

def test_reservation_refuses_other_employee():
    from datetime import datetime,timezone,timedelta
    service=MagicMock();lease={'o':'Anna','t':'other','e':int((datetime.now(timezone.utc)+timedelta(minutes=10)).timestamp())};service.files().get().execute.return_value={'appProperties':{LEASE_KEY:json.dumps(lease)}};team=TeamDrive(DriveApiClient(service))
    with pytest.raises(Exception,match='Anna'):team.reserve('id1','Bob','12345678')
    service.files().update.assert_not_called()

def test_reservation_property_fits_google_limit():
    service=MagicMock();store={}
    service.files().get().execute.side_effect=lambda:{'appProperties':store.copy()}
    def update(**kw):store.update(kw['body']['appProperties']);return MagicMock()
    service.files().update.side_effect=update;team=TeamDrive(DriveApiClient(service));value=team.reserve('id1','Łódź — pracownik spedycji','12345678');assert value['owner'];assert len((LEASE_KEY+store[LEASE_KEY]).encode())<=124;team.release('id1','12345678');assert store[LEASE_KEY] is None

def test_transport_ui_and_shortcuts(qapp):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.transport_center import TransportCenter
    win=MainWindow();dialog=TransportCenter(win)
    assert dialog.tabs.count()==5;assert dialog.entry.count()>=9;assert dialog.profile.count()>=4
    assert win._transport_actions['transport_center'].shortcut().toString()=='Ctrl+Shift+T';assert win._transport_actions['save_next'].shortcut().toString()=='Ctrl+Alt+N'
    dialog.temp.cleanup();win.close()

def test_save_next_cancel_does_not_advance(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    win=MainWindow();a=make_pdf(tmp_path/'a.pdf');make_pdf(tmp_path/'b.pdf');win.open_document(str(a))
    with patch.object(win,'_save_working_copy',return_value=False),patch.object(win,'open_document') as opening:win._save_and_next();opening.assert_not_called()
    win.close()

def test_save_next_after_local_commit_opens_following(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    win=MainWindow();a=make_pdf(tmp_path/'a.pdf');b=make_pdf(tmp_path/'b.pdf');win.open_document(str(a))
    with patch('pdfmanager.ui.main_window.QMessageBox.question',return_value=__import__('PySide6.QtWidgets',fromlist=['QMessageBox']).QMessageBox.Yes):win._save_and_next()
    assert win._current_viewer().source_path==b;win.close()

def test_failed_drive_download_preserves_existing_file(tmp_path):
    from pdfmanager.drive.api_client import download_request
    target=tmp_path/'old.pdf';target.write_bytes(b'keep original')
    with patch('pdfmanager.drive.api_client.MediaIoBaseDownload') as downloader:
        downloader.return_value.next_chunk.side_effect=OSError('offline')
        with pytest.raises(OSError):download_request(MagicMock(),target)
    assert target.read_bytes()==b'keep original';assert not list(tmp_path.glob('pdfmanager-drive-*.tmp'))

def test_queue_rejects_unknown_account_and_missing_employee(tmp_path):
    source=make_pdf(tmp_path/'a.pdf');outbox=Outbox(tmp_path/'outbox')
    with pytest.raises(ValueError):outbox.enqueue(source,baseline(),'Anna','')
    with pytest.raises(ValueError):outbox.enqueue(source,baseline(),'','account')
    assert outbox.items()==[]

def test_no_two_local_senders_can_process_queue(tmp_path):
    outbox=Outbox(tmp_path/'outbox')
    with outbox._lock():
        with pytest.raises(OSError):outbox.process(MagicMock(),'account')

def test_empty_transport_order_rejected(tmp_path):
    with pytest.raises(ValueError):create_order(tmp_path,'','')
    assert list(tmp_path.iterdir())==[]

def test_save_next_on_drive_preserves_api_link(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow,DriveTabInfo
    from pdfmanager.i18n.translator import translator
    win=MainWindow();a=make_pdf(tmp_path/'a.pdf');win.open_document(str(a));client=MagicMock(spec=DriveApiClient)
    first=DriveFile('a','a.pdf','application/pdf','now',100,'a',('folder',));second=DriveFile('b','b.pdf','application/pdf','now',100,'b',('folder',));client.list_folder.return_value=[first,second];win._current_viewer().drive_info=DriveTabInfo('a',first,client)
    with patch.object(win,'_save_working_copy',return_value='durable-job'),patch.object(win,'_open_drive_file') as opening:
        win._save_and_next();opening.assert_called_once_with(client,second);client.list_folder.assert_called_once_with('folder')
    win.close()

def test_drive_folder_pagination_does_not_drop_next_documents():
    service=MagicMock();service.files().list().execute.side_effect=[{'files':[raw(baseline())],'nextPageToken':'second-page'},{'files':[raw(baseline('second'))]}]
    files=DriveApiClient(service).list_folder('folder');assert len(files)==2;assert service.files().list.call_args.kwargs['pageToken']=='second-page'

def test_stamp_in_ui_is_undoable_and_keeps_original(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.transport_center import TransportCenter
    win=MainWindow();source=make_pdf(tmp_path/'a.pdf');before=source.read_bytes();win.open_document(str(source));dialog=TransportCenter(win);dialog.employee.setText('Anna');dialog.text.setPlainText('OPŁACONO');dialog.metadata.setChecked(False)
    dialog.apply_mark();viewer=win._current_viewer()
    with pymupdf.open(viewer.path) as doc:assert 'OPŁACONO' in doc[0].get_text()
    viewer.undo()
    with pymupdf.open(viewer.path) as doc:assert 'OPŁACONO' not in doc[0].get_text()
    assert source.read_bytes()==before;dialog.temp.cleanup();win.close()

def test_background_queue_updates_confirmed_state(qapp,tmp_path):
    import time
    from PySide6.QtTest import QTest
    from pdfmanager.ui.main_window import MainWindow,DriveTabInfo
    from pdfmanager.i18n.translator import translator
    from pdfmanager.dms.preferences import Preferences
    source=make_pdf(tmp_path/'a.pdf');outbox=Outbox(tmp_path/'outbox');outbox.enqueue(source,baseline(),'Anna','account')
    client=DriveApiClient(MagicMock());client._team_account_id='account';win=MainWindow();win.open_document(str(source));win._current_viewer().drive_info=DriveTabInfo('id1',baseline(),client);Preferences().put('transport_auto_send',True)
    with patch('pdfmanager.drive.teamwork.Outbox',return_value=outbox),patch('pdfmanager.drive.teamwork.TeamDrive.publish',return_value=baseline('new')):
        win._transport_tick();deadline=time.monotonic()+5
        while win._transport_sending and time.monotonic()<deadline:QTest.qWait(20)
        assert not win._transport_sending;assert outbox.items()[0]['state']=='Zapisano na Google Drive';assert win._drive_queue_status.text()==translator.text('Drive: oczekuje {waiting} • konflikty {conflicts}',waiting=0,conflicts=0)
    win.close()
