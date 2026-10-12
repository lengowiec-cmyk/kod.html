"""Original PDFManager ribbon: grouped tools, own identity and responsive scrolling."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QToolButton,QTabBar,QStackedWidget,QMenuBar,QFrame,QScrollArea
from .vector_icons import vector_icon

class TitleBar(QWidget):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setObjectName('WorkspaceTitleBar');self.setAttribute(Qt.WA_StyledBackground,True);self.setFixedHeight(34)
        row=QHBoxLayout(self);row.setContentsMargins(12,0,0,0)
        mark=QLabel();mark.setPixmap(vector_icon('brand',23).pixmap(23,23));row.addWidget(mark)
        self.title=QLabel('PDFManager • Centrum dokumentów');row.addWidget(self.title);row.addStretch()
        for text,tip,callback in [('—','Minimalizuj',window.showMinimized),('□','Maksymalizuj / przywróć',self.toggle_maximize),('×','Zamknij',window.close)]:
            button=QToolButton();button.setText(text);button.setToolTip(tip);button.setFixedSize(46,34);button.clicked.connect(callback);row.addWidget(button)
        window.windowTitleChanged.connect(lambda title:self.title.setText('PDFManager • Centrum dokumentów'))
    def toggle_maximize(self):self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.window.windowHandle():self.window.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:self.toggle_maximize()

class WorkspaceShell(QWidget):
    def __init__(self,window,old_menu,pages):
        super().__init__(window);self.setObjectName('WorkspaceShell');layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        layout.addWidget(TitleBar(window));self.tabs=QTabBar();self.tabs.setObjectName('WorkspaceTabs');self.tabs.setExpanding(False);self.tabs.setUsesScrollButtons(True);layout.addWidget(self.tabs)
        self.ribbon=QStackedWidget();self.ribbon.setFixedHeight(103)
        for label,actions in pages:
            self.tabs.addTab(label);scroll=QScrollArea();scroll.setObjectName('RibbonScroll');scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.NoFrame);scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            panel=QWidget();panel.setObjectName('RibbonPanel');row=QHBoxLayout(panel);row.setContentsMargins(10,6,10,4);row.setSpacing(10)
            chunks=[actions[i:i+4] for i in range(0,len(actions),4)]
            names={'Organizuj':['Archiwum','Porządkowanie','Dokumenty','Narzędzia'],'Skrzynka':['Pozyskiwanie','Przetwarzanie','Pliki','Narzędzia'],'Edytor PDF':['Dokument','Strony i OCR','Oznaczenia','Ustawienia']}.get(label,['Dokumenty','Operacje','Narzędzia','Dodatkowe'])
            for i,chunk in enumerate(chunks):
                group=QWidget();group.setObjectName('RibbonGroup');group_layout=QVBoxLayout(group);group_layout.setContentsMargins(3,0,3,0);group_layout.setSpacing(1);buttons=QHBoxLayout();buttons.setSpacing(4)
                for action in chunk:
                    button=QToolButton();button.setDefaultAction(action);button.setIconSize(QSize(31,31));button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon);button.setMinimumWidth(65);button.setFixedHeight(65);buttons.addWidget(button)
                group_layout.addLayout(buttons);caption=QLabel(names[min(i,len(names)-1)]);caption.setObjectName('RibbonCaption');caption.setAlignment(Qt.AlignCenter);group_layout.addWidget(caption);row.addWidget(group)
                if i<len(chunks)-1:
                    line=QFrame();line.setFrameShape(QFrame.VLine);line.setObjectName('RibbonDivider');row.addWidget(line)
            row.addStretch();scroll.setWidget(panel);self.ribbon.addWidget(scroll)
        layout.addWidget(self.ribbon)
        menu=QMenuBar();menu.setNativeMenuBar(False)
        for action in old_menu.actions():
            if action.menu():action.menu().setParent(window,Qt.Popup);action.menu().hide()
            menu.addAction(action)
        old_menu.clear();old_menu.hide();layout.addWidget(menu);self.tabs.currentChanged.connect(self.ribbon.setCurrentIndex)
        from pdfmanager.app_settings import settings
        if settings.compact_toolbar:
            self.ribbon.setFixedHeight(78)
            for button in self.ribbon.findChildren(QToolButton):button.setFixedHeight(46);button.setIconSize(QSize(23,23))
