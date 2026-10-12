from PySide6.QtTest import QTest
import pymupdf
from pdfmanager.ui.main_window import MainWindow
from pdfmanager.ui.viewer import PdfViewerWidget


def test_ribbon_and_thumbnail_navigation(qapp, tmp_path):
    path = tmp_path/'pages.pdf'
    with pymupdf.open() as doc:
        for i in range(3):
            page = doc.new_page()
            page.insert_text((50, 50), f'Page {i+1}')
        doc.save(path)
    win = MainWindow()
    win.open_document(str(path))
    viewer = win._current_viewer()
    assert isinstance(viewer, PdfViewerWidget)
    assert viewer._thumbnails.count() == 3
    viewer._thumbnails.setCurrentRow(2)
    assert viewer.current_page == 2
    assert viewer._page_input.value() == 3
    viewer._page_input.setValue(1)
    assert viewer.current_page == 0
    QTest.qWait(1500)
    assert all(not viewer._thumbnails.item(i).icon().isNull() for i in range(3))
    assert all(action.isEnabled() for action in win._extended_actions)
    viewer.release_document()
    with pymupdf.open(viewer.path) as doc:
        doc.delete_page(2)
        data = doc.tobytes()
    viewer.path.write_bytes(data)
    viewer.reload_document()
    assert viewer._thumbnails.count() == 2
    win.close()
