# Walidacja PDFManager 0.13

Data: 13 października 2026. Python 3.12, PySide6 6.12, PyMuPDF 1.28.2. Środowisko Linux; interfejs Qt uruchomiony bez ekranu (`QT_QPA_PLATFORM=offscreen`).

## Regresja

Pełny przebieg: **433 testy zakończone poprawnie, 1 oczekiwane niepowodzenie (xfail), 0 błędów nieoczekiwanych**, 704,99 sekundy. Oczekiwane niepowodzenie dotyczy znanej dokładności Tesseract przy wielkiej literze Ź w skanie 150 DPI (rozpoznanie jako Ż). Nie jest to test zaliczony.

Polecenie: `python -m pytest -q -o faulthandler_timeout=90`. Dwa testy zwalniania okien dodane po rozpoczęciu tego przebiegu wykonano w dodatkowym zestawie poniżej.

Dodatkowe sprawdzenia po poprawkach zamykania okien: **15 testów zakończonych poprawnie**, 41,06 sekundy. Mechanizm zwalniania okien Centrum spedycji, ustawień, menedżera stron i korekty OCR jest sprawdzany przy powtarzanym otwieraniu i zamykaniu. Testy licencji, okna głównego i tłumaczeń: 35 zakończonych poprawnie. Zapis, cofanie i odzyskiwanie: 44 zakończone poprawnie. Nie należy sumować tych liczb — część testów się powtarza.

Poprawiono ścieżkę zamykania pustego okna po anulowaniu otwierania PDF. Dopasowano wcześniejszy test odzyskiwania do celowego usuwania kopii, w której wszystkie zmiany cofnięto: test sprawdza teraz cofnięcie do identycznej treści oraz zachowanie rzeczywistej niezapisanej zmiany po ponowieniu. Nie wyłączono kontroli zachowania źródła ani szyfrowania.

## Przyciski i funkcje

Spis [CONTROL_INVENTORY_0.13.json](CONTROL_INVENTORY_0.13.json) obejmuje 411 nazwanych akcji i przycisków w oknie głównym, Centrum spedycji i ustawieniach. Sprawdzono połączenia sygnałów, akcje domyślne przycisków, menu, grupy Qt i pola formularzy odczytywane przy zapisie. Nie wykryto elementów bez obsługi. Spis połączeń sam w sobie nie potwierdza poprawności działania każdej operacji.

Rzeczywiste kliknięcia sprawdzają pogrubienie, kursywę, podkreślenie, przekreślenie, indeksy, zmianę rozmiaru, kolory, zakreślenie, wyrównanie, listy, wcięcia, sortowanie, znaki formatowania, tło, ramkę, style, schowek, malarza formatów i czyszczenie formatowania. Oddzielne testy sprawdzają zastosowanie tekstu do PDF, Unicode, pieczątki na wielu stronach, cofanie, formularze, operacje na stronach, OCR, wyszukiwanie, skany, aktualizacje, licencję, kody i bezpieczeństwo plików.

Testy Google Drive używają kontrolowanych odpowiedzi API. Testy skanera sprawdzają kod i komunikaty, a nie urządzenie sprzętowe. Nie wykonano wszystkich możliwych kombinacji przycisków i plików. Przed wdrożeniem konieczna jest [checklista Windows](CHECKLIST_WINDOWS_0.13.md).

## Powtarzana sesja GUI

Test trwał 604,19 sekundy i wykonał 93 cykle: otwarcie trzystronicowego PDF, dodanie notatki, cofnięcie, ponowienie, ponowne cofnięcie, zamknięcie karty i zmiana języka. Dokumenty były demonstracyjne i lokalne.

- Błędy operacji: 0.
- Plik źródłowy pozostał identyczny.
- Liczba pomiarów reakcji pętli Qt: 5914.
- Największa przerwa między pomiarami: 0,829 sekundy, przy pomiarze co 100 ms.
- Szczytowe zużycie pamięci procesu w tym teście: 215,9 MB.

Dziesięć minut testu nie dowodzi niezawodności przez całą zmianę roboczą ani zachowania z bardzo dużymi lub uszkodzonymi PDF. Wynik nie jest gwarancją braku zawieszeń.

## Licencja i bezpieczeństwo

[Szczegółowe sprawdzenie licencji](LICENSE_CHECKS_0.13.md) opisuje granice sześciu miesięcy, ostatnich siedmiu dni, blokadę podczas pracy, kody, zachowanie istniejących terminów i podpisaną blokadę zdalną. Procesy pomocnicze zbudowanego programu sprawdzają dostęp przed operacją i zapisem wyniku; rzeczywisty EXE wymaga próby na Windows.

Sprawdzono szyfrowanie kolejki, szkiców i cofania, konflikt dwóch lokalnych kopii, zmianę celu przed zatwierdzeniem zapisu, błędy zabezpieczenia odzyskiwania, odrzucenie zmienionego szkicu i eksport CSV zabezpieczony przed formułami. Złośliwy PDF nadal może wykorzystywać nieznaną lukę w bibliotece natywnej — te testy nie są dowodem pełnej odporności na wszystkie ataki.

ZIP zawiera pełne źródła aplikacji oraz pliki budowania. Nie zawiera gotowego Windows EXE, prywatnych kluczy, konfiguracji kont użytkowników, produkcyjnych dokumentów ani indywidualnego parowania pracowników.
