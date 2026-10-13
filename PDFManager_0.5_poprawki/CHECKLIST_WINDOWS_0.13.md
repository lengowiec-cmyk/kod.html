# Sprawdzenie stanowiska przed wdrożeniem

Testy automatyczne wykonano w środowisku Linux z Qt bez ekranu. Nie zastępują testu zbudowanych EXE na Windows i sprzętu firmy. Pracuj na wydzielonym folderze testowym i kopiach PDF.

- Zbuduj aplikację i program właściciela według instrukcji packaging. Uruchom jako zwykły użytkownik Windows. Sprawdź skalowanie 100%, 150% i 200%, wszystkie zakładki oraz menu PL/EN/UK.
- Otwórz firmowy CMR i AWB, wpisz polski i ukraiński tekst, wybierz czcionkę, rozmiar, listę, wyrównanie i kolor. Zastosuj do PDF, cofnij, ponów, zapisz nową wersję i otwórz ją ponownie.
- Wstaw pieczątkę na stronach 1 i 3, sprawdź stronę 2. Sprawdź puste pole, błędny zakres i anulowanie. Scal i podziel dokumenty, sprawdź formularze, zakładki, obrazy i trwałe usuwanie danych na kopii.
- Zeskanuj kilka kartek na rzeczywistym skanerze, także dwustronnie, jeśli sterownik to obsługuje. Sprawdź OCR w trzech językach, orientację, prostowanie i brak ucięcia brzegów.
- Na dwóch komputerach sprawdź rezerwację, modyfikację tego samego dokumentu, konflikt zapisu, nową wersję, synchronizację i powrót po rozłączeniu Google Drive. Nie używaj produkcyjnych dokumentów do próby konfliktu.
- Sprawdź kolejkę weryfikacji i raport CSV. Kolejki są lokalne, nie wspólne. Zmiana statusu i usunięcie wpisu nie mogą zmieniać PDF.
- W osobnej maszynie testowej sprawdź pierwsze uruchomienie, ponowne uruchomienie, termin zapisany w licencji, przypomnienie i blokadę. Nie przestawiaj zegara na produkcyjnym komputerze. Testy granic dat znajdują się w tests/test_license_boundaries_013.py.
- Przygotuj sparowaną paczkę testową, wyślij podpisaną blokadę z programu właściciela, sprawdź okno kodu, błędny kod oraz poprawny kod na konkretny okres. Offline nowe polecenie zostanie odebrane po synchronizacji.
- Prześlij testową, podpisaną aktualizację; sprawdź odrzucenie błędnego podpisu i zachowanie dokumentów. Nie wyłączaj Defendera ani kontroli podpisów.
- Pracuj przez pełną zmianę roboczą na typowym zestawie dokumentów, obserwuj RAM, wolne miejsce i czas reakcji. Krótkie testy automatyczne nie dowodzą niezawodności przez osiem godzin.
- Sprawdź odzyskanie kopii po wymuszonym zakończeniu na maszynie testowej, brak miejsca na dysku, anulowanie dłuższej operacji i komunikaty błędów. Przed aktualizacją wykonaj kopię danych aplikacji i dokumentów.
