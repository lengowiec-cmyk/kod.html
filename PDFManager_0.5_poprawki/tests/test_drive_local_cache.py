from pdfmanager.drive.local_cache import cache_dir, cache_path_for


def test_cache_dir_is_created_and_returned():
    path = cache_dir()
    assert path.is_dir()
    assert path.name == "drive_files"


def test_cache_path_for_sanitizes_unsafe_characters():
    path = cache_path_for("abc123", 'raport: wersja "ostateczna"?.pdf')
    assert path.parent == cache_dir()
    assert path.name.startswith("abc123_")
    for forbidden in '<>:"/\\|?*':
        assert forbidden not in path.name


def test_cache_path_for_appends_pdf_extension_if_missing():
    path = cache_path_for("id1", "dokument_bez_rozszerzenia")
    assert path.name.endswith(".pdf")


def test_cache_path_for_different_ids_are_distinct_even_with_same_name():
    a = cache_path_for("id1", "umowa.pdf")
    b = cache_path_for("id2", "umowa.pdf")
    assert a != b


def test_cache_path_for_polish_and_ukrainian_characters_in_name():
    path = cache_path_for("id1", "Zażółć gęślą – Привіт.pdf")
    assert path.name.startswith("id1_")
    assert path.suffix == ".pdf"
