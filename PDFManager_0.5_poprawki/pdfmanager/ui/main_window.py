"""Główne okno aplikacji — Etap 1 (fundament): przeglądanie lokalnych PDF-ów."""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pdfmanager.app_settings import settings
from pdfmanager.drive.api_client import DriveApiClient, DriveApiError, DriveConflictError, DriveFile
from pdfmanager.drive.auth import DriveAuthError, get_credentials
from pdfmanager.drive.local_cache import cache_path_for
from pdfmanager.drive.sync_folder import is_online_only, looks_like_drive_desktop_folder
from pdfmanager.i18n.translator import SUPPORTED_LANGUAGES, translator
from pdfmanager.licensing.license_manager import LicenseManager, get_default_license_manager
from pdfmanager.logging_setup import get_logger, log_dir
from pdfmanager.pdf_engine import page_ops
from pdfmanager.pdf_engine.text_edit import TextEditError, TextSpan
from pdfmanager.ui.document_list import DocumentListView
from pdfmanager.ui.drive_browser_dialog import DriveBrowserDialog
from pdfmanager.ui.folder_tree import FolderTreeView
from pdfmanager.ui.header_bar import HeaderBar
from pdfmanager.ui.icon_set import badge_icon, folder_icon
from pdfmanager.ui.license_dialogs import ActivationDialog, ExpiryWarningDialog
from pdfmanager.ui.page_manager_dialog import PageManagerDialog
from pdfmanager.ui.proofreading_dialog import ProofreadingDialog
from pdfmanager.ui.theme import SUPPORTED_THEMES, THEME_DARK, THEME_LIGHT, apply_theme
from pdfmanager.windows.file_association import (
    FileAssociationError,
    is_registered_as_default,
    open_default_apps_settings,
    register_application,
)

DAILY_LICENSE_CHECK_MS = 24 * 60 * 60 * 1000

# Osobisty dopisek w oknie "O programie" — zawsze w tej formie, niezależnie
# od języka interfejsu (tak jak nota o prawach autorskich w pasku nagłówka).
ABOUT_DEDICATION = "Dla mojego kochanego Kubusia z Gromnika Love"

APP_ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "branding" / "icon_mark.png"

_logger = get_logger("main_window")
from pdfmanager.ui.viewer import (
    TOOL_DELETE_ANNOTATION,
    TOOL_EDIT_TEXT,
    TOOL_FREE_TEXT,
    TOOL_HIGHLIGHT,
    TOOL_LINE,
    TOOL_NOTE,
    TOOL_RECTANGLE,
    TOOL_SELECT,
    TOOL_STAMP,
    TOOL_STRIKEOUT,
    TOOL_CIRCLE,
    TOOL_UNDERLINE,
    PdfViewerWidget,
)

TOOL_LABEL_KEYS = {
    TOOL_SELECT: "menu.edit.tool_select",
    TOOL_EDIT_TEXT: "menu.edit.tool_edit_text",
    TOOL_HIGHLIGHT: "menu.edit.tool_highlight",
    TOOL_UNDERLINE: "menu.edit.tool_underline",
    TOOL_STRIKEOUT: "menu.edit.tool_strikeout",
    TOOL_NOTE: "menu.edit.tool_note",
    TOOL_FREE_TEXT: "menu.edit.tool_free_text",
    TOOL_RECTANGLE: "menu.edit.tool_rectangle",
    TOOL_CIRCLE: "menu.edit.tool_circle",
    TOOL_LINE: "menu.edit.tool_line",
    TOOL_STAMP: "menu.edit.tool_stamp",
    TOOL_DELETE_ANNOTATION: "menu.edit.tool_delete_annotation",
}

LANGUAGE_LABEL_KEYS = {
    "pl": "menu.settings.language.pl",
    "en": "menu.settings.language.en",
    "uk": "menu.settings.language.uk",
}

THEME_LABEL_KEYS = {
    THEME_LIGHT: "menu.settings.theme_light",
    THEME_DARK: "menu.settings.theme_dark",
}

@dataclass
class DriveTabInfo:
    """Metadane Google Dysku (Workflow A) powiązane z otwartą kartą."""

    file_id: str
    baseline: DriveFile  # metadane zapamiętane w momencie otwarcia/ostatniego zapisu — do wykrywania konfliktu
    client: DriveApiClient


class MainWindow(QMainWindow):
    def __init__(self, license_manager: LicenseManager | None = None) -> None:
        super().__init__()
        self.resize(1200, 800)
        self.license_manager = license_manager or get_default_license_manager()

        if APP_ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        self._header_bar = HeaderBar(self)
        self._header_bar.language_selected.connect(self._select_language)

        self._folder_tree = FolderTreeView(self)
        self._document_list = DocumentListView(self)
        self._viewer_placeholder = QLabel(self)
        self._viewer_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._viewer_placeholder.setWordWrap(True)
        self._tabs = QTabWidget(self)
        self._tabs.setTabsClosable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._update_status_bar)
        self._tabs.currentChanged.connect(self._update_undo_redo_actions)
        self._tabs.currentChanged.connect(self._update_drive_actions)
        self._tabs.currentChanged.connect(self._update_save_as_action)

        self._viewer_stack = QStackedWidget(self)
        self._viewer_stack.addWidget(self._viewer_placeholder)  # index 0
        self._viewer_stack.addWidget(self._tabs)  # index 1

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._folder_tree)
        splitter.addWidget(self._document_list)
        splitter.addWidget(self._viewer_stack)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 4)
        self._folder_tree.hide()
        self._document_list.hide()

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self._header_bar.hide()
        self._central_layout = central_layout
        central_layout.addWidget(splitter)
        self.setCentralWidget(central)
        self._content_splitter = splitter
        self._workspace_stack = QStackedWidget(self)
        central_layout.removeWidget(splitter)
        self._workspace_stack.addWidget(splitter)
        central_layout.addWidget(self._workspace_stack)
        self._compare_viewer = None
        self._compare_temp = None
        self.setAcceptDrops(True)

        self._folder_tree.folder_selected.connect(self._on_folder_selected)
        self._document_list.document_activated.connect(self.open_document)
        self._document_list.is_open_document = lambda path: any(
            isinstance(self._tabs.widget(i), PdfViewerWidget) and self._tabs.widget(i).source_path.resolve()==path.resolve()
            for i in range(self._tabs.count()))

        self._status_folder_label = QLabel(self)
        self._status_page_label = QLabel(self)
        self._status_license_label = QLabel(self)
        self.statusBar().addWidget(self._status_folder_label, 1)
        self.statusBar().addPermanentWidget(self._status_license_label)
        self.statusBar().addPermanentWidget(self._status_page_label)

        self._build_menu()
        self._build_toolbar()
        self._build_classic_ribbon()

        translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

        last_folder = settings.last_folder
        if last_folder and Path(last_folder).is_dir():
            self._on_folder_selected(last_folder)
        else:
            self._update_status_bar()

        if settings.window_geometry():self.restoreGeometry(settings.window_geometry())
        self._update_license_status_bar()
        self._license_check_timer = QTimer(self)
        self._license_check_timer.setInterval(DAILY_LICENSE_CHECK_MS)
        self._license_check_timer.timeout.connect(self._check_license_and_warn)
        self._license_check_timer.start()

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        self._menu_file = menu_bar.addMenu("")
        self._action_open_folder = QAction(self)
        self._action_open_folder.triggered.connect(self._prompt_open_folder)
        self._action_open_file = QAction(self)
        self._action_open_file.triggered.connect(self._prompt_open_file)
        self._action_save_as_local = QAction(self)
        self._action_save_as_local.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._action_save_as_local.triggered.connect(self._save_as_local)
        self._action_save_as_local.setEnabled(False)
        self._action_drive_connect = QAction(self)
        self._action_drive_connect.triggered.connect(self._connect_drive)
        self._action_drive_save = QAction(self)
        self._action_drive_save.triggered.connect(self._save_to_drive)
        self._action_drive_save.setEnabled(False)
        self._action_drive_save_as_new = QAction(self)
        self._action_drive_save_as_new.triggered.connect(self._save_as_new_on_drive)
        self._action_drive_save_as_new.setEnabled(False)
        self._action_close_tab = QAction(self)
        self._action_close_tab.triggered.connect(lambda: self._close_tab(self._tabs.currentIndex()))
        self._action_exit = QAction(self)
        self._action_exit.triggered.connect(self.close)
        self._menu_file.addAction(self._action_open_folder)
        self._menu_file.addAction(self._action_open_file)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_save_as_local)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_drive_connect)
        self._menu_file.addAction(self._action_drive_save)
        self._menu_file.addAction(self._action_drive_save_as_new)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_close_tab)
        self._menu_file.addSeparator()
        self._menu_file.addAction(self._action_exit)

        self._menu_edit = menu_bar.addMenu("")
        self._active_tool = TOOL_SELECT
        self._stamp_image_path: Path | None = None
        self._tool_actions: dict[str, QAction] = {}
        tool_group = QActionGroup(self)
        self._tool_group = tool_group
        tool_group.setExclusive(True)
        tool_rows = [
            (TOOL_SELECT,),
            (TOOL_EDIT_TEXT,),
            None,
            (TOOL_HIGHLIGHT, TOOL_UNDERLINE, TOOL_STRIKEOUT),
            None,
            (TOOL_NOTE, TOOL_FREE_TEXT),
            None,
            (TOOL_RECTANGLE, TOOL_CIRCLE, TOOL_LINE, TOOL_STAMP),
            None,
            (TOOL_DELETE_ANNOTATION,),
        ]
        for row in tool_rows:
            if row is None:
                self._menu_edit.addSeparator()
                continue
            for tool in row:
                action = QAction(self)
                action.setCheckable(True)
                action.setChecked(tool == TOOL_SELECT)
                action.triggered.connect(lambda checked, tool=tool: self._on_tool_triggered(tool))
                tool_group.addAction(action)
                self._menu_edit.addAction(action)
                self._tool_actions[tool] = action

        self._menu_edit.addSeparator()
        self._action_undo = QAction(self)
        self._action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._action_undo.triggered.connect(lambda: self._with_viewer(lambda v: v.undo()))
        self._action_redo = QAction(self)
        self._action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._action_redo.triggered.connect(lambda: self._with_viewer(lambda v: v.redo()))
        self._menu_edit.addAction(self._action_undo)
        self._menu_edit.addAction(self._action_redo)

        self._menu_pages = menu_bar.addMenu("")
        self._action_manage_pages = QAction(self)
        self._action_manage_pages.triggered.connect(self._open_page_manager)
        self._action_merge_pdfs = QAction(self)
        self._action_merge_pdfs.triggered.connect(self._merge_pdfs)
        self._menu_pages.addAction(self._action_manage_pages)
        self._menu_pages.addAction(self._action_merge_pdfs)

        self._menu_tools = menu_bar.addMenu("")
        self._action_proofread = QAction(self)
        self._action_proofread.triggered.connect(self._open_proofreading)
        self._menu_tools.addAction(self._action_proofread)

        self._menu_view = menu_bar.addMenu("")
        self._action_zoom_in = QAction(self)
        self._action_zoom_in.triggered.connect(lambda: self._with_viewer(lambda v: v.zoom_in()))
        self._action_zoom_out = QAction(self)
        self._action_zoom_out.triggered.connect(lambda: self._with_viewer(lambda v: v.zoom_out()))
        self._action_fit_width = QAction(self)
        self._action_fit_width.triggered.connect(lambda: self._with_viewer(lambda v: v.fit_width()))
        self._action_actual_size = QAction(self)
        self._action_actual_size.triggered.connect(lambda: self._with_viewer(lambda v: v.set_zoom(100)))
        for action in (
            self._action_zoom_in,
            self._action_zoom_out,
            self._action_fit_width,
            self._action_actual_size,
        ):
            self._menu_view.addAction(action)

        self._menu_settings = menu_bar.addMenu("")
        self._menu_language = self._menu_settings.addMenu("")
        self._language_actions: dict[str, QAction] = {}
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        for lang in SUPPORTED_LANGUAGES:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(lang == translator.language)
            action.triggered.connect(lambda checked, lang=lang: self._select_language(lang))
            language_group.addAction(action)
            self._menu_language.addAction(action)
            self._language_actions[lang] = action

        self._menu_theme = self._menu_settings.addMenu("")
        self._theme_actions: dict[str, QAction] = {}
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for theme in SUPPORTED_THEMES:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(theme == settings.theme)
            action.triggered.connect(lambda checked, theme=theme: self._select_theme(theme))
            theme_group.addAction(action)
            self._menu_theme.addAction(action)
            self._theme_actions[theme] = action

        self._menu_settings.addSeparator()
        self._action_set_default_pdf_app = QAction(self)
        self._action_set_default_pdf_app.triggered.connect(self._set_default_pdf_app)
        self._action_check_default_pdf_app = QAction(self)
        self._action_check_default_pdf_app.triggered.connect(self._check_default_pdf_app)
        self._menu_settings.addAction(self._action_set_default_pdf_app)
        self._menu_settings.addAction(self._action_check_default_pdf_app)

        self._menu_help = menu_bar.addMenu("")
        self._action_show_log = QAction(self)
        self._action_show_log.triggered.connect(self._show_log_file)
        self._action_about = QAction(self)
        self._action_about.triggered.connect(self._show_about)
        self._menu_help.addAction(self._action_show_log)
        self._menu_help.addSeparator()
        self._menu_help.addAction(self._action_about)

    def _build_toolbar(self) -> None:
        self._toolbar = self.addToolBar("main")
        self._toolbar.setMovable(False)
        self._tb_open_folder = QAction(folder_icon(), "", self)
        self._tb_open_folder.triggered.connect(self._prompt_open_folder)
        self._tb_prev_page = QAction(badge_icon("‹"), "", self)
        self._tb_prev_page.triggered.connect(lambda: self._with_viewer(lambda v: v.prev_page()))
        self._tb_next_page = QAction(badge_icon("›"), "", self)
        self._tb_next_page.triggered.connect(lambda: self._with_viewer(lambda v: v.next_page()))
        self._tb_zoom_out = QAction(badge_icon("−"), "", self)
        self._tb_zoom_out.triggered.connect(lambda: self._with_viewer(lambda v: v.zoom_out()))
        self._tb_zoom_in = QAction(badge_icon("+"), "", self)
        self._tb_zoom_in.triggered.connect(lambda: self._with_viewer(lambda v: v.zoom_in()))
        self._tb_fit_width = QAction(badge_icon("↔"), "", self)
        self._tb_fit_width.triggered.connect(lambda: self._with_viewer(lambda v: v.fit_width()))
        self._toolbar.addAction(self._tb_open_folder)
        self._toolbar.addSeparator()
        self._toolbar.addAction(self._tb_prev_page)
        self._toolbar.addAction(self._tb_next_page)
        self._toolbar.addSeparator()
        self._toolbar.addAction(self._tb_zoom_out)
        self._toolbar.addAction(self._tb_zoom_in)
        self._toolbar.addAction(self._tb_fit_width)
        self._toolbar.addSeparator()
        self._toolbar.addAction(self._action_undo)
        self._toolbar.addAction(self._action_redo)

        self._annotation_toolbar = self.addToolBar("annotations")
        self._annotation_toolbar.setMovable(False)
        for tool in (
            TOOL_SELECT,
            TOOL_EDIT_TEXT,
            TOOL_HIGHLIGHT,
            TOOL_UNDERLINE,
            TOOL_STRIKEOUT,
            TOOL_NOTE,
            TOOL_FREE_TEXT,
            TOOL_RECTANGLE,
            TOOL_CIRCLE,
            TOOL_LINE,
            TOOL_STAMP,
            TOOL_DELETE_ANNOTATION,
        ):
            self._annotation_toolbar.addAction(self._tool_actions[tool])

    def _build_classic_ribbon(self) -> None:
        from pdfmanager.ui.vector_icons import vector_icon
        from pdfmanager.ui.workspace_shell import WorkspaceShell
        from pdfmanager.ui.document_tools import DocumentTools
        from pdfmanager.ui.search_panel import SearchPanel
        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QComboBox, QToolButton
        from PySide6.QtCore import QSize
        self._tools = DocumentTools(self)
        self._extended_actions = []
        self._actions_by_name = {}
        def action(name, text, icon, callback, document=True):
            result = QAction(vector_icon(icon), text, self)
            result.triggered.connect(callback)
            self._actions_by_name[name] = result
            if document:
                self._extended_actions.append(result)
            return result
        self._action_open_file.setIcon(vector_icon('open'))
        self._action_save_as_local.setIcon(vector_icon('save'))
        for tool, icon in {TOOL_SELECT:'select', TOOL_EDIT_TEXT:'text', TOOL_HIGHLIGHT:'highlight',
                           TOOL_UNDERLINE:'text', TOOL_STRIKEOUT:'text', TOOL_NOTE:'note',
                           TOOL_FREE_TEXT:'text', TOOL_RECTANGLE:'rectangle', TOOL_CIRCLE:'circle',
                           TOOL_LINE:'line', TOOL_STAMP:'signature', TOOL_DELETE_ANNOTATION:'delete'}.items():
            self._tool_actions[tool].setIcon(vector_icon(icon,22))
        self._action_undo.setIcon(vector_icon('back',22));self._action_redo.setIcon(vector_icon('extract',22))
        for a,icon in [(self._tb_open_folder,'open'),(self._tb_prev_page,'previous'),(self._tb_next_page,'next'),(self._tb_zoom_out,'zoom_out'),(self._tb_zoom_in,'zoom_in'),(self._tb_fit_width,'fit')]:a.setIcon(vector_icon(icon,22))
        for bar in (self._toolbar,self._annotation_toolbar):
            bar.setIconSize(QSize(22,22))
            bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.insertToolBarBreak(self._annotation_toolbar)
        pages = action('pages','Strony','pages',self._open_page_manager)
        merge = action('merge','Scal','merge',self._tools.merge,False)
        ocr = action('ocr','OCR','ocr',self._tools.ocr)
        ocr_models = action('ocr_models','Języki OCR','ocr',self._tools.install_ocr_language,False)
        self._menu_tools.addAction(ocr_models)
        ocr_text = action('ocr_text','OCR do tekstu','ocr',lambda:self._tools.ocr(True))
        text = action('text','Eksport tekstu','text',self._tools.extract_text)
        search = action('search','Znajdź','search',self._search_document)
        open_image = action('open_image','Otwórz obraz','image',self._prompt_open_media,False)
        self._menu_file.addAction(open_image)
        images = action('images','PNG / JPEG','image',self._export_page_images)
        watermark = action('watermark','Znak wodny','text',self._watermark_document)
        numbers = action('numbers','Numeracja','pages',self._number_document)
        flatten = action('flatten','Spłaszcz','pages',self._flatten_document)
        crop = action('crop','Przytnij','image',self._tools.crop)
        resize = action('resize','Rozmiar','image',self._tools.resize)
        forms = action('forms','Formularz','text',self._tools.forms)
        bookmarks = action('bookmarks','Zakładki','guide',self._tools.bookmarks)
        compare = action('compare','Porównaj','compare',self._tools.compare)
        protect = action('protect','Hasło','document',self._tools.protect)
        decrypt = action('decrypt','Usuń hasło','document',self._tools.decrypt)
        repair = action('repair','Optymalizuj','tools',self._tools.repair)
        attach = action('attach','Dodaj załącznik','insert',self._tools.attach)
        extract_attachment = action('extract_attachment','Zapisz załącznik','extract',self._tools.extract_attachment)
        sign = action('sign','Podpis PKCS#12','signature',self._tools.sign)
        verify = action('verify','Sprawdź podpisy','signature',self._tools.verify)
        batch = action('batch','Wsadowo','tools',self._tools.batch,False)
        print_action = action('print','Drukuj','print',self._print_document)
        browser = action('browser','Foldery','folder',lambda:self._set_workspace_page(2),False)
        settings_action = action('settings','Ustawienia','settings',self._show_appearance_settings,False)
        help_action = action('help','O programie','help',self._show_about,False)
        from pdfmanager.ui.content_editor import insert_content
        content_action = action('insert_content', 'Wstaw tekst / obraz', 'insert', lambda: insert_content(self, self._current_viewer()))
        paste_action = action('paste_content', 'Wklej ze schowka', 'insert', lambda: insert_content(self, self._current_viewer(), clipboard=True))
        paste_action.setShortcut('Ctrl+V')
        self.addAction(paste_action)
        self._menu_tools.addAction(content_action)
        self._menu_tools.addAction(paste_action)
        from pdfmanager.ui.cabinet_tools import CabinetTools
        self._cabinet_tools = CabinetTools(self)
        cabinets = action('cabinets', 'Szafki', 'folder', self._cabinet_tools.select, False)
        add_cabinet = action('add_cabinet', 'Dodaj szafkę', 'folder', self._cabinet_tools.add, False)
        client = action('client', 'Nowy klient', 'insert', self._cabinet_tools.client, False)
        template = action('folder_template', 'Szablony folderów', 'folder', self._cabinet_tools.template, False)
        scans = action('scans', 'Import skanów', 'scan', self._cabinet_tools.scans, False)
        scanner_folder = action('scanner_folder', 'Folder skanera', 'scan', self._cabinet_tools.scanner_folder, False)
        batch_split = action('batch_split', 'Podziel PDF wsadowo', 'split', self._cabinet_tools.batch_split, False)
        cabinet_search = action('cabinet_search', 'Szukaj w szafce', 'search', self._cabinet_tools.search_cabinet, False)
        dms_menu = self._menu_tools.addMenu('Szafki i skanowanie')
        for dms_action in (cabinets, add_cabinet, client, template, scans, scanner_folder, cabinet_search, batch_split):
            dms_menu.addAction(dms_action)
        save = action('save', 'Zapisz', 'save', self._save_working_copy)
        save.setShortcut(QKeySequence.StandardKey.Save);self.addAction(save);self._menu_file.addAction(save)
        recovery = action('recovery', 'Odzyskaj dokument', 'open', self._recover_documents, False)
        self._menu_file.addAction(recovery)
        backups = action('backups', 'Kopie zapasowe', 'open', self._open_backup, False)
        self._menu_file.addAction(backups)
        trash = action('trash', 'Kosz', 'folder', self._cabinet_tools.restore_trash, False)
        favorites = action('favorites', 'Ulubione szafki', 'folder', self._cabinet_tools.favorites, False)
        favorite = action('favorite', 'Dodaj do ulubionych', 'folder', self._cabinet_tools.favorite, False)
        recent = action('recent', 'Ostatnie dokumenty', 'open', self._recent_documents, False)
        for extra in (trash,favorites,favorite,recent):dms_menu.addAction(extra)
        from pdfmanager.ui.scan_automation import ScanAutomation
        self._scan_automation=ScanAutomation(self)
        scan_actions={}
        for name,label,callback in [('scan_config','Ustawienia importu skanów',self._scan_automation.configure),('watch_scans','Włącz / wyłącz obserwowanie',self._scan_automation.toggle),('wia','Skanuj WIA',self._scan_automation.wia),('twain','Aplikacja skanera TWAIN',self._scan_automation.vendor)]:
            scan_actions[name]=action(name,label,'scan',callback,False)
            dms_menu.addAction(scan_actions[name])
        from pdfmanager.ui.text_properties import TextProperties
        self._text_properties=TextProperties(self);self.addDockWidget(Qt.RightDockWidgetArea,self._text_properties)
        properties=action('text_properties','Panel czcionek','text',lambda:self._text_properties.setVisible(not self._text_properties.isVisible()))
        self._menu_tools.addAction(properties)
        for name,label in [('move_content','Przesuń dodany element'),('scale_content','Skaluj dodany element')]:
            item=action(name,label,'transform',lambda checked=False,n=name:self._with_viewer(lambda v:v.set_active_tool(n)))
            self._toolbar.addAction(item);self._menu_tools.addAction(item)
        transformations=[]
        for name,label in [('flip_horizontal','Odbij poziomo'),('flip_vertical','Odbij pionowo'),('rotate','Obrót skanu'),('deskew','Prostowanie'),('levels','Poziomy'),('perspective','Perspektywa')]:
            transformations.append(action(name,label,'transform',lambda checked=False,n=name:self._tools.transform(n)))
        for title, actions in [('Konwersja',[images,text,watermark,numbers,flatten,resize]),
                               ('Dokument',[ocr,ocr_text,crop,forms,bookmarks,protect,decrypt,repair,attach,extract_attachment,sign,verify]),
                               ('Obrazy',transformations),('Porównanie i druk',[compare,print_action])]:
            menu=self._menu_tools.addMenu(title)
            for a in actions:menu.addAction(a)
        self._menu_tools.addAction(batch)
        modes=QComboBox(self)
        modes.addItems(['Jedna strona','Ciągły','Dwie strony','Książka','Siatka'])
        modes.currentIndexChanged.connect(lambda index:self._with_viewer(lambda v:v.set_view_mode(['single','continuous','two','book','grid'][index])))
        self._view_modes = modes
        self._toolbar.addWidget(modes)
        night=action('night','Tryb nocny','image',lambda:self._with_viewer(lambda v:v.toggle_night_mode()))
        self._night_action = night
        night.setCheckable(True)
        self._toolbar.addAction(night)
        sidebar=action('sidebar','Przenieś miniatury','pages',lambda:self._with_viewer(lambda v:v.toggle_sidebar_side()))
        self._menu_view.addAction(sidebar)
        nup=action('nup','Strony na arkuszu','grid',self._export_nup)
        self._menu_tools.addAction(nup)
        split=action('side_by_side','Dwa dokumenty','compare',self._toggle_compare_pane)
        self._toolbar.addAction(split)
        zoom=QComboBox(self);zoom.setEditable(True);zoom.addItems(['50%','75%','100%','125%','150%','200%']);zoom.setCurrentText('100%')
        zoom.activated.connect(lambda _:self._apply_zoom_text(zoom.currentText()))
        zoom.lineEdit().returnPressed.connect(lambda:self._apply_zoom_text(zoom.currentText()))
        self._zoom_combo = zoom
        self._toolbar.addWidget(zoom)
        from PySide6.QtWidgets import QColorDialog
        color=action('color','Kolor adnotacji','image',self._choose_annotation_color)
        self._annotation_toolbar.addAction(color)
        width=QComboBox(self);width.addItems(['1 pt','2 pt','3 pt','5 pt']);width.setCurrentIndex(1)
        width.currentIndexChanged.connect(lambda _:self._with_viewer(lambda v:setattr(v,'annotation_width',float(width.currentText().split()[0]))))
        self._annotation_toolbar.addWidget(width)
        shortcuts=action('shortcuts','Skróty klawiatury','guide',self._show_shortcuts,False)
        shortcuts.setShortcut(QKeySequence('F1'));self.addAction(shortcuts)
        self._menu_tools.addAction(shortcuts)
        recovery=QAction(self);recovery.setShortcut(QKeySequence('Ctrl+Shift+K'));recovery.triggered.connect(lambda:self._shell.tabs.setCurrentIndex(3));self.addAction(recovery)
        self._action_open_file.setShortcut(QKeySequence.StandardKey.Open)
        search.setShortcut(QKeySequence.StandardKey.Find)
        print_action.setShortcut(QKeySequence.StandardKey.Print)
        self._tb_next_page.setShortcut(QKeySequence('PgDown'))
        self._tb_prev_page.setShortcut(QKeySequence('PgUp'))
        for a in [self._action_open_file,search,print_action,self._tb_next_page,self._tb_prev_page]:self.addAction(a)
        for name,label,icon,callback in [
            ('ink','Rysuj','ink',lambda:self._activate_extended_tool('ink')),
            ('redact','Usuń poufne dane','redact',lambda:self._activate_extended_tool('redact')),
            ('copy_region','Kopiuj tekst','select',lambda:self._activate_extended_tool('copy_region')),
            ('ocr_region','OCR obszaru','ocr',lambda:self._activate_extended_tool('ocr_region')),
            ('draw_signature','Narysuj podpis','signature',self._draw_signature),
            ('polygon','Wielokąt','rectangle',lambda:self._activate_extended_tool('polygon')),
            ('arrow','Strzałka','line',lambda:self._activate_extended_tool('arrow'))]:
            tool_action = action(name,label,icon,callback)
            if name != 'draw_signature':
                tool_action.setCheckable(True);self._tool_group.addAction(tool_action)
            self._annotation_toolbar.addAction(tool_action)
        self._home_page=QWidget(self);home=QVBoxLayout(self._home_page)
        home.setContentsMargins(24,24,24,24)
        headline=QLabel('PDFManager');headline.setObjectName('HomeHeadline');home.addWidget(headline)
        home.addWidget(QLabel('Dokumenty PDF, OCR i organizacja plików — lokalnie na Twoim komputerze.'))
        home.addWidget(self._header_bar);self._header_bar.show()
        for label,callback in [('Otwórz dokument',self._prompt_open_file),('Wybierz folder',self._prompt_open_folder),('Aktywacja licencji',self._open_activation_dialog)]:
            button=QPushButton(label);button.setMaximumWidth(240);button.clicked.connect(callback);home.addWidget(button)
        home.addStretch();self._workspace_stack.addWidget(self._home_page)
        self._search_page=SearchPanel(self)
        self._search_page.open_requested.connect(self._open_search_result)
        self._workspace_stack.addWidget(self._search_page)
        old_menu=self.menuBar()
        self._shell=WorkspaceShell(self,old_menu,[
            ('Start',[self._action_open_file,browser,settings_action,help_action]),
            ('Skrzynka',[scan_actions['wia'],scans,scan_actions['scan_config'],scan_actions['watch_scans'],scan_actions['twain'],scanner_folder,browser,self._action_open_file,ocr,merge,pages,images,settings_action]),
            ('Organizuj',[cabinets,favorites,trash,add_cabinet,client,template,scans,merge,batch_split,pages,cabinet_search,settings_action]),
            ('Edytor PDF',[self._action_open_file,save,self._action_save_as_local,print_action,pages,forms,ocr,crop,images,watermark,numbers,sign,properties,settings_action,help_action]),
            ('Edytor obrazu',[open_image,images,*transformations,flatten,ocr,settings_action]),
            ('Szukaj',[self._action_open_file,search,compare,text,settings_action,help_action]),
        ])
        self.setMenuWidget(self._shell)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self._shell.tabs.currentChanged.connect(self._set_workspace_page)
        self._tabs.currentChanged.connect(self._update_extended_actions)
        self._tabs.currentChanged.connect(self._refresh_comparison)
        self._shell.tabs.setCurrentIndex(3)
        self._update_extended_actions()

    def _activate_extended_tool(self,name):
        self._active_tool=name
        self._with_viewer(lambda v:v.set_active_tool(name))

    def _show_appearance_settings(self):
        from pdfmanager.ui.appearance_dialog import AppearanceDialog
        AppearanceDialog(self).exec()

    def _prompt_open_media(self):
        from pdfmanager.pdf_engine.workflows import merge_inputs
        from PySide6.QtCore import QStandardPaths
        from uuid import uuid4
        path,_=QFileDialog.getOpenFileName(self,'Otwórz obraz','','Obrazy (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)')
        if not path:return
        folder=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))/'images'/uuid4().hex
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/(Path(path).stem+'.pdf')
        from pdfmanager.ui.background_job import run_job
        def complete(_):
            self.open_document(str(output));self._shell.tabs.setCurrentIndex(4)
        run_job(self,'Otwieranie obrazu',lambda:merge_inputs([Path(path)],output),complete)

    def _choose_annotation_color(self):
        from PySide6.QtWidgets import QColorDialog
        color=QColorDialog.getColor(parent=self)
        if color.isValid():
            self._with_viewer(lambda v:setattr(v,'annotation_color',(color.redF(),color.greenF(),color.blueF())))

    def _show_shortcuts(self):
        from PySide6.QtWidgets import QTableWidget,QTableWidgetItem
        dialog=QDialog(self);dialog.setWindowTitle('Skróty klawiatury');dialog.resize(600,430)
        layout=QVBoxLayout(dialog);table=QTableWidget(0,2);table.setHorizontalHeaderLabels(['Funkcja','Skrót'])
        for action in self.findChildren(QAction):
            if not action.shortcut().isEmpty():
                row=table.rowCount();table.insertRow(row)
                table.setItem(row,0,QTableWidgetItem(action.text() or 'Przywróć edytor PDF'))
                table.setItem(row,1,QTableWidgetItem(action.shortcut().toString()))
        table.resizeColumnsToContents();layout.addWidget(table);dialog.exec()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):event.acceptProposedAction()

    def dropEvent(self,event):
        from pdfmanager.pdf_engine.workflows import merge_inputs
        from pdfmanager.ui.background_job import run_job
        paths=[Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths:return
        if len(paths)==1 and paths[0].suffix.lower()=='.pdf':self.open_document(str(paths[0]));event.acceptProposedAction();return
        output=self._tools.output('Scal upuszczone pliki')
        if output:run_job(self,'Scalanie',lambda:merge_inputs(paths,output),lambda _:self.open_document(str(output)))
        event.acceptProposedAction()

    def _set_workspace_page(self,index):
        if index==0:
            self._workspace_stack.setCurrentWidget(self._home_page)
        elif index==5:
            self._workspace_stack.setCurrentWidget(self._search_page)
            self._search_page.folder.setText(settings.last_folder)
        else:
            self._workspace_stack.setCurrentIndex(0)
            browsing=index in (1,2)
            self._folder_tree.setVisible(browsing)
            self._document_list.setVisible(browsing)
            self._viewer_stack.setVisible(True)
            if browsing:self._content_splitter.setSizes([245,400,850])
            else:self._content_splitter.setSizes([0,0,1000])
        if self._compare_viewer:self._compare_viewer.setVisible(index in (3,4))
        editing=index in (3,4)
        self._toolbar.setVisible(editing)
        self._annotation_toolbar.setVisible(index==3)

    def _open_search_result(self,path,page):
        self.open_document(path)
        self._with_viewer(lambda v:v.go_to_page(page))

    def _apply_zoom_text(self,text):
        try:percent=int(text.rstrip('%'))
        except ValueError:return
        self._with_viewer(lambda v:v.set_zoom(percent))

    def _toggle_compare_pane(self):
        if self._compare_viewer is not None:
            self._compare_viewer.release_document();self._compare_viewer.deleteLater();self._compare_viewer=None
            if self._compare_temp:self._compare_temp.cleanup();self._compare_temp=None
            return
        if self._tabs.count()<2:
            QMessageBox.information(self,'Dwa dokumenty','Otwórz co najmniej dwa dokumenty.');return
        self._refresh_comparison(force=True)

    def _refresh_comparison(self,*_,force=False):
        if not force and self._compare_viewer is None:return
        from tempfile import TemporaryDirectory
        if self._compare_viewer:
            self._compare_viewer.release_document();self._compare_viewer.deleteLater();self._compare_viewer=None
        if self._compare_temp:self._compare_temp.cleanup();self._compare_temp=None
        if self._tabs.count()<2:return
        index=self._tabs.currentIndex()
        other=self._tabs.widget((index-1)%self._tabs.count())
        self._compare_temp=TemporaryDirectory(prefix='pdfmanager-compare-')
        path=Path(self._compare_temp.name)/other.path.name
        shutil.copyfile(other.path,path)
        self._compare_viewer=PdfViewerWidget(str(path),self)
        self._content_splitter.addWidget(self._compare_viewer)
        self._content_splitter.setSizes([0,0,600,600])

    def _draw_signature(self):
        from pdfmanager.ui.signature_dialog import SignatureDialog
        dialog=SignatureDialog(self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        self._stamp_image_path=dialog.saved_path
        self._with_viewer(lambda v:setattr(v,'stamp_image_path',dialog.saved_path))
        self._on_tool_triggered(TOOL_STAMP)

    def _export_nup(self):
        from pdfmanager.pdf_engine.workflows import nup_document
        selected,ok=QInputDialog.getItem(self,'Strony na arkuszu','Liczba stron:', ['1','2','4','6','9'],1,False)
        if ok:self._tools.export('Strony na arkuszu',lambda src,out:nup_document(src,out,int(selected)))

    def _print_document(self):
        from PySide6.QtPrintSupport import QPrinter,QPrintPreviewDialog
        from pdfmanager.ui.printing import paint_document
        viewer=self._current_viewer()
        if not viewer:return
        printer=QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog=QPrintPreviewDialog(printer,self)
        dialog.paintRequested.connect(lambda p:paint_document(p,viewer.path))
        dialog.exec()

    def _toggle_browser(self):
        visible = not self._folder_tree.isVisible()
        self._folder_tree.setVisible(visible)
        self._document_list.setVisible(visible)

    def _update_extended_actions(self, *_):
        viewer = self._current_viewer()
        for action in self._extended_actions:
            action.setEnabled(viewer is not None and viewer.is_loaded)

    def _search_document(self):
        from pdfmanager.pdf_engine.extended_ops import search_text
        viewer = self._current_viewer()
        if not viewer:
            return
        query, ok = QInputDialog.getText(self, "Search", "Find text:")
        if not ok or not query.strip():
            return
        try:
            hits = search_text(viewer.path, query)
            if not hits:
                QMessageBox.information(self, "Search", "No matches found.")
                return
            labels = [f"Page {page+1} — {count} matches" for page, count in hits]
            selected, ok = QInputDialog.getItem(self, "Search", "Results:", labels, 0, False)
            if ok:
                viewer.go_to_page(hits[labels.index(selected)][0])
                viewer.show_search(query)
        except Exception as exc:
            QMessageBox.critical(self, "Search", str(exc))

    def _export_page_images(self):
        from pdfmanager.pdf_engine.extended_ops import export_images
        from pdfmanager.pdf_engine.workflows import parse_pages
        from pdfmanager.ui.background_job import run_job
        viewer = self._current_viewer()
        if not viewer:return
        expression,ok=QInputDialog.getText(self,'Eksport obrazów','Strony, np. 1-3,5 lub *:',text=str(viewer.current_page+1))
        if not ok:return
        try:indices=parse_pages(expression,viewer.page_count)
        except ValueError as exc:QMessageBox.warning(self,'Eksport obrazów',str(exc));return
        fmt,ok=QInputDialog.getItem(self,'Eksport obrazów','Format:', ['png','jpg'],0,False)
        if not ok:return
        dpi,ok=QInputDialog.getInt(self,'Eksport obrazów','DPI:',150,72,600)
        if not ok:return
        folder=QFileDialog.getExistingDirectory(self,'Folder docelowy')
        if folder:run_job(self,'Eksport obrazów',lambda:export_images(viewer.path,Path(folder),indices,dpi,fmt),lambda files:QMessageBox.information(self,'Eksport obrazów',f'Wyeksportowano {len(files)} stron.'))

    def _export_pdf_copy(self, title, operation):
        self._tools.export(title,operation)

    def _watermark_document(self):
        from pdfmanager.pdf_engine.extended_ops import stamp_document
        text, ok = QInputDialog.getText(self, "Watermark", "Text:")
        if ok and text.strip():
            self._export_pdf_copy("Watermark", lambda src, out: stamp_document(src, out, text=text))

    def _number_document(self):
        from pdfmanager.pdf_engine.extended_ops import stamp_document
        self._export_pdf_copy("Page numbers", lambda src, out: stamp_document(src, out, page_numbers=True))

    def _flatten_document(self):
        from pdfmanager.pdf_engine.extended_ops import flatten_document
        reply = QMessageBox.question(self, "Flatten PDF", "Create an image-only copy? Text search, forms, links and digital signatures will not be preserved. The original remains unchanged.")
        if reply == QMessageBox.StandardButton.Yes:
            self._export_pdf_copy("Flatten PDF", flatten_document)

    # --------------------------------------------------------------- akcje
    def _prompt_open_folder(self) -> None:
        start_dir = settings.last_folder or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, translator.tr("dialog.select_folder_title"), start_dir)
        if path:
            self._on_folder_selected(path)

    def _prompt_open_file(self) -> None:
        start_dir = settings.last_folder or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, translator.tr("menu.file.open_file"), start_dir, "PDF (*.pdf)")
        if path:
            self.open_document(path)

    def _open_backup(self):
        from pdfmanager.dms.recovery import data_dir
        folder=data_dir()/'backups';folder.mkdir(parents=True,exist_ok=True)
        path,_=QFileDialog.getOpenFileName(self,'Kopie zapasowe — zapisz odzyskany dokument przez Zapisz jako',str(folder),'PDF (*.pdf)')
        if path:
            self.open_document(path)
            if self._current_viewer():self._current_viewer().require_save_as=True

    def _recent_documents(self):
        from pdfmanager.dms.preferences import Preferences
        paths=Preferences().get('recent',[])
        if not paths:return
        path,ok=QInputDialog.getItem(self,'Ostatnie dokumenty','Dokument:',paths,0,False)
        if ok:self.open_document(path)

    def _working_copy_changed(self,viewer):
        index=self._tabs.indexOf(viewer)
        if index>=0:self._tabs.setTabText(index,viewer.source_path.name+' *')
        self.statusBar().showMessage('Zmiany w kopii roboczej. Ctrl+S zapisuje dokument; kopia jest dostępna do odzyskania.',5000)

    def _save_working_copy(self):
        viewer=self._current_viewer()
        if not viewer:return
        if not viewer.working_copy or getattr(viewer,'require_save_as',False):return self._save_as_local()
        if QMessageBox.question(self,'Zapisz dokument','Zapisać zmiany w pliku źródłowym? Poprzednia wersja zostanie zachowana w kopii zapasowej.')!=QMessageBox.Yes:return
        try:
            viewer.working_copy.save();self._tabs.setTabText(self._tabs.indexOf(viewer),viewer.source_path.name)
            self.statusBar().showMessage('Zapisano dokument i kopię zapasową.',4000)
        except Exception as exc:QMessageBox.warning(self,'Zapis dokumentu',str(exc))

    def _recover_documents(self):
        from pdfmanager.dms.recovery import recoverable
        entries=recoverable()
        if not entries:QMessageBox.information(self,'Odzyskiwanie','Brak niezapisanych kopii roboczych.');return
        labels=[f'{Path(source).name} — {updated} — {path.parent.name[:8]}' for path,source,updated in entries]
        label,ok=QInputDialog.getItem(self,'Odzyskiwanie','Wybierz kopię; zapisz wynik przez Zapisz jako:',labels,0,False)
        if ok:
            self.open_document(str(entries[labels.index(label)][0]))
            self._current_viewer().require_save_as=True

    def _save_as_local(self) -> None:
        """Zapisuje kopię bieżącego (już edytowanego, bo zmiany zapisują się
        na bieżąco) dokumentu w wybranym przez użytkownika miejscu na dysku
        lokalnym. Działa zarówno dla dokumentów lokalnych, jak i otwartych
        z Google Dysku — w tym drugim przypadku powstaje niezależna, czysto
        lokalna kopia (karta przestaje być powiązana z Dyskiem)."""
        viewer = self._current_viewer()
        if viewer is None or not viewer.is_loaded:
            return

        suggested = str(Path(settings.last_folder or str(Path.home())) / viewer.path.name)
        target, _ = QFileDialog.getSaveFileName(self, translator.tr("menu.file.save_as"), suggested, "PDF (*.pdf)")
        if not target:
            return

        target_path = Path(target)
        if target_path.suffix.lower() != ".pdf":
            target_path = target_path.with_suffix(".pdf")

        try:
            if target_path.exists() and QMessageBox.question(self,'Zapisz jako','Plik istnieje. Utworzyć kopię zapasową i nadpisać?')!=QMessageBox.Yes:return
            if viewer.working_copy:
                viewer.working_copy.save(target_path)
                viewer.source_path=target_path.resolve()
            else:
                from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
                atomic_write_bytes(target_path,viewer.path.read_bytes())
        except OSError as exc:
            _logger.exception("Zapisz jako nie powiodlo sie: %s -> %s", viewer.path, target_path)
            QMessageBox.critical(self, translator.tr("menu.file.save_as"), str(exc))
            return

        if not viewer.working_copy:viewer.path = target_path
        viewer.require_save_as=False
        viewer.drive_info = None  # kopia lokalna nie jest już powiązana z Google Dyskiem
        index = self._tabs.indexOf(viewer)
        if index != -1:
            self._tabs.setTabText(index, target_path.name)
        self._update_drive_actions()
        self.statusBar().showMessage(translator.tr("status.saved_as", path=str(target_path)), 3500)

    def _update_save_as_action(self, *_: object) -> None:
        viewer = self._current_viewer()
        self._action_save_as_local.setEnabled(viewer is not None and viewer.is_loaded)

    def _on_folder_selected(self, path: str) -> None:
        if hasattr(self,'_shell'):
            self._shell.tabs.setCurrentIndex(2)
            self._set_workspace_page(2)
        self._folder_tree.show()
        self._document_list.show()
        self._document_list.show_folder(path)
        self._folder_tree.set_current_folder(path)
        self._search_page.folder.setText(path)
        settings.last_folder = path
        self._update_status_bar()

    # Kopia robocza (pełna kopia pliku + SHA-256 całej treści, patrz
    # dms/recovery.WorkingCopy) poniżej tego rozmiaru jest szybka na lokalnym
    # dysku i tworzenie jej synchronicznie nie jest odczuwalne. Powyżej —
    # zwłaszcza na udziale sieciowym szafki DMS — blokowałaby UI na dłużej,
    # bez progress bara i bez możliwości anulowania, więc idzie w tło.
    _ASYNC_OPEN_THRESHOLD_BYTES = 8 * 1024 * 1024

    def _build_working_copy(self, path: str):
        from pdfmanager.dms.recovery import WorkingCopy
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        if size <= self._ASYNC_OPEN_THRESHOLD_BYTES:
            try:return WorkingCopy(path)
            except Exception as exc:
                self._on_load_failed(path,str(exc))
                return None
        from pdfmanager.ui.background_job import run_job
        result_box = {}
        run_job(self, 'Otwieranie dokumentu…', lambda: WorkingCopy(path), lambda wc: result_box.update(value=wc))
        return result_box.get('value')  # None jeśli anulowano albo wystąpił błąd

    def open_document(self, path: str) -> None:
        if hasattr(self,'_shell'):
            self._shell.tabs.setCurrentIndex(3)
            self._set_workspace_page(3)
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if isinstance(widget, PdfViewerWidget) and str(widget.source_path) == str(Path(path).resolve()):
                self._tabs.setCurrentIndex(index)
                self._viewer_stack.setCurrentWidget(self._tabs)
                return

        # Workflow B: ostrzegamy, jeśli plik jest jeszcze "tylko w chmurze"
        # (Google Drive for desktop w trybie strumieniowym) — jego otwarcie
        # wywoła pobranie w tle, co może chwilę potrwać albo zawiedzie bez
        # połączenia z internetem.
        if is_online_only(Path(path)):
            QMessageBox.information(self, translator.tr("drive.browser_title"), translator.tr("drive.online_only_warning"))

        import pymupdf
        protected=False
        try:
            with pymupdf.open(path) as probe:
                protected=probe.needs_pass
            if protected:
                password,ok=QInputDialog.getText(self,'Hasło PDF','Hasło dokumentu:',QLineEdit.EchoMode.Password)
                if not ok:return
                from pdfmanager.pdf_engine.workflows import resave
                from PySide6.QtCore import QStandardPaths
                from uuid import uuid4
                folder=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))/'unlocked'/uuid4().hex
                folder.mkdir(parents=True,exist_ok=True)
                target=folder/Path(path).name
                resave(Path(path),target,password=password)
                path=str(target)
                QMessageBox.information(self,'Hasło PDF','Otwarto lokalną odszyfrowaną kopię roboczą. Oryginał pozostaje niezmieniony. Zapisz kopię w wybranym miejscu przez Zapisz jako.')
        except Exception as exc:
            self._on_load_failed(path,str(exc));return

        working_copy = self._build_working_copy(path)
        if working_copy is None:
            return  # anulowano w oknie postępu albo błąd (zgłoszony już przez run_job)
        viewer = PdfViewerWidget(path, self, working_copy=working_copy)
        viewer.require_save_as=protected
        viewer.load_failed.connect(self._on_load_failed)
        if not viewer.is_loaded:
            return
        viewer.state_changed.connect(self._update_status_bar)
        viewer.ocr_region_requested.connect(lambda rect,v=viewer:self._tools.ocr(True,rect))
        viewer.undo_redo_changed.connect(self._update_undo_redo_actions)
        viewer.document_saved.connect(lambda v=viewer: self._working_copy_changed(v))
        viewer.edit_span_requested.connect(lambda span, v=viewer: self._on_edit_span_requested(v, span))
        viewer.note_requested.connect(lambda point, v=viewer: self._on_note_requested(v, point))
        viewer.free_text_requested.connect(lambda rect, v=viewer: self._on_free_text_requested(v, rect))
        from pdfmanager.dms.preferences import Preferences
        prefs=Preferences();prefs.recent(viewer.source_path)
        state=prefs.view(viewer.source_path)
        if state:
            viewer.set_zoom(state.get('zoom',100))
            viewer.go_to_page(min(state.get('page',0),viewer.page_count-1))
            viewer.set_view_mode(state.get('mode','single'))
        viewer.state_changed.connect(lambda v=viewer:prefs.view(v.source_path,{'zoom':v.zoom_percent,'page':v.current_page,'mode':v.view_mode}))
        viewer.set_active_tool(self._active_tool)
        viewer.stamp_image_path = self._stamp_image_path
        index = self._tabs.addTab(viewer, Path(path).name)
        self._tabs.setCurrentIndex(index)
        self._viewer_stack.setCurrentWidget(self._tabs)
        self._update_status_bar()
        self._update_save_as_action()

    def _on_load_failed(self, path: str, error: str) -> None:
        _logger.error("Nie udalo sie otworzyc pliku %s: %s", path, error)
        QMessageBox.critical(
            self,
            translator.tr("viewer.open_error_title"),
            translator.tr("viewer.open_error_message", path=path, error=error),
        )

    def _close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        if widget is not None:
            widget.close()
            widget.deleteLater()
        if self._tabs.count() == 0:
            self._viewer_stack.setCurrentWidget(self._viewer_placeholder)
        self._update_status_bar()
        self._update_save_as_action()

    def _with_viewer(self, func) -> None:
        viewer = self._current_viewer()
        if viewer is not None:
            func(viewer)

    def _current_viewer(self) -> PdfViewerWidget | None:
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, PdfViewerWidget) else None

    # --------------------------------------------------------- Google Dysk
    def _ensure_drive_client(self) -> DriveApiClient | None:
        secret_path = settings.drive_client_secret_path
        if not secret_path or not Path(secret_path).is_file():
            chosen, _ = QFileDialog.getOpenFileName(
                self, translator.tr("drive.client_secret_prompt_title"), "", "JSON (*.json)"
            )
            if not chosen:
                return None
            settings.drive_client_secret_path = chosen
            secret_path = chosen

        try:
            credentials = get_credentials(Path(secret_path), interactive=True)
            return DriveApiClient.from_credentials(credentials)
        except DriveAuthError as exc:
            _logger.exception("Logowanie do Google Dysku nie powiodlo sie")
            QMessageBox.critical(self, translator.tr("drive.auth_error_title"), str(exc))
            return None

    def _connect_drive(self) -> None:
        client = self._ensure_drive_client()
        if client is None:
            return

        dialog = DriveBrowserDialog(client, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_file is None:
            return

        drive_file = dialog.selected_file
        local_path = cache_path_for(drive_file.id, drive_file.name)
        try:
            client.download(drive_file.id, local_path)
        except DriveApiError as exc:
            _logger.exception("Pobieranie pliku z Google Dysku nie powiodlo sie: %s", drive_file.id)
            QMessageBox.critical(self, translator.tr("drive.download_error_title"), str(exc))
            return

        self.open_document(str(local_path))
        viewer = self._current_viewer()
        if viewer is not None:
            viewer.drive_info = DriveTabInfo(file_id=drive_file.id, baseline=drive_file, client=client)
            self._update_drive_actions()
            self._update_status_bar()

    def _save_to_drive(self) -> None:
        viewer = self._current_viewer()
        info: DriveTabInfo | None = getattr(viewer, "drive_info", None) if viewer else None
        if viewer is None or info is None:
            return

        try:
            updated = info.client.upload_new_revision(info.file_id, viewer.path, info.baseline)
        except DriveConflictError as exc:
            _logger.warning("Konflikt wersji na Google Dysku dla pliku %s", info.file_id)
            QMessageBox.warning(
                self, translator.tr("drive.conflict_title"), translator.tr("drive.conflict_message", name=exc.remote.name)
            )
            return
        except DriveApiError as exc:
            _logger.exception("Zapis do Google Dysku nie powiodl sie: %s", info.file_id)
            QMessageBox.critical(self, translator.tr("drive.error_title"), str(exc))
            return

        viewer.drive_info = DriveTabInfo(file_id=info.file_id, baseline=updated, client=info.client)
        QMessageBox.information(self, translator.tr("drive.browser_title"), translator.tr("drive.save_success"))

    def _save_as_new_on_drive(self) -> None:
        viewer = self._current_viewer()
        info: DriveTabInfo | None = getattr(viewer, "drive_info", None) if viewer else None
        if viewer is None or info is None:
            return

        name, ok = QInputDialog.getText(
            self, translator.tr("drive.save_as_name_prompt_title"), translator.tr("drive.save_as_name_prompt_title"),
            text=viewer.path.name,
        )
        if not ok or not name.strip():
            return

        parent_id = info.baseline.parents[0] if info.baseline.parents else None
        try:
            new_file = info.client.upload_new_file(viewer.path, name.strip(), parent_folder_id=parent_id)
        except DriveApiError as exc:
            _logger.exception("Zapis jako nowy plik na Google Dysku nie powiodl sie")
            QMessageBox.critical(self, translator.tr("drive.error_title"), str(exc))
            return

        QMessageBox.information(
            self, translator.tr("drive.browser_title"), translator.tr("drive.save_as_success", name=new_file.name)
        )

    def _update_drive_actions(self, *_: object) -> None:
        viewer = self._current_viewer()
        is_drive_tab = viewer is not None and getattr(viewer, "drive_info", None) is not None
        self._action_drive_save.setEnabled(is_drive_tab)
        self._action_drive_save_as_new.setEnabled(is_drive_tab)

    def _select_language(self, lang: str) -> None:
        translator.set_language(lang)
        settings.language = lang

    def _select_theme(self, theme: str) -> None:
        settings.theme = theme
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)

    # ---------------------------------------------------------------- licencja
    def _open_activation_dialog(self) -> None:
        dialog = ActivationDialog(self.license_manager, self, allow_cancel=True)
        dialog.exec()
        self._update_license_status_bar()

    def _update_license_status_bar(self) -> None:
        status = self.license_manager.get_status()
        if status.is_near_expiry:
            self._status_license_label.setText(translator.tr("status.license_days_remaining", days=status.days_remaining))
            self._status_license_label.setVisible(True)
        else:
            self._status_license_label.clear()
            self._status_license_label.setVisible(False)

    def _check_license_and_warn(self) -> None:
        """Wywoływane przy starcie i raz na dobę podczas pracy (QTimer)."""
        status = self.license_manager.get_status()
        self._update_license_status_bar()
        if not status.is_near_expiry:
            return
        warning = ExpiryWarningDialog(status.days_remaining, self)
        warning.exec()
        if warning.enter_key_requested:
            self._open_activation_dialog()

    # ------------------------------------------------- skojarzenie z PDF (Windows)
    def _set_default_pdf_app(self) -> None:
        if sys.platform != "win32":
            QMessageBox.information(self, translator.tr("winassoc.title"), translator.tr("winassoc.windows_only"))
            return

        if not getattr(sys, "frozen", False):
            # Uruchomione ze źródeł (python -m pdfmanager.main) — sys.executable
            # to interpreter Pythona, nie nasz program. Zarejestrowanie go jako
            # domyślnego programu wskazywałoby na python.exe, nie na aplikację —
            # ta operacja ma sens tylko dla spakowanej wersji (.exe z instalatora).
            QMessageBox.information(self, translator.tr("winassoc.title"), translator.tr("winassoc.dev_mode_warning"))
            return

        try:
            register_application(Path(sys.executable))
        except FileAssociationError as exc:
            _logger.exception("Rejestracja skojarzenia z PDF nie powiodla sie")
            QMessageBox.critical(self, translator.tr("winassoc.title"), str(exc))
            return

        QMessageBox.information(self, translator.tr("winassoc.title"), translator.tr("winassoc.instructions"))
        try:
            open_default_apps_settings()
        except FileAssociationError as exc:
            _logger.exception("Otwarcie Ustawien Windows nie powiodlo sie")
            QMessageBox.critical(self, translator.tr("winassoc.title"), str(exc))

    def _check_default_pdf_app(self) -> None:
        if sys.platform != "win32":
            QMessageBox.information(self, translator.tr("winassoc.title"), translator.tr("winassoc.windows_only"))
            return
        is_default = is_registered_as_default()
        message = translator.tr("winassoc.status_yes") if is_default else translator.tr("winassoc.status_no")
        QMessageBox.information(self, translator.tr("winassoc.title"), message)

    def _on_tool_triggered(self, tool: str) -> None:
        if tool == TOOL_STAMP:
            path, _ = QFileDialog.getOpenFileName(
                self, translator.tr("annot.choose_image_title"), "", "Obrazy (*.png *.jpg *.jpeg *.bmp)"
            )
            if not path:
                # Użytkownik nie wybrał obrazu — wracamy do poprzednio aktywnego narzędzia.
                self._tool_actions[self._active_tool].setChecked(True)
                return
            self._stamp_image_path = Path(path)

        self._active_tool = tool
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if isinstance(widget, PdfViewerWidget):
                widget.stamp_image_path = self._stamp_image_path
                widget.set_active_tool(tool)

    def _open_page_manager(self) -> None:
        viewer = self._current_viewer()
        if viewer is None:
            return
        path = viewer.path
        # Zwalniamy uchwyt pliku PRZED otwarciem okna operacji na stronach —
        # na Windows nadpisanie pliku, który wciąż jest otwarty w tym
        # procesie (nawet tylko do podglądu), zakończyłoby się błędem.
        before=viewer.path.read_bytes()
        viewer.release_document()
        try:
            dialog = PageManagerDialog(path, self)
            dialog.exec()
        finally:
            viewer.reload_document()
            viewer.record_external_edit(before)
            self._update_status_bar()

    def _merge_pdfs(self) -> None:
        sources, _ = QFileDialog.getOpenFileNames(self, translator.tr("menu.pages.merge"), "", "PDF (*.pdf)")
        if len(sources) < 2:
            return
        output, _ = QFileDialog.getSaveFileName(self, translator.tr("menu.pages.merge"), "", "PDF (*.pdf)")
        if not output:
            return
        try:
            page_ops.merge_documents([Path(p) for p in sources], Path(output))
        except page_ops.PageOpError as exc:
            _logger.exception("Scalanie plikow PDF nie powiodlo sie")
            QMessageBox.warning(self, translator.tr("pages.error_title"), str(exc))
            return
        QMessageBox.information(self, translator.tr("menu.pages.merge"), translator.tr("menu.pages.merge_done", path=output))

    def _open_proofreading(self) -> None:
        viewer = self._current_viewer()
        if viewer is None or not viewer.is_loaded:
            return
        path, page_count = viewer.path, viewer.page_count
        # Tak jak w Menedżerze stron: zwalniamy uchwyt pliku na czas działania
        # okna, żeby ewentualne poprawki (zapis na dysk) nie zablokowały się
        # na Windows o własny, wciąż otwarty uchwyt podglądu.
        before=viewer.path.read_bytes()
        viewer.release_document()
        try:
            dialog = ProofreadingDialog(path, page_count, self)
            dialog.exec()
        finally:
            viewer.reload_document()
            viewer.record_external_edit(before)
            self._update_status_bar()

    def _on_note_requested(self, viewer: PdfViewerWidget, point: tuple) -> None:
        text, ok = QInputDialog.getText(self, translator.tr("annot.note_dialog_title"), translator.tr("annot.note_dialog_label"))
        if ok and text.strip():
            viewer.add_note_at(point, text)

    def _on_free_text_requested(self, viewer: PdfViewerWidget, rect: tuple) -> None:
        text, ok = QInputDialog.getText(
            self, translator.tr("annot.freetext_dialog_title"), translator.tr("annot.freetext_dialog_label")
        )
        if ok and text.strip():
            viewer.add_free_text_at(rect, text)

    def _update_undo_redo_actions(self, *_: object) -> None:
        viewer = self._current_viewer()
        self._action_undo.setEnabled(viewer is not None and viewer.can_undo)
        self._action_redo.setEnabled(viewer is not None and viewer.can_redo)

    def _on_edit_span_requested(self, viewer: PdfViewerWidget, span: TextSpan) -> None:
        if self._text_properties.isVisible():
            self._text_properties.select_span(viewer,span)
            return
        from pdfmanager.ui.content_editor import TextStyleDialog
        dialog = TextStyleDialog(self, span)
        if not dialog.exec():
            return
        new_text, style = dialog.result_style()
        if not new_text.strip():
            return

        try:
            result = viewer.apply_text_edit(span, new_text, style=style, font_file=dialog.font_file)
        except TextEditError as exc:
            _logger.exception("Edycja tekstu nie powiodla sie")
            QMessageBox.critical(self, translator.tr("textedit.error_title"), str(exc))
            return

        if result.warnings:
            message = "\n".join(translator.tr(f"textedit.warning.{code}") for code in result.warnings)
            QMessageBox.warning(self, translator.tr("textedit.warnings_title"), message)

    def _show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(translator.tr("about.title"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.RichText)
        body = translator.tr("about.text").replace("\n", "<br>")
        box.setText(f"{body}<br><br><b>{ABOUT_DEDICATION}</b>")
        box.exec()

    def _show_log_file(self) -> None:
        """Otwiera folder z plikiem dziennika (log.txt) — przydatne do
        wysłania zrzutu błędów przy zgłaszaniu problemu."""
        folder = log_dir()
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not opened:
            QMessageBox.information(self, translator.tr("menu.help.show_log"), translator.tr("log.location_message", path=str(folder)))

    # ------------------------------------------------------------ status bar
    def _flash_saved_message(self) -> None:
        self.statusBar().showMessage(translator.tr("status.saved"), 2500)

    def _update_status_bar(self, *_: object) -> None:
        viewer = self._current_viewer()
        drive_info: DriveTabInfo | None = getattr(viewer, "drive_info", None) if viewer else None

        if drive_info is not None:
            # Workflow A: wyraźnie odróżniamy dokument obsługiwany przez
            # Google Drive API od zwykłego pliku lokalnego.
            folder_text = translator.tr("status.drive_document", name=drive_info.baseline.name)
        else:
            folder = settings.last_folder
            if folder and looks_like_drive_desktop_folder(Path(folder)):
                folder_text = translator.tr("status.local_sync_folder", path=folder)
            else:
                folder_text = folder if folder else translator.tr("status.no_folder")
        self._status_folder_label.setText(folder_text)

        if viewer is not None and viewer.is_loaded:
            text = translator.tr(
                "status.page_info",
                current=viewer.current_page + 1,
                total=viewer.page_count,
                zoom=viewer.zoom_percent,
            )
        else:
            text = ""
        self._status_page_label.setText(text)
        if viewer and hasattr(self,'_view_modes'):
            self._view_modes.blockSignals(True)
            self._view_modes.setCurrentIndex(['single','continuous','two','book','grid'].index(viewer.view_mode))
            self._view_modes.blockSignals(False)
            self._zoom_combo.blockSignals(True);self._zoom_combo.setCurrentText(f'{viewer.zoom_percent}%');self._zoom_combo.blockSignals(False)
            self._night_action.setChecked(viewer.night_mode)

    # ------------------------------------------------------------- i18n
    def retranslate_ui(self) -> None:
        translator_ = translator  # krótszy alias lokalny
        self.setWindowTitle(translator_.tr("app.title"))

        self._menu_file.setTitle(translator_.tr("menu.file"))
        self._action_open_folder.setText(translator_.tr("menu.file.open_folder"))
        self._action_open_file.setText(translator_.tr("menu.file.open_file"))
        self._action_save_as_local.setText(translator_.tr("menu.file.save_as"))
        self._action_drive_connect.setText(translator_.tr("menu.file.drive_connect"))
        self._action_drive_save.setText(translator_.tr("menu.file.drive_save"))
        self._action_drive_save_as_new.setText(translator_.tr("menu.file.drive_save_as_new"))
        # Wyszarzone dla dokumentów lokalnych — tooltip wyjaśnia dlaczego,
        # żeby nie wyglądało to na usterkę (patrz zgłoszenie użytkownika).
        self._action_drive_save.setToolTip(translator_.tr("drive.save_requires_drive_document"))
        self._action_drive_save_as_new.setToolTip(translator_.tr("drive.save_requires_drive_document"))
        self._action_close_tab.setText(translator_.tr("menu.file.close_tab"))
        self._action_exit.setText(translator_.tr("menu.file.exit"))

        self._menu_edit.setTitle(translator_.tr("menu.edit"))
        for tool, action in self._tool_actions.items():
            action.setText(translator_.tr(TOOL_LABEL_KEYS[tool]))
        self._action_undo.setText(translator_.tr("menu.edit.undo"))
        self._action_redo.setText(translator_.tr("menu.edit.redo"))

        self._menu_pages.setTitle(translator_.tr("menu.pages"))
        self._action_manage_pages.setText(translator_.tr("menu.pages.manage"))
        self._action_merge_pdfs.setText(translator_.tr("menu.pages.merge"))

        self._menu_tools.setTitle(translator_.tr("menu.tools"))
        self._action_proofread.setText(translator_.tr("menu.tools.proofread"))

        self._menu_view.setTitle(translator_.tr("menu.view"))
        self._action_zoom_in.setText(translator_.tr("menu.view.zoom_in"))
        self._action_zoom_out.setText(translator_.tr("menu.view.zoom_out"))
        self._action_fit_width.setText(translator_.tr("menu.view.fit_width"))
        self._action_actual_size.setText(translator_.tr("menu.view.actual_size"))

        self._menu_settings.setTitle(translator_.tr("menu.settings"))
        self._menu_language.setTitle(translator_.tr("menu.settings.language"))
        for lang, action in self._language_actions.items():
            action.setText(translator_.tr(LANGUAGE_LABEL_KEYS[lang]))
            action.setChecked(lang == translator_.language)
        self._menu_theme.setTitle(translator_.tr("menu.settings.theme"))
        for theme, action in self._theme_actions.items():
            action.setText(translator_.tr(THEME_LABEL_KEYS[theme]))
        self._action_set_default_pdf_app.setText(translator_.tr("menu.settings.set_default_pdf_app"))
        self._action_check_default_pdf_app.setText(translator_.tr("menu.settings.check_default_pdf_app"))

        self._menu_help.setTitle(translator_.tr("menu.help"))
        self._action_show_log.setText(translator_.tr("menu.help.show_log"))
        self._action_about.setText(translator_.tr("menu.help.about"))

        self._tb_open_folder.setText(translator_.tr("toolbar.open_folder"))
        self._tb_prev_page.setText(translator_.tr("toolbar.prev_page"))
        self._tb_next_page.setText(translator_.tr("toolbar.next_page"))
        self._tb_zoom_out.setText(translator_.tr("toolbar.zoom_out"))
        self._tb_zoom_in.setText(translator_.tr("toolbar.zoom_in"))
        self._tb_fit_width.setText(translator_.tr("toolbar.fit_width"))

        self._viewer_placeholder.setText(translator_.tr("viewer.no_document"))

        self._update_status_bar()
        self._update_undo_redo_actions()

    # ------------------------------------------------------------- zamknięcie
    def closeEvent(self, event) -> None:
        self._scan_automation.stop()
        if self._compare_viewer:
            self._compare_viewer.release_document()
        if self._compare_temp:
            self._compare_temp.cleanup()
        for index in range(self._tabs.count()):
            widget=self._tabs.widget(index)
            widget.release_document()
            if widget.working_copy:widget.working_copy.close()
        settings.set_window_geometry(self.saveGeometry())
        super().closeEvent(event)
