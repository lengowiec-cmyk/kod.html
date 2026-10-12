# PDFManager 0.7 — narzędzia dla spedycji

Wersja rozwija 0.6 i zachowuje dotychczasowe narzędzia PDF, DMS, skany,
OCR, wydatki, zabezpieczenia i istniejący mechanizm aktywacji. Katalog
`PDFManager_0.5_poprawki` pozostaje pod dawną nazwą, aby zachować wcześniejsze linki.

## Uruchomienie i budowanie

Na Windows z Pythonem 3.11 lub nowszym:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pdfmanager.main
```

Budowanie EXE: `packaging\build_windows.bat`. Instalator wymaga Inno Setup.
ZIP zawiera źródła, zasoby, testy, instrukcje i podglądy; nie zawiera gotowego EXE.
Tesseract i modele językowe są potrzebne do OCR. Zabezpieczenia Defendera,
DPAPI, Job Object, skanery i instalator wymagają prób na rzeczywistym Windows.

## Centrum spedycji

Otwórz **Spedycja** na wstążce Organizuj lub Edytor PDF, albo **Ctrl+Shift+T**.
Pięć zakładek obejmuje wszystkie nowe działania.

### Stemple i teksty

Gotowe oznaczenia: ZATWIERDZONO, DO POPRAWY, OPŁACONO, BRAK PODPISU,
DOKUMENT KOMPLETNY, POD PODPIS, OTRZYMANO, KOPIA i POD POTWIERDZONY.
Dodawaj, edytuj i usuwaj własne wzory. Bloki tekstu zawierają przykładowe
prośby o potwierdzenie, uzupełnienie podpisów i przesłanie CMR/POD.

Wypełnij pracownika, numer zlecenia i kontrahenta. Pola `{data}`, `{godzina}`,
`{pracownik}`, `{zlecenie}`, `{kontrahent}` zostają zastąpione wartościami.
Opcjonalnie dodaj datę, godzinę i pracownika do stempla. Profile CMR, POD,
zlecenia i faktury zapisują pozycję, rozmiar pola, rozmiar czcionki, kolor
oraz własny plik TTF/OTF. Domyślna DejaVu Sans obsługuje polskie znaki.
Profile można dodawać. Pozycje są w punktach PDF (72 punkty = 1 cal),
liczone od lewego górnego rogu. Profil nie rozpoznaje automatycznie układu
każdego formularza: ustaw i sprawdź miejsce dla dokumentów swojej firmy.

**Podgląd** nie zmienia dokumentu. **Wstaw** dodaje tekst do bieżącej strony
w kopii roboczej, z obsługą Cofnij/Ponów. Przepełnione pole lub pozycja poza
stroną są odrzucane. Przycisk obrazu/logo włącza wstawianie graficznej
pieczątki: przeciągnij jej obszar na stronie. Wybieraj własne grafiki.
Pieczątka, nazwa pracownika i obraz podpisu nie są podpisem cyfrowym.

### Teczki zleceń

Wskaż istniejący katalog, wpisz numer zlecenia i kontrahenta, utwórz teczkę.
Powstaną foldery Zlecenie, CMR, POD, Faktury i Korespondencja.
Istniejąca teczka nie zostaje nadpisana. W każdej teczce zapisywana jest
jawna lista kontrolna `zlecenie.pdfmanager.json`, przeznaczona do współdzielenia
razem z dokumentami. Nie umieszczaj w niej haseł ani innych sekretów.

Dołącz PDF do odpowiedniego folderu i **ręcznie potwierdź** podpisany CMR,
POD i fakturę po sprawdzeniu treści. Samo dołączenie pliku nie potwierdza
jego kompletności. Przycisk przeglądu braków sprawdza teczki bezpośrednio
w wybranym katalogu. Lista kontrolna nie jest systemem wieloosobowych
transakcji: wspólne aktualizacje listy należy uzgodnić w zespole.

**Automatyczna nazwa** tworzy lokalną kopię, np.
`2026-10-12_ZL-1542_CMR_Transport Alfa.pdf`. Niedozwolone znaki Windows są
usuwane lub zastępowane, nazwy zarezerwowane są odrzucane.
Podpowiedź numeru zlecenia korzysta z tekstu PDF, a przy jego braku z OCR
`pol+eng`. To prosty wzorzec rozpoznawania: użytkownik sprawdza wynik.
Nie jest to automatyczne rozpoznawanie wszystkich danych z każdego CMR.

### Pakiety i operacje zbiorcze

Dodaj PDF-y i ustaw kolejność przeciąganiem. Pakiet zawiera stronę tytułową,
listę dokumentów, zakładki oraz numerację stron. Źródła pozostają bez zmian.

Operacje listy: stempel/tekst na wszystkich stronach, numeracja, obrót
90/180/270 stopni, kompresja bez rasteryzacji i kopie z nowymi nazwami.
Wyniki trafiają do nowego, osobnego folderu; raport wskazuje powodzenia
oraz błędy poszczególnych plików. Kompresja może nie zmniejszyć już
zoptymalizowanego pliku. Nie zmienia jakości skanów przez ich ponowne skalowanie.

Porównanie dwóch pierwszych PDF-ów tworzy raport: oryginał, nowa wersja,
czerwone zaznaczenie różnic i procent zmienionych pikseli. Porównanie
jest wizualne przy 72 DPI; nie potwierdza prawnej ani semantycznej równoważności.

Trwała redakcja włącza istniejące narzędzie usuwania treści w zaznaczonym
obszarze. Sprawdź wynik przez podgląd i eksport tekstu. Oryginały, kopie
zapasowe, historia Drive i wcześniejsze wysłane dokumenty nadal mogą
zawierać dane. Udostępniaj sprawdzony dokument po redakcji.

### Google Drive — zespół

**Funkcje zespołowe wymagają połączenia przez Google Drive API** z menu Plik.
Wymagane są własna konfiguracja OAuth typu Desktop i uprawnienia do folderów.
Wszyscy pracownicy powinni używać tej samej aplikacji OAuth, aby widzieli
prywatne właściwości rezerwacji i historii PDFManagera. Program nie zawiera
cudzych tokenów ani poświadczeń. W tym środowisku testy używały atrap API;
nie wysyłano rzeczywistych dokumentów firmowych.

Folder Google Drive Desktop jest nadal obsługiwany jak folder lokalny.
Zapis lokalny **nie potwierdza synchronizacji** i nie daje rezerwacji API.
Stan synchronizacji sprawdzaj w aplikacji Google Drive Desktop.

Rezerwacja pokazuje pracownika i wygasa po 15 minutach. Można ją zwolnić
lub odnowić. Program odnawia zapamiętane rezerwacje przy otwartym dokumencie
API Drive i działającym połączeniu. Po zamknięciu programu wygasają.
To **ostrzeżenie doradcze**, nie atomowa blokada serwerowa. Inne programy,
inny klient OAuth i równoczesne żądania mogą je ominąć. Z tego powodu zapis
nie polega na rezerwacji jako jedynym zabezpieczeniu.

**Ctrl+S / Zapisz na Drive** tworzy zaszyfrowaną lokalną migawkę w kolejce.
Stan „Oczekuje na wysłanie” nie oznacza jeszcze zapisu w chmurze. Do pierwszego
ustalenia konta potrzebny jest internet; potem podczas bieżącej sesji
można kolejkować także offline. Kolejka jest przypisana do potwierdzonego
konta: inne konto nie wyśle tych dokumentów.

Przed wysłaniem program porównuje sumę kontrolną lub datę zmiany oryginału
z metadanymi z chwili otwarcia. Konflikt zatrzymuje wpis i zachowuje kopię.
Każdy udany zapis tworzy **osobny plik wersji w folderze oryginału** — nigdy
nie zastępuje oryginału. Ta strategia chroni przed utratą cudzych zmian
również w krótkim wyścigu dwóch zapisów. Pracownicy muszą wybierać aktualną
wersję świadomie; nie ma automatycznego scalania zmian dwóch dokumentów.

„Wyślij / ponów” uruchamia kolejkę. Domyślnie aplikacja ponawia ją co minutę,
gdy jest otwarty dokument API Drive i znane konto. Można to wyłączyć.
Stały pasek pokazuje liczbę oczekujących wpisów i konfliktów. Błędy nie
kasują dokumentu. Wpis konfliktowy nie jest automatycznie ponawiany:
zachowaj lokalną kopię, porównaj wersje, otwórz aktualny dokument i przygotuj
nowy zapis. Kontrola identyfikatora zadania ogranicza duplikaty po zerwaniu
odpowiedzi HTTP; nie jest gwarancją transakcji rozproszonej ani dokładnie
jednego wysłania w każdej awarii usługi.

Historia pokazuje pliki wersji PDFManagera, pracownika oraz czas. Możesz
pobrać wcześniejszą wersję jako nową lokalną kopię, sprawdzić ją i użyć jako
podstawy kolejnej wersji. Osobna historia oryginału korzysta z rewizji Google;
ich dostępność zależy od retencji i uprawnień Google Drive. Nie usuwamy
ani nie zastępujemy istniejących wersji w chmurze.

### Ulubione i skróty

Wybierz narzędzia do własnego paska: centrum spedycji, zapis i następny,
kolejka i wysyłanie. Ostatnie foldery są zapamiętywane.

- Ctrl+Shift+T: centrum spedycji.
- Ctrl+Alt+N: zapisz i otwórz następny PDF w bieżącym folderze alfabetycznie; dla API Drive zachowuje połączenie kolejnego dokumentu z chmurą.
- Ctrl+S: zapis lokalny po potwierdzeniu albo migawka do kolejki API Drive.
- Ctrl+Shift+S: dotychczasowe Zapisz jako.

Anulowany lub nieudany zapis nie przechodzi do następnego pliku. Przy Drive
przejście oznacza trwałe zapisanie lokalnej kolejki, nie potwierdzone wysłanie.

## Dowody i ograniczenia

Wyniki: `TEST_RESULTS_0.7.txt`. Nowe testy: `tests/test_transport_07.py`.
Podglądy rzeczywistej aplikacji: `previews_0.7/`.
Przewodnik: `docs/PDFManager_0.7_spedycja.pdf`.
Zabezpieczenia 0.6 pozostają aktywne: `BEZPIECZENSTWO_0.6.md`.
Oddzielne procesy PDF nie są pełnym AppContainer; nie deklarujemy całkowitej
odporności na złośliwe dokumenty. Nowy interfejs i wzory są własną implementacją.
