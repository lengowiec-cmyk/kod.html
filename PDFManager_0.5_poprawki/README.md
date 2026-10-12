# PDFManager 0.5

Aplikacja desktopowa Python / PySide6: edycja PDF, OCR, szafki DMS i import skanów.

## Uruchomienie na Windows

Z terminala w tym katalogu:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pdfmanager.main
```

Program zachowuje istniejący mechanizm licencji PDFManager.

- [Pełna instrukcja](README_ROZBUDOWA.md)
- [Nowe funkcje 0.5 i ograniczenia](ZMIANY_0.5.md)
- [Szafki DMS](MODUL_DMS.md)
- [Sprawdzenie na Windows](tools/CHECK_WINDOWS.md)
- [Budowanie EXE i instalatora](packaging/BUILD_INSTRUCTIONS.md)
- [Wyniki testów](TEST_RESULTS.txt)
- [Wymagania licencyjne](LICENSING.md)

Źródła, testy i konfiguracja instalatora są dostępne w tym katalogu.
Gotowy instalator Windows nie został zbudowany ani zweryfikowany w środowisku Linux.
Kod funkcji inspirowanych KillerPDF został napisany niezależnie; nie skopiowano
jego kodu GPL ani zasobów FileCenter. Dystrybucja z zamkniętym kodem wymaga
rozstrzygnięcia licencji PyMuPDF zgodnie z LICENSING.md.
