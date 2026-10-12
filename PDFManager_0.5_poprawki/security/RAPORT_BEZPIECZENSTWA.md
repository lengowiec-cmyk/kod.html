> Raport historyczny wersji 0.5. Aktualny zakres zmian opisuje ../BEZPIECZENSTWO_0.6.md.

# Przegląd bezpieczeństwa PDFManager_0.5_poprawki

Data: 12 października 2026 r. Badany kod: commit
`7cf1739f9a532f62bedf02402869691856d5072f`.

## Wniosek

Programu nie należy obecnie traktować jako odpornego na wszystkie złośliwe PDF-y.
Nie wykazano zdalnego wykonania kodu przez konkretny exploit. Potwierdzono jednak
braki ograniczeń zasobów i ryzykowne przekazywanie plików do systemu operacyjnego.
Brak znanych podatności w sprawdzonych pakietach nie jest dowodem braku luk.

## Zakres i wyniki

- Przegląd kodu otwierania, renderowania, OCR, archiwów, załączników, połączeń
  sieciowych, uruchamiania procesów, kopii roboczych i indeksowania.
- pip-audit 2.10.1: **57 zainstalowanych pakietów runtime, 0 znanych podatności**,
  bez pominiętych pakietów. Badano rzeczywiście zainstalowane wersje z ich
  zależnościami w Linux, nie przyszłą instalację wynikającą z szerokich zakresów
  wersji w requirements.txt. Narzędzie korzystało z bazy podatności PyPI.
- PyMuPDF/MuPDF 1.28.2, PySide6/Qt 6.12.0, Pillow 12.3.0, cryptography 50.0.2.
- Bandit 1.9.4: 12 sygnałów do ręcznej oceny (1 HIGH, 2 MEDIUM, 9 LOW).
  To nie jest liczba potwierdzonych luk. Interpretację podano niżej.
- 5 bezpiecznych prób kontrolnych zakończonych poprawnie. Dwa testy potwierdzają
  ryzykowne uruchamianie plików, a jeden brak limitu eksportu. Ich zaliczenie
  oznacza odtworzenie zachowania, a nie usunięcie słabości.
- Nie używano prawdziwego malware, nie uruchamiano EXE testowego, nie wykonywano
  destrukcyjnego testu wyczerpania pamięci. Nie przeprowadzono fuzzingu ani
  testu gotowego EXE na Windows, skanera, aktualnego Defendera lub sterowników.
- pip-audit nie obejmuje pełnego audytu natywnych składników MuPDF/Qt/Tesseract,
  systemowego Pythona, wszystkich kodeków ani Windows. Wersje i zależności
  kompilacji Windows trzeba skontrolować osobno.

## Najważniejsze ustalenia

### A. Brak izolacji silnika PDF — wysoki priorytet zabezpieczenia

`pdfmanager/pdf_engine/render.py`, `pdfmanager/pdf_engine/workflows.py` oraz
`pdfmanager/dms/search.py` otwierają PDF przez PyMuPDF w procesie aplikacji.
Renderowanie, odczyt tekstu, osadzonych czcionek i obrazów przetwarza dane
pochodzące od autora dokumentu. Przeniesienie zadania do QThread nie jest
piaskownicą i nie oddziela uprawnień ani przestrzeni pamięci od głównego procesu.

Jeżeli w silniku natywnym lub kodeku wystąpi podatność, złośliwy plik może
spowodować awarię, a przy luce pozwalającej na wykonanie kodu — działać z
uprawnieniami konta użytkownika aplikacji. Jest to ryzyko architektury,
nie potwierdzony exploit przeciw wskazanej wersji MuPDF.

Zalecenie: osobny proces do obsługi niezaufanych dokumentów, ograniczony token
Windows/AppContainer tam, gdzie to możliwe, limity pamięci i czasu oraz brak
sieci i dostępu do poświadczeń dla procesu parsującego. Sam osobny proces
bez ograniczenia uprawnień nie wystarcza. Pracować jako zwykły użytkownik,
aktualizować komponenty i korzystać z ochrony antywirusowej systemu.

### B. Niepełne limity zasobów — potwierdzony brak ochrony przed DoS

Podgląd ma limit 20 milionów pikseli, ale nie obejmuje on wszystkich operacji.
Bezpośrednie `get_pixmap()` w OCR, eksporcie obrazów, spłaszczaniu, porównaniu,
przekształceniach i przygotowaniu arkuszy nie korzysta z tego limitu.

Bezpieczna próba: PDF z jedną stroną 10 000 × 10 000 punktów i eksport 600 DPI
przechodzi do renderera z żądaniem ponad 6,9 miliarda pikseli — ponad 20 GB
samego bufora RGB. Wywołanie renderera zastąpiono atrapą, aby nie zużywać tej
pamięci. Skutkiem rzeczywistego pliku może być zawieszenie lub zamknięcie programu;
nie wykazano w ten sposób możliwości przejęcia komputera.

Załączniki odczytywane przez `embfile_get()` również nie mają limitu rozmiaru
po rozpakowaniu. Limit 512 MB w scalaniu nie ogranicza rozmiaru rozkodowanego
obrazu ani liczby stron, obiektów czy wpisów w ZIP. Archiwum ZIP jest czytane
bez wypakowania ścieżek, ale nie ma niezależnego limitu liczby jego elementów.

Zalecenie: wspólny budżet pikseli dla wszystkich ścieżek, limity wejścia, liczby
stron i załączników, rozpakowanej zawartości oraz czasu CPU. Limity należy
sprawdzać przed kosztownym odczytem/dekodowaniem. Uzupełnić izolacją procesu.

### C. Otwieranie dowolnych plików z listy — potwierdzone ryzyko po dwukliku

`ui/document_list.py:40` i `ui/search_panel.py` przekazują pliki inne niż PDF
bezpośrednio do `QDesktopServices.openUrl()`. W Windows może to uruchomić np.
EXE, skrypt, skrót LNK lub URL. Bezpieczne testy na pustym EXE i atrapach
potwierdziły przekazanie pliku do systemu bez osobnego potwierdzenia.

Wymaga to działania użytkownika na złośliwym pliku. Nie oznacza automatycznego
uruchamiania kodu z treści PDF. Uruchomienie typowego pliku dokumentu może
również otworzyć go w zewnętrznym programie, którego bezpieczeństwo jest odrębne.

Zalecenie: domyślnie blokować formaty wykonywalne, skrypty i skróty zarówno
w liście, jak i wynikach wyszukiwania. Stosować listę dozwolonych formatów,
jasne ostrzeżenie przed zewnętrznym otwarciem i zachować oznaczenie pobrania
z Internetu (Mark-of-the-Web) przy kopiowaniu na Windows.

### D. Poufność lokalnych kopii i indeksu — ryzyko zależne od dostępu do konta

Kopie robocze, zapasowe, odszyfrowane PDF-y, kosz i tekst w SQLite są przechowywane
w danych użytkownika bez własnego szyfrowania. Osoba lub złośliwy program mający
odpowiedni dostęp do konta/pliku może je odczytać. Usunięcie wpisów SQL nie jest
bezpiecznym wymazaniem wszystkich dawnych bajtów z dysku. Nie jest to wykazana
możliwość odczytu przez dowolnego atakującego z Internetu.

Zalecenie: ograniczyć uprawnienia katalogów, wprowadzić kontrolę czasu
przechowywania i bezpieczne zarządzanie cache, rozważyć szyfrowanie kopii
wrażliwych dokumentów, szyfrowanie dysku oraz bezpieczne czyszczenie indeksu.

### E. Zakres Google Drive i kompilacje bez stałych wersji

OAuth korzysta z zakresu obejmującego cały Google Drive. Nie znaleziono w tym
przeglądzie błędu umożliwiającego kradzież tokenu; jest przechowywany przez keyring.
Szeroki zakres zwiększa jednak skutki przejęcia aplikacji lub konta. Rozważyć
węższe uprawnienia, jeśli pozwoli na to sposób wybierania dokumentów.

requirements.txt dopuszcza zakresy wersji zamiast jednej zweryfikowanej kompilacji.
Do publikacji EXE przygotować ustalone wersje i sumy kontrolne, zestawienie
składników oraz ponowny skan każdej kompilacji Windows.

## Zabezpieczenia zauważone w kodzie

- Nie znaleziono mechanizmu uruchamiającego JavaScript PDF ani polecenia systemowe
  zapisane w PDF. Testowy, nieszkodliwy OpenAction/JavaScript został przetworzony bez wywołania
  zewnętrznego programu. Ta pojedyncza próba nie dowodzi bezpieczeństwa parsera.
- Linki otwierane z podglądu PDF są ograniczone do HTTP/HTTPS i wymagają kliknięcia.
  Nadal mogą prowadzić do phishingu; przydatne jest pokazanie docelowej domeny.
- Załączniki nie są automatycznie uruchamiane; zapis wskazuje użytkownik.
- ZIP-y nie są wypakowywane według ścieżek z archiwum. Test z `../` nie zapisał
  niczego poza wybranym wynikiem — nie odtworzono Zip Slip w tej funkcji.
- SQL korzysta z parametrów; zapytanie wyszukiwania nie jest składane jako kod SQL.
- Procesy OCR są uruchamiane bez `shell=True`; ścieżka WIA jest przekazywana przez
  środowisko, a nie wklejana do tekstu PowerShell.
- Pobieranie modeli OCR używa HTTPS, przypiętej wersji i sprawdzania zawartości.
- Korekta LanguageTool wymaga zgody na wysyłanie tekstu do usługi.
- Nie znaleziono ogólnego serwera nasłuchującego dla zdalnego sterowania programem.
  Logowanie Google może na czas autoryzacji uruchamiać lokalny serwer OAuth.

## Ocena sygnałów Bandit

SHA-1 w sprawdzaniu modeli OCR został oznaczony HIGH. Używany jest jako identyfikator
Git blob przypiętej treści, nie do podpisywania użytkowników lub haseł. Model jest
pobierany przez HTTPS i porównywany z istniejącym identyfikatorem. Nie wykazano
praktycznego podstawienia pliku; warto dodać niezależny SHA-256.

Ostrzeżenia urlopen oceniono w kontekście stałych adresów HTTPS. Nie znaleziono
ścieżki, w której autor PDF może podstawić schemat file:// do tych wywołań.
Ostrzeżenia subprocess nie wykazały wstrzyknięcia polecenia przez treść dokumentu.
Puste domyślne hasło PDF oznacza brak hasła, nie ukryte hasło administracyjne.
Wywołanie os.startfile w skojarzeniach Windows używa stałego URI ustawień systemu.

## Co dalej

Najpierw ograniczyć uruchamianie niebezpiecznych formatów i zasoby renderowania,
następnie wdrożyć izolację natywnego parsera, ochronę cache i powtarzalne
kompilacje. Osobno wykonać testy bezpieczeństwa zbudowanego EXE na Windows.
Ten raport nie zmienia kodu aplikacji ani nie usuwa opisanych ryzyk.

Materiały: `dependency_audit.json`, `audited_runtime_versions.txt`,
`static_analysis.json`, `security_test_results.txt`, `test_security_review.py`.
