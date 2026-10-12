# Pochodzenie i licencje dodatków

Nie skopiowano kodu ani zasobów KillerPDF (GPLv3) lub FileCenter.
Nowe moduły Python i rysunki ikon wykonano niezależnie w ramach rozwoju PDFManagera.
Nie nadano całemu projektowi GPL ani nie zmieniono produkcyjnego mechanizmu licencji.

Dodane zależności:

| Pakiet | Licencja odczytana z zainstalowanej dystrybucji |
|---|---|
| Pillow 12.3.0 | MIT-CMU |
| NumPy 2.5.4 | BSD-3-Clause / 0BSD / MIT / Zlib / CC0-1.0 (składniki) |
| pyHanko 0.37.0 | MIT |
| Oficjalne modele tessdata_fast | Apache-2.0; pobierane opcjonalnie, nie dołączone do ZIP |
| Tesseract OCR 5 | Apache-2.0; instalowany osobno |

Przy dystrybucji należy zachować wymagane noty licencyjne i sprawdzić komplet
zależności przechodnich zainstalowanych do finalnej wersji Windows.
Oryginalne obowiązki dotyczące PySide6, PyMuPDF, fontów i pozostałych bibliotek
opisano w LICENSING.md. W szczególności zamknięta dystrybucja nadal wymaga
rozwiązania licencji PyMuPDF; nie stanowi to przeszkody do osobistego rozwoju.

Pobierane modele OCR pochodzą wyłącznie z:
https://github.com/tesseract-ocr/tessdata_fast
Wersja: 87416418657359cb625c412a48b6e1d6d41c29bd.
Kod sprawdza identyfikatory blobów z tej wersji, z zachowaniem weryfikacji TLS.

Własne ikony nie są kopią grafik FileCenter. Ocena całego wyglądu/brandingu
przed komercyjną publikacją jest osobnym krokiem; nie deklaruje się gwarancji
prawnej „identyczne 1:1 i bez naruszeń”.

## Dodatek 0.6

zxing-cpp (ZXing C++): Apache-2.0; używany do odczytu kodów QR i 1D/2D.
Nowe grafiki są własnymi rysunkami wektorowymi PDFManagera.
