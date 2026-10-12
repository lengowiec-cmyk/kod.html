from pathlib import Path
from decimal import Decimal
from datetime import date
from unittest.mock import patch
import sqlite3
import pymupdf
import pytest
from pdfmanager.security.limits import check_pixels,DocumentLimitError
from pdfmanager.security.isolation import call,encode,decode
from pdfmanager.security.cache import CacheCipher
from pdfmanager.dms.receipts import ReceiptStore
from pdfmanager.dms.automation import route_documents
from pdfmanager.pdf_engine.utilities import barcode_pdf,prepare_scan

def pdf(path,text='Invoice customer 123'):
    with pymupdf.open() as doc:doc.new_page().insert_text((30,40),text);doc.save(path)

def test_pixel_limit_and_worker_allowlist(tmp_path):
    with pytest.raises(DocumentLimitError):check_pixels(10000,10000,600)
    path=tmp_path/'doc.pdf';pdf(path)
    assert call('document.info',path)['pages']==1
    with pytest.raises(ValueError):call('document.__unknown',path)
    with pytest.raises(ValueError):call('os.system','unused')

def test_wire_dictionary_cannot_impersonate_special_type():
    value={'$path':'not-a-path','$type':'TextSpan','data':{'$bytes':'unexpected'}}
    assert decode(encode(value))==value

def test_dangerous_external_format_blocked(qapp,tmp_path):
    from pdfmanager.security.opening import open_document_file
    path=tmp_path/'dangerous.lnk';path.write_text('dummy')
    with patch('pdfmanager.security.opening.QMessageBox.warning') as warning,patch('pdfmanager.security.opening.QDesktopServices.openUrl') as opened:
        assert open_document_file(None,path) is False
        assert warning.called and not opened.called

def test_encrypted_cache_and_search(qapp,tmp_path):
    from pdfmanager.dms.search import search_files
    source=tmp_path/'doc.pdf';pdf(source,'Secret customer name')
    index=tmp_path/'index.sqlite3';assert search_files(tmp_path,'Secret',fulltext=True,index_path=index)[0]
    assert b'Secret customer name' not in index.read_bytes()
    with sqlite3.connect(index) as db:text=db.execute('SELECT text FROM pages').fetchone()[0]
    assert text.startswith('enc:v1:') and 'secret' not in text
    assert search_files(tmp_path,'Secret',fulltext=True,index_path=index)[0]

def test_receipts_encrypted_and_csv_formula_neutralized(tmp_path):
    store=ReceiptStore(tmp_path/'receipts.db');identifier=store.save({'date':'2026-10-12','payee':'=SUM(A1:A3)','amount':'12,34','currency':'PLN'})
    assert store.all()[0][1]['amount']=='12.34'
    assert b'=SUM' not in store.path.read_bytes()
    path=tmp_path/'expenses.csv';store.export(path);assert "'=SUM" in path.read_text(encoding='utf-8-sig')
    store.remove(identifier);assert store.all()==[]
    with pytest.raises(ValueError):store.save({'date':'2026-10-12','payee':'Shop','amount':'NaN'})

def test_automation_routes_text_without_overwriting(tmp_path):
    source=tmp_path/'invoice.pdf';pdf(source);target=tmp_path/'client';target.mkdir();before=source.read_bytes()
    rules=[{'name':'Invoices','kind':'Tekst PDF','match':'customer','target':str(target),'enabled':True}]
    result=route_documents([source],rules);assert result[0][1]=='Invoices' and Path(result[0][2]).exists()
    assert source.read_bytes()==before
    second=route_documents([source],rules);assert second[0][2]!=result[0][2]

def test_real_qr_recognition(tmp_path):
    import zxingcpp
    from PIL import Image
    barcode=zxingcpp.create_barcode('CLIENT-2026',zxingcpp.BarcodeFormat.QRCode)
    bitmap=zxingcpp.write_barcode_to_image(barcode,scale=5)
    image=Image.fromarray(bitmap);source=tmp_path/'qr.pdf'
    import io
    data=io.BytesIO();image.save(data,format='PNG')
    with pymupdf.open() as doc:
        page=doc.new_page();page.insert_image(pymupdf.Rect(100,100,350,350),stream=data.getvalue());doc.save(source)
    result=barcode_pdf(source);assert any(r['text']=='CLIENT-2026' for r in result)

def test_scan_profile_blank_omission(tmp_path):
    source=tmp_path/'scan.pdf';output=tmp_path/'profile.pdf'
    with pymupdf.open() as doc:doc.new_page();doc.new_page().insert_text((30,40),'Visible text on scan');doc.save(source)
    profile={'dpi':100,'color':'Szarość','omit_blank':True,'rotation':0}
    prepare_scan(source,output,profile)
    with pymupdf.open(output) as doc:assert len(doc)==1

def test_workspace_panels_and_settings(qapp):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.ui.settings_center import SettingsCenter
    window=MainWindow();window.show()
    assert window._shell.tabs.count()==8
    window._shell.tabs.setCurrentIndex(1);assert window._workspace_stack.currentWidget()==window._inbox_page
    window._shell.tabs.setCurrentIndex(6);assert window._workspace_stack.currentWidget()==window._receipts_page
    window._shell.tabs.setCurrentIndex(7);assert window._workspace_stack.currentWidget()==window._automation_page
    dialog=SettingsCenter(window);assert dialog.navigation.count()==10;dialog.close();window.close()

def test_closed_working_copy_and_backup_are_encrypted(qapp,tmp_path):
    from pdfmanager.dms.recovery import WorkingCopy,recoverable
    from pdfmanager.security.cache import crypt_file
    source=tmp_path/'source.pdf';pdf(source,'Original sensitive document')
    copy=WorkingCopy(source,tmp_path/'recovery');pdf(copy.path,'Edited sensitive document');copy.changed();copy.save()
    backups=list((tmp_path/'backups').glob('*.pdm'));assert len(backups)==1
    assert backups[0].read_bytes().startswith(b'PDMENC1')
    restored=tmp_path/'restored.pdf';crypt_file(backups[0],restored,decrypt=True)
    with pymupdf.open(restored) as doc:assert 'Original sensitive' in doc[0].get_text()
    pdf(copy.path,'Unsaved private edit');copy.changed();copy.close()
    assert copy.path.suffix=='.pdm' and copy.path.read_bytes().startswith(b'PDMENC1')
    assert recoverable(tmp_path/'recovery')[0][0]==copy.path
    tampered=tmp_path/'tampered.pdm';data=bytearray(copy.path.read_bytes());data[-20]^=1;tampered.write_bytes(data)
    with pytest.raises(Exception):crypt_file(tampered,tmp_path/'must-not-exist.pdf',decrypt=True)
    assert not (tmp_path/'must-not-exist.pdf').exists()

def test_render_input_and_attachment_limits(tmp_path):
    from pdfmanager.pdf_engine.extended_ops import export_images
    source=tmp_path/'large.pdf'
    with pymupdf.open() as doc:doc.new_page(width=10000,height=10000);doc.save(source)
    with pytest.raises(ValueError,match='limit 20'):export_images(source,tmp_path/'out',[0],600)

def test_windows_antivirus_failure_blocks_processing(tmp_path,monkeypatch):
    import pdfmanager.security.antivirus as av
    import pdfmanager.dms.jobs as jobs
    from subprocess import CompletedProcess
    source=tmp_path/'source.pdf';pdf(source)
    # Patch module OS locally without changing pathlib's global platform.
    class WindowsOS:
        name='nt';environ={}
    monkeypatch.setattr(av,'os',WindowsOS())
    monkeypatch.setattr(av,'executable',lambda:Path('MpCmdRun.exe'))
    monkeypatch.setattr(jobs,'run_process',lambda *a,**k:CompletedProcess(a[0],2,'',''))
    with pytest.raises(ValueError,match='zablokowane'):av.scan(source)


def test_secret_recovery_opens_without_leaving_decrypted_temp(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.dms.recovery import WorkingCopy
    source=tmp_path/'source.pdf';pdf(source);copy=WorkingCopy(source,tmp_path/'recovery');pdf(copy.path,'Unsaved recovered text');copy.changed();copy.close()
    window=MainWindow();window._open_secure_copy(copy.path);viewer=window._current_viewer()
    assert viewer is not None and viewer.require_save_as
    assert not viewer.source_path.exists()
    assert 'Unsaved recovered' in '\n'.join(call('document.texts',viewer.path))
    window.close()

def test_legacy_migration_skips_active_session(qapp,tmp_path,monkeypatch):
    import json,os
    import pdfmanager.dms.recovery as recovery
    from pdfmanager.security.cache import migrate_legacy_storage
    monkeypatch.setattr(recovery,'data_dir',lambda:tmp_path)
    backups=tmp_path/'backups';backups.mkdir();pdf(backups/'older.pdf')
    active=tmp_path/'recovery/active';active.mkdir(parents=True);pdf(active/'active.pdf')
    (active/'session.json').write_text(json.dumps({'pid':os.getpid(),'file':'active.pdf','dirty':True}))
    count,errors=migrate_legacy_storage();assert count==1 and not errors
    assert (active/'active.pdf').exists() and (backups/'older.pdf.pdm').exists() and not (backups/'older.pdf').exists()

def test_barcode_separators_keep_every_page(tmp_path):
    import zxingcpp,io
    from PIL import Image
    from pdfmanager.pdf_engine.utilities import split_by_codes
    source=tmp_path/'separators.pdf'
    with pymupdf.open() as doc:
        for text in ('CLIENT-A',None,'CLIENT-B',None):
            page=doc.new_page()
            if text:
                image=Image.fromarray(zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(text,zxingcpp.BarcodeFormat.QRCode),scale=5));data=io.BytesIO();image.save(data,format='PNG');page.insert_image(pymupdf.Rect(100,100,350,350),stream=data.getvalue())
            else:page.insert_text((30,40),'Document contents')
        doc.save(source)
    results=split_by_codes(source,tmp_path)
    assert len(results)==2
    assert [len(pymupdf.open(path)) for path in results]==[2,2]

def test_both_comparison_panes_remain_visible(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from PySide6.QtTest import QTest
    a=tmp_path/'a.pdf';b=tmp_path/'b.pdf';pdf(a,'First');pdf(b,'Second')
    window=MainWindow();window.resize(1500,900);window.show();window.open_document(str(a));window.open_document(str(b));window._toggle_compare_pane();QTest.qWait(50)
    assert window._content_splitter.count()==5
    assert window._content_splitter.sizes()[-1]>100 and window._content_splitter.sizes()[-2]>100
    window._shell.tabs.setCurrentIndex(2);window._shell.tabs.setCurrentIndex(3)
    assert window._content_splitter.sizes()[-1]>100
    window.close()

def test_camera_image_without_print_dpi_fits_paper(tmp_path):
    from PIL import Image
    from pdfmanager.pdf_engine.workflows import merge_inputs
    image=tmp_path/'camera.jpg';Image.new('RGB',(1600,2400),'white').save(image,dpi=(72,72));output=tmp_path/'camera.pdf';merge_inputs([image],output)
    with pymupdf.open(output) as doc:assert doc[0].rect.width<=595.1 and doc[0].rect.height<=842.1
