"""Original vector icons drawn for PDFManager; no FileCenter assets."""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath


def vector_icon(name: str, size: int = 32) -> QIcon:
    pix = QPixmap(size,size);pix.fill(Qt.GlobalColor.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.scale(size/32,size/32)
    p.setPen(QPen(QColor('#247bbd'),1.25));p.setBrush(Qt.BrushStyle.NoBrush)
    def line(x,y,a,b):p.drawLine(QPointF(x,y),QPointF(a,b))
    def rect(x,y,w,h):p.drawRect(QRectF(x,y,w,h))
    if name=='brand':
        p.setPen(Qt.NoPen);p.setBrush(QColor('#43b6c9'));p.drawRoundedRect(QRectF(1,1,30,30),7,7);p.setPen(QColor('white'));p.drawText(QRectF(0,0,32,32),Qt.AlignmentFlag.AlignCenter,'P')
    elif name in ('cabinet','receipt','barcode','automate'):
        p.setPen(QPen(QColor('#1e607c'),1.5));p.setBrush(QColor('#e3f2f7'));rect(5,3,22,26)
        if name=='cabinet':
            rect(8,7,16,7);rect(8,18,16,7);line(13,10,19,10);line(13,21,19,21)
        elif name=='barcode':
            for x in (8,10,13,17,20,24):line(x,7,x,25)
        elif name=='receipt':
            for y in (9,14,19):line(9,y,23,y)
        else:
            p.drawEllipse(QRectF(10,10,12,12));line(8,8,24,24)
    elif name in ('previous','next','first','last'):
        right=name in ('next','last');x=20 if right else 12
        line(x-6 if right else x+6,6,x,16);line(x,16,x-6 if right else x+6,26)
        if name in ('first','last'):line(25 if right else 7,6,25 if right else 7,26)
    elif name in ('zoom_in','zoom_out','fit'):
        if name=='fit':
            rect(3,4,26,24);line(8,16,24,16);line(8,16,12,12);line(8,16,12,20);line(24,16,20,12);line(24,16,20,20)
        else:
            p.drawEllipse(QRectF(3,3,20,20));line(20,20,29,29);line(7,13,19,13)
            if name=='zoom_in':line(13,7,13,19)
    elif name in ('open','folder','inbox'):
        p.setPen(QPen(QColor('#ee9835'),1.25))
        path=QPainterPath();path.moveTo(3,24);path.lineTo(3,7);path.lineTo(12,7);path.lineTo(15,11);path.lineTo(29,11);path.lineTo(25,25);path.closeSubpath();p.drawPath(path)
        line(3,24,9,15);line(9,15,28,15)
    elif name=='save':
        p.setPen(QPen(QColor('#a64dc6'),1.25));rect(4,3,24,26);rect(8,3,15,10);rect(8,18,16,11);line(19,5,19,11)
    elif name in ('search','preview','compare'):
        p.drawEllipse(QRectF(5,4,17,17));line(20,19,29,29)
        if name=='compare':rect(3,3,11,23);rect(18,3,11,23)
    elif name in ('home','back'):
        if name=='back':line(5,16,28,16);line(5,16,16,5);line(5,16,16,27)
        else:
            path=QPainterPath();path.moveTo(2,15);path.lineTo(16,3);path.lineTo(30,15);p.drawPath(path);rect(7,15,18,14);rect(13,21,6,8)
    elif name in ('scan','print'):
        rect(3,14,26,10);rect(8,3,16,11);rect(8,23,16,7);line(22,18,26,18)
    elif name in ('settings','tools','ocr'):
        p.drawEllipse(QRectF(10,10,12,12))
        for x,y,a,b in [(16,2,16,8),(16,24,16,30),(2,16,8,16),(24,16,30,16),(5,5,9,9),(23,23,27,27),(5,27,9,23),(23,9,27,5)]:line(x,y,a,b)
        if name=='ocr':p.drawText(QRectF(3,2,26,28),Qt.AlignmentFlag.AlignCenter,'T')
    elif name in ('help','guide'):
        if name=='help':p.drawEllipse(QRectF(2,2,28,28));p.drawText(QRectF(2,2,28,28),Qt.AlignmentFlag.AlignCenter,'?')
        else:rect(3,4,12,24);rect(17,4,12,24);line(16,4,16,29)
    elif name in ('image','signature','transform'):
        rect(3,5,26,22);p.drawEllipse(QRectF(19,9,4,4));line(4,24,12,15);line(12,15,20,24);line(20,24,26,18)
    elif name in ('split','pages','grid'):
        rect(3,3,26,26);line(3,13,29,13)
        if name in ('pages','grid'):line(16,3,16,29);line(3,22,29,22)
    elif name in ('text','note','highlight','rectangle','circle','line','select','ink','redact','delete'):
        color='#d75651' if name in ('rectangle','circle','line','redact','delete') else '#5d92b7'
        p.setPen(QPen(QColor(color),1.25))
        if name=='rectangle':rect(3,5,26,22)
        elif name=='circle':p.drawEllipse(QRectF(3,4,26,24))
        elif name=='line':line(3,28,29,4)
        elif name=='delete':line(5,5,27,27);line(5,27,27,5)
        elif name=='note':rect(3,4,26,21);line(7,9,25,9);line(7,14,25,14);line(7,19,19,19)
        elif name=='redact':p.fillRect(QRectF(3,8,26,16),QColor('#263746'))
        elif name=='ink':
            path=QPainterPath();path.moveTo(2,24);path.cubicTo(12,0,5,30,21,12);path.cubicTo(30,2,15,30,30,22);p.drawPath(path)
        elif name=='select':
            path=QPainterPath();path.moveTo(7,3);path.lineTo(24,17);path.lineTo(16,18);path.lineTo(13,27);path.closeSubpath();p.drawPath(path)
        else:p.drawText(QRectF(2,0,28,30),Qt.AlignmentFlag.AlignCenter,'T');line(6,28,26,28)
    else:
        rect(6,2,20,28);line(10,8,21,8);line(10,13,21,13);line(10,18,19,18)
        if name in ('insert','merge'):p.setPen(QPen(QColor('#58a966'),1.5));line(21,19,21,29);line(16,24,28,24)
        if name=='extract':line(17,23,28,23);line(24,19,28,23);line(24,27,28,23)
    p.end();return QIcon(pix)
