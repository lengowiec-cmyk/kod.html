# PDFManager 0.12 — profesjonalny pasek formatowania

Pasek Edytora PDF ma teraz kompaktowy układ z grupami Schowek, Czcionka,
Akapit, Style i Dokument PDF. Kolorowe, własne ikony wektorowe są rysowane
w rzeczywistej skali ekranu, również przy powiększeniu Windows 125–300%.
Nie wykorzystano grafik ani zasobów Microsoft Word lub FileCenter.

Galeria pokazuje wygląd sześciu stylów tekstu. Kliknięcie kafelka stosuje styl
do zaznaczonego tekstu lub tekstu wpisywanego w szkicu. Przycisk › przewija
kolejne kafelki; pełna lista znajduje się również pod galerią.
Przyciski czcionki i akapitu mają opisowe, tłumaczone podpowiedzi.
Pasek zachowuje funkcje kopiowania, wklejania, zmiany czcionki i rozmiaru,
kolorów, list, wyrównania oraz zastosowania zmian do PDF.

Na mniejszych ekranach pasek można przewijać w poziomie. Ikony i podpisy
nie są ściskane do nieczytelnych rozmiarów. Wybrany kolor tekstu pokazuje
kolorowa kreska pod ikoną A. Galeria podświetla wybrany styl.

Zmiany najpierw dotyczą szkicu i kopii roboczej. Po wybraniu tekstu w PDF
ustaw format, kliknij „Zastosuj do PDF”, sprawdź wynik i zapisz dokument.
Źródłowy plik nie jest nadpisywany przez samo kliknięcie stylu.

- [Rzeczywisty wygląd paska](previews_0.12/02_pasek.png)
- [Całe okno programu](previews_0.12/01_pasek_formatowania.png)
- [Wyniki testów tego wydania](TEST_RESULTS_0.12.txt)

## Budowa EXE na Windows

ZIP zawiera pełne źródła. Rozpakuj do osobnego folderu `C:\PDFManager_0.12`
i uruchom w PowerShellu:

```powershell
Set-Location 'C:\PDFManager_0.12'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
.\packaging\build_windows.bat
.\dist\PDFManager\PDFManager.exe
```

Do uruchamiania potrzebny jest cały folder `dist\PDFManager`, również
`_internal` i podfoldery. Stare EXE nie zmieni wyglądu po skopiowaniu
obok niego plików Python. Budowę i działanie EXE trzeba sprawdzić na Windows.
