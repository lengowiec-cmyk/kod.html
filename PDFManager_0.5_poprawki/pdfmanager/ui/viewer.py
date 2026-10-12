"""Widżet podglądu jednego dokumentu PDF (jedna karta w QTabWidget)."""
from __future__ import annotations

from pdfmanager.security.limits import safe_open

from pathlib import Path
from typing import Callable, TypeVar

from PySide6.QtCore import QPoint, Qt, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap, QIcon, QPainter, QColor, QPen
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QSplitter, QHBoxLayout, QToolButton, QSpinBox, QStackedWidget, QApplication, QMessageBox, QInputDialog

from pdfmanager.pdf_engine import annotations
from pdfmanager.pdf_engine.annotations import AnnotationInfo
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
from pdfmanager.pdf_engine.render import DEFAULT_DPI, PdfDocument
from pdfmanager.pdf_engine.text_edit import EditResult, TextSpan, get_default_text_edit_engine

ZOOM_MIN = 25
ZOOM_MAX = 400
ZOOM_STEP_FACTOR = 1.25
POINTS_PER_INCH = 72.0
MAX_UNDO_HISTORY = 20
MIN_DRAG_DISTANCE_PT = 2.0

T = TypeVar("T")

# Narzędzia aktywne w podglądzie — tylko jedno naraz (patrz MainWindow, QActionGroup).
TOOL_SELECT = "select"
TOOL_EDIT_TEXT = "edit_text"
TOOL_HIGHLIGHT = "highlight"
TOOL_UNDERLINE = "underline"
TOOL_STRIKEOUT = "strikeout"
TOOL_NOTE = "note"
TOOL_FREE_TEXT = "free_text"
TOOL_RECTANGLE = "rectangle"
TOOL_CIRCLE = "circle"
TOOL_LINE = "line"
TOOL_STAMP = "stamp"
TOOL_DELETE_ANNOTATION = "delete_annotation"

_DRAG_TOOLS = {
    TOOL_HIGHLIGHT,
    TOOL_UNDERLINE,
    TOOL_STRIKEOUT,
    TOOL_FREE_TEXT,
    TOOL_RECTANGLE,
    TOOL_CIRCLE,
    TOOL_LINE,
    TOOL_STAMP,
    'place_content', 'move_content', 'scale_content', 'redact', 'copy_region', 'ocr_region', 'polygon', 'arrow',
}
_CLICK_TOOLS = {TOOL_EDIT_TEXT, TOOL_NOTE, TOOL_DELETE_ANNOTATION}


class _PageImageLabel(QLabel):
    """QLabel strony PDF zgłaszający kliknięcia i przeciągnięcia (piksele obrazu)."""

    clicked_at = Signal(QPoint)
    drag_finished = Signal(QPoint, QPoint)
    stroke_finished = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._press_point: QPoint | None = None
        self.trace_ink = False
        self.drag_preview=False
        self._drag_current=None
        self._stroke = []

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_point = event.position().toPoint()
            self._stroke = [self._press_point]
            self._drag_current=self._press_point
            self.clicked_at.emit(self._press_point)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_point is not None:
            if self.trace_ink:
                self._stroke.append(event.position().toPoint())
                self.stroke_finished.emit(self._stroke[:])
            else:
                self.drag_finished.emit(self._press_point, event.position().toPoint())
            self._stroke = []
            self.update()
            self._press_point = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag_preview and self._press_point is not None:
            self._drag_current=event.position().toPoint();self.update()
        if self.trace_ink and self._press_point is not None:
            self._stroke.append(event.position().toPoint());self.update()
        super().mouseMoveEvent(event)

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.drag_preview and self._press_point is not None and self._drag_current is not None and not self.trace_ink:
            from PySide6.QtCore import QRect
            painter=QPainter(self);painter.setPen(QPen(QColor('#286fad'),1,Qt.DashLine))
            painter.drawRect(QRect(self._press_point,self._drag_current).normalized());painter.end()
        if self.trace_ink and self._stroke:
            painter=QPainter(self);painter.setPen(QPen(QColor('#286fad'),2))
            for a,b in zip(self._stroke,self._stroke[1:]):painter.drawLine(a,b)
            painter.end()


class PdfViewerWidget(QWidget):
    """Renderuje i wyświetla strony jednego otwartego dokumentu PDF."""

    ocr_region_requested = Signal(tuple)
    state_changed = Signal()  # emitowany po zmianie strony/zoomu — do status bara
    load_failed = Signal(str, str)  # (ścieżka, komunikat błędu)
    edit_span_requested = Signal(object)  # TextSpan — kliknięto fragment tekstu w trybie edycji
    note_requested = Signal(tuple)  # (x, y) w punktach PDF — potrzebny tekst notatki od użytkownika
    free_text_requested = Signal(tuple)  # (x0, y0, x1, y1) w punktach PDF — potrzebny tekst
    undo_redo_changed = Signal()
    document_saved = Signal()  # emitowany po każdym pomyślnym zapisie (edycja/adnotacja/cofnij/powtórz)

    def __init__(self, path: str, parent=None, *, safe_edit=False, working_copy=None) -> None:
        super().__init__(parent)
        self.pending_content=None
        self.source_path = Path(path).resolve()
        # `working_copy` pozwala wywołującemu (MainWindow.open_document) utworzyć
        # WorkingCopy wcześniej, w tle, dla dużych plików — patrz komentarz przy
        # _ASYNC_OPEN_THRESHOLD w main_window.py. `safe_edit=True` bez podanej
        # kopii zachowuje dawne, synchroniczne tworzenie (np. w testach).
        self.working_copy = working_copy
        if safe_edit and self.working_copy is None:
            from pdfmanager.dms.recovery import WorkingCopy
            self.working_copy=WorkingCopy(path)
        self.path = self.working_copy.path if self.working_copy else Path(path)
        self.current_page = 0
        self.zoom_percent = 100
        self.view_mode = "single"
        self.night_mode = False
        self.annotation_color = (0.1, 0.3, 0.7)
        self.annotation_width = 2.0
        self.search_query = ""
        self.active_tool = TOOL_SELECT
        self.stamp_image_path: Path | None = None
        # Ustawiane przez MainWindow, gdy dokument został otwarty z Google
        # Dysku (Workflow A) — niesie id pliku, metadane „bazowe” do
        # wykrywania konfliktu wersji i klienta API. None = plik czysto
        # lokalny (albo z lokalnego folderu zsynchronizowanego, Workflow B).
        self.drive_info = None
        self._doc: PdfDocument | None = None
        self._text_engine = get_default_text_edit_engine()
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll_area.setWidgetResizable(False)
        self._image_label = _PageImageLabel(self)
        self._image_label.clicked_at.connect(self._on_image_clicked)
        self._image_label.drag_finished.connect(self._on_image_drag_finished)
        self._image_label.stroke_finished.connect(self._on_ink_stroke)
        self._scroll_area.setWidget(self._image_label)
        self._thumbnails = QListWidget(self)
        self._thumbnails.setObjectName('PageThumbnails')
        self._thumbnails.setViewMode(QListWidget.ViewMode.IconMode)
        self._thumbnails.setFlow(QListWidget.Flow.TopToBottom)
        self._thumbnails.setWrapping(False)
        self._thumbnails.setMovement(QListWidget.Movement.Static)
        self._thumbnails.setIconSize(QSize(90, 120))
        self._thumbnails.setMinimumWidth(110)
        self._thumbnails.setMaximumWidth(230)
        self._thumbnails.currentRowChanged.connect(self.go_to_page)
        splitter = QSplitter(self)
        self._viewer_splitter = splitter
        splitter.addWidget(self._thumbnails)
        self._page_views=QStackedWidget(self)
        self._page_views.addWidget(self._scroll_area)
        self._multi_view=QListWidget(self)
        self._multi_view.setViewMode(QListWidget.ViewMode.IconMode)
        self._multi_view.setMovement(QListWidget.Movement.Static)
        self._multi_view.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._multi_view.setSpacing(6)
        self._multi_view.itemDoubleClicked.connect(self._activate_multi_page)
        self._multi_view.verticalScrollBar().valueChanged.connect(lambda _:self._queue_multi_render())
        self._multi_view.horizontalScrollBar().valueChanged.connect(lambda _:self._queue_multi_render())
        self._page_views.addWidget(self._multi_view)
        splitter.addWidget(self._page_views)
        splitter.setSizes([125, 900])
        layout.addWidget(splitter)
        from pdfmanager.ui.vector_icons import vector_icon
        footer = QHBoxLayout()
        footer.addStretch()
        for label, callback in [('⏮', lambda: self.go_to_page(0)), ('◀', self.prev_page)]:
            button = QToolButton(self)
            button.setIcon(vector_icon({'⏮':'first','◀':'previous','▶':'next','⏭':'last'}[label],18))
            button.setToolTip(label)
            button.clicked.connect(callback)
            footer.addWidget(button)
        self._page_input = QSpinBox(self)
        self._page_input.setMinimum(1)
        self._page_input.valueChanged.connect(lambda n: self.go_to_page(n-1))
        footer.addWidget(self._page_input)
        self._page_total = QLabel(self)
        footer.addWidget(self._page_total)
        for label, callback in [('▶', self.next_page), ('⏭', lambda: self.go_to_page(self.page_count-1))]:
            button = QToolButton(self)
            button.setIcon(vector_icon({'⏮':'first','◀':'previous','▶':'next','⏭':'last'}[label],18))
            button.setToolTip(label)
            button.clicked.connect(callback)
            footer.addWidget(button)
        footer.addStretch()
        layout.addLayout(footer)
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.timeout.connect(self._render_next_thumbnail)
        self._thumbnail_cursor = 0

        self.load_error=''
        try:
            self._doc = PdfDocument(self.path)
            self._refresh_thumbnails()
            self._render_current_page()
        except Exception as exc:
            self.load_error=str(exc)
            self._thumbnail_timer.stop()
            if self._doc:self._doc.close()
            self._doc=None
            self.load_failed.emit(str(self.path),self.load_error)
            return

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    @property
    def is_loaded(self) -> bool:
        return self._doc is not None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def edit_mode(self) -> bool:
        return self.active_tool == TOOL_EDIT_TEXT

    def set_edit_mode(self, enabled: bool) -> None:
        self.set_active_tool(TOOL_EDIT_TEXT if enabled else TOOL_SELECT)

    def set_active_tool(self, tool: str) -> None:
        if tool != TOOL_SELECT and self.view_mode != 'single':
            self.set_view_mode('single')
        self.active_tool = tool
        self._image_label.drag_preview=tool in _DRAG_TOOLS
        self._image_label.trace_ink = tool == 'ink' 
        if tool == TOOL_EDIT_TEXT:
            cursor = Qt.CursorShape.IBeamCursor
        elif tool == TOOL_NOTE:
            cursor = Qt.CursorShape.PointingHandCursor
        elif tool == TOOL_DELETE_ANNOTATION:
            cursor = Qt.CursorShape.ForbiddenCursor
        elif tool in _DRAG_TOOLS:
            cursor = Qt.CursorShape.CrossCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self._image_label.setCursor(cursor)

    def _effective_zoom_matrix_scale(self) -> float:
        scale=(DEFAULT_DPI / POINTS_PER_INCH) * (self.zoom_percent / 100.0)
        if self._doc:
            from pdfmanager.pdf_engine.render import safe_render_scale
            width,height=self._doc.page_size_points(self.current_page)
            scale=safe_render_scale(width,height,scale)
        return scale

    def _to_pdf_point(self, point: QPoint) -> tuple[float, float]:
        scale = self._effective_zoom_matrix_scale()
        return self._doc.unrotate_point(self.current_page,point.x()/scale,point.y()/scale) if self._doc else (point.x()/scale,point.y()/scale)

    def _page_icon(self,image):
        pixmap=QPixmap.fromImage(image);icon=QIcon()
        for mode in (QIcon.Mode.Normal,QIcon.Mode.Selected,QIcon.Mode.Active):
            icon.addPixmap(pixmap,mode,QIcon.State.Off)
        return icon

    def _refresh_thumbnails(self):
        self._thumbnail_timer.stop()
        self._thumbnails.blockSignals(True)
        self._thumbnails.clear()
        for i in range(self.page_count):
            item = QListWidgetItem(str(i+1), self._thumbnails)
            item.setSizeHint(QSize(105, 142))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnails.blockSignals(False)
        self._thumbnail_cursor = 0
        self._thumbnail_timer.start(15)

    def _render_next_thumbnail(self):
        if not self._doc or self._thumbnail_cursor >= self.page_count:
            self._thumbnail_timer.stop()
            return
        i = self._thumbnail_cursor
        width, height = self._doc.page_size_points(i)
        try:image = self._doc.render_page(i, min(90/width, 120/height))
        except Exception as exc:
            self._thumbnail_timer.stop();self.load_failed.emit(str(self.path),str(exc));return
        self._thumbnails.item(i).setIcon(self._page_icon(image))
        self._thumbnail_cursor += 1

    def _render_current_page(self) -> None:
        if self._doc is None:
            return
        image = self._doc.render_page(self.current_page, zoom=self._effective_zoom_matrix_scale())
        if self.night_mode:image.invertPixels()
        pixmap = QPixmap.fromImage(image)
        if self.search_query:
            painter=QPainter(pixmap);painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(255,205,50,95))
            for rect in self._doc.search_rects(self.current_page,self.search_query):
                from PySide6.QtCore import QRectF
                scale=self._effective_zoom_matrix_scale()
                painter.drawRect(QRectF(rect[0]*scale,rect[1]*scale,(rect[2]-rect[0])*scale,(rect[3]-rect[1])*scale))
            painter.end()
        self._image_label.setPixmap(pixmap)
        self._image_label.resize(pixmap.size())
        self._page_input.blockSignals(True)
        self._page_input.setMaximum(self.page_count)
        self._page_input.setValue(self.current_page+1)
        self._page_input.blockSignals(False)
        self._page_total.setText(f'of {self.page_count}')
        self._thumbnails.blockSignals(True)
        self._thumbnails.setCurrentRow(self.current_page)
        self._thumbnails.blockSignals(False)
        if self.view_mode != "single":self._setup_multi_view()
        self.state_changed.emit()

    def toggle_sidebar_side(self):
        current=self._viewer_splitter.indexOf(self._thumbnails)
        self._viewer_splitter.insertWidget(1 if current==0 else 0,self._thumbnails)

    def set_view_mode(self,mode):
        if mode not in ('single','continuous','two','book','grid'):
            raise ValueError('Nieznany tryb podglądu.')
        self.view_mode=mode
        self._page_views.setCurrentIndex(0 if mode=='single' else 1)
        if mode!='single':self._setup_multi_view()
        self.state_changed.emit()

    def toggle_night_mode(self):
        self.night_mode=not self.night_mode
        self._render_current_page()

    def show_search(self,query):
        self.search_query=query
        self._render_current_page()

    def _setup_multi_view(self):
        if not self._doc:return
        self._multi_view.clear()
        if self.view_mode in ('two','book'):
            first=self.current_page//2*2 if self.view_mode=='two' else (0 if self.current_page==0 else 1+(self.current_page-1)//2*2)
            indices=list(range(first,min(first+2,self.page_count)))
        else:indices=range(self.page_count)
        if self.view_mode=='grid':width,height=140,190
        elif self.view_mode in ('two','book'):width,height=max(140,self._page_views.width()//2-40),max(190,self._page_views.height()-50)
        else:width,height=max(200,self._page_views.width()-45),max(280,round((self._page_views.width()-45)*1.42))
        self._multi_view.setIconSize(QSize(width,height))
        self._multi_view.setFlow(QListWidget.Flow.TopToBottom if self.view_mode=='continuous' else QListWidget.Flow.LeftToRight)
        self._multi_view.setWrapping(self.view_mode=='grid')
        if self.view_mode=='book' and self.current_page==0:
            blank=QListWidgetItem('',self._multi_view);blank.setData(Qt.ItemDataRole.UserRole,None);blank.setSizeHint(QSize(width+15,height+25))
            indices=[0]
        for i in indices:
            item=QListWidgetItem(str(i+1),self._multi_view);item.setData(Qt.ItemDataRole.UserRole,i)
            item.setSizeHint(QSize(width+15,height+25));item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._queue_multi_render()

    def _queue_multi_render(self):
        QTimer.singleShot(0,self._render_visible_multi)

    def _render_visible_multi(self):
        if not self._doc or self.view_mode=='single':return
        viewport=self._multi_view.viewport().rect()
        icon_size=self._multi_view.iconSize()
        for row in range(self._multi_view.count()):
            item=self._multi_view.item(row);index=item.data(Qt.ItemDataRole.UserRole)
            visible=self._multi_view.visualItemRect(item).intersects(viewport)
            if index is None:continue
            if not visible:
                # Retain placeholders, release offscreen raster images.
                if not item.icon().isNull():item.setIcon(QIcon())
                continue
            if not item.icon().isNull():continue
            width,height=self._doc.page_size_points(index)
            scale=min(icon_size.width()/width,icon_size.height()/height)
            image=self._doc.render_page(index,scale)
            if self.night_mode:image.invertPixels()
            item.setIcon(self._page_icon(image))

    def _activate_multi_page(self,item):
        index=item.data(Qt.ItemDataRole.UserRole)
        if index is None:return
        self.set_view_mode('single');self.go_to_page(index)

    def _on_ink_stroke(self,points):
        from pdfmanager.pdf_engine.workflows import add_ink
        if self._doc is None or self.active_tool!='ink':return
        coordinates=[self._to_pdf_point(p) for p in points]
        try:self._mutate_file(lambda:add_ink(self.path,self.current_page,coordinates))
        except Exception as exc:QMessageBox.warning(self,'Rysowanie',str(exc))

    def go_to_page(self, page_index: int) -> None:
        if self._doc is None:
            return
        page_index = max(0, min(page_index, self._doc.page_count - 1))
        if page_index != self.current_page:
            self.current_page = page_index
            self._render_current_page()

    def next_page(self) -> None:
        self.go_to_page(self.current_page + 1)

    def prev_page(self) -> None:
        self.go_to_page(self.current_page - 1)

    def set_zoom(self, percent: int) -> None:
        percent = max(ZOOM_MIN, min(ZOOM_MAX, percent))
        if percent != self.zoom_percent:
            self.zoom_percent = percent
            self._render_current_page()

    def zoom_in(self) -> None:
        self.set_zoom(round(self.zoom_percent * ZOOM_STEP_FACTOR))

    def zoom_out(self) -> None:
        self.set_zoom(round(self.zoom_percent / ZOOM_STEP_FACTOR))

    def fit_width(self) -> None:
        if self._doc is None:
            return
        page_width_pt, _ = self._doc.page_size_points(self.current_page)
        viewport_width = self._scroll_area.viewport().width()
        page_width_px_at_100 = page_width_pt / POINTS_PER_INCH * DEFAULT_DPI
        if page_width_px_at_100 <= 0:
            return
        percent = round((viewport_width / page_width_px_at_100) * 100)
        self.set_zoom(percent)

    # --------------------------------------------------------- wejście myszy
    def _on_image_clicked(self, point: QPoint) -> None:
        if self._doc is None:return
        pdf_point = self._to_pdf_point(point)
        if self.active_tool == TOOL_SELECT:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            x,y=pdf_point
            for link in self._doc.links(self.current_page):
                x0,y0,x1,y1=link['from']
                if x0<=x<=x1 and y0<=y<=y1:
                    if link.get('page',-1)>=0:self.go_to_page(link['page'])
                    elif link.get('uri'):
                        url=QUrl(link['uri'])
                        if url.isValid() and url.scheme() in ('http','https') and url.host() and not url.userInfo():
                            encoded=bytes(url.toEncoded()).decode('ascii','replace')
                            if QMessageBox.question(self,'Link z dokumentu',f'Otworzyć zewnętrzną stronę?\n{encoded[:1800]}\nSprawdź adres przed podaniem danych.')==QMessageBox.Yes:QDesktopServices.openUrl(url)
                    return
            for annot in annotations.list_annotations(self.path,self.current_page):
                x0,y0,x1,y1=annot.rect
                if annot.type_name=='Text' and x0<=x<=x1 and y0<=y<=y1:
                    text,ok=QInputDialog.getMultiLineText(self,'Notatka','Treść:',annot.content)
                    if ok and text!=annot.content:self._mutate_file(lambda:annotations.update_note(self.path,self.current_page,annot.xref,text))
                    return
            return
        if self.active_tool not in _CLICK_TOOLS:return
        if self.active_tool == TOOL_EDIT_TEXT:
            self._handle_edit_text_click(pdf_point)
        elif self.active_tool == TOOL_NOTE:
            self.note_requested.emit(pdf_point)
        elif self.active_tool == TOOL_DELETE_ANNOTATION:
            self.delete_annotation_at(pdf_point)

    def _handle_edit_text_click(self, pdf_point: tuple[float, float]) -> None:
        pdf_x, pdf_y = pdf_point
        for span in self._text_engine.extract_spans(self.path, self.current_page):
            x0, y0, x1, y1 = span.bbox
            if x0 <= pdf_x <= x1 and y0 <= pdf_y <= y1:
                self.edit_span_requested.emit(span)
                return

    def _on_image_drag_finished(self, start: QPoint, end: QPoint) -> None:
        if self._doc is None or self.active_tool not in _DRAG_TOOLS:
            return
        p1 = self._to_pdf_point(start)
        p2 = self._to_pdf_point(end)
        rect = (min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
        if (rect[2] - rect[0]) < MIN_DRAG_DISTANCE_PT and (rect[3] - rect[1]) < MIN_DRAG_DISTANCE_PT:
            return  # zbyt małe przeciągnięcie — traktujemy jako nieumyślne kliknięcie

        if self.active_tool=='place_content' and self.pending_content:
            from pdfmanager.pdf_engine.content import insert_content_at
            import pymupdf
            options=self.pending_content
            display_rect=pymupdf.Rect(rect)*self._doc.rotation_matrix(self.current_page)
            try:
                self._mutate_file(lambda:insert_content_at(self.path,self.current_page,tuple(display_rect),**options))
                self.pending_content=None;self.set_active_tool(TOOL_SELECT)
            except Exception as exc:QMessageBox.warning(self,'Wstawianie',str(exc))
            return
        if self.active_tool in ('move_content','scale_content'):
            from pdfmanager.pdf_engine.content import inserted_objects,transform_inserted
            import pymupdf
            candidates=[item for item in inserted_objects(self.path,self.current_page) if pymupdf.Rect(item['rect']).contains(pymupdf.Point(p1))]
            if not candidates:return
            item=candidates[-1];old=pymupdf.Rect(item['rect'])
            if self.active_tool=='move_content':
                dx=p2[0]-p1[0];dy=p2[1]-p1[1];target=(old.x0+dx,old.y0+dy,old.x1+dx,old.y1+dy)
            else:
                # Drag within an element to set its bottom-right corner; aspect ratio is preserved.
                factor=max((p2[0]-old.x0)/old.width,(p2[1]-old.y0)/old.height)
                if factor<=0:return
                target=(old.x0,old.y0,old.x0+old.width*factor,old.y0+old.height*factor)
            try:self._mutate_file(lambda:transform_inserted(self.path,self.current_page,item['id'],target))
            except Exception as exc:QMessageBox.warning(self,'Zmiana elementu',str(exc))
            return
        if self.active_tool in ('copy_region','ocr_region','redact','polygon','arrow'):
            from pdfmanager.pdf_engine import workflows
            if self.active_tool=='copy_region':
                import pymupdf
                from pdfmanager.security.isolation import call
                text=call('document.text_region',self.path,self.current_page,rect)
                QApplication.clipboard().setText(text)
            elif self.active_tool=='ocr_region':
                self.ocr_region_requested.emit(rect)
            elif self.active_tool=='redact':
                reply=QMessageBox.question(self,'Usunięcie danych','Trwale usunąć treść w obszarze? Zmiana zapisze się w bieżącym pliku; Cofnij przywraca poprzedni stan tylko w tej sesji.')
                if reply==QMessageBox.StandardButton.Yes:
                    self._mutate_file(lambda:workflows.redact(self.path,self.current_page,rect))
            elif self.active_tool=='arrow':
                self._mutate_file(lambda:annotations.add_arrow(self.path,self.current_page,p1,p2))
            else:
                x0,y0,x1,y1=rect
                points=[((x0+x1)/2,y0),(x1,y0+(y1-y0)*.4),(x1-(x1-x0)*.2,y1),(x0+(x1-x0)*.2,y1),(x0,y0+(y1-y0)*.4)]
                self._mutate_file(lambda:annotations.add_polygon(self.path,self.current_page,points))
        elif self.active_tool == TOOL_HIGHLIGHT:
            self.add_highlight_at(rect)
        elif self.active_tool == TOOL_UNDERLINE:
            self.add_underline_at(rect)
        elif self.active_tool == TOOL_STRIKEOUT:
            self.add_strikeout_at(rect)
        elif self.active_tool == TOOL_RECTANGLE:
            self.add_rectangle_at(rect)
        elif self.active_tool == TOOL_CIRCLE:
            self.add_circle_at(rect)
        elif self.active_tool == TOOL_LINE:
            self.add_line_at(p1, p2)
        elif self.active_tool == TOOL_FREE_TEXT:
            self.free_text_requested.emit(rect)
        elif self.active_tool == TOOL_STAMP and self.stamp_image_path is not None:
            self.add_stamp_at(rect, self.stamp_image_path)

    # --------------------------------------------------- bezpieczna mutacja
    def _reload_after(self, fn: Callable[[], T]) -> T:
        """Zamyka własny uchwyt pliku, wykonuje `fn` (operacja na dysku), otwiera na nowo.

        Krytyczne dla Windows: nadpisanie pliku z otwartym w tym procesie
        uchwytem (nawet tylko do odczytu, do renderowania) kończy się
        błędem systemowym — inaczej niż na Linuksie/macOS.
        """
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        try:
            result = fn()
        finally:
            self._doc = PdfDocument(self.path)
            self._refresh_thumbnails()
            self._render_current_page()
        return result

    def _push_undo_snapshot(self) -> None:
        try:
            data = self.path.read_bytes()
        except OSError:
            return
        self._undo_stack.append(data)
        if len(self._undo_stack) > MAX_UNDO_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.undo_redo_changed.emit()

    def _mutate_file(self, fn: Callable[[], T]) -> T:
        before=self.path.read_bytes()
        result=self._reload_after(fn)
        self._undo_stack.append(before)
        while len(self._undo_stack)>MAX_UNDO_HISTORY or (len(self._undo_stack)>1 and sum(map(len,self._undo_stack))>64*1024*1024):
            self._undo_stack.pop(0)
        self._redo_stack.clear();self.undo_redo_changed.emit()
        if self.working_copy:self.working_copy.changed()
        self.document_saved.emit()
        return result

    def record_external_edit(self,before):
        if self.path.read_bytes()==before:return
        self._undo_stack.append(before)
        while len(self._undo_stack)>MAX_UNDO_HISTORY or (len(self._undo_stack)>1 and sum(map(len,self._undo_stack))>64*1024*1024):self._undo_stack.pop(0)
        self._redo_stack.clear();self.undo_redo_changed.emit()
        if self.working_copy:self.working_copy.changed()
        self.document_saved.emit()

    def undo(self) -> None:
        if not self._undo_stack:
            return
        current = self.path.read_bytes()
        previous = self._undo_stack.pop()
        self._reload_after(lambda: atomic_write_bytes(self.path, previous))
        self._redo_stack.append(current)
        self.undo_redo_changed.emit()
        if self.working_copy:self.working_copy.changed()
        self.document_saved.emit()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        current = self.path.read_bytes()
        next_data = self._redo_stack.pop()
        self._reload_after(lambda: atomic_write_bytes(self.path, next_data))
        self._undo_stack.append(current)
        self.undo_redo_changed.emit()
        if self.working_copy:self.working_copy.changed()
        self.document_saved.emit()

    # ------------------------------------------------------------- edycja tekstu
    def apply_text_edit(self, span: TextSpan, new_text: str, **options) -> EditResult:
        return self._mutate_file(lambda: self._text_engine.apply_edit(self.path, span, new_text, **options))

    # ---------------------------------------------------------------- adnotacje
    def add_highlight_at(self, rect: tuple[float, float, float, float]) -> AnnotationInfo | None:
        return self._mutate_file(lambda: annotations.add_highlight(self.path, self.current_page, rect))

    def add_underline_at(self, rect: tuple[float, float, float, float]) -> AnnotationInfo | None:
        return self._mutate_file(lambda: annotations.add_underline(self.path, self.current_page, rect))

    def add_strikeout_at(self, rect: tuple[float, float, float, float]) -> AnnotationInfo | None:
        return self._mutate_file(lambda: annotations.add_strikeout(self.path, self.current_page, rect))

    def add_note_at(self, point: tuple[float, float], text: str) -> AnnotationInfo:
        return self._mutate_file(lambda: annotations.add_sticky_note(self.path, self.current_page, point, text))

    def add_free_text_at(self, rect: tuple[float, float, float, float], text: str) -> AnnotationInfo:
        return self._mutate_file(lambda: annotations.add_free_text(self.path, self.current_page, rect, text))

    def add_rectangle_at(self, rect: tuple[float, float, float, float]) -> AnnotationInfo:
        return self._mutate_file(lambda: annotations.add_rectangle(self.path, self.current_page, rect, color=self.annotation_color, width=self.annotation_width))

    def add_circle_at(self, rect: tuple[float, float, float, float]) -> AnnotationInfo:
        return self._mutate_file(lambda: annotations.add_circle(self.path, self.current_page, rect, color=self.annotation_color, width=self.annotation_width))

    def add_line_at(self, start: tuple[float, float], end: tuple[float, float]) -> AnnotationInfo:
        return self._mutate_file(lambda: annotations.add_line(self.path, self.current_page, start, end, color=self.annotation_color, width=self.annotation_width))

    def add_stamp_at(self, rect: tuple[float, float, float, float], image_path: Path) -> AnnotationInfo:
        return self._mutate_file(lambda: annotations.add_image_stamp(self.path, self.current_page, rect, image_path))

    def delete_annotation_at(self, point: tuple[float, float]) -> bool:
        def do() -> bool:
            for info in annotations.list_annotations(self.path, self.current_page):
                x0, y0, x1, y1 = info.rect
                if x0 <= point[0] <= x1 and y0 <= point[1] <= y1:
                    return annotations.delete_annotation(self.path, self.current_page, info.xref)
            return False

        return self._mutate_file(do)

    # -------------------------------------------------- udostępnianie uchwytu
    def release_document(self) -> None:
        """Zamyka własny uchwyt pliku — do użycia przed operacją zewnętrzną
        (np. w oknie zarządzania stronami), by nie blokować pliku na Windows."""
        self._thumbnail_timer.stop()
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    def reload_document(self) -> None:
        """Otwiera plik na nowo i odświeża podgląd — po operacji zewnętrznej."""
        self._doc = PdfDocument(self.path)
        self.current_page = min(self.current_page, max(0, self._doc.page_count - 1))
        self._refresh_thumbnails()
        self._render_current_page()

    def closeEvent(self, event) -> None:
        self.release_document()
        if self.working_copy:self.working_copy.close()
        super().closeEvent(event)
