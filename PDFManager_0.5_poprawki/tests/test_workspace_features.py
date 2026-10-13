from pathlib import Path
from unittest.mock import patch
import pymupdf
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtPrintSupport import QPrinter
from pdfmanager.ui.main_window import MainWindow
from pdfmanager.ui.printing import paint_document
from pdfmanager.ui.background_job import run_job
from pdfmanager.ui.vector_icons import vector_icon
from pdfmanager.ui.theme import apply_theme
from pdfmanager.cli import main as cli_main


def pdf(path,label='hello'):
    with pymupdf.open() as doc:
        for i in range(3):
            page=doc.new_page(width=300,height=400);page.insert_text((40,60),label)
        doc.save(path)


def test_views_comparison_and_workspace(qapp,tmp_path):
    apply_theme(qapp,'light')
    a=tmp_path/'a.pdf';b=tmp_path/'b.pdf';pdf(a);pdf(b,'world')
    win=MainWindow();win.show();win.open_document(str(a));win.open_document(str(b))
    assert win._shell.tabs.count()==8
    viewer=win._current_viewer()
    for mode in ('continuous','two','book','grid'):
        viewer.set_view_mode(mode)
        # Rasterization now runs in the background; wait for its delivered result.
        import time
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and not any(not viewer._multi_view.item(i).icon().isNull() for i in range(viewer._multi_view.count())):QTest.qWait(20)
        assert viewer._page_views.currentWidget()==viewer._multi_view
        assert any(not viewer._multi_view.item(i).icon().isNull() for i in range(viewer._multi_view.count()))
    viewer.set_view_mode('single');original=viewer._image_label.pixmap().toImage().pixelColor(0,0)
    viewer.toggle_night_mode();assert viewer._image_label.pixmap().toImage().pixelColor(0,0)!=original
    win._toggle_compare_pane();assert win._compare_viewer is not None
    assert win._compare_viewer.path!=a and win._compare_viewer.path!=b
    win._toggle_compare_pane();assert win._compare_viewer is None
    win._shell.tabs.setCurrentIndex(0);assert win._workspace_stack.currentWidget()==win._home_page
    win._shell.tabs.setCurrentIndex(5);assert win._workspace_stack.currentWidget()==win._search_page
    win.close()


def test_print_to_pdf_honors_range(qapp,tmp_path):
    source=tmp_path/'source.pdf';pdf(source);output=tmp_path/'printed.pdf'
    printer=QPrinter(QPrinter.PrinterMode.HighResolution);printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output));printer.setFromTo(2,3)
    paint_document(printer,source)
    with pymupdf.open(output) as doc:
        assert len(doc)==2
        assert doc[0].get_images()


def test_worker_callback_and_error(qapp):
    win=MainWindow();results=[]
    run_job(win,'Test',lambda:42,results.append)
    assert results==[42]
    def fail():raise ValueError('EXPECTED ERROR')
    with patch('pdfmanager.ui.background_job.QMessageBox.critical') as critical:
        run_job(win,'Test',fail);assert critical.call_args.args[-1]=='EXPECTED ERROR'
    win.close()


def test_icons_are_independent_vectors(qapp):
    for name in ('open','save','scan','image','ocr','search','rectangle','circle','help','print','ink','redact','home'):
        assert not vector_icon(name).isNull()


def test_cli_exports_and_invalid_ranges(tmp_path):
    source=tmp_path/'source.pdf';pdf(source)
    out=tmp_path/'selected.pdf'
    with patch('pdfmanager.licensing.license_manager.get_default_license_manager') as manager:
        manager.return_value.get_status.return_value.is_blocked=False
        assert cli_main(['extract-pages',str(source),'1,3',str(out)])==0
        with pymupdf.open(out) as doc:assert len(doc)==2
        assert cli_main(['extract-pages',str(source),'9',str(tmp_path/'invalid.pdf')])==1
        assert not (tmp_path/'invalid.pdf').exists()


def test_cli_preserves_license_gate(tmp_path):
    with patch('pdfmanager.licensing.license_manager.get_default_license_manager') as manager:
        manager.return_value.get_status.return_value.is_blocked=True
        assert cli_main(['text',str(tmp_path/'x.pdf'),str(tmp_path/'x.txt')])==1
        assert not (tmp_path/'x.txt').exists()


def test_cli_print_to_pdf(qapp,tmp_path):
    source=tmp_path/'source.pdf';pdf(source);output=tmp_path/'printed.pdf'
    with patch('pdfmanager.licensing.license_manager.get_default_license_manager') as manager:
        manager.return_value.get_status.return_value.is_blocked=False
        assert cli_main(['print',str(source),'--output',str(output),'--pages','1,3'])==0
    with pymupdf.open(output) as doc:assert len(doc)==2


def test_sidebar_can_dock_both_sides(qapp,tmp_path):
    source=tmp_path/'source.pdf';pdf(source)
    win=MainWindow();win.open_document(str(source));viewer=win._current_viewer()
    assert viewer._viewer_splitter.indexOf(viewer._thumbnails)==0
    viewer.toggle_sidebar_side();assert viewer._viewer_splitter.indexOf(viewer._thumbnails)==1
    viewer.toggle_sidebar_side();assert viewer._viewer_splitter.indexOf(viewer._thumbnails)==0
    win.close()
