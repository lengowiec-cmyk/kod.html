# PDFManager 0.5 — dodatki do codziennej pracy

## Najważniejsza zmiana: zapis

Dokument otwarty w głównym oknie jest teraz edytowany w osobnej kopii roboczej.
Oryginał nie zmienia się przy edycji, redakcji, operacjach na stronach ani Cofnij.
Gwiazdka na karcie oznacza zmiany w kopii roboczej. **Zapisz / Ctrl+S** pyta o zapis
w pliku źródłowym i wcześniej tworzy kopię zapasową. **Zapisz jako** wybiera nowy
plik i przełącza miejsce kolejnych zapisów. Zmiana oryginału przez inny program
lub jego usunięcie blokuje zwykły zapis: wybierz wtedy Zapisz jako.

**Plik → Odzyskaj dokument** pokazuje niezapisane kopie z poprzednich sesji.
Zamknięcie karty/programu pozostawia niezapisane kopie do odzyskania; odzyskany
plik trzeba zapisać przez Zapisz jako. **Plik → Kopie zapasowe** pozwala otworzyć
poprzednią zapisaną wersję. Kopie robocze i zapasowe są w danych lokalnych
użytkownika Windows, nie w katalogu instalacyjnym. Pliki te zajmują miejsce i
mogą zawierać odszyfrowane dokumenty; mają uprawnienia zwykłych danych konta.
Folder kopii zapasowych ma teraz retencję: maksymalnie 5 ostatnich kopii na
plik źródłowy oraz łączny limit 2 GiB (najstarsze kopie są usuwane
automatycznie przy kolejnym zapisie) — wcześniej rósł bez ograniczeń.

Otwarcie dokumentu większego niż 8 MB tworzy kopię roboczą (kopiowanie +
SHA-256 całej treści) w tle, z oknem postępu i możliwością anulowania —
zamiast blokować interfejs bez żadnej informacji, co było odczuwalne
zwłaszcza dla szafek DMS na udziale sieciowym. Mniejsze pliki wciąż otwierają
się synchronicznie (bez migania oknem postępu).

CLI nadal pracuje na ścieżkach podanych przez użytkownika i nie tworzy sesji
GUI. Zawsze dobieraj osobną ścieżkę wynikową do poleceń CLI.

## Edycja

- **Panel czcionek** na wstążce Edytor PDF: otwórz panel, wybierz narzędzie
  edycji tekstu i kliknij fragment strony. Zmień tekst, rozmiar, kolor, styl lub
  plik TTF/OTF, następnie zatwierdź. Dla własnego pliku czcionki styl pochodzi
  z wybranego pliku (np. wariantu Bold), a nie ze sztucznego pogrubienia. Przy ukrytym panelu działa osobny dialog.
- **Wstaw tekst / obraz**, **Ctrl+V**: opcja umieszczenia myszą jest domyślna.
  Zatwierdź zawartość, następnie przeciągnij pole na stronie. Podczas przeciągania
  widoczny jest obrys. Można także wyłączyć opcję i podać współrzędne.
- **Przesuń dodany element**: przeciągnij od wnętrza elementu do nowej pozycji.
- **Skaluj dodany element**: zacznij wewnątrz elementu i przeciągnij w kierunku
  docelowego prawego dolnego narożnika. Skalowanie zachowuje proporcje.
- Przesuwanie i skalowanie obejmuje tekst/obrazy wstawione modułem tej wersji.
  Nie obejmuje dowolnych starych obiektów PDF, wcześniejszych pieczątek ani
  elementów utworzonych przed wersją 0.5. Identyfikatory są zapisane w PDF i
  zachowane po ponownym otwarciu. Edycja treści elementu może usunąć jego
  identyfikator; wtedy wstaw go ponownie. Spłaszczanie i eksport do innych
  programów również może usuwać te informacje.
- Cofnij/Ponów działa osobno na kartach: maksymalnie 20 stanów. Budżet 64 MiB
  ogranicza przechowywane starsze stany; dla dużego pojedynczego stanu zostaje
  jedna kopia. Historia cofania nie jest przechowywana między sesjami.
- Podgląd ma limit 20 milionów pikseli / 16384 pikseli na bok. Bardzo duża strona
  może być wyświetlana przy mniejszej rzeczywistej skali niż zadany procent,
  aby ograniczyć zużycie pamięci. Wydruk/eksport nie jest testem jakości podglądu.

## Pliki i wyszukiwanie

- Prawy przycisk na liście plików → **Przenieś do kosza PDFManager**.
  To kosz aplikacji, nie kosz Windows. **Organizuj → Kosz** przywraca plik.
  Jeśli nazwa jest zajęta, wybierz nową; istniejący plik nie jest nadpisywany.
- **Narzędzia → Szafki i skanowanie → Dodaj do ulubionych** zapisuje szafkę.
  **Ulubione szafki** na wstążce przywraca wybraną lokalizację.
- **Ostatnie dokumenty** oraz ostatni folder, geometria okna, strona, powiększenie
  i tryb widoku są zapamiętywane lokalnie.
- Wyszukiwanie treści zapisuje tekst stron w lokalnym indeksie SQLite. Zmieniony
  PDF jest indeksowany ponownie; niezmieniony nie jest ponownie odczytywany.
  Nie istniejące pliki nie trafiają do wyników. **Wyczyść indeks PDF** usuwa
  przechowywany tekst; kolejny pełnotekstowy przebieg odbuduje indeks.
- Postęp i **Anuluj** działają dla wyszukiwania, OCR oraz etapów operacji wsadowych.
  Anulowanie jest współpracujące: nie przerywa atomowego zapisu w połowie,
  część operacji kończy bieżący krok. Ukończone wyniki wsadowe pozostają na dysku.

## Skanowanie i automatyczny import

1. W Skrzynce otwórz **Ustawienia importu skanów**. Wybierz folder skanera i osobny
   katalog PDF poza nim. Reguła nazwy obsługuje `{date}`, `{time}`, `{source}`,
   `{counter}`, np. `{date}_{source}_{counter}`. Zajęta nazwa otrzyma unikalny sufiks.
2. Opcjonalnie włącz OCR i wybierz pol/eng/ukr. Wymagany jest zainstalowany
   Tesseract oraz model językowy. Pobieranie modeli jest dostępne w narzędziach OCR.
3. **Włącz / wyłącz obserwowanie**: sprawdza katalog co 3 sekundy i czeka, aż
   rozmiar/data pliku będą stabilne przez kolejne przebiegi. Importuje każdy plik
   jako osobny PDF; wielostronicowy TIFF jako jeden wielostronicowy dokument.
4. SHA-256 zawartości zapobiega ponownemu importowi identycznego skanu do tego
   samego katalogu. Jeśli wynik usunięto, plik można ponownie zaimportować.
   Oryginały pozostają w folderze skanera. Błędy są w pasku stanu i dzienniku.
   Po poprawieniu konfiguracji zapisz ją ponownie, aby ponowić błędne pliki.
5. Konfiguracja jest trwała, lecz obserwowanie trzeba świadomie włączyć po
   każdym uruchomieniu. Przy zamykaniu aplikacja anuluje pracę obserwatora.
6. **Skanuj WIA** wywołuje okno urządzenia Windows i po pobraniu obrazu zapisuje PDF.
   Ten tryb pobiera pojedynczy obraz w jednym wywołaniu. Nie implementuje własnej
   pętli podajnika ADF/dupleksu. Wielostronicowe dokumenty można importować z TIFF/PDF.
7. **Aplikacja skanera TWAIN** uruchamia wskazany EXE producenta. Ustaw w nim zapis
   do obserwowanego folderu. Nie jest to własna implementacja sterownika TWAIN.

## Sprawdzenie i ograniczenia

`tools/check_windows.py` oraz `tools/CHECK_WINDOWS.md` zawierają diagnostykę i
listę prób: polskie ścieżki, zapis/odzyskiwanie, OCR, drukarki, urządzenia WIA,
udziały sieciowe oraz budowanie EXE/instalatora. Z tego środowiska wykonano testy
Linux/Qt offscreen, test rzeczywistego OCR Tesseract i próbę z 300-stronicowym PDF.
Nie wykonano fizycznego skanowania, drukowania ani instalacji na Windows.
`TEST_RESULTS.txt` i `PERFORMANCE_CHECK.json` zawierają wyniki bieżącej wersji;
syntetyczny test wydajności nie gwarantuje podobnych czasów dla innych PDF.

PyMuPDF nadal wymaga rozstrzygnięcia licencji przed dystrybucją zamkniętego
programu: komercyjna licencja Artifex lub wymiana silnika. Samymi zmianami kodu
nie można przyznać takiej licencji. Zobacz LICENSING.md i DODATKOWE_LICENCJE.md.
