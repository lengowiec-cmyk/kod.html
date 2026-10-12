from PyInstaller.utils.hooks import collect_submodules
# -*- mode: python ; coding: utf-8 -*-
"""Specyfikacja PyInstaller dla Menedżera PDF.

WAŻNE: plik .exe dla Windows trzeba zbudować NA WINDOWS (PyInstaller nie
pozwala budować krzyżowo z Linuksa/macOS na Windows). Uruchom na Windows,
w aktywowanym środowisku wirtualnym projektu z zainstalowanym
`pyinstaller` (patrz requirements.txt oraz packaging/build_windows.bat):

    pyinstaller packaging\\pdfmanager.spec --noconfirm

Wynik: dist\\PDFManager\\PDFManager.exe (tryb --onedir: szybszy start niż
jeden wielki plik .exe i łatwiej zdiagnozować brakujące zależności —
wszystkie pliki potrzebne do działania są w folderze dist\\PDFManager).

Jeśli pierwsze uruchomienie zbudowanego .exe zgłosi ModuleNotFoundError
dla jakiegoś pakietu (typowe np. dla opcjonalnych backendów `keyring` albo
wtyczek Qt) — dodaj go do `hiddenimports` poniżej i zbuduj ponownie.
"""
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent  # packaging/ -> korzeń projektu
ICON_PATH = PROJECT_ROOT / "packaging" / "pdfmanager.ico"

configuration=PROJECT_ROOT/'pdfmanager/resources/management.json'
management_data=[(str(configuration),'pdfmanager/resources')] if configuration.is_file() else []

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / "pdfmanager" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[(str(PROJECT_ROOT / 'third_party' / 'ZXing_CPP_LICENSE.txt'), 'third_party'),
        # Klucz PUBLICZNY do weryfikacji kluczy aktywacyjnych (patrz
        # pdfmanager/licensing/license_key.py) — bezpieczny do dystrybucji;
        # klucz PRYWATNY (tools/private_key_DO_NOT_SHIP.pem) NIE jest tu
        # wymieniony i nigdy nie powinien trafić do spakowanej wersji.
        (str(PROJECT_ROOT / "pdfmanager" / "licensing" / "public_key.pem"), "pdfmanager/licensing"),
    ]+management_data,
    hiddenimports=[
        # keyring wybiera backend dynamicznie (pkgutil/entry_points) — na
        # Windows potrzebujemy mieć WinVaultKeyring dostępny w spakowanej
        # wersji, nawet jeśli statyczna analiza importów tego nie wykryje.
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
        "pyhanko.sign.validation",
        "pyhanko.sign.signers",
    ]+collect_submodules('pdfmanager.pdf_engine')+collect_submodules('pdfmanager.security')+['zxingcpp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Pliki danych aplikacji, które nie są kodem Pythona — tłumaczenia (JSON)
# i czcionka zastępcza DejaVu Sans (patrz pdf_engine/font_resolver.py).
# `Tree(...)` kopiuje cały katalog do spakowanej wersji pod tą samą
# ścieżką względną co w repozytorium, dzięki czemu istniejący kod
# (Path(__file__).parent / "resources" / "fonts" itd.) działa bez zmian
# również po spakowaniu.
locales_tree = Tree(
    str(PROJECT_ROOT / "pdfmanager" / "i18n" / "locales"),
    prefix="pdfmanager/i18n/locales",
)
fonts_tree = Tree(
    str(PROJECT_ROOT / "pdfmanager" / "resources" / "fonts"),
    prefix="pdfmanager/resources/fonts",
)
branding_tree = Tree(
    str(PROJECT_ROOT / "pdfmanager" / "resources" / "branding"),
    prefix="pdfmanager/resources/branding",
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDFManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # aplikacja okienkowa — bez konsoli w tle
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    locales_tree,
    fonts_tree,
    branding_tree,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PDFManager",
)
