# Szafki i skanowanie — PDFManager 0.4

To rozszerzenie istniejącego programu PySide6. Nie wykorzystuje kodu ani zasobów FileCenter.

## Obsługa

1. Zakładka **Organizuj → Dodaj szafkę**: wybierz istniejący katalog Windows
   (również dostępny udział sieciowy) i nazwij szafkę. Rejestr jest zapisywany
   w QSettings użytkownika. **Szafki** pozwala przełączać zapisane lokalizacje.
2. **Szablony folderów**: podaj nazwę i listę względnych ścieżek, po jednej na linię.
   **Nowy klient** tworzy nowy folder w szafce wraz z podfolderami szablonu.
   Nazwy Windows są sprawdzane, istniejący klient nie jest nadpisywany.
3. Drzewo pokazuje strukturę wybranej szafki, lista zawiera pliki bieżącego folderu.
   PDF otwiera się w osadzonym podglądzie; inne formaty w domyślnej aplikacji Windows.
   Prawy przycisk na liście: kopiowanie, przenoszenie i zmiana nazwy.
   Wielokrotny wybór: Ctrl/Shift. Operacje nie nadpisują istniejących plików.
   Dokument otwarty w karcie trzeba zamknąć przed przeniesieniem lub zmianą nazwy.
4. **Szukaj w szafce** ustawia korzeń i podfoldery w panelu wyszukiwania.
   Domyślnie szuka nazw wszystkich plików, zaznaczenie **Szukaj także w treści PDF**
   dodaje pełnotekstowe wyniki PDF z numerem strony. Skan bez warstwy tekstowej
   wymaga wcześniejszego OCR. Błędy odczytu są podawane obok liczby wyników.
5. **Scalanie** używa istniejącego modułu PDF i obrazów. **Podziel PDF wsadowo**
   wybiera wiele PDF oraz liczbę stron na część. Każdy dokument otrzymuje osobny,
   nowy folder wynikowy; niepowodzenie jednego dokumentu nie ukrywa wyników innych.
6. Zakładka **Skrzynka → Import skanów**: wybierz PDF, PNG, JPEG, TIFF, BMP lub WebP,
   ustaw kolejność przez przeciąganie, wybierz folder docelowy. Powstanie jeden PDF
   z unikalną nazwą. Wielostronicowy TIFF zachowuje wszystkie klatki.
   **Folder skanera** importuje aktualną zawartość katalogu po potwierdzeniu, w
   kolejności alfabetycznej. Oryginały nie są usuwane; ponowny import tworzy nowy PDF.

## Moduły

- `pdfmanager/dms/cabinets.py`: trwały rejestr szafek i szablonów.
- `pdfmanager/dms/scanning.py`: pliki wejściowe skanera → PDF.
- `pdfmanager/dms/files.py`: wsadowy podział oraz kopiowanie/przenoszenie.
- `pdfmanager/dms/search.py`: wyszukiwanie nazw i tekstu PDF.
- `pdfmanager/ui/cabinet_tools.py`: dialogi i integracja z głównym oknem.

## Zakres i ograniczenia

Wybrano wariant obsługi plików wejściowych ze skanera dopuszczony w wymaganiu.
Sterownik producenta skanera zapisuje pliki do folderu; aplikacja je importuje.
Od wersji 0.5 dodano WIA i obserwowanie folderu z deduplikacją; instrukcja jest
w ZMIANY_0.5.md. Poniższe uwagi o ponownym imporcie dotyczą ręcznego importu. Import folderu obejmuje także wcześniej importowane pliki pozostawione
w katalogu. Aby uniknąć duplikatów, wybieraj konkretne pliki albo przenoś gotowe
oryginały do osobnego archiwum. Nie ma bazy DMS, kontroli wersji ani uprawnień
użytkowników poza uprawnieniami systemu plików Windows.

Testy działają w środowisku Linux z Qt offscreen. Nie wykonano testu rzeczywistego
skanera, udziału sieciowego Windows ani instalatora Windows. Dotychczasowe wymagania
licencji PyMuPDF opisane w LICENSING.md pozostają aktualne.
