"""Ikony flag (Polska/Ukraina/USA) dla przełącznika języka w pasku nagłówka.

Rysowane programowo przez QPainter — bez zewnętrznych plików graficznych,
więc bez zależności od sieci i bez wątpliwości co do praw do konkretnej
grafiki flagi. To uproszczone, małe ikony (do przycisku), nie precyzyjne
odwzorowania heraldyczne.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

_WIDTH, _HEIGHT = 24, 16
_BORDER_COLOR = QColor("#B0B0B0")


def _new_pixmap() -> QPixmap:
    pixmap = QPixmap(_WIDTH*4, _HEIGHT*4)
    pixmap.setDevicePixelRatio(4)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _draw_border(painter: QPainter) -> None:
    painter.setPen(_BORDER_COLOR)
    painter.drawRect(0, 0, _WIDTH - 1, _HEIGHT - 1)


def _poland_pixmap() -> QPixmap:
    pixmap = _new_pixmap()
    painter = QPainter(pixmap)
    half = _HEIGHT // 2
    painter.fillRect(QRect(0, 0, _WIDTH, half), QColor("white"))
    painter.fillRect(QRect(0, half, _WIDTH, _HEIGHT - half), QColor("#DC143C"))
    _draw_border(painter)
    painter.end()
    return pixmap


def _ukraine_pixmap() -> QPixmap:
    pixmap = _new_pixmap()
    painter = QPainter(pixmap)
    half = _HEIGHT // 2
    painter.fillRect(QRect(0, 0, _WIDTH, half), QColor("#0057B7"))
    painter.fillRect(QRect(0, half, _WIDTH, _HEIGHT - half), QColor("#FFD700"))
    _draw_border(painter)
    painter.end()
    return pixmap


def _usa_pixmap() -> QPixmap:
    pixmap = _new_pixmap()
    painter = QPainter(pixmap)
    stripe_count = 7
    for i in range(stripe_count):
        color = QColor("#B22234") if i % 2 == 0 else QColor("white")
        y = round(i * _HEIGHT / stripe_count)
        y_end = round((i + 1) * _HEIGHT / stripe_count)
        painter.fillRect(QRect(0, y, _WIDTH, y_end - y), color)
    canton_width = round(_WIDTH * 0.42)
    canton_height = round(_HEIGHT * 0.55)
    painter.fillRect(QRect(0, 0, canton_width, canton_height), QColor("#3C3B6E"))
    _draw_border(painter)
    painter.end()
    return pixmap


_BUILDERS = {"pl": _poland_pixmap, "uk": _ukraine_pixmap, "en": _usa_pixmap}


def flag_icon(language_code: str) -> QIcon:
    builder = _BUILDERS.get(language_code)
    if builder is None:
        raise ValueError(f"Brak ikony flagi dla języka: {language_code}")
    return QIcon(builder())
