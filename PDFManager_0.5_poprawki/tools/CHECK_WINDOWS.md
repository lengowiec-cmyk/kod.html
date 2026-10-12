# Sprawdzenie na Windows

Uruchom z katalogu projektu w aktywowanym środowisku .venv:

```
python -m pip check
python tools/check_windows.py --wia
python -m pytest -q
```

Diagnostyka sprawdza ścieżki z polskimi znakami, zachowanie oryginału podczas
edycji, zapis kopii, dostępność OCR, listę drukarek i liczbę urządzeń WIA.
Nie uruchamia drukowania ani skanowania, nie instaluje sterowników.

Próba ręczna:

1. Otwórz własny PDF z kopii bezpieczeństwa, zmień tekst i zamknij aplikację
   bez zapisu. Oryginał ma pozostać bez zmian; Plik → Odzyskaj dokument ma
   udostępnić kopię. Zapisz odzyskaną wersję przez Zapisz jako.
2. Zmień plik źródłowy w drugim programie. Zapis PDFManager powinien odmówić
   nadpisania zmienionego oryginału i wskazać Zapisz jako.
3. Wstaw tekst/obraz, przeciągnij obszar na stronie. Sprawdź przesuwanie,
   skalowanie oraz Cofnij/Ponów. Panel czcionek otwórz w Narzędziach.
4. Przenieś plik do kosza i przywróć. Sprawdź konflikt nazw bez nadpisywania.
5. Wybierz udział sieciowy jako szafkę; sprawdź dostępność i uprawnienia.
6. Ustaw folder skanera i osobny folder wynikowy. Włącz obserwowanie.
   Zapisz do niego skan, następnie identyczną kopię pod inną nazwą: ma powstać
   jeden wynik. Wypróbuj OCR dopiero po zainstalowaniu Tesseract i języka.
7. Wybierz Skanuj WIA. Jeśli urządzenie nie ma sterownika WIA, uruchom aplikację
   producenta przez Aplikacja skanera TWAIN i zapisuj do obserwowanego folderu.
8. Sprawdź podgląd wydruku, wybrane strony i drukarkę fizyczną.
9. Zbuduj oba EXE przez packaging\build_windows.bat i instalator Inno Setup.
   Zainstaluj na drugim komputerze Windows bez środowiska Pythona.

Nie wykonano tych prób sprzętowych w środowisku chmurowym Linux. Skrypt i
lista umożliwiają ich wykonanie na komputerze użytkownika; nie zastępują wyników.

## Dodatkowe próby wersji 0.6

- Sprawdź uruchamianie procesów PDF w obu EXE oraz odrzucanie operacji przy braku limitów Job Object.
- Zweryfikuj integrację Defendera i zachowanie przy braku jego narzędzia.
- Zamknij dokument bez zapisu, odzyskaj zaszyfrowaną kopię i sprawdź kosz oraz migrację starszych kopii.
- Sprawdź profile skanów, prawdziwy kod QR, podział po kodach i reguły kopiowania do szafek.
- Sprawdź wszystkie osiem zakładek, ustawienia, wydatki oraz eksport CSV.
