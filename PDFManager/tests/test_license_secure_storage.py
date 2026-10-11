from pathlib import Path
from unittest.mock import patch

import pytest

from pdfmanager.licensing import secure_storage as ss

KEY_PATH = r"Software\PDFManager\TestLicense"
VALUE_NAME = "state"


class _FakeKey:
    def __init__(self, store: dict, path: str) -> None:
        self._store, self._path = store, path

    def __enter__(self):
        self._store.setdefault(self._path, {})
        return self

    def __exit__(self, *exc):
        return False


class FakeWinReg:
    HKEY_CURRENT_USER = object()
    REG_SZ = object()

    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}

    def CreateKey(self, hive, subkey):
        return _FakeKey(self.keys, subkey)

    def SetValueEx(self, key, name, reserved, value_type, value):
        self.keys[key._path][name] = value

    def OpenKey(self, hive, subkey, reserved=0, access=0):
        if subkey not in self.keys:
            raise OSError("brak klucza")
        return _FakeKey(self.keys, subkey)

    def QueryValueEx(self, key, name):
        values = self.keys.get(key._path, {})
        if name not in values:
            raise OSError("brak wartości")
        return values[name], None


@pytest.fixture
def fake_registry():
    fake = FakeWinReg()
    with patch.object(ss, "_registry", fake):
        yield fake


def test_write_and_read_dual_roundtrip(fake_registry, tmp_path):
    file_path = tmp_path / "state.dat"
    ss.write_dual(KEY_PATH, VALUE_NAME, file_path, {"started_at": "2026-01-01T00:00:00"})

    records = ss.read_dual(KEY_PATH, VALUE_NAME, file_path)
    assert len(records) == 2
    assert all(r == {"started_at": "2026-01-01T00:00:00"} for r in records)


def test_surviving_file_record_recovered_after_registry_wiped(fake_registry, tmp_path):
    file_path = tmp_path / "state.dat"
    ss.write_dual(KEY_PATH, VALUE_NAME, file_path, {"started_at": "2026-01-01T00:00:00"})

    fake_registry.keys.clear()  # symuluje odinstalowanie/wyczyszczenie rejestru

    records = ss.read_dual(KEY_PATH, VALUE_NAME, file_path)
    assert records == [{"started_at": "2026-01-01T00:00:00"}]


def test_surviving_registry_record_recovered_after_file_deleted(fake_registry, tmp_path):
    file_path = tmp_path / "state.dat"
    ss.write_dual(KEY_PATH, VALUE_NAME, file_path, {"started_at": "2026-01-01T00:00:00"})

    file_path.unlink()

    records = ss.read_dual(KEY_PATH, VALUE_NAME, file_path)
    assert records == [{"started_at": "2026-01-01T00:00:00"}]


def test_read_dual_returns_empty_list_when_nothing_stored(fake_registry, tmp_path):
    assert ss.read_dual(KEY_PATH, VALUE_NAME, tmp_path / "missing.dat") == []


def test_tampered_file_record_is_rejected(fake_registry, tmp_path):
    file_path = tmp_path / "state.dat"
    ss.write_dual(KEY_PATH, VALUE_NAME, file_path, {"started_at": "2026-01-01T00:00:00"})

    fake_registry.keys.clear()  # izolujemy test od drugiej (wciąż prawidłowej) kopii w rejestrze
    original = file_path.read_text(encoding="utf-8")
    tampered = original[:-4] + "XXXX"  # psujemy część podpisu/danych
    file_path.write_text(tampered, encoding="utf-8")

    records = ss.read_dual(KEY_PATH, VALUE_NAME, file_path)
    assert records == []  # zepsuty plik jest odrzucony, a nie ślepo zaufany


def test_hidden_file_attribute_is_set_on_windows(fake_registry, tmp_path):
    file_path = tmp_path / "state.dat"
    with patch.object(ss, "IS_WINDOWS", True), patch("ctypes.windll", create=True) as mock_windll:
        ss.write_dual(KEY_PATH, VALUE_NAME, file_path, {"a": 1})
        mock_windll.kernel32.SetFileAttributesW.assert_called_once()
