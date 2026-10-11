from pdfmanager.i18n.translator import translator
from pdfmanager.ui.header_bar import COPYRIGHT_TEXT, HeaderBar


def test_header_bar_shows_copyright_text(qapp):
    header = HeaderBar()
    assert header._copyright_label.text() == COPYRIGHT_TEXT


def test_flag_click_emits_language_selected(qapp):
    header = HeaderBar()
    captured = []
    header.language_selected.connect(captured.append)

    header._flag_buttons["uk"].click()

    assert captured == ["uk"]


def test_checked_flag_follows_translator_language(qapp):
    header = HeaderBar()
    translator.set_language("pl")
    assert header._flag_buttons["pl"].isChecked() is True
    assert header._flag_buttons["en"].isChecked() is False

    translator.set_language("en")
    assert header._flag_buttons["en"].isChecked() is True
    assert header._flag_buttons["pl"].isChecked() is False
