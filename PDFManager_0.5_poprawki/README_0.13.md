# PDFManager 0.13 — codzienna praca ze spedycją

Zachowano główne menu i własną, kolorową wstążkę formatowania. Rozbudowano Centrum spedycji i zabezpieczenia zapisu. Interfejs jest dostępny po polsku, angielsku i ukraińsku; język pieczątki można wybrać niezależnie od języka menu.

## Pieczątki i wstawki

Otwórz PDF i Centrum spedycji. Wybierz Pieczątki albo Wstawki, język oraz gotowy wzór. Dostępnych jest 16 pieczątek i 7 wstawek w każdym z trzech języków. Uzupełnij dane przesyłki, np. AWB, HAWB, MAWB, trasę, przewoźnika, liczbę sztuk i masę. Możesz zmienić tekst oraz zapisać własną wstawkę w ulubionych.

Wybierz bieżącą stronę, wszystkie strony lub zakres, np. `1,3-5`. Sprawdź podgląd i zastosuj oznaczenie. Operacja dotyczy kopii roboczej i obsługuje cofanie. Zapis oryginału wykonujesz osobno. Funkcja „Zapisz nową wersję bez nadpisywania” tworzy nowy dokument.

Wzory pomagają oznaczać dokumenty; nie zastępują urzędowych formularzy AWB/CMR, podpisów cyfrowych ani kontroli poprawności danych transportowych.

## Zlecenia i weryfikacja

Przy zakładaniu zlecenia wybierz transport drogowy albo lotniczy. Program tworzy odpowiednie foldery i listę wymaganych dokumentów. Transport lotniczy obejmuje m.in. AWB, HAWB, MAWB, fakturę handlową, listę pakunkową i dokumenty celne. Zaznaczenie sprawdzenia dokumentu jest czynnością pracownika, a nie automatycznym zatwierdzeniem jego treści.

W zakładce „Weryfikacja dokumentów” dodaj PDF, numer zlecenia/AWB, pracownika i status. Możesz wyszukiwać zadania i eksportować raport CSV. Kolejka jest lokalna na danym komputerze, przechowywana w zaszyfrowanej bazie. Eksport udostępnisz zespołowi; nie jest to wspólna baza z automatyczną synchronizacją. Usunięcie wpisu nie usuwa PDF.

## Skanowanie i szkice

Gotowe profile OCR obsługują polski, angielski i ukraiński oraz ich połączenia. Opcjonalne prostowanie skanu koryguje niewielkie przekrzywienia, gdy wynik analizy jest jednoznaczny; zachowuje brzegi. OCR wymaga Tesseract i odpowiednich modeli językowych. Wynik rozpoznawania zawsze sprawdź, szczególnie numery AWB, kwoty i nazwiska.

Szkic tekstu zapisuje się lokalnie, w postaci zaszyfrowanej, po krótkiej przerwie w pisaniu. „Przywróć zapisany szkic” odtwarza formatowanie i treść do dalszej edycji. Wybierz miejsce wstawienia i zastosuj do PDF. Przywrócenie szkicu samo nie zmienia dokumentu.

„Sprawdź gotowość stanowiska” sprawdza wolne miejsce, OCR i czcionkę Unicode. Nie zapisuje dokumentów na Dysku Google ani nie uruchamia skanera.

## Zapis i dłuższa praca

Historia cofania jest szyfrowana na lokalnym dysku, zamiast przechowywać całe dokumenty w RAM. Liczba otwartych PDF jest ograniczona do 12, a renderowanie podglądów jest kolejkowane. Zamykanie karty czeka na zakończenie jej pracowników. Błąd zabezpieczenia kopii przy zamykaniu pozostawia program otwarty i wyświetla komunikat. Zamknięte okna Centrum spedycji, ustawień, menedżera stron i korekty OCR są zwalniane, zamiast narastać w pamięci przy kolejnych otwarciach.

Zapis porównuje dokument źródłowy z wersją otwartą. Zmiana przez innego użytkownika powoduje konflikt zamiast cichego nadpisania. Lokalna blokada zapisu koordynuje instancje na jednym komputerze. Google Drive synchronizuje się z opóźnieniem: sam lokalny zapis nie zapewnia blokady między komputerami. Do pracy zespołowej używaj istniejącej rezerwacji dokumentu i sprawdzaj synchronizację.

[Szczegółowy opis sprawdzenia licencji](LICENSE_CHECKS_0.13.md).

## Licencja i zdalne polecenia

Nowa instalacja zapisuje datę pierwszego uruchomienia i termin sześciu miesięcy kalendarzowych. Od siedmiu dni przed końcem pokazuje przypomnienie. Po wygaśnięciu blokuje edycję i wymaga poprawnego, niewykorzystanego kodu. Termin jest sprawdzany również podczas pracy. Istniejące instalacje zachowują swój zapisany termin, w tym wcześniejsze okresy 182 dni; aktualizacja nie uruchamia nowego okresu.

Podpisana zdalna blokada wywołuje okno licencji po odebraniu polecenia. Komputer offline nie odbierze nowej blokady do czasu połączenia i synchronizacji kanału sterowania. Aby używać programu właściciela, przed przekazaniem aplikacji pracownikowi przygotuj sparowaną paczkę według [instrukcji 0.9](README_0.9.md). Pełny ZIP źródeł nie zawiera Twoich prywatnych kluczy ani indywidualnego parowania.

Nie istnieje stuprocentowa odporność mechanizmu lokalnego na administratora systemu, zmianę kodu lub całkowite usunięcie danych. Wykrywanie cofnięcia zegara ogranicza proste obchodzenie terminu. Podpisy kryptograficzne weryfikują polecenia i kody właściciela.

## Budowa EXE na Windows

Rozpakuj pełny ZIP do osobnego folderu `C:\PDFManager_0.13`. W PowerShellu:

```powershell
Set-Location 'C:\PDFManager_0.13'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r packaging\requirements-build.txt
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
.\packaging\build_windows.bat
.\dist\PDFManager\PDFManager.exe
```

Przekazuj cały folder `dist\PDFManager`, z `_internal`. Ta paczka zawiera źródła, nie gotowy instalator EXE. Zanim zastąpisz firmową wersję, wykonaj [testy stanowiska Windows](CHECKLIST_WINDOWS_0.13.md) na kopiach dokumentów.
