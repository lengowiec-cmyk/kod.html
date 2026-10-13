"""Original, resolution-independent artwork for the text formatting ribbon."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QIcon,QPen,QColor,QFont,QPainterPath,QPalette
from .vector_icons import VectorIconEngine
from PySide6.QtWidgets import QApplication

class OfficeIconEngine(VectorIconEngine):
    def __init__(self,name,color=None):
        super().__init__(name);self.color=color
    def clone(self):return OfficeIconEngine(self.name,self.color)
    def paint(self,p,rect,mode,state):
        p.save();p.translate(rect.x(),rect.y());p.scale(rect.width()/32,rect.height()/32)
        p.setRenderHint(p.RenderHint.Antialiasing)
        if mode==QIcon.Disabled:p.setOpacity(.35)
        ink=QApplication.palette().color(QPalette.Text);blue=QColor('#287cce');orange=QColor('#e7a13e')
        def pen(color=ink,width=1.6):p.setPen(QPen(color,width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(Qt.NoBrush)
        def line(x,y,a,b):p.drawLine(QPointF(x,y),QPointF(a,b))
        def box(x,y,w,h,fill=None):
            if fill:p.setBrush(QColor(fill))
            p.drawRoundedRect(QRectF(x,y,w,h),1.4,1.4);p.setBrush(Qt.NoBrush)
        def glyph(text,size=19,color=ink,bold=False,italic=False):
            f=QFont('Segoe UI');f.setPixelSize(size);f.setBold(bold);f.setItalic(italic);p.setFont(f);p.setPen(color);p.drawText(QRectF(1,0,30,30),Qt.AlignCenter,text)
        pen()
        key=self.name
        if key=='paste':
            pen(orange);box(7,5,19,24,'#fff2cf');pen(ink);box(11,3,11,5,'#f8fafc');pen(blue);box(16,13,12,15,'#ffffff');line(19,18,25,18);line(19,22,25,22)
        elif key=='copy':
            pen(blue);box(5,3,17,22,'#eff6ff');box(11,9,17,21,'#ffffff');line(15,16,24,16);line(15,21,24,21)
        elif key=='cut':
            pen(blue,2);p.drawEllipse(QRectF(3,21,8,8));p.drawEllipse(QRectF(20,21,8,8));line(9,23,25,3);line(22,23,8,3)
        elif key=='painter':
            pen(orange,2);box(4,4,24,9,'#ffe7bb');pen(blue,2);line(17,13,17,18);line(17,18,13,18);box(11,18,5,11,'#dceeff')
        elif key in ('bold','italic','underline','strike','sub','super','grow','shrink','show_marks'):
            glyph({'bold':'B','italic':'I','underline':'U','strike':'ab','sub':'x₂','super':'x²','grow':'A','shrink':'A','show_marks':'¶'}[key],22 if key in ('grow','shrink') else 20,blue if key in ('grow','shrink') else ink,key=='bold',key=='italic')
            pen()
            if key=='underline':line(9,28,23,28)
            if key=='strike':line(4,16,28,16)
            if key in ('grow','shrink'):
                pen(blue);line(27,4,27,13);line(24,7 if key=='grow' else 10,27,4 if key=='grow' else 13);line(30,7 if key=='grow' else 10,27,4 if key=='grow' else 13)
        elif key=='color':
            glyph('A',23);p.fillRect(QRectF(4,27,24,4),QColor(self.color or '#d23b43'))
        elif key in ('highlight','clear'):
            pen(QColor('#8961b5') if key=='clear' else orange);path=QPainterPath();path.moveTo(10,21);path.lineTo(23,5);path.lineTo(29,10);path.lineTo(16,25);path.closeSubpath();p.fillPath(path,QColor('#f0dcff') if key=='clear' else QColor('#ffe49b'));p.drawPath(path);pen(ink);line(8,22,4,27);p.fillRect(QRectF(3,28,25,3),QColor(self.color or '#ffe04d') if key=='highlight' else QColor('#b68fd3'))
        elif key in ('bullets','numbers','left','center','right','justify','less_indent','more_indent'):
            for i,y in enumerate((7,13,19,25)):
                pen(ink);start=12 if key in ('bullets','numbers') else 14 if key in ('less_indent','more_indent') else 4;end=28
                if i%2 and key=='left':end=22
                if i%2 and key=='right':start=10
                if i%2 and key=='center':start,end=8,24
                line(start,y,end,y)
                if key=='bullets':pen(blue,3);line(5,y,5.1,y)
                if key=='numbers':
                    f=QFont('Segoe UI');f.setPixelSize(8);p.setFont(f);p.setPen(blue);p.drawText(QRectF(1,y-5,9,10),Qt.AlignCenter,str(i+1))
            if key in ('less_indent','more_indent'):
                pen(blue,2);x=3 if key=='less_indent' else 11;other=11 if x==3 else 3;line(x,16,other,16);line(x,16,7,12);line(x,16,7,20)
        elif key=='sort':
            glyph('A',13,blue);pen(blue,2);line(26,4,26,26);line(22,22,26,26);line(30,22,26,26);p.drawText(QRectF(2,19,14,12),Qt.AlignCenter,'Z')
        elif key=='border':
            pen(ink);box(5,5,22,22);line(16,5,16,27);line(5,16,27,16);pen(blue,2.5);line(5,27,27,27)
        elif key=='paragraph_color':
            pen(blue);path=QPainterPath();path.moveTo(7,5);path.lineTo(24,19);path.lineTo(15,27);path.lineTo(2,15);path.closeSubpath();p.fillPath(path,QColor(self.color or '#bfe6fb'));p.drawPath(path);line(3,15,20,15);pen(orange,2);line(24,24,28,29)
        elif key in ('edit_pdf','new_text','apply_pdf'):
            pen(blue);box(5,3,20,26,'#eff6ff');line(9,9,20,9);line(9,14,17,14)
            if key=='apply_pdf':pen(QColor('#25875a'),3);line(13,22,18,27);line(18,27,29,15)
            elif key=='new_text':pen(blue,2);line(22,18,22,29);line(17,23,28,23)
            else:pen(orange,4);line(17,25,29,13)
        p.restore()

def office_icon(name,color=None):return QIcon(OfficeIconEngine(name,color))
