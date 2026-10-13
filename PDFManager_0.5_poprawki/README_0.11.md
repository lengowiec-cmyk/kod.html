# PDFManager 0.11 — zmiana języka menu bez restartu

Poprawiono obsługę polskiego, angielskiego i ukraińskiego w głównym menu,
wszystkich ośmiu zakładkach, przyciskach wstążki, pasku formatowania tekstu,
ustawieniach, profilach skanowania, bibliotece folderów i centrum spedycji.

## Jak zmienić język

Wybierz **Ustawienia → Język interfejsu**, a następnie Polski, English albo
Українська. Zmiana pojawia się od razu, także w otwartym oknie ustawień.
Nowo otwierane okna otrzymują bieżący język. Wybrany język jest zapamiętywany.

Przełączanie języka nie tłumaczy zawartości PDF, wpisanego tekstu, nazw plików,
szafek, profili użytkownika, zapisanych wzorów stempli ani nazw czcionek.
Wybrane opcje zachowują swoje wewnętrzne wartości — np. profil „Szarość” nadal
uruchamia przetwarzanie w odcieniach szarości, choć interfejs pokazuje „Grayscale”.

Zmiana dotyczy interfejsu aplikacji. Komunikaty systemu Windows, sterowników
skanera i usług zewnętrznych mogą używać języka wybranego w tych systemach.
Nie jest to automatyczne tłumaczenie treści dokumentów ani wszystkich opisów
błędów i komunikatów silnika PDF.

## Aktualizacja na Windows

ZIP zawiera cały projekt źródłowy. Aby poprawka znalazła się w programie,
zbuduj nowe EXE. Samo skopiowanie plików Python obok starego EXE go nie aktualizuje.
Rozpakuj nowe źródła do osobnego folderu, np. `C:\PDFManager_0.11`.
W PowerShellu uruchom:

```powershell
Set-Location 'C:\PDFManager_0.11'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
.\packaging\build_windows.bat
.\dist\PDFManager\PDFManager.exe
```

Zachowaj cały folder `dist\PDFManager`, łącznie z `_internal` i podfolderami.
Skrypt dołącza nowe katalogi tłumaczeń oraz standardowe tłumaczenia okien Qt.
Budowę i działanie EXE trzeba sprawdzić na Windows — testy tego wydania wykonano
w środowisku Linux z rzeczywistymi widżetami PySide6.

Jeśli przygotowujesz sparowaną paczkę dla pracowników, użyj nowego
`dist\PDFManager` w dotychczasowym programie właściciela. Nie przenoś prywatnych
kluczy właściciela do paczki klienta.

## Zrzuty rzeczywistego interfejsu

- [Język angielski](previews_0.11/01_english.png)
- [Język ukraiński](previews_0.11/02_ukrainian.png)

To zrzuty działającej aplikacji PySide6 przy skali 200%, z przykładowym
dokumentem. Język dokumentu pozostaje polski mimo zmiany języka menu.
