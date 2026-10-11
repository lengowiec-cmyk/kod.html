from pdfmanager.i18n.translator import SUPPORTED_LANGUAGES, Translator


def test_all_languages_load():
    t = Translator()
    for lang in SUPPORTED_LANGUAGES:
        assert lang in t._strings
        assert t._strings[lang], f"Brak tłumaczeń dla języka: {lang}"


def test_all_languages_have_same_keys():
    t = Translator()
    reference_keys = set(t._strings["pl"].keys())
    for lang in SUPPORTED_LANGUAGES:
        keys = set(t._strings[lang].keys())
        missing = reference_keys - keys
        extra = keys - reference_keys
        assert not missing, f"Język '{lang}' nie ma kluczy: {missing}"
        assert not extra, f"Język '{lang}' ma dodatkowe, nieużywane klucze: {extra}"


def test_tr_switches_language():
    t = Translator()
    t.set_language("en")
    assert t.tr("menu.file") == "File"
    t.set_language("pl")
    assert t.tr("menu.file") == "Plik"
    t.set_language("uk")
    assert t.tr("menu.file") == "Файл"


def test_tr_formats_placeholders():
    t = Translator()
    t.set_language("pl")
    result = t.tr("status.page_info", current=1, total=5, zoom=100)
    assert result == "Strona 1 z 5  •  100%"


def test_tr_unknown_key_falls_back_to_key_itself():
    t = Translator()
    assert t.tr("nieistniejacy.klucz") == "nieistniejacy.klucz"
