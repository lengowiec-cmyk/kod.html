# PDFManager 0.10 — pasek formatowania tekstu i responsywny podgląd

Zachowano dotychczasowe menu, osiem zakładek i funkcje aplikacji. W Edytorze
PDF pojawił się dodatkowy pasek formatowania oraz panel szkicu tekstu.
Układ i grafika są własne; nie skopiowano zasobów ani kodu Microsoft Word.

[Zrzut rzeczywistego okna](previews_0.10/01_pasek_formatowania.png).

## Jak edytować tekst

1. Otwórz PDF i wybierz na nowym pasku **Edytuj tekst PDF**.
2. Kliknij fragment tekstu na stronie. Po prawej pojawi się jego szkic.
3. Zaznacz w szkicu tekst, który chcesz sformatować, i użyj paska nad PDF.
   Bez zaznaczenia formatowanie dotyczy miejsca wpisywania nowego tekstu.
4. Kliknij **Zastosuj do PDF**. Zmiana dotyczy kopii roboczej. Sprawdź wynik
   na stronie; **Cofnij** przywraca poprzednią wersję.
5. Dopiero **Zapisz / Ctrl+S** zapisuje wynik do dokumentu źródłowego, zgodnie
   z dotychczasowym mechanizmem potwierdzenia, kopii zapasowej i konfliktów.

**Nowy tekst** otwiera pusty szkic. Po wpisaniu i sformatowaniu tekstu wybierz
Zastosuj do PDF, a następnie przeciągnij prostokąt na stronie. Jego rozmiar
wyznacza pole dla tekstu. Wklejanie do szkicu przyjmuje tekst ze schowka;
nie pobiera zewnętrznych obrazów ani zasobów z wklejonego HTML.

PDF nie jest dokumentem Word: aplikacja nie przebudowuje automatycznie całej
strony i kolejnych stron. Formatowany jest wskazany fragment lub nowe pole.
Jeżeli tekst się nie mieści, zmiana nie zostaje zapisana. Powiększ szerokość
lub wysokość pola w panelu albo zmniejsz czcionkę. Skan bez warstwy tekstowej
wymaga OCR lub wstawienia nowego pola — nie zawiera fragmentów do wybrania.

## Narzędzia paska

- Lista czcionek zainstalowanych w systemie, z podglądem nazw w ich kroju.
  Czcionka jest rozwiązywana i osadzana w procesie PDF. Dostępność krojów
  takich jak Calibri, Arial czy Aptos zależy od komputera.
- Rozmiary 8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48 i 72
  punktów, możliwość wpisania własnego rozmiaru oraz zwiększanie/zmniejszanie.
- Pogrubienie, kursywa, podkreślenie, przekreślenie, indeks dolny i górny.
- Kolor tekstu, zakreślenie, zmiana wielkości liter i usuwanie formatowania.
- Listy punktowane i numerowane, wyrównanie do lewej, środka, prawej oraz
  justowanie, wcięcia, interlinia, tło akapitu i ramka.
- Style Normalny, Bez odstępów, Nagłówek 1, Nagłówek 2, Tytuł i Podtytuł.
- Wklejanie, kopiowanie i wycinanie tekstu w szkicu, sortowanie akapitów
  alfabetycznie i pokazywanie znaków odstępów/akapitów.
- Malarz formatów: zaznacz tekst źródłowy i kliknij przycisk, zaznacz tekst
  docelowy i kliknij go ponownie.

Efekty formatowania są zapisywane do PDF, a nie tylko pokazywane w panelu.
Nieobsługiwany krój lub wariant może wymagać dołączonej czcionki zastępczej.
Brak wymaganych znaków powoduje odmowę zapisu, zamiast usunięcia oryginału.

## Ograniczenie zawieszania

W przesłanym logu jest starszy błąd `ModuleNotFoundError: numpy`. Ostatnie
uruchomienia nie zawierają stosu zawieszenia, więc nie potwierdzają jego
konkretnej przyczyny. Przegląd kodu wykazał natomiast oczekiwanie na operacje
PDF i antywirusa w głównym wątku Qt.

W tej wersji:

- Operacje izolowanego procesu PDF i skanowanie Defenderem są wykonywane
  w zadaniu w tle. Podczas oczekiwania działa pętla zdarzeń Qt i okno postępu.
- Kopia robocza powstaje w tle także dla małych plików: mały plik z Drive może
  wymagać długiego pobrania. Zapis dokumentu i kopii również korzysta z tła.
- Miniatury i rastry widoków wielostronicowych są obliczane poza głównym
  wątkiem. W tle działa jednocześnie jeden renderer podglądu dla wszystkich
  kart. Liczba widocznych ikon miniatur jest ograniczona, zamiast tworzenia
  rastrów wszystkich stron dużego dokumentu.
- Anulowanie, także zamknięciem okna postępu, zgłasza zatrzymanie zadania.
  Program czeka na zakończenie bezpiecznego kroku; nie niszczy działających
  wątków. Kopiowanie sprawdza anulowanie między porcjami danych.
- Anulowany podgląd usuwa stary obraz i wyłącza jego edycję. Ponowny wybór
  strony pozwala odtworzyć podgląd; nie edytuje się starego obrazu jako
  innej strony.
- Zachowano ograniczenia czasu, pamięci, liczby stron, rozmiarów plików,
  rastrów i odizolowane procesy PDF. Nie wyłączono antywirusa.
- Pakowanie jawnie uwzględnia `numpy`. Zależność nadal znajduje się
  w requirements.txt.
- Jeżeli pętla okna przestanie działać przez 15 sekund, diagnostyka zapisze
  stosy w pliku `hang-traces.txt`, obok zwykłego log.txt w danych aplikacji.

To ogranicza konkretne źródła blokowania UI. Nie jest gwarancją, że dowolny
uszkodzony PDF, sterownik drukarki, niedostępny udział sieciowy czy awaria
systemu nigdy nie spowoduje problemu. Operacja wejścia/wyjścia w systemie
może wymagać oczekiwania mimo zgłoszonego anulowania.

## Zbudowanie nowej wersji na Windows — PowerShell

Rozpakuj nowy projekt do **C:\PDFManager_0.10**. Nie uruchamiaj poleceń
z C:\Windows\System32. Wpisuj je kolejno i zatrzymaj się w razie błędu:

```powershell
Set-Location C:\PDFManager_0.10
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.0
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
$env:Path = "$PWD\.venv\Scripts;$env:Path"
.\packaging\build_windows.bat
.\dist\PDFManager\PDFManager.exe
```

Zachowaj cały folder dist\PDFManager wraz z zależnościami. Program właściciela
buduje się nadal przez packaging\build_admin_windows.bat. Przygotowanie
firmowej paczki działa zgodnie z [instrukcją 0.9](README_0.9.md).
Nie kasuj danych aplikacji w profilu Windows ani prywatnego katalogu
właściciela — aktualizacja źródeł i EXE nie wymaga ich usuwania.

Wyniki weryfikacji: [TEST_RESULTS_0.10.txt](TEST_RESULTS_0.10.txt).
Gotowy Windows EXE, rzeczywisty Drive Desktop i sterowniki sprzętu wymagają
sprawdzenia na Windows; środowisko rozwoju dla tej zmiany działa na Linux.
