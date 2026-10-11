"""Testy rejestracji skojarzenia z plikami PDF — z atrapą rejestru Windows,
żeby dało się to zweryfikować również poza Windows."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pdfmanager.windows import file_association as fa


class _FakeKey:
    def __init__(self, store: dict, path: str) -> None:
        self._store = store
        self._path = path

    def __enter__(self) -> "_FakeKey":
        self._store.setdefault(self._path, {})
        return self

    def __exit__(self, *exc_info) -> None:
        return False


class FakeWinReg:
    """Minimalna atrapa modułu `winreg` — hierarchiczny magazyn w pamięci."""

    HKEY_CURRENT_USER = object()
    REG_SZ = object()
    KEY_SET_VALUE = object()

    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}

    def CreateKey(self, hive, subkey):
        assert hive is self.HKEY_CURRENT_USER
        return _FakeKey(self.keys, subkey)

    def SetValueEx(self, key: _FakeKey, name, reserved, value_type, value) -> None:
        self.keys[key._path][name if name is not None else ""] = value

    def OpenKey(self, hive, subkey, reserved=0, access=0):
        assert hive is self.HKEY_CURRENT_USER
        if subkey not in self.keys:
            raise OSError(f"Klucz nie istnieje: {subkey}")
        return _FakeKey(self.keys, subkey)

    def QueryValueEx(self, key: _FakeKey, name):
        values = self.keys.get(key._path, {})
        if name not in values:
            raise OSError(f"Brak wartości: {name}")
        return values[name], None

    def DeleteKey(self, hive, subkey) -> None:
        assert hive is self.HKEY_CURRENT_USER
        if subkey not in self.keys:
            raise OSError(f"Klucz nie istnieje: {subkey}")
        del self.keys[subkey]

    def DeleteValue(self, key: _FakeKey, name) -> None:
        values = self.keys.get(key._path, {})
        if name not in values:
            raise OSError(f"Brak wartości: {name}")
        del values[name]


@pytest.fixture
def fake_registry():
    fake = FakeWinReg()
    with patch.object(fa, "_registry", fake):
        yield fake


def test_register_application_writes_expected_keys(fake_registry):
    fa.register_application(Path("C:/Program Files/PDFManager/PDFManager.exe"))

    prog_id_key = fake_registry.keys[rf"Software\Classes\{fa.PROG_ID}"]
    assert prog_id_key[""] == "Dokument PDF (Menedżer PDF)"

    # Uwaga: na tym (nie-Windows) systemie testowym `Path` nie normalizuje
    # separatorów do `\`, więc sprawdzamy tylko strukturę cytowania, nie
    # dokładny znak separatora — na realnym Windows `Path` jest `WindowsPath`
    # i da naturalnie poprawny, natywny zapis ze `\`.
    command_key = fake_registry.keys[rf"Software\Classes\{fa.PROG_ID}\shell\open\command"]
    assert command_key[""].startswith('"')
    assert command_key[""].endswith('" "%1"')
    assert "PDFManager.exe" in command_key[""]

    file_assoc_key = fake_registry.keys[rf"{fa.CAPABILITIES_KEY}\FileAssociations"]
    assert file_assoc_key[".pdf"] == fa.PROG_ID

    registered_apps = fake_registry.keys[fa.REGISTERED_APPS_KEY]
    assert registered_apps[fa.APP_REGISTERED_NAME] == fa.CAPABILITIES_KEY


def test_is_registered_as_default_false_when_user_choice_missing(fake_registry):
    assert fa.is_registered_as_default() is False


def test_is_registered_as_default_true_when_user_choice_matches(fake_registry):
    with fake_registry.CreateKey(fake_registry.HKEY_CURRENT_USER, fa.USER_CHOICE_KEY) as key:
        fake_registry.SetValueEx(key, "ProgId", 0, fake_registry.REG_SZ, fa.PROG_ID)
    assert fa.is_registered_as_default() is True


def test_is_registered_as_default_false_when_user_choice_is_another_app(fake_registry):
    with fake_registry.CreateKey(fake_registry.HKEY_CURRENT_USER, fa.USER_CHOICE_KEY) as key:
        fake_registry.SetValueEx(key, "ProgId", 0, fake_registry.REG_SZ, "SomeOtherApp.pdf")
    assert fa.is_registered_as_default() is False


def test_unregister_application_removes_keys_without_error(fake_registry):
    fa.register_application(Path("C:/PDFManager.exe"))
    fa.unregister_application()

    assert rf"Software\Classes\{fa.PROG_ID}" not in fake_registry.keys
    assert fa.APP_REGISTERED_NAME not in fake_registry.keys.get(fa.REGISTERED_APPS_KEY, {})


def test_unregister_application_is_safe_when_nothing_registered(fake_registry):
    fa.unregister_application()  # nie powinno zgłosić wyjątku


def test_functions_raise_clear_error_outside_windows():
    with patch.object(fa, "_registry", None):
        with pytest.raises(fa.FileAssociationError, match="tylko w systemie Windows"):
            fa.register_application(Path("/tmp/app.exe"))
        with pytest.raises(fa.FileAssociationError):
            fa.is_registered_as_default()
        with pytest.raises(fa.FileAssociationError):
            fa.open_default_apps_settings()
