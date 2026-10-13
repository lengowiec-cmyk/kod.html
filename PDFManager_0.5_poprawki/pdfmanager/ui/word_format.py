"""Independent office-style controls; all commands operate on the text draft."""
from pdfmanager.i18n.translator import translator
from PySide6.QtCore import Qt,QSignalBlocker,QSize
from PySide6.QtGui import QFont,QTextCharFormat,QTextBlockFormat,QTextListFormat,QTextCursor,QColor,QDoubleValidator
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QToolButton,QFontComboBox,QComboBox,QColorDialog,QScrollArea,QTextEdit,QFrame,QButtonGroup

from .office_icons import office_icon

class SafeTextEdit(QTextEdit):
    def insertFromMimeData(self,source):
        if source.hasText():self.insertPlainText(source.text())

class WordFormatBar(QWidget):
    SIZES=[8,9,10,11,12,14,16,18,20,22,24,26,28,36,48,72]
    def __init__(self,panel,parent=None):
        super().__init__(parent);self.panel=panel;self.editor=panel.editor;self.painter_format=None;self.buttons={}
        self.setObjectName('WordFormatBar')
        self.setStyleSheet("""
            QWidget#WordFormatBar {background:palette(base);border-bottom:1px solid #cbd5e1;}
            QWidget#FormatRibbonBody {background:palette(base);}
            QToolButton {border:1px solid transparent;border-radius:4px;padding:3px;color:palette(text);background:transparent;}
            QToolButton:hover {background:#eaf3fd;border-color:#b8d3f0;color:#21394e;}
            QToolButton:checked {background:#dcecff;border-color:#8ebce8;color:#21394e;}
            QToolButton:disabled {color:#9ca3af;}
            QComboBox {background:palette(base);border:1px solid #cbd5e1;border-radius:3px;padding:2px 4px;min-height:21px;}
            QToolButton#StyleTile {background:palette(base);border:1px solid #d7e0ea;border-radius:3px;padding:5px;}
            QToolButton#StyleTile:checked {background:#f0f6ff;border:2px solid #4289c9;}
            QToolButton#StyleTile:hover {background:#edf5ff;border-color:#8ebce8;}
            QToolButton#ApplyPdf {background:#e6f5ec;border-color:#bee1cb;color:#216443;}
            QToolButton#ApplyPdf:hover {background:#d4eddf;border-color:#78b494;}
            QLabel#FormatCaption {color:#64748b;font-size:10px;}
            QScrollArea {border:0;background:transparent;}
            QScrollBar:horizontal {height:7px;background:#f1f5f9;}
            QScrollBar::handle:horizontal {background:#c1d3e3;border-radius:3px;min-width:24px;}
            QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {width:0;}
        """)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);self.scroll.setFrameShape(QScrollArea.NoFrame);self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body=QWidget();body.setObjectName('FormatRibbonBody');row=QHBoxLayout(body);row.setContentsMargins(8,6,8,3);row.setSpacing(9)
        def group(title,width):
            if row.count():
                divider=QFrame();divider.setFrameShape(QFrame.VLine);divider.setStyleSheet('color:#d4dde6');row.addWidget(divider)
            box=QWidget();box.setFixedWidth(width);box.setFixedHeight(96);layout=QVBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3);row.addWidget(box)
            tools=QWidget();tools.setMinimumHeight(66);stack=QVBoxLayout(tools);stack.setContentsMargins(0,0,0,0);stack.setSpacing(3)
            first=QHBoxLayout();second=QHBoxLayout();first.setSpacing(2);second.setSpacing(2);stack.addLayout(first);stack.addLayout(second);layout.addWidget(tools)
            label=QLabel(title);label.setObjectName('FormatCaption');label.setAlignment(Qt.AlignCenter);layout.addWidget(label);return first,second
        first,second=group('Schowek',162)
        paste=self.button(first,'paste','Wklej',self.editor.paste);paste.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);paste.setIconSize(QSize(27,27));paste.setMinimumHeight(32)
        self.button(first,'cut','Wytnij',self.editor.cut);self.button(first,'copy','Kopiuj',self.editor.copy);first.addStretch()
        self.button(second,'painter','Malarz formatów',self.paint_format).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        first,second=group('Czcionka',340)
        self.family=QFontComboBox();self.family.setMinimumWidth(150);first.addWidget(self.family,1)
        self.size=QComboBox();self.size.setEditable(True);self.size.addItems([str(x) for x in self.SIZES]);self.size.setCurrentText('11');self.size.setFixedWidth(52);self.size.lineEdit().setValidator(QDoubleValidator(1,300,1,self));first.addWidget(self.size)
        self.family.currentFontChanged.connect(lambda font:self.change('family',font.family()))
        self.family.activated.connect(lambda _:self.change('family',self.family.currentFont().family()))
        self.size.activated.connect(lambda _:self.set_size());self.size.lineEdit().editingFinished.connect(self.set_size)
        self.button(first,'grow','Powiększ czcionkę',lambda:self.step_size(1));self.button(first,'shrink','Zmniejsz czcionkę',lambda:self.step_size(-1))
        self.cases=QComboBox();self.cases.addItems(['Aa','WIELKIE LITERY','małe litery','Jak Tytuł']);self.cases.setFixedWidth(45);self.cases.view().setMinimumWidth(145);first.addWidget(self.cases);self.cases.activated.connect(self.case)
        self.button(first,'clear','Wyczyść format',self.clear_format)
        for key,label in [('bold','Pogrubienie'),('italic','Kursywa'),('underline','Podkreśl'),('strike','Przekreśl'),('sub','Indeks dolny'),('super','Indeks górny')]:self.button(second,key,label,lambda checked=False,k=key:self.change(k,checked),True)
        self.button(second,'color','Kolor tekstu',lambda:self.choose_color(False));self.button(second,'highlight','Zakreślenie',lambda:self.choose_color(True));second.addStretch()
        first,second=group('Akapit',238)
        self.button(first,'bullets','• Lista',lambda:self.list_format(False));self.button(first,'numbers','1. Lista',lambda:self.list_format(True))
        self.button(first,'less_indent','← Wcięcie',lambda:self.indent(-1));self.button(first,'more_indent','Wcięcie →',lambda:self.indent(1));self.button(first,'sort','Sortuj akapity',self.sort_text);self.button(first,'show_marks','Pokaż znaki formatowania',self.show_marks,True);first.addStretch()
        for key,label,value in [('left','Wyrównaj do lewej',Qt.AlignLeft),('center','Wyśrodkuj',Qt.AlignHCenter),('right','Wyrównaj do prawej',Qt.AlignRight),('justify','Wyjustuj',Qt.AlignJustify)]:self.button(second,key,label,lambda checked=False,v=value:self.editor.setAlignment(v))
        self.spacing=QComboBox();self.spacing.addItems(['1,0','1,15','1,5','2,0']);self.spacing.setFixedWidth(48);self.spacing.setToolTip('Interlinia');second.addWidget(self.spacing);self.spacing.activated.connect(self.line_spacing)
        self.button(second,'paragraph_color','Tło',self.paragraph_color);self.button(second,'border','Ramka',self.border,True)
        first,second=group('Style',350)
        self.styles=QComboBox();self.styles.addItems(['Normalny','Bez odstępów','Nagłówek 1','Nagłówek 2','Tytuł','Podtytuł']);self.styles.setFixedWidth(112);self.styles.activated.connect(self.style)
        self.style_group=QButtonGroup(self);self.style_group.setExclusive(True);self.style_tiles=[]
        gallery=QScrollArea();gallery.setWidgetResizable(True);gallery.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff);gallery.setFixedHeight(43);gallery.setFixedWidth(323);gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tiles=QWidget();tiles_row=QHBoxLayout(tiles);tiles_row.setContentsMargins(0,0,0,0);tiles_row.setSpacing(4)
        for i,label in enumerate(['Normalny','Bez odstępów','Nagłówek 1','Nagłówek 2','Tytuł','Podtytuł']):
            tile=QToolButton();tile.setObjectName('StyleTile');tile.setText(label);tile.setToolTip(label);tile.setCheckable(True);tile.setFixedSize(105,35);tile.setFocusPolicy(Qt.NoFocus)
            font=QFont('Segoe UI');font.setPointSize([10,9,13,11,16,11][i]);font.setItalic(i==5);tile.setFont(font)
            tile.setStyleSheet(f'font-size:{[12,11,17,15,21,14][i]}px;color:'+('#276cb6;' if i in (2,3) else 'palette(text);')+('font-style:italic;' if i==5 else ''))
            self.style_group.addButton(tile,i);tiles_row.addWidget(tile);self.style_tiles.append(tile);tile.clicked.connect(lambda checked=False,index=i:self.choose_style(index))
        self.style_tiles[0].setChecked(True);gallery.setWidget(tiles);first.addWidget(gallery);more=QToolButton();more.setText('›');more.setToolTip('Przewiń style');more.setFixedSize(23,35);first.addWidget(more)
        more.clicked.connect(lambda:gallery.horizontalScrollBar().setValue(0 if gallery.horizontalScrollBar().value()>=gallery.horizontalScrollBar().maximum() else gallery.horizontalScrollBar().value()+109))
        second.addWidget(self.styles);second.addStretch();tip=QLabel('Podgląd stylów');tip.setObjectName('FormatCaption');second.addWidget(tip)
        first,second=group('Dokument PDF',169)
        self.button(first,'edit_pdf','Edytuj tekst PDF',panel.edit_pdf).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button(first,'new_text','Nowy tekst',panel.new_text)
        apply=self.button(second,'apply_pdf','Zastosuj do PDF',panel.apply);apply.setObjectName('ApplyPdf');apply.setToolButtonStyle(Qt.ToolButtonTextBesideIcon);second.addStretch()
        row.addStretch();self.scroll.setWidget(body);outer.addWidget(self.scroll);self.setMinimumHeight(112);self.setMaximumHeight(122)
        self.editor.currentCharFormatChanged.connect(self.sync);self.sync(self.editor.currentCharFormat())
    def button(self,row,key,label,callback,check=False):
        b=QToolButton();b.setText(label);b.setToolTip(label);b.setAccessibleName(label);b.setIcon(office_icon(key));b.setIconSize(QSize(20,20));b.setToolButtonStyle(Qt.ToolButtonIconOnly);b.setAutoRaise(True);b.setFixedHeight(28);b.setFocusPolicy(Qt.NoFocus);b.setCheckable(check);row.addWidget(b);self.buttons[key]=b;b.clicked.connect(lambda checked=False:(self.panel.show(),callback(checked) if check else callback()));return b
    def choose_style(self,index):
        self.styles.setCurrentIndex(index);self.panel.show();self.style(index)
    def change(self,key,value):
        self.panel.show()
        f=QTextCharFormat()
        if key=='family':f.setFontFamilies([value])
        elif key=='size':f.setFontPointSize(value)
        elif key=='bold':f.setFontWeight(QFont.Bold if value else QFont.Normal)
        elif key=='italic':f.setFontItalic(value)
        elif key=='underline':f.setFontUnderline(value)
        elif key=='strike':f.setFontStrikeOut(value)
        elif key in ('super','sub'):f.setVerticalAlignment(QTextCharFormat.AlignSuperScript if value and key=='super' else QTextCharFormat.AlignSubScript if value else QTextCharFormat.AlignNormal)
        self.editor.mergeCurrentCharFormat(f)
    def set_size(self):
        try:value=float(self.size.currentText().replace(',','.'))
        except ValueError:return
        if 1<=value<=300:self.change('size',value)
    def step_size(self,direction):
        value=self.editor.currentCharFormat().fontPointSize() or 11
        values=[n for n in self.SIZES if n>value] if direction>0 else [n for n in self.SIZES if n<value]
        self.change('size',(min(values) if direction>0 else max(values)) if values else max(1,min(300,value+direction)))
    def sync(self,f):
        blocks=[QSignalBlocker(self.family),QSignalBlocker(self.size)]
        self.buttons['color'].setIcon(office_icon('color',f.foreground().color().name() if f.foreground().style()!=Qt.NoBrush else '#334155'))
        font=f.font();self.family.setCurrentFont(font);self.size.setCurrentText(f'{f.fontPointSize() or 11:g}')
        for key,value in [('bold',f.fontWeight()>=QFont.Bold),('italic',f.fontItalic()),('underline',f.fontUnderline()),('strike',f.fontStrikeOut()),('super',f.verticalAlignment()==QTextCharFormat.AlignSuperScript),('sub',f.verticalAlignment()==QTextCharFormat.AlignSubScript)]:
            with QSignalBlocker(self.buttons[key]):self.buttons[key].setChecked(value)
    def choose_color(self,background):
        c=QColorDialog.getColor(QColor('#fff36b' if background else '#174a75'),self)
        if c.isValid():
            f=QTextCharFormat();f.setBackground(c) if background else f.setForeground(c);self.editor.mergeCurrentCharFormat(f)
            self.buttons['highlight' if background else 'color'].setIcon(office_icon('highlight' if background else 'color',c.name()))
    def case(self,index):
        if not index:return
        cursor=self.editor.textCursor()
        if not cursor.hasSelection():cursor.select(QTextCursor.Document)
        text=cursor.selectedText().replace('\u2029','\n');cursor.insertText([text,text.upper(),text.lower(),text.title()][index]);self.cases.setCurrentIndex(0)
    def clear_format(self):
        f=QTextCharFormat();f.setFont(QFont(self.family.currentText(),11));self.editor.textCursor().setCharFormat(f);self.editor.setCurrentCharFormat(f)
    def paint_format(self):
        if self.painter_format is None:self.painter_format=QTextCharFormat(self.editor.currentCharFormat());self.panel.message.setText(translator.text('Zaznacz tekst docelowy i kliknij Malarz formatów ponownie.'))
        else:self.editor.mergeCurrentCharFormat(self.painter_format);self.painter_format=None;self.panel.message.setText(translator.text('Format zastosowany w szkicu.'))
    def list_format(self,numbered):
        fmt=QTextListFormat();fmt.setStyle(QTextListFormat.ListDecimal if numbered else QTextListFormat.ListDisc);fmt.setIndent(1);self.editor.textCursor().createList(fmt)
    def indent(self,amount):
        cursor=self.editor.textCursor();f=cursor.blockFormat();f.setIndent(max(0,min(20,f.indent()+amount)));cursor.mergeBlockFormat(f)
    def line_spacing(self,index):
        f=QTextBlockFormat();f.setLineHeight([100,115,150,200][index],QTextBlockFormat.ProportionalHeight.value);self.editor.textCursor().mergeBlockFormat(f)
    def paragraph_color(self):
        c=QColorDialog.getColor(QColor('#edf4fc'),self)
        if c.isValid():f=QTextBlockFormat();f.setBackground(c);self.editor.textCursor().mergeBlockFormat(f)
    def border(self,checked):
        f=QTextBlockFormat();f.setProperty(QTextCharFormat.UserProperty+7,checked);self.editor.textCursor().mergeBlockFormat(f)
    def sort_text(self):
        cursor=self.editor.textCursor()
        if not cursor.hasSelection():cursor.select(QTextCursor.Document)
        cursor.insertText('\n'.join(sorted(cursor.selectedText().replace('\u2029','\n').splitlines(),key=str.casefold)))
    def show_marks(self,checked):
        from PySide6.QtGui import QTextOption
        option=self.editor.document().defaultTextOption();option.setFlags(option.flags()|(QTextOption.ShowTabsAndSpaces|QTextOption.ShowLineAndParagraphSeparators) if checked else option.flags()&~(QTextOption.ShowTabsAndSpaces|QTextOption.ShowLineAndParagraphSeparators));self.editor.document().setDefaultTextOption(option)
    def style(self,index):
        self.style_tiles[index].setChecked(True)
        with QSignalBlocker(self.styles):self.styles.setCurrentIndex(index)
        sizes=[11,11,20,16,28,14];self.change('size',sizes[index]);self.change('bold',index in (2,3,4));self.change('italic',index==5)
        f=QTextBlockFormat();f.setTopMargin(0);f.setBottomMargin(0 if index==1 else 6);self.editor.textCursor().mergeBlockFormat(f)

def payload(editor):
    paragraphs=[];block=editor.document().begin()
    while block.isValid():
        fmt=block.blockFormat();align=fmt.alignment()
        paragraph={'after':fmt.bottomMargin(),'align':'justify' if align&Qt.AlignJustify else 'right' if align&Qt.AlignRight else 'center' if align&Qt.AlignHCenter else 'left','indent':min(20,fmt.indent()),'spacing':(fmt.lineHeight()/100 if fmt.lineHeightType()==QTextBlockFormat.ProportionalHeight.value else 1.0),'border':bool(fmt.property(QTextCharFormat.UserProperty+7)),'runs':[]}
        if fmt.background().style()!=Qt.NoBrush:paragraph['background']=fmt.background().color().getRgb()[:3]
        listing=block.textList()
        if listing:paragraph['prefix']=(str(listing.itemNumber(block)+1)+'. ' if listing.format().style()==QTextListFormat.ListDecimal else '• ')
        it=block.begin()
        while not it.atEnd():
            fragment=it.fragment()
            if fragment.isValid():
                f=fragment.charFormat();run={'text':fragment.text(),'family':(f.fontFamilies() or [editor.font().family()])[0],'size':f.fontPointSize() or editor.font().pointSizeF() or 11,'bold':f.fontWeight()>=QFont.Bold,'italic':f.fontItalic(),'underline':f.fontUnderline(),'strike':f.fontStrikeOut(),'color':f.foreground().color().getRgb()[:3] if f.foreground().style()!=Qt.NoBrush else (0,0,0),'script':'super' if f.verticalAlignment()==QTextCharFormat.AlignSuperScript else 'sub' if f.verticalAlignment()==QTextCharFormat.AlignSubScript else ''}
                if f.background().style()!=Qt.NoBrush:run['background']=f.background().color().getRgb()[:3]
                paragraph['runs'].append(run)
            it+=1
        if not paragraph['runs']:paragraph['runs']=[{'text':'\n','family':'DejaVu Sans','size':11,'color':(0,0,0)}]
        paragraphs.append(paragraph);block=block.next()
    return paragraphs

def restore_payload(editor,paragraphs):
    """Restore our structured draft without passing HTML or external resources to Qt."""
    if not isinstance(paragraphs,list) or len(paragraphs)>1000:raise ValueError('Nieprawidłowy szkic.')
    editor.clear();cursor=editor.textCursor();active_list=None;active_kind=None
    for i,p in enumerate(paragraphs):
        if i:cursor.insertBlock()
        block=QTextBlockFormat();block.setAlignment({'left':Qt.AlignLeft,'center':Qt.AlignHCenter,'right':Qt.AlignRight,'justify':Qt.AlignJustify}.get(p.get('align'),Qt.AlignLeft));block.setIndent(min(20,max(0,int(p.get('indent',0)))));block.setBottomMargin(float(p.get('after',0)));block.setLineHeight(float(p.get('spacing',1))*100,QTextBlockFormat.ProportionalHeight.value);block.setProperty(QTextCharFormat.UserProperty+7,bool(p.get('border')))
        if 'background' in p:block.setBackground(QColor(*p['background']))
        cursor.setBlockFormat(block)
        if p.get('prefix'):
            kind=QTextListFormat.ListDisc if p['prefix']=='• ' else QTextListFormat.ListDecimal
            if active_list is not None and active_kind==kind:active_list.add(cursor.block())
            else:
                listing=QTextListFormat();listing.setStyle(kind);listing.setIndent(1)
                if kind==QTextListFormat.ListDecimal:listing.setStart(int(p['prefix'].split('.')[0]))
                active_list=cursor.createList(listing);active_kind=kind
        else:active_list=None;active_kind=None
        for run in p.get('runs',[]):
            f=QTextCharFormat();f.setFontFamilies([run.get('family','DejaVu Sans')]);f.setFontPointSize(float(run.get('size',11)));f.setFontWeight(QFont.Bold if run.get('bold') else QFont.Normal);f.setFontItalic(bool(run.get('italic')));f.setFontUnderline(bool(run.get('underline')));f.setFontStrikeOut(bool(run.get('strike')));f.setForeground(QColor(*run.get('color',[0,0,0])))
            f.setVerticalAlignment(QTextCharFormat.AlignSuperScript if run.get('script')=='super' else QTextCharFormat.AlignSubScript if run.get('script')=='sub' else QTextCharFormat.AlignNormal)
            if 'background' in run:f.setBackground(QColor(*run['background']))
            cursor.insertText(run['text'] if run['text']!='\n' else '',f)
    editor.setTextCursor(cursor)
