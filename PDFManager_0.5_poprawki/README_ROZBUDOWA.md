# PDFManager 0.5 — własny interfejs i rozszerzone funkcje PDF

Ta wersja rozwija przesłany kod PDFManagera w Pythonie/PySide6. Funkcje zostały
zaimplementowane niezależnie na podstawie zakresu możliwości KillerPDF.
Nie dołączono ani nie skopiowano kodu C# KillerPDF, jego silnika .NET ani
ikon, logo, tekstów marketingowych lub plików graficznych FileCenter.

## Uruchomienie na Windows

Rozpakuj ZIP do NOWEGO folderu. Zachowaj oryginalny projekt i oryginalne PDF-y.
W terminalu w folderze z requirements.txt:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pdfmanager.main
```

Mechanizm licencji PDFManagera oraz oryginalny klucz publiczny pozostają bez zmian.
Testy używają tymczasowych kluczy testowych; nie potrzebują klucza sprzedawcy.
Nie dołączono żadnego prywatnego klucza, certyfikatu podpisu ani poświadczeń.

## OCR

OCR wymaga Tesseract 5. Instrukcje instalacji:
https://tesseract-ocr.github.io/tessdoc/Installation.html
Na Windows program szuka tesseract.exe w PATH oraz standardowych katalogach
Program Files/Tesseract-OCR. Sam silnik Tesseract nie jest dołączony do instalatora.

Narzędzia → Języki OCR pobiera model pol, eng lub ukr z oficjalnego tessdata_fast.
Model jest przypięty do konkretnego commitu i sprawdzany względem identyfikatora
obiektu Git; nie wyłącza się TLS ani kontroli integralności. Pobieranie modeli
wymaga połączenia z raw.githubusercontent.com. Dokumenty nie są tam wysyłane.
Zainstalowane modele systemowe pozostają dostępne, również inne języki.
OCR wymaga kontroli wyników: w teście wielkich polskich liter przy 150 DPI
model fast rozpoznaje Ź jako Ż. Ten przypadek pozostaje oznaczonym testem
oczekiwanego niepowodzenia (xfail), a nie ukrytym sukcesem.
Wybrany model kopiuje się do tymczasowego katalogu na czas rozpoznawania.

OCR może tworzyć przeszukiwalny PDF lub tekst, obejmować wszystkie strony,
bieżącą stronę albo zaznaczony obszar. Wynik tekstowy można zapisać lub skopiować
do schowka. PDF z OCR jest nową kopią rastrową z warstwą tekstu, a nie aktualizacją
oryginalnego PDF zachowującą jego formularze/podpisy.

## Interfejs

Sześć obszarów: Start, Skrzynka, Organizuj, Edytor PDF, Edytor obrazu, Szukaj.
Skrzynka i Organizuj udostępniają lokalny system plików; nie wprowadzono
odrębnego serwera skrzynki, faksu ani katalogu szaf z FileCenter.
Układ, biała wstążka, niebieski pasek tytułu i szary obszar PDF odpowiadają
ogólnemu układowi dostarczonych zrzutów. Ikony są własnymi rysunkami wektorowymi.
To nie jest kopia piksel w piksel i nie stanowi gwarancji prawnego dopuszczenia
całego projektu do dystrybucji. Branding i logo PDFManagera pochodzą z przesłanej aplikacji.

Ustawienia pozwalają zmieniać motyw jasny/ciemny, sześć kolorów tytułu,
biały/szary kolor wstążki i kompaktowy rozmiar. Opcje są zapamiętywane.
Okno można przesuwać paskiem tytułu, maksymalizować dwuklikiem i zmieniać
rozmiar dolnym uchwytem. F1 pokazuje skróty; Ctrl+Shift+K przywraca edytor PDF.
Dotychczasowe tłumaczenia PL/EN/UK pozostają; nowe dialogi są głównie po polsku.

## Najważniejsze operacje

- Pięć widoków: jedna strona, ciągły, dwie strony, książka i siatka.
  Obrazy widocznych stron w widokach wielostronicowych są renderowane leniwie.
  Dwuklik strony wraca do widoku pojedynczego. Edycja odbywa się w pojedynczym widoku.
  Widok → Przenieś miniatury przełącza panel między lewą i prawą stroną.
- Miniatury, nawigacja, zoom, wyróżnianie wyników wyszukiwania i tryb nocny.
- Porównanie wizualne stron i raport procentu zmienionych pikseli.
- Dwa dokumenty obok siebie; panel porównawczy jest niezależną kopią do podglądu.
- Adnotacje, kolory/grubość kształtów, odręczne rysowanie, strzałki, pięciokąt,
  edytowalne notatki, tekst, podświetlenie Multiply i podpisy graficzne.
- Redakcja usuwa treść w prostokącie w kopii roboczej; sprawdź wynik przed zapisem.
  Nie jest to pełny audyt usunięcia danych z metadanych, załączników ani innych stron.
- OCR, wyciąganie tekstu, prostokątne kopiowanie tekstu, aktywne linki HTTP/HTTPS.
- Formularze AcroForm: tekst, checkbox, radio, lista/combobox; zapis nowej kopii.
- Zakładki: przeglądanie, przechodzenie i dodawanie zakładki do bieżącej strony.
- Dodawanie i eksport załączników PDF.
- Scalanie PDF, obrazów, TIFF wielostronicowego, folderów i ZIP, także po upuszczeniu.
- PNG/JPEG: wybrane zakresy stron, DPI 72–600; bez nadpisywania istniejących obrazów.
- Przycinanie marginesów, zmiana rozmiaru strony, znak wodny i numeracja.
- Obrót, odbicie, prostowanie kątem, poziomy czerni/bieli/gamma, korekcja perspektywy.
  Operacje skanów tworzą rastrową kopię wszystkich stron.
- Otwieranie PDF z hasłem jako osobnej odszyfrowanej kopii roboczej w lokalnym cache.
  Oryginał pozostaje bez zmian; użyj Zapisz jako, aby zachować edycje w wybranym miejscu.
- Szyfrowanie AES-256, usuwanie hasła, optymalizacja/ponowny zapis czytelnych PDF.
- Podpisy cyfrowe lokalnym certyfikatem PFX/P12 oraz weryfikacja integralności,
  poprawności kryptograficznej i zaufania. Brak internetowej kontroli OCSP/CRL.
- Podgląd wydruku Qt i drukowanie; eksport 1/2/4/6/9 stron na arkuszu;
  zbiorczy ponowny zapis z raportem CSV.
- Dłuższe operacje działają w wątku roboczym. OCR, wyszukiwanie i operacje wsadowe
  zgłaszają postęp i wspierają anulowanie na granicach kroków; zapis jest atomowy.

Pełne porównanie z KillerPDF i ograniczenia: FUNKCJE_KILLERPDF.md.

## Zapis i bezpieczeństwo plików

Od wersji 0.5 główne okno edytuje KOPIĘ ROBOCZĄ. Zapisz / Ctrl+S zapisuje ją
po potwierdzeniu i tworzy kopię zapasową oryginału. Zapisz jako wybiera inne miejsce.
Niezapisane kopie pozostają do odzyskania z menu Plik. Cofnij/Powtórz działa osobno
na każdej karcie; zamknięcie usuwa historię cofania, ale pozostawia niezapisany PDF.

Nowe eksporty tworzą osobny plik. GUI pyta przed nadpisaniem istniejącego
wyjścia; CLI może zastępować istniejący plik docelowy, dlatego wybieraj nową ścieżkę.
Wstawianie znaków wodnych, redakcja, wypełnianie formularza i inne zmiany w
podpisanym dokumencie mogą unieważnić jego podpis; zachowuj oryginał i sprawdzaj wynik.
Spłaszczenie/rasteryzacja usuwa wyszukiwalny tekst, formularze, linki i podpisy cyfrowe.
Obsługa uszkodzonych PDF zależy od tego, czy PyMuPDF potrafi je otworzyć.

## CLI

```powershell
.venv\Scripts\python -m pdfmanager.cli --help
.venv\Scripts\python -m pdfmanager.cli merge out.pdf a.pdf b.pdf scan.png
.venv\Scripts\python -m pdfmanager.cli extract-pages in.pdf 1-3,5 out.pdf
.venv\Scripts\python -m pdfmanager.cli ocr scan.pdf searchable.pdf --lang pol
.venv\Scripts\python -m pdfmanager.cli to-image in.pdf images --dpi 150 --format jpg
.venv\Scripts\python -m pdfmanager.cli print in.pdf --output printed.pdf --pages 1,3
.venv\Scripts\python -m pdfmanager.cli batch-resave input-folder output-folder
```

EXE po spakowaniu obsługuje np. PDFManager.exe --merge out.pdf a.pdf b.pdf.
Do widocznego stdout/stderr i pomocy służy osobna wersja konsolowa
PDFManagerCLI.exe merge out.pdf a.pdf b.pdf, budowana drugim spec.
Instalator dołącza ją do podfolderu CLI, jeśli build obu wersji się powiedzie.
Hasło do decrypt podaje się ukrytym promptem lub przez --password-stdin,
nie jako argument widoczny na liście procesów. CLI zachowuje blokadę licencji.
Kody zakończenia: 0 sukces, 1 błąd/blokada, 2 częściowe niepowodzenie wsadu.

## Budowanie Windows

```powershell
.venv\Scripts\python -m pip install -r packaging\requirements-build.txt
.venv\Scripts\Activate.ps1
packaging\build_windows.bat
```

Następnie skompiluj packaging/installer.iss przez Inno Setup na Windows.
Wersja instalatora: 0.2.0. Zaktualizowano spec PyInstaller do współczesnego PYZ
oraz uwzględniono dynamiczne importy podpisów PDF. Prywatnego klucza sprzedawcy
ani plików PFX/P12 nie włącza się do aplikacji. Testów i tools również nie pakuje się w EXE.
Skrypt setup_dev_cert.ps1 jest opcjonalnym oryginalnym narzędziem testowym;
nie został uruchomiony w tej pracy.

Windows EXE i Inno Setup NIE zostały zbudowane ani uruchomione tutaj.
Środowisko jest linuksowe; PyInstaller nie buduje krzyżowo aplikacji Windows.
Sprawdzono składnię spec i aktualne API PyInstaller, a nie gotowy instalator.

## Testy i dystrybucja

```powershell
.venv\Scripts\python -m pytest -q
```

Wyniki z tego środowiska: TEST_RESULTS.txt — 262 zaliczonych, 1 oczekiwane
niepowodzenie dokładności OCR (xfail), 1 ostrzeżenie biblioteki weryfikacji certyfikatów. Modele OCR mogą powodować pominięcie
odpowiedniego testu na maszynie, gdzie nie zainstalowano Tesseract lub modelu pol.
Testy aktywacji korzystają z tymczasowych par Ed25519, a test podpisu PDF
z tymczasowego certyfikatu PKCS#12. Nie zmieniono produkcyjnego klucza publicznego.

Przed zamkniętą dystrybucją trzeba rozwiązać istniejącą licencję PyMuPDF
(komercyjna licencja lub wymiana silnika). Własna implementacja funkcji
KillerPDF nie usuwa tego warunku. Patrz LICENSING.md i DODATKOWE_LICENCJE.md.

## Rozszerzenie edytora 0.3

Kliknięcie tekstu narzędziem edycji otwiera edytor treści, rozmiaru (1–300 pt),
koloru, pogrubienia i kursywy. Można zachować oryginalną osadzoną czcionkę,
użyć DejaVu Sans lub wybrać plik TTF/OTF. Wybrana czcionka musi zawierać
wszystkie znaki tekstu. Zmiana stylu może wymagać czcionki zastępczej.
Narzędzia → Wstaw tekst / obraz dodaje zawartość w zadanej pozycji i rozmiarze.
Narzędzia → Wklej ze schowka (Ctrl+V w widoku dokumentu) przyjmuje tekst lub obraz.
W polach tekstowych Ctrl+V działa jak standardowe wklejanie do pola.
Pozycja oraz szerokość/wysokość są podawane w punktach PDF; obraz zachowuje proporcje.
Przepełnienie nowego pola tekstowego przerywa zapis i pozostawia PDF bez zmian.
Operacje korzystają z historii Cofnij/Ponów. W głównym oknie zmieniają kopię
roboczą; Ctrl+S zapisuje oryginał dopiero po potwierdzeniu. Edycja istniejącego tekstu PDF nie jest edytorem Word:
nie przepływa automatycznie między akapitami i może kolidować z sąsiednim tekstem.
To rozszerzenie nie oznacza pełnej zgodności funkcjonalnej z FileCenter ani KillerPDF.

## Moduł DMS 0.4

Instrukcja nowych szafek, szablonów folderów, operacji na plikach, wyszukiwania
i importu skanów znajduje się w `MODUL_DMS.md`.

## Dodatki 0.5

Instrukcja bezpiecznego zapisu, panelu edycji, kosza, indeksu i automatyzacji
skanowania znajduje się w `ZMIANY_0.5.md`.
