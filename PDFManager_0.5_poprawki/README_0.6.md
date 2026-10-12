# PDFManager 0.6 — centrum dokumentów

Rozbudowa wersji poprawionej przez Claude. Nowy interfejs wykorzystuje własny
znak programu, własne ikony i niezależnie zaprojektowane elementy graficzne.
Inspiracją jest organizacja pracy pokazana na dostarczonych ekranach; nie
skopiowano logo, ikon, kodu ani materiałów graficznych FileCenter.

## Główne obszary

- **Organizuj:** szafki, szuflady, drzewo folderów, lista plików i podgląd PDF.
- **Skrzynka:** dokumenty przychodzące i docelowe szafki obok siebie; kopiowanie
  zaznaczonych plików oraz przeciąganie dokumentów do prawego panelu.
- **Edytor PDF:** tekst, czcionki, obrazy, adnotacje, formularze, strony,
  scalanie, dzielenie, OCR, podpisy i konwersje.
- **Szukaj:** nazwy, tekst PDF, podfoldery, typy plików i zakres dat;
  dostępne katalogi sieciowe Windows można wybrać tak samo jak lokalne.
- **Wydatki:** wpisy paragonów z podglądem PDF, sprzedawcą, datą, kwotą,
  walutą, kategorią, formą płatności, opisem i oznaczeniem „do zwrotu”; eksport CSV.
- **Automatyzacja:** reguły kierowania według nazwy, tekstu albo kodu kreskowego.
- **Edytor obrazu:** istniejące przekształcenia skanów i obrazów.

## Uruchomienie ze źródeł na Windows

Uruchom cmd w tym katalogu:

```bat
py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m pdfmanager.main
```

Tesseract 5 i modele językowe są potrzebne tylko do OCR. Zainstalowane modele
pol/eng/ukr można wybrać w dialogu OCR. Pobierane modele mają przypiętą wersję
repozytorium i sprawdzane SHA-256. Program domyślnie uruchamia polski interfejs.

## Budowanie EXE

```bat
python -m pip install -r packaging\requirements-build.txt
call packaging\build_windows.bat
```

Wynik: `dist\PDFManager\PDFManager.exe` i wersja konsolowa
`dist\PDFManagerCLI\PDFManagerCLI.exe`. Zachowaj cały folder programu.
Instalator powstaje przez kompilację `packaging\installer.iss` w Inno Setup.
Do obu specyfikacji dodano moduły procesów PDF i rozpoznawania kodów.
Nie zbudowano gotowego instalatora Windows w środowisku Linux.

## Jak korzystać z nowych funkcji

1. **Szafki i szuflady:** dodaj szafkę wskazując katalog. Szuflady są folderami
   pierwszego poziomu. W panelu po lewej wybierz szafkę i filtruj szuflady.
   Wybrany folder pojawi się w drzewie i na liście dokumentów.
2. **Szablony folderów:** w Organizuj otwórz bibliotekę szablonów. Dodaj strukturę,
   wpisując względne ścieżki po jednej na linię. Sprawdź podgląd drzewa i wybierz
   „Utwórz klienta z szablonu”. Istniejące foldery klienta nie są nadpisywane.
3. **Skrzynka:** wybierz folder przychodzący, szafkę albo folder docelowy.
   Przeciągnij dokument na prawą listę lub wybierz „Kopiuj zaznaczone”.
   Oryginały zostają w skrzynce; konflikty nazw są zgłaszane.
4. **Profile skanowania:** w Skrzynce wybierz Profile skanowania. Ustaw DPI,
   kolor/szarość/czerń i biel, obrót, pomijanie pustych stron i OCR.
   Zapisz profil i wybierz „Importuj skany według profilu”. Papier i dupleks
   sprzętowy ustawiasz w sterowniku urządzenia — profil przetwarza odebrane pliki.
5. **Reguły:** w Automatyzacji dodaj nazwę reguły, warunek, frazę oraz folder.
   Pierwsza pasująca aktywna reguła wygrywa. Uruchom przetwarzanie wskazanych
   dokumentów albo w ustawieniach obserwatora zaznacz używanie reguł kierowania.
   Obserwator zachowuje kopię w folderze importu i tworzy kopię w docelowej szafce.
6. **Kody:** otwórz PDF i wybierz Kody kreskowe. Program rozpoznaje QR i typowe
   formaty 1D/2D obsługiwane przez ZXing. Wyniki pokazują treść i numer strony.
   Reguła „Kod kreskowy” może kierować dokument na podstawie odczytanej treści.
   „Podział wg kodów” tworzy części rozpoczynające się stronami z kodami; strony
   z kodem zostają zachowane, a wyniki trafiają do nowego podfolderu.
7. **Wydatki:** dodaj wpis, wybierz PDF paragonu i uzupełnij dane. Program sumuje
   kwoty osobno dla każdej waluty. Dane można edytować, usuwać i eksportować do CSV.
   Kwoty i kategorie są wprowadzane ręcznie; nie deklarujemy automatycznej księgowości.
8. **Udostępnianie:** przygotuj ZIP z wybranymi dokumentami. Następnie przekaż go
   samodzielnie przez wybraną usługę lub pocztę. Nie jest to kopia usługi Portal
   ani nowy serwer wystawiony w Internecie. Integracja Google Drive pozostaje w menu.
9. **Ustawienia:** dostępnych jest dziesięć kategorii, w tym wygląd, profile, zapis,
   wyszukiwanie, integracje i bezpieczeństwo. Przełącz podgląd w Organizuj,
   wybierz widok/powiększenie, językowe opcje wyszukiwania i zakładkę startową.

## Bezpieczne kopie i zapis

Edycja działa w kopii roboczej; Zapisz / Ctrl+S prosi o potwierdzenie zapisu
oryginału. Poprzednia wersja trafia do zaszyfrowanej kopii `.pdm`. Zapisz jako
wybiera nowe miejsce. Po zwykłym zamknięciu niezapisana kopia zostaje zaszyfrowana.
Plik → Odzyskaj dokument i Kopie zapasowe odczytują te pliki wewnątrz programu.
Zapisz odzyskany dokument jako zwykły PDF przed przekazaniem innej osobie.

Kosz, indeks i dane wydatków są szyfrowane. W Windows klucz jest zabezpieczony
przez DPAPI konta użytkownika. Zachowaj katalog danych oraz profil Windows;
samo przeniesienie plików `.pdm` na inne konto może nie wystarczyć do ich odczytu.
W Ustawienia → Bezpieczeństwo można zaszyfrować starsze lokalne kopie.
Zamknij inne uruchomione wersje programu przed taką migracją.

## Sprawdzenie

Aktualny wynik: `TEST_RESULTS_0.6.txt`. Zrzuty działających okien są w
`previews_0.6`. Mapa wymagań: `FUNKCJE_0.6.md`; szczegóły zabezpieczeń i ograniczeń:
`BEZPIECZENSTWO_0.6.md`. Testy uruchomiono na Linux z Qt offscreen.
Rzeczywisty skaner, drukarka, DPAPI, Defender, Windows Job Object i gotowy
instalator wymagają prób na Windows według `tools/CHECK_WINDOWS.md`.
