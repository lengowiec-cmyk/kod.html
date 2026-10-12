# Kontynuacja poprawionej wersji PDFManager

Bazą dalszej pracy jest katalog `PDFManager_0.5_poprawki` pobrany z gałęzi `main`
repozytorium `lengowiec-cmyk/kod.html`. Zachowano poprawki Claude dotyczące
przygotowania dużych kopii roboczych w tle, ograniczania kopii zapasowych oraz
nowe testy automatyzacji skanowania.

Podczas przeglądu uzupełniono mechanizm kopii:

- Retencja jest wykonywana po pomyślnym zapisie, a nie przed nim.
- Najnowsza kopia pozostaje chroniona, nawet gdy sama przekracza limit rozmiaru.
- Nazwy zawierające nawiasy kwadratowe są porównywane dosłownie.
- Nowe kopie dokumentów o tej samej nazwie w różnych folderach są grupowane
  według pełnej ścieżki oryginału. Limit liczby kopii jest odrębny dla każdej grupy.
- Błąd porządkowania kopii nie zmienia pomyślnego zapisu w błąd zapisu;
  problem trafia do dziennika aplikacji.
- Nieudane tworzenie kopii roboczej usuwa niedokończony katalog sesji.
- Błąd otwierania małego dokumentu jest pokazywany w oknie komunikatu.

Dodano testy tych zachowań. Aktualny wynik całego zestawu znajduje się w
`TEST_RESULTS.txt`. Testy wykonano w Linux z Qt offscreen; fizyczny skaner,
drukarka i instalator Windows nadal wymagają prób na komputerze Windows.

Katalog `PDFManager` i wcześniejsze paczki ZIP pozostają historyczną wersją.
Przy dalszych zmianach oraz budowaniu EXE korzystaj z `PDFManager_0.5_poprawki`.
