"""Tabbed document workspace with original line icons and PDFManager identity."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QWidget,QHBoxLayout,QVBoxLayout,QLabel,QToolButton,QTabBar,
                              QStackedWidget,QMenuBar,QFrame)
from .vector_icons import vector_icon


class TitleBar(QWidget):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setObjectName('WorkspaceTitleBar');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True);self.setFixedHeight(28)
        row=QHBoxLayout(self);row.setContentsMargins(6,0,0,0)
        mark=QLabel();mark.setPixmap(vector_icon('brand',20).pixmap(20,20));row.addWidget(mark)
        self.title=QLabel('PDFManager');row.addWidget(self.title);row.addStretch()
        for text,tip,callback in [('—','Minimalizuj',window.showMinimized),('□','Maksymalizuj / przywróć',self.toggle_maximize),('×','Zamknij',window.close)]:
            button=QToolButton(self);button.setText(text);button.setToolTip(tip);button.setFixedSize(45,28);button.clicked.connect(callback);row.addWidget(button)
        window.windowTitleChanged.connect(self.title.setText)
    def toggle_maximize(self):
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window.windowHandle():self.window.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.toggle_maximize()


class WorkspaceShell(QWidget):
    def __init__(self,window,old_menu,pages):
        super().__init__(window);self.setObjectName('WorkspaceShell')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        layout.addWidget(TitleBar(window))
        self.tabs=QTabBar(self);self.tabs.setObjectName('WorkspaceTabs');self.tabs.setExpanding(False)
        self.ribbon=QStackedWidget(self);self.ribbon.setFixedHeight(76)
        for label,actions in pages:
            self.tabs.addTab(label)
            panel=QWidget();row=QHBoxLayout(panel);row.setContentsMargins(7,5,7,5);row.setSpacing(5)
            for action in actions:
                button=QToolButton(panel);button.setDefaultAction(action);button.setIconSize(QSize(30,30))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon);button.setMinimumWidth(48);button.setFixedHeight(63);row.addWidget(button)
            row.addStretch();self.ribbon.addWidget(panel)
        layout.addWidget(self.tabs);layout.addWidget(self.ribbon)
        menu=QMenuBar(self)
        for action in old_menu.actions():
            if action.menu():
                action.menu().setParent(window,Qt.WindowType.Popup)
                action.menu().hide()
            menu.addAction(action)
        old_menu.clear()
        old_menu.hide()
        menu.setNativeMenuBar(False)
        layout.addWidget(menu)
        from pdfmanager.app_settings import settings
        if settings.compact_toolbar:
            self.ribbon.setFixedHeight(56)
            for button in self.ribbon.findChildren(QToolButton):
                button.setFixedHeight(44);button.setIconSize(QSize(22,22))
        self.tabs.currentChanged.connect(self.ribbon.setCurrentIndex)
