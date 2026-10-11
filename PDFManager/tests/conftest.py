import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402 (musi być po ustawieniu zmiennej środowiskowej)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeRegKey:
    def __init__(self, store: dict, path: str) -> None:
        self._store, self._path = store, path

    def __enter__(self):
        self._store.setdefault(self._path, {})
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


class FakeWinReg:
    """Minimalna atrapa modułu `winreg` (hierarchiczny magazyn w pamięci),
    współdzielona przez testy modułów używających rejestru Windows."""

    HKEY_CURRENT_USER = object()
    REG_SZ = object()
    KEY_SET_VALUE = object()

    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}

    def CreateKey(self, hive, subkey):
        return _FakeRegKey(self.keys, subkey)

    def SetValueEx(self, key, name, reserved, value_type, value) -> None:
        self.keys[key._path][name if name is not None else ""] = value

    def OpenKey(self, hive, subkey, reserved=0, access=0):
        if subkey not in self.keys:
            raise OSError(f"Klucz nie istnieje: {subkey}")
        return _FakeRegKey(self.keys, subkey)

    def QueryValueEx(self, key, name):
        values = self.keys.get(key._path, {})
        if name not in values:
            raise OSError(f"Brak wartości: {name}")
        return values[name], None

    def DeleteKey(self, hive, subkey) -> None:
        if subkey not in self.keys:
            raise OSError(f"Klucz nie istnieje: {subkey}")
        del self.keys[subkey]

    def DeleteValue(self, key, name) -> None:
        values = self.keys.get(key._path, {})
        if name not in values:
            raise OSError(f"Brak wartości: {name}")
        del values[name]


@pytest.fixture
def test_signing_key(tmp_path, monkeypatch):
    """Ephemeral Ed25519 pair: exercise real crypto without a vendor secret."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    from pdfmanager.licensing import license_key
    key = Ed25519PrivateKey.generate()
    public_path = tmp_path / 'test_public.pem'
    public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    private_path = tmp_path / 'test_private.pem'
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    monkeypatch.setattr(license_key, 'PUBLIC_KEY_PATH', public_path)
    return license_key.load_private_key_for_signing(private_path)
