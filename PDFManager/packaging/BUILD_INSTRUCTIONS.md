# Budowanie, podpisywanie i zgłaszanie fałszywych alarmów Defender

Ten plik dotyczy wyłącznie problemu "SmartScreen/Windows Defender ostrzega
albo blokuje mój (czysty) plik PDFManager.exe". Nie dotyczy licencji
zależności — to opisuje `LICENSING.md`.

## Dlaczego to się dzieje

Pliki `.exe` zbudowane przez PyInstaller są częstym celem fałszywych alarmów
antywirusowych z dwóch niezwiązanych ze sobą powodów:
1. **Brak reputacji** — SmartScreen ocenia pliki m.in. na podstawie tego, jak
   szeroko są rozpowszechnione i podpisane. Nowy, niepodpisany plik od
   nieznanego wydawcy startuje z zerową reputacją.
2. **Heurystyka pakera** — sposób, w jaki PyInstaller pakuje interpreter
   Pythona i biblioteki w jeden plik, przypomina techniki używane też przez
   złośliwe oprogramowanie do pakowania swojego kodu, więc silniki
   heurystyczne czasem reagują na samo to, jak plik jest zbudowany, nie na
   jego rzeczywistą zawartość.

Żadnego z tych problemów nie rozwiązuje się przez wyłączanie antywirusa u
klienta — to tylko usuwa ochronę, nie usuwa przyczyny ostrzeżenia, i dlatego
w tym projekcie nie ma takiego skryptu (patrz niżej "Czego świadomie nie
zrobiliśmy").

## Rozwiązanie trwałe: prawdziwy podpis Code Signing

1. Zdobądź certyfikat Code Signing z uznanego źródła:
   - **Microsoft Trusted Signing** — abonament, tani, bez sprzętowego tokenu
     EV, zaprojektowany dokładnie dla niezależnych deweloperów:
     https://learn.microsoft.com/en-us/azure/trusted-signing/
   - Albo certyfikat OV/EV Code Signing od uznanego CA (DigiCert, Sectigo,
     SSL.com itd.).
2. Po otrzymaniu certyfikatu podpisz zbudowany plik. W `build_windows.bat`
   jest gotowe, zakomentowane miejsce na wywołanie `signtool` — wystarczy
   uzupełnić ścieżkę do certyfikatu i odkomentować tę sekcję.
3. Podpisany, rozpowszechniany plik stopniowo buduje reputację w
   SmartScreen — im więcej osób go pobiera i uruchamia bez zgłaszania
   problemu, tym mniej ostrzeżeń.

## Rozwiązanie na już: zgłoszenie fałszywego alarmu do Microsoft

Jeśli Defender/SmartScreen już teraz blokuje albo oznacza zbudowany plik
jako złośliwy, a masz pewność, że jest czysty:

1. Wejdź na https://www.microsoft.com/en-us/wdsi/filesubmission
   (Microsoft Security Intelligence — zgłaszanie plików).
2. Zaloguj się kontem Microsoft.
3. Wybierz typ zgłoszenia **"Software developer"** (nie "Home user") — to
   przyspiesza i ułatwia rozpatrzenie.
4. Wgraj plik `dist\PDFManager\PDFManager.exe` (ten, który faktycznie
   trafia do klientów).
5. W opisie podaj: że to legalna aplikacja desktopowa w Pythonie spakowana
   PyInstallerem, nazwę wykrycia zgłoszoną przez Defender (jeśli jest), oraz
   link do tego repozytorium/projektu, jeśli jest publiczny.
6. Status zgłoszenia możesz sprawdzić na tej samej stronie (zakładka
   historii zgłoszeń). Analiza trwa zwykle od kilkunastu godzin do kilku dni.
7. Po zatwierdzeniu fałszywego alarmu Microsoft aktualizuje definicje
   Defender globalnie — rozwiązuje to problem u WSZYSTKICH użytkowników,
   nie tylko lokalnie, w przeciwieństwie do wyłączenia antywirusa.

Warto zgłaszać ponownie po każdej istotnej zmianie w sposobie budowania
pliku (np. zmiana wersji PyInstaller) — nowy układ binarny może ponownie
trafić w inną heurystykę.

## Lokalne testy deweloperskie

Do podpisania zbudowanego pliku WYŁĄCZNIE na własnym komputerze w trakcie
pracy nad projektem (żeby zobaczyć, jak zachowuje się podpisany plik, bez
czekania na prawdziwy certyfikat) służy `packaging\setup_dev_cert.ps1`.
Tworzy certyfikat testowy i dodaje go tylko do magazynu wydawców bieżącego
użytkownika (`Cert:\CurrentUser\TrustedPublisher`) — nie wymaga uprawnień
administratora, nie dotyka Root CA, nie zmienia ustawień Windows Defender.
To NIE rozwiązuje SmartScreen/Defender u klientów — tylko ułatwia lokalne
testowanie podpisanego pliku.

## Czego świadomie nie zrobiliśmy

Nie dodaliśmy skryptu instalacyjnego, który importowałby certyfikat do
`Cert:\LocalMachine\Root` i/lub automatycznie dodawał wykluczenia Windows
Defender dla pliku `.exe`. Ta kombinacja (zaufanie na poziomie całego
systemu + automatyczne wyłączenie skanowania) jest typowym wzorcem
używanym przez instalatory złośliwego oprogramowania do maskowania swojej
obecności — niezależnie od intencji, nie jest to coś, co powinno się
dystrybuować klientom jako normalny krok instalacji. Powyższe dwie metody
(prawdziwy podpis + zgłoszenie fałszywego alarmu) rozwiązują ten sam
problem użytkownika bez obniżania jego bezpieczeństwa.
