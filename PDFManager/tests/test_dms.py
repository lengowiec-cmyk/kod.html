from pathlib import Path
import pymupdf
import pytest
from PIL import Image
from PySide6.QtCore import QSettings
from pdfmanager.dms.cabinets import CabinetStore,validate_relative
from pdfmanager.dms.scanning import import_scans
from pdfmanager.dms.files import batch_split

@pytest.mark.parametrize('value',['../outside','C:\\escape','CON','NUL.txt','folder.','a/b/../../x','bad:name','\\\\server\\share'])
def test_reject_windows_unsafe_paths(value):
    with pytest.raises(ValueError):validate_relative(value)

def test_cabinet_template_and_existing_client(tmp_path):
    store=CabinetStore(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat))
    root=tmp_path/'cabinet';root.mkdir();store.add('Klienci',root)
    assert store.read()[0]['root']==str(root)
    store.save_template('Własny',['Umowy/2026','Faktury'])
    client=store.create_client(root,'Firma','Własny')
    assert (client/'Umowy/2026').is_dir()
    (client/'important.txt').write_text('preserve')
    with pytest.raises(FileExistsError):store.create_client(root,'Firma','Własny')
    assert (client/'important.txt').read_text()=='preserve'
    assert CabinetStore(QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)).templates()['Własny']==['Umowy/2026','Faktury']

def test_scan_multiframe_order_and_no_overwrite(tmp_path):
    source=tmp_path/'scan.tiff';frames=[Image.new('RGB',(100,150),color) for color in ('red','blue')]
    frames[0].save(source,save_all=True,append_images=frames[1:])
    before=source.read_bytes();output=import_scans([source],tmp_path,'result.pdf')
    with pymupdf.open(output) as doc:
        assert len(doc)==2
        assert doc[0].get_pixmap().pixel(10,10)[0]>200
        assert doc[1].get_pixmap().pixel(10,10)[2]>200
    with pytest.raises(FileExistsError):import_scans([source],tmp_path,'result.pdf')
    assert source.read_bytes()==before

def test_batch_split_partial_failure_and_rerun(tmp_path):
    source=tmp_path/'source.pdf'
    with pymupdf.open() as doc:
        for i in range(5):doc.new_page().insert_text((40,50),str(i))
        doc.save(source)
    before=source.read_bytes();broken=tmp_path/'broken.pdf';broken.write_text('not PDF')
    results=batch_split([source,broken],tmp_path,2)
    assert len(results[0][1])==3 and results[1][2]
    with pymupdf.open(results[0][1][-1]) as doc:assert len(doc)==1
    assert source.read_bytes()==before
    assert batch_split([source],tmp_path,2)[0][1][0]!=results[0][1][0]

def test_copy_move_conflicts_preserve_files(tmp_path):
    from pdfmanager.dms.files import transfer_file
    a=tmp_path/'a.pdf';b=tmp_path/'b.pdf';a.write_bytes(b'original');b.write_bytes(b'existing')
    with pytest.raises(FileExistsError):transfer_file(a,b,move=True)
    assert a.read_bytes()==b'original' and b.read_bytes()==b'existing'
    c=tmp_path/'c.pdf';transfer_file(a,c,move=True)
    assert not a.exists() and c.read_bytes()==b'original'

def test_name_and_content_search(tmp_path):
    from pdfmanager.dms.search import search_files
    source=tmp_path/'invoice.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((40,50),'Customer contract');doc.save(source)
    assert search_files(tmp_path,'INVOICE',fulltext=False)[0][0][1]==-1
    assert search_files(tmp_path,'Customer',fulltext=False)[0]==[]
    assert search_files(tmp_path,'Customer',fulltext=True)[0][0][1]==0
    (tmp_path/'broken.pdf').write_text('not PDF')
    assert len(search_files(tmp_path,'Customer',fulltext=True)[1])==1

def test_cabinet_search_root_and_embedded_preview(qapp,tmp_path):
    from pdfmanager.ui.main_window import MainWindow
    from pdfmanager.app_settings import settings
    root=tmp_path/'cabinet';child=root/'client';child.mkdir(parents=True)
    win=MainWindow();win.show()
    win._cabinet_tools.active={'name':'Clients','root':str(root)}
    win._folder_tree.set_cabinet_root(str(root))
    win._on_folder_selected(str(child))
    assert not win._viewer_stack.isHidden()
    win._cabinet_tools.search_cabinet()
    assert win._search_page.folder.text()==str(root)
    assert win._search_page.recursive.isChecked()
    assert not win._search_page.fulltext.isChecked()
    win.close()
