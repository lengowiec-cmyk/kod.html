# Zabezpieczenia wersji 0.6

## Wdrożone zmiany

- Otwieranie, renderowanie, odczyt tekstu i operacje PDF wykonywane przez
  interfejs/CLI przekierowano do osobnych procesów. Transport jest oparty na
  JSON i jawnej liście operacji; nie używa pickle, eval ani dowolnych poleceń.
- Procesy mają limit pamięci 2 GiB, limit CPU 240 s i limit czasu ściennego
  300 s. Linux używa resource, Windows — Job Object z zakończeniem potomków.
  Przy braku możliwości ustawienia limitów Windows operacja jest odrzucana.
- Wejście: maksymalnie 256 MB, 5000 stron; raster: 20 mln pikseli. Limity są
  sprawdzane przed alokacją w OCR, eksporcie, transformacjach i innych rasterach.
  PNG zwracany przez proces PDF jest sprawdzany przed dekodowaniem w GUI.
- Archiwa mają limit liczby wpisów, rozpakowanej zawartości i podejrzanego
  stopnia kompresji. Ścieżki archiwum nie są wypakowywane na dysk.
- Załączniki mają limit odczytu 50 MB, transport danych limit porcji 32 MB
  i odpowiedzi 64 MB; formularze limit 1000 pól, linki limit liczby wpisów.
- EXE, skrypty, skróty i formaty spoza listy dozwolonych są blokowane w listach
  plików i wynikach wyszukiwania. Pozostałe zewnętrzne otwarcia wymagają potwierdzenia.
- Linki z PDF wymagają potwierdzenia; akceptowane są tylko poprawne HTTP/HTTPS
  bez danych logowania w URL. Wyświetlany jest zakodowany adres do sprawdzenia.
- Kopiowanie na Windows próbuje zachować oznaczenie Zone.Identifier.
- Indeks i dane wydatków: AES-256-GCM. Nowe kopie zapasowe, kosz i kopie robocze
  po zamknięciu również są szyfrowane. Zmieniony szyfrogram jest odrzucany bez
  zapisania niezweryfikowanego PDF-a wynikowego.
- Windows chroni klucz przez DPAPI użytkownika. W Linux klucz znajduje się
  w prywatnym pliku 0600 wewnątrz katalogu 0700. Linuxowy klucz nie jest
  chroniony przez DPAPI i nie zabezpiecza przed przejęciem tego samego konta.
- Ustawienia pozwalają zabezpieczyć starsze lokalne kopie. Bieżące sesje są pomijane.
- W Windows można włączyć sprawdzanie plików przez Microsoft Defender; domyślnie
  jest aktywne. Niezgodny wynik lub brak narzędzia blokuje przetwarzanie. Dla
  innego antywirusa można świadomie wyłączyć tę integrację w ustawieniach.
  Skan jest bez automatycznej remediacji; nie zapewnia wykrycia każdego malware.
- Modele OCR mają przypięty commit, HTTPS i sprawdzanie SHA-256.
- Ustalono dokładne wersje zależności bezpośrednich i narzędzia PyInstaller.
  Eksport CSV neutralizuje początkowe znaki formuł w danych wydatków.

## Granice ochrony

**To nie jest pełny AppContainer ani antywirus.** Oddzielny proces i Job Object
ograniczają awarie oraz zasoby, ale nie odbierają wszystkich uprawnień konta,
dostępu do plików ani sieci. Potencjalny exploit natywnego silnika w takim
procesie nadal może mieć skutki dla danych użytkownika. Nie deklarujemy pełnej
odporności na nieznane lub specjalnie przygotowane PDF-y.

Aktywna kopia podczas edycji jest jawnym PDF-em w prywatnym katalogu. Awaria
przed zamknięciem może pozostawić taką kopię. Odzyskiwanie działa również dla
starszych jawnych kopii; migracja danych umożliwia ich późniejsze szyfrowanie.
Starsze pliki nie są automatycznie usuwane z powodu aktualizacji. Klucza i profilu
Windows nie należy utracić — zaszyfrowane kopie mogą wtedy być nieodczytywalne.

Wymagane pozostają aktualizacje Windows, bibliotek, skanera i antywirusa,
używanie zwykłego konta oraz ostrożność przy plikach z nieznanych źródeł.
Skan pakietów nie obejmuje pełnego audytu wszystkich natywnych kodeków.
Nie wykonano testów fizycznego sprzętu i zabezpieczeń Windows w tym środowisku.

## Dowody

`TEST_RESULTS_0.6.txt`: bieżące testy funkcjonalne, granic i ochrony danych.
`security/dependency_audit_0.6.json`: skan 58 zainstalowanych pakietów runtime
na Linux, bez znanych podatności w bazie PyPI podczas tego przebiegu.
`security/audited_runtime_0.6_linux.txt`: sprawdzone wersje, nie pełny lock Windows.
Starszy raport 0.5 w katalogu security dotyczy stanu sprzed tych zmian.
