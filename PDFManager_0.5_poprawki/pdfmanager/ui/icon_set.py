"""Proste, rysowane programowo ikony dla przycisków toolbara.

Jak `flag_icons.py` — bez zewnętrznych plików graficznych. Chodzi o to,
żeby pasek narzędzi nie składał się z samego tekstu (co wygląda bardzo
surowo), a jednocześnie żeby nie dodawać zależności od sieci/zasobów
graficznych o niejasnych prawach.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

_SIZE = 22
_ACCENT = "#2F6FED"
_DANGER = "#D64545"


def _blank_pixmap() -> QPixmap:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def badge_icon(symbol: str, color: str = _ACCENT) -> QIcon:
    """Zaokrąglony kolorowy kwadrat z jednym znakiem/symbolem na środku."""
    pixmap = _blank_pixmap()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(1, 1, _SIZE - 2, _SIZE - 2), 5, 5)

    font = QFont()
    font.setBold(True)
    font.setPointSizeF(_SIZE * 0.48)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), symbol)
    painter.end()
    return QIcon(pixmap)


def outline_icon(shape: str, color: str = _ACCENT) -> QIcon:
    """Ikona z narysowanym konturem kształtu: 'rect', 'circle' albo 'line'."""
    pixmap = _blank_pixmap()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = painter.pen()
    pen.setColor(QColor(color))
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    margin = 4
    rect = QRectF(margin, margin, _SIZE - 2 * margin, _SIZE - 2 * margin)
    if shape == "rect":
        painter.drawRoundedRect(rect, 2, 2)
    elif shape == "circle":
        painter.drawEllipse(rect)
    elif shape == "line":
        painter.drawLine(rect.bottomLeft(), rect.topRight())
    painter.end()
    return QIcon(pixmap)


def folder_icon(color: str = _ACCENT) -> QIcon:
    pixmap = _blank_pixmap()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(2, 7, 6, 4), 1, 1)
    painter.drawRoundedRect(QRectF(2, 9, 18, 11), 2, 2)
    painter.end()
    return QIcon(pixmap)
