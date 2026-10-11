import pytest

from pdfmanager.ui.icon_set import badge_icon, folder_icon, outline_icon


def test_badge_icon_is_valid(qapp):
    icon = badge_icon("+")
    assert not icon.isNull()


def test_outline_icon_shapes_are_valid(qapp):
    for shape in ("rect", "circle", "line"):
        icon = outline_icon(shape)
        assert not icon.isNull()


def test_folder_icon_is_valid(qapp):
    icon = folder_icon()
    assert not icon.isNull()
