# PDFManager 0.9 — gotowa paczka firmowa i bezpieczny kanał Google Drive

PDFManager pracownika zachowuje dotychczasowe menu, osiem zakładek, wygląd,
edycję PDF, narzędzia spedycyjne i pozostałe funkcje. Nie ma w nim panelu
administratora ani formularza parowania. Osobny PDFManagerAdmin („matka”)
przygotowuje połączenie **przed przekazaniem programu pracownikom**.

## Przygotowanie na Windows przez właściciela

1. Zbuduj aplikację i pomocnika: `packaging\build_windows.bat`.
   Najpierw: `python -m pip install --upgrade pip==26.2.0`.
   Zależności: `python -m pip install -r requirements.txt -r packaging\requirements-build.txt`.
   Zbuduj program właściciela: `packaging\build_admin_windows.bat`.
2. Uruchom `dist\PDFManagerAdmin.exe`. Kliknij „1. Połącz z firmowym folderem
   Google Drive” i wskaż istniejący folder dostępny pracownikom. Zalecany jest
   **osobny folder współdzielony przeznaczony tylko do połączenia**, poza
   katalogami z umowami, CMR i fakturami. Program utworzy wewnątrz własny
   podfolder `PDFManager-Polaczenie-…`.
3. Kliknij „2. Przygotuj gotową paczkę PDFManager dla pracowników”. Wskaż cały
   zbudowany folder `dist\PDFManager` i nową nazwę ZIP. Paczka zawiera pełną
   aplikację, zależności, pomocnika i podpisane dane połączenia. Klucza
   prywatnego nie otrzymują pracownicy. Nie potrzeba ponownej kompilacji dla
   tego parowania.
4. Przekaż pracownikowi ZIP przez zaufany kanał. Pracownik rozpakowuje całość
   na lokalnym dysku, poza folderem współdzielonym i katalogami z dokumentami,
   i uruchamia `PDFManager\PDFManager.exe`. Google Drive Desktop musi już
   zapewniać dostęp i synchronizację tego samego firmowego folderu. Program
   wyszukuje kanał także po zmianie litery dysku i w rozpoznanych lokalizacjach
   Google Drive; przy niedostępnym folderze czeka na kolejne sprawdzenie.
5. Uruchom „matkę”, aby odebrała pierwsze zgłoszenia komputerów. Zmień ich
   lokalne opisy na nazwy stanowisk lub pracowników. Następnie można wystawić
   blokadę, cofnąć ją, utworzyć kod czasowy albo wysłać aktualizację.

**Paczka firmowa jest przenośną aplikacją, a nie instalatorem.** Należy zachować
cały rozpakowany folder. Źródłowy ZIP z GitHuba również nie jest instalatorem;
pliki Windows EXE trzeba zbudować na Windows. Nie publikuj firmowej paczki
ani prywatnego katalogu właściciela w publicznym repozytorium.

Normalne połączenie Drive nie wymaga serwera, domeny, portów, certyfikatów TLS
ani kodu parowania u pracownika. Nie może natomiast samo przyznać dostępu do
cudzego Dysku Google ani włączyć synchronizacji na innym komputerze. Dostęp
pracowników do folderu musi zostać zapewniony w Google Drive. Opcjonalny
wcześniejszy tryb HTTPS pozostaje w ustawieniach zaawansowanych.

## Dokumenty i synchronizacja

Kanał sterujący zapisuje tylko własny znacznik, zgłoszenia instalacji,
podpisane polecenia oraz kopie wskazanych instalatorów w swoim podfolderze.
Nie skanuje zawartości dokumentów firmy, nie usuwa ich i nie wysyła ich
programowi właściciela. Przekazuje anonimowy UUID instalacji, wersję programu
oraz czas zgłoszenia. Dotychczasowe funkcje otwierania, edycji i zapisywania
PDF nadal działają na dokumentach wybranych przez użytkownika.

Blokada obejmuje dostęp do PDFManagera, nie Dysk Google ani pliki. Nie jest
mechanizmem cofnięcia dostępu do dokumentów: takie uprawnienia zarządza się
oddzielnie w Google Workspace. Niedostępność Drive nie usuwa istniejącej
blokady, nie resetuje identyfikatora ani okresu dostępu. Pierwotny okres
pozostaje 182 dni od pierwszego uruchomienia; po wygaśnięciu wymagany jest kod.

Klient sprawdza polecenia przy uruchomieniu i co około minutę. Dotarcie
polecenia wymaga synchronizacji Drive i działającego połączenia komputera.
Nie można zdalnie natychmiast zablokować komputera offline. „Matka” po
opublikowaniu polecenia może zostać zamknięta, ale Google Drive musi najpierw
przesłać pliki. Nie wysyła automatycznie kodu pracownikowi — kod przekazuje
właściciel uzgodnionym kanałem.

## Zabezpieczenia

- Podpisy Ed25519: polecenia, konfiguracja firmowej paczki i znacznik kanału.
  Polecenie jest związane z konkretną instalacją i ma termin ważności.
- Monotoniczna kolejność poleceń uniemożliwia cofnięcie blokady przez
  ponowne podstawienie starszego polecenia. Lokalny stan zachowuje się po
  ponownym uruchomieniu; kody czasowe są jednorazowe dla danej instalacji.
- Właściciel po pierwszym uruchomieniu jest przypięty w lokalnej,
  uwierzytelnionej konfiguracji AES-GCM. Jej klucz oraz automatyczne
  odblokowanie klucza właściciela chroni na Windows DPAPI danego konta.
  Klucz prywatny właściciela pozostaje w lokalnym katalogu aplikacji.
- Kanał dopuszcza tylko ustalone ścieżki. Odsyłacze, dowiązania symboliczne
  i junctions w jego katalogach są odrzucane. Są limity rozmiarów zgłoszeń,
  poleceń, liczby rejestrowanych komputerów i wyszukiwania katalogu.
- Aktualizacja wymaga poprawnego podpisu, właściwego kanału, nowszej wersji,
  rozmiaru i SHA-256. Pomocnik ponownie weryfikuje plik po zamknięciu GUI.
  Przed uruchomieniem aktualizacji na Windows obowiązkowo wywołuje Defendera
  bez automatycznej naprawy plików. Nieudany lub niedostępny skan wstrzymuje
  aktualizację. Wyłączenie opcjonalnego skanowania dokumentów nie wyłącza
  tego sprawdzenia aktualizacji.
- Instalator uruchamiany jest po bezpiecznym zamknięciu GUI, bez poleceń
  powłoki i bez dowolnych zdalnych skryptów. Dotychczasowe ograniczenia PDF,
  osobne procesy robocze oraz szyfrowanie lokalnych kopii pozostają.
- Pakowanie odrzuca znane prywatne pliki, prywatne PEM, certyfikaty PFX/P12,
  odsyłacze i starszy build bez obsługi gotowego połączenia.

## Granice ochrony

To zabezpieczenia aplikacyjne, a nie gwarancja odporności na każdy atak.
Pierwsza firmowa paczka musi pochodzić od właściciela: samopodpisanie nie
uwierzytelnia nieznanego nadawcy. Osoba z prawem zapisu do kanału Drive może
usunąć pliki lub zakłócić synchronizację; bez klucza prywatnego nie podpisze
ważnego polecenia. Przydziel uprawnienia tylko odpowiednim kontom i włącz
uwierzytelnianie dwuskładnikowe Google.

DPAPI nie chroni przed złośliwym procesem działającym jako zalogowany
właściciel ani przed przejęciem jego komputera. Komputer właściciela powinien
mieć BitLocker, aktualny system i ochronę antywirusową. Trzeba zachować
bezpieczną kopię katalogu prywatnego oraz możliwość odzyskania profilu
Windows/kluczy DPAPI — kopiowanie samego katalogu na inne konto nie gwarantuje
odblokowania klucza.

Podpis potwierdza, kto zatwierdził instalator, ale nie dowodzi, że jest on
pozbawiony błędów. Publikuj wyłącznie własne, sprawdzone instalatory Inno
Setup. Instalator jest kodem wykonywalnym i ma uprawnienia zalogowanego
użytkownika; nie jest odizolowany od dokumentów. Zalecany jest także rzeczywisty
podpis Authenticode, którego ta wersja automatycznie nie zapewnia.

Parser PDF i Defender nie wykrywają każdego nieznanego zagrożenia. Procesy
PDF mają limity i odrębny cykl życia, ale nie są pełnym sandboxem Windows
AppContainer. Audyt pakietów Python uzupełnia te testy, ale nie obejmuje wszystkich
podatności systemu Windows ani bibliotek natywnych. Utrzymuj aktualne zależności.
Nadal potrzebne są kopie zapasowe
ważnych dokumentów; synchronizacja Drive nie zastępuje niezależnego backupu.

## Weryfikacja

[Rzeczywiste okno programu właściciela](previews_0.9/01_program_wlasciciela.png).

Testy kanału wykorzystują wyłącznie lokalne, syntetyczne pliki. Sprawdzają
rejestrację, blokadę, kod, cofnięcie blokady, pobieranie aktualizacji,
podmianę podpisów i plików, odmowę wykonania po nieudanym skanowaniu,
przekierowane foldery, niezmienione dokumenty, przechowanie parowania,
zmianę montowania Drive oraz kompletność paczki i wykluczenie kluczy.

Wyniki: [TEST_RESULTS_0.9.txt](TEST_RESULTS_0.9.txt).
Audyt 91 zainstalowanych pakietów Python po poprawkach: zero zgłoszonych
znanych luk, zero pominiętych pakietów. Zaktualizowano `pip` do 26.2
i `pytest` do 9.0.3. [Raport audytu](SECURITY_AUDIT_0.9.json).
Nie przetestowano prawdziwej synchronizacji Google Drive Desktop, skanowania
Defendera ani instalatora EXE na Windows w tym środowisku Linux. Przed
wdrożeniem wykonaj próbę na testowym koncie Windows i osobnym folderze Drive.
