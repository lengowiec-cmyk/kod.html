"""Original transparent drawn signature image; distinct from cryptographic signing."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt, QStandardPaths
from PySide6.QtGui import QImage, QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget,QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel


class Canvas(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(600,200);self.strokes=[];self.active=None
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.active=[event.position().toPoint()];self.strokes.append(self.active)
    def mouseMoveEvent(self,event):
        if self.active is not None:self.active.append(event.position().toPoint());self.update()
    def mouseReleaseEvent(self,event):self.active=None;self.update()
    def draw(self,painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setPen(QPen(QColor('#203954'),2.5))
        for stroke in self.strokes:
            for a,b in zip(stroke,stroke[1:]):painter.drawLine(a,b)
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),Qt.GlobalColor.white);self.draw(painter);painter.end()
    def image(self):
        image=QImage(self.size(),QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image);self.draw(painter);painter.end();return image


class SignatureDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('Narysuj podpis / inicjały');layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Podpis graficzny — nie jest podpisem cyfrowym certyfikatem.'))
        self.canvas=Canvas(self);layout.addWidget(self.canvas);row=QHBoxLayout()
        clear=QPushButton('Wyczyść');clear.clicked.connect(self.clear);row.addWidget(clear)
        save=QPushButton('Użyj podpisu');save.clicked.connect(self.save);row.addWidget(save)
        cancel=QPushButton('Anuluj');cancel.clicked.connect(self.reject);row.addWidget(cancel);layout.addLayout(row)
        self.saved_path=None
    def clear(self):self.canvas.strokes.clear();self.canvas.update()
    def save(self):
        if not any(len(stroke)>1 for stroke in self.canvas.strokes):return
        folder=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))/'signatures';folder.mkdir(parents=True,exist_ok=True)
        self.saved_path=folder/(uuid4().hex+'.png');self.canvas.image().save(str(self.saved_path));self.accept()
