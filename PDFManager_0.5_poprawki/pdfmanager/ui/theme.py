"""Motywy wizualne aplikacji (jasny/ciemny) — paleta Qt + arkusz stylów.

Używa stylu `Fusion` (jedyny styl Qt w pełni sterowalny przez QPalette na
każdej platformie, w tym Windows) + lekki arkusz QSS dla bardziej
nowoczesnego wyglądu (zaokrąglone rogi, spójne odstępy, kolor akcentu).
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

THEME_LIGHT = "light"
THEME_DARK = "dark"
SUPPORTED_THEMES = (THEME_LIGHT, THEME_DARK)

_ACCENT = "#2F6FED"
_ACCENT_HOVER = "#4C84F0"

_BASE_STYLESHEET = """
QWidget {{
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background-color: {window};
}}
QToolBar {{
    background-color: {panel};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 6px;
    padding: 6px 8px;
}}
QToolBar::separator {{
    background-color: {border};
    width: 1px;
    margin: 4px 6px;
}}
QMenuBar {{
    background-color: {panel};
    border-bottom: 1px solid {border};
    padding: 2px 4px;
}}
QMenuBar::item {{
    padding: 5px 10px;
    border-radius: 5px;
}}
QMenuBar::item:selected {{
    background-color: {accent};
    color: white;
}}
QMenu {{
    background-color: {panel};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background-color: {accent};
    color: white;
}}
QMenu::item:checked {{
    font-weight: 700;
}}
QMenu::separator {{
    height: 1px;
    background-color: {border};
    margin: 6px 4px;
}}
QPushButton {{
    background-color: {button};
    border: 1px solid {border};
    border-radius: 7px;
    padding: 6px 16px;
}}
QPushButton:hover {{
    background-color: {accent_hover};
    color: white;
    border-color: {accent_hover};
}}
QPushButton:pressed {{
    background-color: {accent};
    color: white;
    font-weight: 700;
}}
QPushButton:disabled {{
    color: {disabled_text};
    border-color: {border};
}}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QListWidget, QTreeView {{
    background-color: {field};
    border: 1px solid {border};
    border-radius: 6px;
    selection-background-color: {accent};
    selection-color: white;
}}
QLineEdit, QComboBox, QSpinBox {{
    padding: 4px 8px;
}}
QTreeView::item, QListView::item {{
    padding: 3px 2px;
    border-radius: 4px;
}}
QTreeView::item:selected, QListView::item:selected {{
    background-color: {accent};
    color: white;
}}
QHeaderView::section {{
    background-color: {panel};
    border: none;
    border-bottom: 1px solid {border};
    padding: 5px 8px;
    font-weight: 600;
}}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background-color: {panel};
    border: 1px solid {border};
    padding: 7px 16px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    background-color: {accent};
    color: white;
    border-color: {accent};
    font-weight: 700;
}}
QTabBar::tab:!selected:hover {{
    background-color: {accent_hover};
    color: white;
}}
QStatusBar {{
    background-color: {panel};
    border-top: 1px solid {border};
}}
QToolButton {{
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}}
QToolButton:hover {{
    background-color: {accent_hover};
    border-color: {accent_hover};
}}
QToolButton:checked {{
    background-color: {accent};
    border-color: {accent};
    color: white;
    font-weight: 700;
}}
QToolButton:pressed {{
    font-weight: 700;
}}
QSplitter::handle {{
    background-color: {border};
    width: 1px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {accent_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {border};
    border-radius: 5px;
    min-width: 24px;
}}
QToolTip {{
    background-color: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 8px;
}}
#HeaderBar {{
    background-color: {header};
    border-bottom: 1px solid {border};
}}
#HeaderCopyrightLabel {{
    color: {header_text};
    font-size: 9pt;
}}
"""


def _light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F4F5F7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1B1F24"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#EEF0F3"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1B1F24"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1B1F24"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8A8F98"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#1B1F24"))
    return palette


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#20232A"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#E6E8EB"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#282C34"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2E333D"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#E6E8EB"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2E333D"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#E6E8EB"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8A8F98"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2E333D"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#E6E8EB"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#6B6F76"))
    return palette


def _stylesheet_colors(theme: str) -> dict[str, str]:
    if theme == THEME_DARK:
        return {
            "window": "#20232A",
            "panel": "#282C34",
            "button": "#2E333D",
            "field": "#1C1F25",
            "border": "#3A3F4B",
            "disabled_text": "#6B6F76",
            "header": "#1A1C21",
            "header_text": "#B8BCC4",
            "text": "#E6E8EB",
        }
    return {
        "window": "#F4F5F7",
        "panel": "#FFFFFF",
        "button": "#FFFFFF",
        "field": "#FFFFFF",
        "border": "#D7DAE0",
        "disabled_text": "#A3A7AE",
        "header": "#FFFFFF",
        "header_text": "#6B6F76",
        "text": "#1B1F24",
    }


def apply_theme(app: QApplication, theme: str) -> None:
    if theme not in SUPPORTED_THEMES:
        raise ValueError(f"Nieznany motyw: {theme}")

    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(_light_palette() if theme == THEME_LIGHT else _dark_palette())

    colors = _stylesheet_colors(theme)
    colors["accent"] = _ACCENT
    colors["accent_hover"] = _ACCENT_HOVER
    from pdfmanager.app_settings import settings
    title = settings.title_color if QColor(settings.title_color).isValid() else '#2d5997'
    toolbar = settings.toolbar_color if QColor(settings.toolbar_color).isValid() else '#ffffff'
    customization = '#WorkspaceTitleBar { background: '+title+'; }'
    if theme == THEME_LIGHT:
        customization += '#WorkspaceShell QStackedWidget { background: '+toolbar+'; }'
    app.setStyleSheet(_BASE_STYLESHEET.format(**colors) + (_CLASSIC_LIGHT + _WORKSPACE_LIGHT if theme == THEME_LIGHT else _WORKSPACE_DARK) + customization)

_CLASSIC_LIGHT = """
QWidget { font-size: 9pt; }
QMainWindow { background: #c4def5; }
QMenuBar, QToolBar, #ClassicRibbon, QStatusBar {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f3f8fe,stop:1 #c7dff5);
    color: #22384d; border-bottom: 1px solid #8db2d4;
}
QToolBar { spacing: 2px; padding: 2px; }
#RibbonToolbar { padding: 0; }
#RibbonGroupLabel { color: #3e5c79; font-size: 8pt; }
QToolButton { border-radius: 2px; padding: 3px; }
QToolButton:hover, QToolButton:checked {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fff3bc,stop:1 #ffd678);
    border: 1px solid #d6a83f; color: #263b50;
}
QMenuBar::item { padding: 3px 10px; border-radius: 1px; }
QTabWidget::pane { border: 1px solid #8db2d4; border-radius: 0; }
QTabBar::tab { background: #dcebf9; border-radius: 0; padding: 3px 12px; }
QTabBar::tab:selected { background: #ffe6a0; color: #25384d; border-color: #c8a854; }
QScrollArea { background: #b9c1ca; border: 1px solid #8b9da9; }
#PageThumbnails { background: #eaf3fc; border: 1px solid #9ab9d4; border-radius: 0; }
#PageThumbnails::item:selected { background: #fff0c1; border: 2px solid #dbac4d; color: #263b50; }
QSplitter::handle { background: #c3dcf2; width: 4px; }
QLineEdit, QSpinBox, QComboBox { border-radius: 1px; padding: 2px 4px; }
"""

_WORKSPACE_LAYOUT = """
#WorkspaceTitleBar { background: #2d5997; }
#WorkspaceTitleBar QLabel, #WorkspaceTitleBar QToolButton { color: white; }
#WorkspaceTitleBar QToolButton { border: none; border-radius: 0; }
#WorkspaceTitleBar QToolButton:hover { background: #4875b1; }
#WorkspaceTabs::tab { padding: 5px 16px; border: none; border-radius: 0; margin: 0; }
#WorkspaceTabs::tab:selected { border-top: 2px solid #338ef4; font-weight: bold; }
#HomeHeadline { font-size: 24pt; }
QToolBar { padding: 1px 3px; spacing: 1px; }
QToolButton { padding: 2px; border-radius: 1px; }
QTabWidget::pane, QTabBar::tab, QMenu, QMenuBar::item, QPushButton,
QLineEdit, QComboBox, QSpinBox, QTreeView, QListWidget { border-radius: 0; }
"""
_WORKSPACE_LIGHT = _WORKSPACE_LAYOUT + """
#WorkspaceShell { background: #f1f1f1; }
#WorkspaceTabs::tab, #WorkspaceTabs::tab:selected { background: #f0f0f0; color: #142332; }
#WorkspaceShell QStackedWidget { background: white; border: 1px solid #d0d0d0; }
QMainWindow { background: #f0f0f0; border: 1px solid #909090; }
QToolBar, QMenuBar, QStatusBar { background: #f3f3f3; border-bottom: 1px solid #d3d3d3; }
QToolButton:hover { background: #e5f0fa; border: 1px solid #afcee9; }
QToolButton:checked { background: #fff0ba; border: 1px solid #d4b45c; }
QScrollArea { background: #b0b0b0; border: 1px solid #909090; }
#PageThumbnails { background: #f1f1f1; border: 1px solid #cccccc; }
QSplitter::handle { background: #ededed; width: 5px; }
"""
_WORKSPACE_DARK = _WORKSPACE_LAYOUT + """
#WorkspaceShell { background: #282c34; }
#WorkspaceTabs::tab, #WorkspaceTabs::tab:selected { background: #282c34; color: #eeeeee; }
#WorkspaceShell QStackedWidget { background: #20232a; border: 1px solid #444; }
"""
