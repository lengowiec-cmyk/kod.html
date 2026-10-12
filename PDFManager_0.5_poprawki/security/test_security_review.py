"""Safe audit fixtures: no malware and no real executable launching."""
from pathlib import Path
from unittest.mock import patch
import zipfile
import pymupdf
import pytest
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtGui import QDesktopServices
from pdfmanager.pdf_engine.workflows import merge_inputs
from pdfmanager.pdf_engine.extended_ops import export_images
from pdfmanager.pdf_engine.render import PdfDocument
from pdfmanager.ui.document_list import DocumentListView
from pdfmanager.ui.search_panel import SearchPanel


@pytest.fixture(scope='module')
def qapp():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    yield app

def make_pdf(path,width=595,height=842):
    with pymupdf.open() as doc:
        doc.new_page(width=width,height=height).insert_text((30,40),'Audit fixture')
        doc.save(path)


def test_zip_member_path_is_not_extracted(tmp_path):
    source=tmp_path/'input.pdf';make_pdf(source)
    archive=tmp_path/'input.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside/security-audit.pdf',source.read_bytes())
    output=tmp_path/'merged.pdf';merge_inputs([archive],output)
    assert not (tmp_path.parent/'outside/security-audit.pdf').exists()
    with pymupdf.open(output) as doc:assert len(doc)==1


def test_pdf_javascript_action_is_not_executed_during_render(tmp_path):
    path=tmp_path/'active.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page();page.insert_text((30,40),'Harmless active-content fixture')
        action=doc.get_new_xref();doc.update_object(action,'<< /S /JavaScript /JS (app.alert\\(\\"audit fixture\\"\\)) >>')
        doc.xref_set_key(doc.pdf_catalog(),'OpenAction',f'{action} 0 R');doc.save(path)
    with patch.object(QDesktopServices,'openUrl') as opened:
        with PdfDocument(path) as doc:assert not doc.render_page(0).isNull()
        assert not opened.called


def test_large_export_is_rejected_before_allocation(tmp_path):
    path=tmp_path/'huge-page.pdf';make_pdf(path,10000,10000)
    with pytest.raises(ValueError,match='limit 20'):
        export_images(path,tmp_path/'images',[0],600)


def test_document_list_blocks_executable(qapp,tmp_path):
    # Empty dummy file, and the OS launch API is mocked.
    path=tmp_path/'audit-dummy.exe';path.write_bytes(b'')
    view=DocumentListView();view.show_folder(str(tmp_path))
    loop=QEventLoop();QTimer.singleShot(150,loop.quit);loop.exec()
    index=view._model.index(str(path));assert index.isValid()
    with patch.object(QDesktopServices,'openUrl',return_value=True) as opened,patch('pdfmanager.security.opening.QMessageBox.warning') as warning:
        view._on_double_clicked(index)
        assert not opened.called and warning.called
    view.close()


def test_search_result_blocks_executable(qapp,tmp_path):
    from PySide6.QtWidgets import QTreeWidgetItem
    from PySide6.QtCore import Qt
    path=tmp_path/'audit-dummy.exe';path.write_bytes(b'')
    panel=SearchPanel();item=QTreeWidgetItem([path.name])
    item.setData(0,Qt.UserRole,(str(path),-1))
    with patch.object(QDesktopServices,'openUrl',return_value=True) as opened,patch('pdfmanager.security.opening.QMessageBox.warning') as warning:
        panel.open_result(item,0);assert not opened.called and warning.called
    panel.close()
