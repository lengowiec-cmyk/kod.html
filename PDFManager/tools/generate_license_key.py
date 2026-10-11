#!/usr/bin/env python3
"""Narzędzie SPRZEDAWCY do generowania kluczy aktywacyjnych Menedżera PDF.

NIE jest częścią aplikacji — PyInstaller go nie paczkuje (paczkuje tylko
to, co importuje pdfmanager/main.py). Wymaga pliku `private_key_DO_NOT_SHIP.pem`
w tym samym katalogu (wygenerowanego razem z publicznym kluczem wbudowanym
w aplikację — patrz pdfmanager/licensing/public_key.pem).

!!! KLUCZ PRYWATNY NIGDY NIE MOŻE TRAFIĆ DO SPAKOWANEJ APLIKACJI, DO
    INSTALATORA ANI DO PUBLICZNEGO REPOZYTORIUM !!! Każdy, kto go zdobędzie,
    może wygenerować dowolną liczbę w pełni prawidłowych kluczy aktywacyjnych
    na dowolny okres. Przechowuj go tylko na swoim komputerze (najlepiej
    w menedżerze haseł albo zaszyfrowanym dysku), poza katalogiem projektu
    jeśli ten katalog jest kiedykolwiek publikowany.

Użycie:
    python tools/generate_license_key.py 12
    python tools/generate_license_key.py 6 --private-key /inna/sciezka.pem
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdfmanager.licensing.license_key import (  # noqa: E402
    DURATION_CODES,
    LicenseKeyError,
    generate_license_key,
    load_private_key_for_signing,
    verify_license_key,
)

DEFAULT_PRIVATE_KEY_PATH = Path(__file__).parent / "private_key_DO_NOT_SHIP.pem"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generuje klucz aktywacyjny Menedżera PDF.")
    parser.add_argument("months", type=int, choices=sorted(DURATION_CODES), help="Okres ważności licencji w miesiącach.")
    parser.add_argument(
        "--private-key", type=Path, default=DEFAULT_PRIVATE_KEY_PATH, help="Ścieżka do klucza prywatnego Ed25519 (PEM)."
    )
    args = parser.parse_args()

    if not args.private_key.is_file():
        print(f"BŁĄD: nie znaleziono klucza prywatnego: {args.private_key}", file=sys.stderr)
        return 1

    private_key = load_private_key_for_signing(args.private_key)
    key = generate_license_key(private_key, args.months)

    try:
        verify_license_key(key)  # sanity check tym samym kodem, który uruchomi klient
    except LicenseKeyError as exc:
        print(f"BŁĄD WEWNĘTRZNY: wygenerowany klucz nie przeszedł własnej weryfikacji: {exc}", file=sys.stderr)
        return 1

    print(f"Klucz aktywacyjny na {args.months} miesięcy:")
    print()
    print(key)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
