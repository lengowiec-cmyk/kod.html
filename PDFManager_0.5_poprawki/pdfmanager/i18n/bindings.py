"""Static UI translations; user data and stored combo values remain unchanged."""
from pathlib import Path
from PySide6.QtCore import QObject, QEvent, QSignalBlocker, Qt, QTranslator, QLibraryInfo, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QAbstractButton, QComboBox,
    QFontComboBox, QDialogButtonBox, QToolButton, QTabBar, QGroupBox, QMenu, QListWidget, QTableWidget, QTreeWidget, QLineEdit)
from .translator import translator
SOURCE_ROLE = int(Qt.UserRole) + 117
LAST_ROLE = SOURCE_ROLE + 1

def current_source(combo):
    """Canonical value for persistence, independent of the display language."""
    value = combo.currentData(SOURCE_ROLE)
    return value if value is not None else combo.currentText()

def select_source(combo, source):
    for i in range(combo.count()):
        if (combo.itemData(i, SOURCE_ROLE) or combo.itemText(i)) == source:
            combo.setCurrentIndex(i)
            return
    combo.setCurrentText(source)

class UiTranslations(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.qt, self.busy = app, None, False
        app.installEventFilter(self)
        translator.language_changed.connect(self.language_changed)
        self.install_qt()

    def install_qt(self):
        if self.qt:
            self.app.removeTranslator(self.qt)
            self.qt = None
        if translator.language == 'en':return
        qt = QTranslator(self)
        for root in [Path(__file__).parents[1]/'resources'/'qt_translations',
                     Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))]:
            if qt.load(str(root/f'qtbase_{translator.language}.qm')):
                self.app.installTranslator(qt);self.qt = qt;break

    def language_changed(self, _):
        self.install_qt()
        for window in self.app.topLevelWidgets():self.retranslate(window)

    def eventFilter(self, obj, event):
        if event.type()==QEvent.LanguageChange and isinstance(obj,QDialogButtonBox) and any(b.property('i18nText') for b in obj.buttons()):
            # This box has explicit application captions, rather than Qt's
            # standard labels. Preserve them when Qt updates its translator.
            self.retranslate(obj)
            return True
        if event.type() in (QEvent.Show,QEvent.LanguageChange) and isinstance(obj,QWidget) and obj.isWindow():
            self.retranslate(obj)
            # Qt standard button boxes may reset captions after the parent Show
            # or LanguageChange event; reapply explicit captions afterwards.
            QTimer.singleShot(0,obj,lambda:self.retranslate(obj))
        return False

    def caption(self, obj, name, getter, setter):
        value = getter()
        if not isinstance(value, str):return
        source_key, last_key = '_i18n_source_'+name, '_i18n_last_'+name
        explicit = obj.property('i18nText') if name=='text' else None
        source = explicit or obj.property(source_key)
        if not explicit and (source is None or value != obj.property(last_key)):
            source = translator.source(value)
            obj.setProperty(source_key, source)
        if source is not None:
            text = translator.text(source)
            if value != text:setter(text)
            obj.setProperty(last_key, text)

    def combo(self, obj):
        with QSignalBlocker(obj):
            for i in range(obj.count()):
                value = obj.itemText(i);source = obj.itemData(i, SOURCE_ROLE)
                if source is None or value != obj.itemData(i, LAST_ROLE):
                    source = translator.source(value);obj.setItemData(i, source, SOURCE_ROLE)
                if source is not None:
                    text = translator.text(source)
                    obj.setItemText(i, text);obj.setItemData(i, text, LAST_ROLE)

    def retranslate(self, root):
        if self.busy:return
        self.busy = True
        try:
            for obj in [root]+root.findChildren(QObject):
                if obj.property('i18nSkip'):continue
                if isinstance(obj, QWidget):
                    self.caption(obj,'windowTitle',obj.windowTitle,obj.setWindowTitle)
                    self.caption(obj,'toolTip',obj.toolTip,obj.setToolTip)
                if isinstance(obj,(QAction,QLabel,QAbstractButton)) and not (isinstance(obj,QToolButton) and obj.defaultAction()):
                    self.caption(obj,'text',obj.text,obj.setText)
                    if isinstance(obj,QAbstractButton):self.caption(obj,'accessibleName',obj.accessibleName,obj.setAccessibleName)
                if isinstance(obj,QAction):
                    self.caption(obj,'toolTip',obj.toolTip,obj.setToolTip)
                    self.caption(obj,'statusTip',obj.statusTip,obj.setStatusTip)
                if isinstance(obj,(QGroupBox,QMenu)):
                    self.caption(obj,'title',obj.title,obj.setTitle)
                if isinstance(obj,QLineEdit):
                    self.caption(obj,'placeholder',obj.placeholderText,obj.setPlaceholderText)
                if isinstance(obj,QComboBox) and not isinstance(obj,QFontComboBox) and not obj.isEditable():self.combo(obj)
                if isinstance(obj,QTabBar):
                    for i in range(obj.count()):
                        key = f'_i18n_tab_{i}';source = obj.property(key)
                        if source is None:
                            source = translator.source(obj.tabText(i));obj.setProperty(key,source)
                        if source is not None:obj.setTabText(i,translator.text(source))
                if isinstance(obj,QListWidget):
                    for i in range(obj.count()):
                        item=obj.item(i)
                        source=item.data(SOURCE_ROLE)
                        if source is None and obj.property('i18nItems'):source=translator.source(item.text())
                        if source:item.setData(SOURCE_ROLE,source);item.setText(translator.text(source))
                if isinstance(obj,QTableWidget):
                    for i in range(obj.columnCount()):
                        item=obj.horizontalHeaderItem(i)
                        if item:
                            source=item.data(SOURCE_ROLE) or translator.source(item.text())
                            if source:item.setData(SOURCE_ROLE,source);item.setText(translator.text(source))
                if isinstance(obj,QTreeWidget):
                    item=obj.headerItem()
                    for i in range(obj.columnCount()):
                        source=item.data(i,SOURCE_ROLE) or translator.source(item.text(i))
                        if source:item.setData(i,SOURCE_ROLE,source);item.setText(i,translator.text(source))
        finally:self.busy=False

def install_ui_translations(root):
    app=QApplication.instance();binder=getattr(app,'_pdfmanager_ui_translations',None)
    if binder is None:
        binder=UiTranslations(app);app._pdfmanager_ui_translations=binder
    binder.retranslate(root)
    return binder
