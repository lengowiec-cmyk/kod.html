"""Generowanie i weryfikacja kluczy aktywacyjnych (podpis Ed25519).

Dlaczego Ed25519 (asymetryczny), a nie HMAC (symetryczny): ta aplikacja
jest pakowana przez PyInstaller, a paczki PyInstaller są w praktyce
trywialne do rozpakowania z powrotem do w zasadzie oryginalnego kodu
Pythona (np. narzędziami typu pyinstxtractor + decompyle3) — każdy
sekret WPISANY w kod aplikacji trzeba traktować jako publicznie
odzyskiwalny. Przy HMAC sekret służący do WERYFIKACJI jest tym samym
sekretem, który służy do GENEROWANIA kluczy — ktoś, kto go wydobędzie
z aplikacji, mógłby sam generować dowolne, wiecznie działające klucze.
Przy Ed25519 aplikacja zawiera tylko klucz PUBLICZNY (`public_key.pem`)
— jego wydobycie nic nie daje, bo tylko klucz PRYWATNY (nigdy nie
wysyłany z aplikacją, patrz `tools/generate_license_key.py`) pozwala
podpisać nowy, prawidłowy klucz. To jedyny sposób, by weryfikacja
działała w pełni offline (bez serwera) i jednocześnie nie była trywialnie
obchodzalna przez samo zdekompilowanie aplikacji.

Cena tego wyboru: podpis Ed25519 (64 bajty) jest dłuższy niż skrócony
HMAC, więc wynikowy klucz aktywacyjny jest długim ciągiem znaków
przeznaczonym do SKOPIOWANIA (np. z maila), nie do ręcznego przepisania
znak po znaku — tak jak to wygląda w praktyce w większości
rzeczywistych systemów licencyjnych.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

PUBLIC_KEY_PATH = Path(__file__).parent / "public_key.pem"

# Kolejność nie ma znaczenia dla bezpieczeństwa — to tylko kompaktowe
# kodowanie dozwolonych okresów ważności klucza w jednym bajcie.
DURATION_CODES: dict[int, int] = {3: 0, 6: 1, 12: 2, 24: 3}
DURATION_BY_CODE: dict[int, int] = {code: months for months, code in DURATION_CODES.items()}

_NONCE_LENGTH = 4
_SIGNATURE_LENGTH = 64
_GROUP_SIZE = 5


class LicenseKeyError(Exception):
    """Klucz aktywacyjny jest nieprawidłowy, uszkodzony albo podrobiony."""


def _load_public_key() -> Ed25519PublicKey:
    return load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())


def _format_key_string(raw: bytes) -> str:
    encoded = base64.b32encode(raw).decode("ascii").rstrip("=")
    groups = [encoded[i : i + _GROUP_SIZE] for i in range(0, len(encoded), _GROUP_SIZE)]
    return "-".join(groups)


def _parse_key_string(key_string: str) -> bytes:
    cleaned = key_string.strip().upper().replace("-", "").replace(" ", "")
    padding_needed = (-len(cleaned)) % 8
    try:
        return base64.b32decode(cleaned + "=" * padding_needed)
    except ValueError as exc:  # obejmuje też binascii.Error (jego podklasę)
        raise LicenseKeyError("Nieprawidłowy format klucza aktywacyjnego.") from exc


def generate_license_key(private_key: Ed25519PrivateKey, months: int) -> str:
    """Generuje nowy klucz aktywacyjny. WYMAGA klucza prywatnego —
    ta funkcja jest przeznaczona dla `tools/generate_license_key.py`
    (narzędzie sprzedawcy), nie dla samej aplikacji."""
    if months not in DURATION_CODES:
        raise ValueError(f"Nieobsługiwany okres: {months} miesięcy. Dozwolone: {sorted(DURATION_CODES)}.")

    payload = bytes([DURATION_CODES[months]]) + os.urandom(_NONCE_LENGTH)
    signature = private_key.sign(payload)
    return _format_key_string(payload + signature)


@dataclass(frozen=True)
class LicenseKeyPayload:
    months: int


def verify_license_key(key_string: str) -> LicenseKeyPayload:
    """Weryfikuje klucz aktywacyjny kluczem PUBLICZNYM. Zgłasza
    `LicenseKeyError`, jeśli klucz jest uszkodzony, podrobiony albo ma
    nieprawidłowy format — nigdy nie zwraca częściowo zaufanego wyniku."""
    raw = _parse_key_string(key_string)
    if len(raw) != 1 + _NONCE_LENGTH + _SIGNATURE_LENGTH:
        raise LicenseKeyError("Nieprawidłowa długość klucza aktywacyjnego.")

    payload, signature = raw[: 1 + _NONCE_LENGTH], raw[1 + _NONCE_LENGTH :]
    public_key = _load_public_key()
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise LicenseKeyError("Klucz aktywacyjny jest nieprawidłowy albo został podrobiony.") from exc

    duration_code = payload[0]
    if duration_code not in DURATION_BY_CODE:
        raise LicenseKeyError("Klucz aktywacyjny zawiera nieznany okres ważności.")
    return LicenseKeyPayload(months=DURATION_BY_CODE[duration_code])


def load_private_key_for_signing(private_key_path: Path) -> Ed25519PrivateKey:
    """Wczytuje klucz prywatny z pliku — używane WYŁĄCZNIE przez narzędzie
    sprzedawcy do generowania kluczy, nigdy przez samą aplikację."""
    data = Path(private_key_path).read_bytes()
    key = load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise LicenseKeyError("Plik nie zawiera klucza prywatnego Ed25519.")
    return key
