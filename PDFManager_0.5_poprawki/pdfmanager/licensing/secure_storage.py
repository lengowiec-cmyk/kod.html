"""Przechowywanie stanu licencji odporne na przypadkowe manipulacje.

Każdy rekord (JSON) jest podpisywany HMAC-SHA256 i zapisywany RÓWNOCZEŚNIE
w dwóch niezależnych miejscach: w rejestrze Windows (`HKEY_CURRENT_USER`,
bez uprawnień administratora) i w pliku oznaczonym jako ukryty w
`%LOCALAPPDATA%`. Dzięki temu usunięcie/wyczyszczenie JEDNEGO miejsca
(typowe np. przy prostym „odinstaluj i zainstaluj ponownie" próbującym
zresetować okres próbny) nie usuwa stanu, o ile drugie miejsce przetrwa.

Uczciwe ograniczenia (żeby nie przeceniać tego mechanizmu):
- Sekret HMAC jest wbudowany w aplikację. Chroni to przed PRZYPADKOWYM
  albo niecelowym grzebaniem w rejestrze/pliku, NIE przed kimś, kto
  zdekompiluje aplikację (paczki PyInstaller są do tego trywialne) i
  odtworzy sekret — to on i tak nie pozwala wygenerować nowych kluczy
  AKTYWACYJNYCH (te są zabezpieczone osobno, kluczem Ed25519 — patrz
  `license_key.py`), ale pozwoliłby podrobić rekord stanu PRÓBNEGO.
- Żadna czysto lokalna (bez serwera czasu) metoda nie obroni się przed
  przestawieniem zegara systemowego do tyłu — to fundamentalne
  ograniczenie każdego offline licznika próbnego, nie błąd tej
  implementacji.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import sys
from pathlib import Path
from typing import Any

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import winreg as _real_winreg
else:
    _real_winreg = None

_registry: Any = _real_winreg

# Sekret lokalnej, wbudowanej w aplikację pieczęci HMAC — patrz ograniczenia
# w docstringu modułu. Celowo odrębny od klucza Ed25519 używanego do
# kluczy aktywacyjnych (inne zagrożenie, inna warstwa).
_HMAC_SECRET = bytes.fromhex("8f3c1a9e6b2d4f7a0c5e8b1d3f6a9c2e5b8d1f4a7c0e3b6d9f2a5c8e1b4d7f0a")

FILE_ATTRIBUTE_HIDDEN = 0x02


def _hmac_sign(payload: bytes) -> bytes:
    return hmac.new(_HMAC_SECRET, payload, hashlib.sha256).digest()


def _wrap(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    signature = _hmac_sign(payload)
    combined = base64.b64encode(payload).decode("ascii") + "." + base64.b64encode(signature).decode("ascii")
    return combined


def _unwrap(blob: str) -> dict | None:
    try:
        payload_b64, signature_b64 = blob.split(".", 1)
        payload = base64.b64decode(payload_b64)
        signature = base64.b64decode(signature_b64)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _hmac_sign(payload)):
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def _write_registry(key_path: str, value_name: str, blob: str) -> None:
    if _registry is None:
        return
    try:
        with _registry.CreateKey(_registry.HKEY_CURRENT_USER, key_path) as key:
            _registry.SetValueEx(key, value_name, 0, _registry.REG_SZ, blob)
    except OSError:
        pass  # najlepszy wysiłek — drugie miejsce (plik) wystarczy


def _read_registry(key_path: str, value_name: str) -> str | None:
    if _registry is None:
        return None
    try:
        with _registry.OpenKey(_registry.HKEY_CURRENT_USER, key_path) as key:
            value, _ = _registry.QueryValueEx(key, value_name)
            return value
    except OSError:
        return None


def _write_file(file_path: Path, blob: str) -> None:
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
        atomic_write_bytes(file_path,blob.encode("utf-8"))
        if IS_WINDOWS:
            ctypes.windll.kernel32.SetFileAttributesW(str(file_path), FILE_ATTRIBUTE_HIDDEN)  # type: ignore[attr-defined]
    except OSError:
        pass  # najlepszy wysiłek — drugie miejsce (rejestr) wystarczy


def _read_file(file_path: Path) -> str | None:
    try:
        return file_path.read_text(encoding="utf-8")
    except OSError:
        return None


def write_dual(key_path: str, value_name: str, file_path: Path, data: dict) -> None:
    """Zapisuje podpisany rekord równocześnie do rejestru i do pliku."""
    blob = _wrap(data)
    _write_registry(key_path, value_name, blob)
    _write_file(file_path, blob)


def read_dual(key_path: str, value_name: str, file_path: Path) -> list[dict]:
    """Zwraca listę poprawnie podpisanych rekordów znalezionych w obu
    miejscach (0, 1 albo 2 elementy) — wołający decyduje, jak je scalić
    (np. najwcześniejsza data dla okresu próbnego)."""
    records = []
    for blob in (_read_registry(key_path, value_name), _read_file(file_path)):
        if blob is None:
            continue
        record = _unwrap(blob)
        if record is not None:
            records.append(record)
    return records
