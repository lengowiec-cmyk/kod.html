import pytest

from pdfmanager.ui.theme import THEME_DARK, THEME_LIGHT, apply_theme


@pytest.mark.parametrize("theme", [THEME_LIGHT, THEME_DARK])
def test_apply_theme_does_not_raise(qapp, theme):
    apply_theme(qapp, theme)
    assert qapp.styleSheet() != ""


def test_apply_theme_rejects_unknown_theme(qapp):
    with pytest.raises(ValueError):
        apply_theme(qapp, "neon")


def test_light_and_dark_produce_different_stylesheets(qapp):
    apply_theme(qapp, THEME_LIGHT)
    light_sheet = qapp.styleSheet()
    apply_theme(qapp, THEME_DARK)
    dark_sheet = qapp.styleSheet()
    assert light_sheet != dark_sheet
