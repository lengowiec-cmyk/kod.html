
from pdfmanager.security.limits import safe_open
"""Qt print preview/printing: honor page range, orientation and printable area."""
from pathlib import Path
import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtPrintSupport import QPrinter
from pdfmanager.pdf_engine.render import render_page_to_qimage


def paint_document(printer: QPrinter, source: Path, selected_indices: list[int] | None = None) -> None:
    painter=QPainter()
    if not painter.begin(printer):raise RuntimeError('Nie można rozpocząć drukowania.')
    try:
        from pdfmanager.pdf_engine.render import PdfDocument
        with PdfDocument(source) as doc:
            start=max(0,printer.fromPage()-1) if printer.fromPage() else 0
            end=min(doc.page_count,printer.toPage()) if printer.toPage() else doc.page_count
            indices=selected_indices if selected_indices is not None else list(range(start,end))
            if printer.pageOrder()==QPrinter.PageOrder.LastPageFirst:indices.reverse()
            for n,i in enumerate(indices):
                if n and not printer.newPage():raise RuntimeError('Nie można rozpocząć kolejnej strony wydruku.')
                image=doc.render_page(i,zoom=300/72)
                area=printer.pageRect(QPrinter.Unit.DevicePixel)
                scaled=image.size().scaled(area.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
                x=area.x()+(area.width()-scaled.width())/2;y=area.y()+(area.height()-scaled.height())/2
                painter.drawImage(int(x),int(y),image.scaled(scaled,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    finally:painter.end()
