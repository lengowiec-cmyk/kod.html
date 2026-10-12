# PDFManager 0.8 — wbudowane połączenie i osobny program „matka”

Menu, osiem zakładek, wstążka i kolorystyka PDFManagera pozostają takie jak
w wersji 0.7. Usunięto dedykację z Pomocy → O programie oraz przycisk
„Aktywacja licencji” ze Startu. **Nie ma panelu administratora, zakładki
administratora ani przycisku konfiguracji połączenia w PDFManagerze.**

Pozostają wszystkie funkcje PDF, spedycji, Google Drive, DMS i zabezpieczenia.
Ikony wstążki są renderowane wektorowo na żądanie w rzeczywistej skali ekranu,
a dodatkowe ikony i flagi mają zasoby o zwiększonej rozdzielczości. Qt 6
obsługuje skalowanie Windows 125%, 150%, 200% i większe bez powiększania
niskiej jakości zrzutów ekranowych. Układ interfejsu pozostaje własny.

## Licencja i blokada

Dotychczasowy okres od pierwszego uruchomienia nie został zresetowany.
Zachowano **182 dni, czyli około sześciu miesięcy**, oraz istniejące okresy
starych kodów aktywacyjnych. Po wygaśnięciu pojawia się obowiązkowe okno
wpisania kodu. Sprawdzenie odbywa się przed uruchomieniem GUI/CLI i co minutę
podczas pracy; blokuje również skróty działań, nie tylko przyciski.

Zdalna blokada może wymusić okno kodu wcześniej. Dokumenty nie są usuwane:
pozostają oryginały i mechanizm kopii roboczych/odzyskiwania. Wyjście z okna
kończy aplikację z zachowaniem istniejących mechanizmów odzyskiwania.

Program „matka” wystawia kod `PDMR1...` dla konkretnej instalacji i liczby dni.
Kod można zrealizować w ciągu siedmiu dni od wystawienia. Dostęp jest liczony
od jego użycia. Kod jest jednorazowy na tej instalacji i nie działa na innym
identyfikatorze. Nowe wykorzystania starych kodów również są zapamiętywane,
aby ponowne wpisanie nie resetowało czasu. Stary kod nie obchodzi zdalnej
blokady: w tym przypadku wymagany jest kod z programu „matki”.

Wystawienie nowego kodu nie oznacza automatycznego wysłania go do użytkownika.
Skopiuj go z panelu i przekaż właściwemu pracownikowi uzgodnionym kanałem.
Cofnięcie blokady z panelu nie przedłuża wygasłego okresu dostępu.
Jeżeli okno kodu jest już otwarte, zakończ aplikację i uruchom ją ponownie,
aby pobrała cofnięcie blokady i ponownie sprawdziła dostęp.

## Dwa osobne programy

- `PDFManager.exe`: aplikacja pracownika, bez panelu administratora.
- `PDFManagerAdmin.exe`: program właściciela („matka”), trzymany wyłącznie
  na jego komputerze. Rejestr instalacji, blokowanie, kody i publikacja aktualizacji.
- `PDFManagerUpdater.exe`: techniczny pomocnik zamknięcia i instalacji,
  dołączany do PDFManagera; nie jest panelem administratora.

Uruchomienie ze źródeł:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt -r packaging\requirements-build.txt
python -m pdfmanager.remote.admin_app
```

Budowanie programu „matki”: `packaging\build_admin_windows.bat`.
Wynik: `dist\PDFManagerAdmin.exe` — nie dołączamy go do instalatora pracowników.

## Jednorazowe przygotowanie połączenia przez właściciela

Wymagany jest stały adres HTTPS dostępny dla komputerów pracowników.
Może to być serwer w firmowej sieci, przez VPN albo odpowiednio skonfigurowany
hosting HTTPS. Sam program nie zapewnia domeny, tunelu, publicznego adresu,
przekierowania portów ani działania przy wyłączonym komputerze „matki”.
Nie podano takiego adresu w rozmowie, dlatego nie wpisano fikcyjnego adresu
produkcyjnego ani nie opublikowano prywatnego klucza w repozytorium.

1. Uruchom `PDFManagerAdmin`. Wybierz prywatny katalog administratora poza
   repozytorium, folderem współdzielonym i publicznym katalogiem serwera.
2. Utwórz klucz administratora, podając hasło co najmniej 12 znaków. Klucz
   jest szyfrowany hasłem. Zachowaj jego bezpieczną kopię i hasło.
3. Wpisz właściwy adres HTTPS. Dla firmowej sieci/VPN można użyć certyfikatu
   LAN utworzonego przez program dla tego adresu. Publiczny certyfikat CA
   trafi do konfiguracji klienta, a klucze prywatne pozostaną u właściciela.
   Certyfikaty testowego serwera LAN są ważne rok; zaplanuj ich odnowienie.
4. Wyeksportuj publiczną konfigurację i zapisz ją w źródłach jako
   **`pdfmanager\resources\management.json`**. Jest to klucz publiczny,
   adres serwera i ewentualny publiczny certyfikat CA — bez sekretów.
5. Uruchom `packaging\build_windows.bat`. Konfiguracja zostanie wbudowana
   jednocześnie w GUI, CLI i pomocnika aktualizacji. Pracownik niczego
   nie konfiguruje i nie widzi panelu administratora.
6. Zbuduj instalator Inno Setup z `packaging\installer.iss` i zainstaluj
   tę wersję na komputerach pracowników. Starsze EXE 0.7 nie mają tego modułu:
   najpierw trzeba wdrożyć pierwszą wersję z obsługą połączenia.
7. W programie „matce” uruchom serwer HTTPS i zapewnij dostępność adresu.
   Przy wbudowanym serwerze używaj adresu bez dodatkowej ścieżki, np.
   `https://nazwa-serwera:8443`. Adres musi zgadzać się z certyfikatem.
8. Instalacje zgłoszą pseudonimowy UUID i numer wersji. Odśwież ich listę
   w programie „matce”. Nie jest przesyłana treść PDF, nazwa użytkownika ani
   zawartość Google Drive. Komputer pracownika nie otwiera portu nasłuchującego.

Paczka źródeł nie zawiera Twojej konfiguracji produkcyjnej ani kluczy
prywatnych. Bez osadzenia konfiguracji moduł sieciowy nie wykonuje połączeń.
Konfiguracja jest osadzana w programie, nie zmieniana z menu użytkownika.

## Blokowanie z programu „matki”

Wybierz zgłoszoną instalację, wpisz komunikat i kliknij Zablokuj. Polecenie
ma podpis Ed25519, identyfikator instalacji i rosnący numer. Przy działającym
połączeniu klient pobiera polecenia co minutę oraz przy uruchomieniu.

**Nie da się dostarczyć nowej blokady do odłączonego komputera.** Już odebrana
blokada jest zachowywana lokalnie i działa po restarcie oraz bez internetu.
Brak połączenia nie tworzy nowej blokady i nie kasuje starej. Przy wznowieniu
połączenia obowiązuje najnowsze dostępne, prawidłowo podpisane polecenie.

Wystaw kod na wybraną liczbę dni i przekaż go użytkownikowi. Kolejne jawne
polecenie blokady może ponownie wymusić nowy kod. Zwykłe opublikowanie
aktualizacji nie blokuje ponownie dostępu odblokowanego już kodem.

## Automatyczne aktualizacje

1. Przygotuj nową wersję źródeł. Zmień wersję w `pdfmanager/remote/__init__.py`
   i `packaging/installer.iss`, zachowując tę samą konfigurację połączenia.
2. Zbuduj GUI, CLI, pomocnika i instalator. Przetestuj instalator na Windows.
3. W programie „matce” wybierz instalację, nową wersję i **instalator Inno Setup
   EXE**, nie ZIP źródeł ani sam plik `PDFManager.exe`.
4. Po potwierdzeniu właściciela publikowana jest kopia instalatora i podpisane
   dane: wersja, adres, rozmiar oraz SHA-256.
5. Klient pobiera aktualizację w tle. Nie zamyka nagle edycji i nie usuwa plików.
   Po zwykłym zamknięciu PDFManagera pomocnik czeka na zakończenie procesu,
   ponownie sprawdza podpis i zawartość, uruchamia instalator bez pytań Inno
   Setup, a po powodzeniu uruchamia PDFManager ponownie.

Automatyczna instalacja działa dla spakowanego EXE na Windows. Uruchomienie
ze źródeł/Linux może sprawdzać i pobierać, ale nie uruchamia instalatora EXE.
Aktualizacja nie używa wymuszonego zabijania aplikacji ani dowolnych komend.
Nie instaluje starszych wersji. Instalator musi obsługiwać standardowe
przełączniki Inno Setup i być zgodny z istniejącą instalacją użytkownika.

Nie włączono automatycznej instalacji podczas aktywnej pracy, aby nie
przerywać edycji. Przy wyjściu kopie zostają obsłużone przez istniejący
mechanizm odzyskiwania, zanim zostanie uruchomiony pomocnik.
Wynik pomocnika zapisuje się w katalogu danych jako `update-result.json`.

## Zabezpieczenia i granice

TLS jest sprawdzany, łącznie z nazwą hosta. Nie ma opcji wyłączania kontroli
certyfikatów. Ed25519 sprawdza podpis polecenia; UUID ogranicza odbiorcę,
numery poleceń chronią przed powtórzeniem, a SHA-256 i rozmiar chronią
integralność instalatora. Przekierowania i adres aktualizacji muszą zachować
HTTPS i serwer administratora. Aktualizacja jest weryfikowana ponownie
bezpośrednio przed wykonaniem. Odebrane blokady są przechowywane w dwóch
lokalizacjach poprzez istniejący mechanizm ochrony stanu.

Klucz prywatny pozwala publikować wykonywalny instalator. Chronienie klucza,
hasła i jakości podpisanych wydań jest obowiązkiem właściciela. Podpisany,
ale wadliwy instalator nadal może spowodować problemy. Podpis manifestu nie
zastępuje certyfikatu Windows Code Signing ani pełnego audytu natywnych bibliotek.

Wbudowany serwer jest małym serwerem dla firmowej sieci/VPN. Ogranicza rozmiar
zgłoszenia, liczbę urządzeń i jednoczesne połączenia, ale nie jest kompletną
usługą hostingową odporną na ataki DDoS. Publiczne wdrożenie powinno korzystać
z właściwie utrzymywanego HTTPS i zabezpieczeń sieciowych.

Program Python/PyInstaller działający na cudzym komputerze nie zapewnia
nieusuwalnego DRM. Osoba kontrolująca system może modyfikować program,
usunąć wszystkie kopie stanu lub zablokować sieć. Ta implementacja nie
próbuje ukrywać procesu, omijać zapory, pobierać dokumentów ani wykonywać
niepodpisanych poleceń. Zdalne sterowanie dotyczy tej aplikacji.

## Weryfikacja

`tests/test_remote_08.py`: podpisy, odbiorca, czas, replay, blokada offline,
kody czasowe, jednorazowość, zmieniony instalator, HTTPS i nazwa hosta,
automatyczne zgłoszenie do prawdziwego lokalnego serwera TLS oraz HiDPI.
Testy instalatora używają atrap wykonania; nie uruchamiano złośliwych plików.
`TEST_RESULTS_0.8.txt`: wynik pełnej regresji.
`tools/CHECK_WINDOWS.md`: próby gotowych EXE, dwóch komputerów i aktualizacji.
