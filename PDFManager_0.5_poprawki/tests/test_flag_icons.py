import pytest

from pdfmanager.ui.flag_icons import flag_icon


@pytest.mark.parametrize("lang", ["pl", "uk", "en"])
def test_flag_icon_is_created_and_non_null(qapp, lang):
    icon = flag_icon(lang)
    assert not icon.isNull()
    pixmap = icon.pixmap(24, 16)
    assert pixmap.width() > 0
    assert pixmap.height() > 0


def test_flag_icon_rejects_unknown_language(qapp):
    with pytest.raises(ValueError):
        flag_icon("fr")
