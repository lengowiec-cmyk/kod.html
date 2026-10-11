# Zakres funkcjonalny względem dostarczonego KillerPDF

Porównanie dotyczy dostarczonego README KillerPDF 1.8.80, bez kopiowania kodu.
„Działa” oznacza własną implementację w PDFManagerze; nie identyczny silnik,
algorytm, interfejs ani identyczną jakość dla wszystkich dokumentów.

| Obszar KillerPDF | PDFManager 0.2 | Ograniczenia / dowód |
|---|---|---|
| Renderowanie i zakładki dokumentów | Działa | PyMuPDF zamiast PDFium; GUI i otwarcie PDF zweryfikowane |
| Single / Continuous / Two-Page / Book / Grid | Działa | Leniwy podgląd; edycja w pojedynczym widoku; test GUI |
| Dwa dokumenty obok siebie | Działa | Drugi panel jest osobną kopią do podglądu; test GUI |
| Cofnij / Powtórz na każdej karcie | Zachowano | Do 20 stanów z budżetem pamięci; historia tylko w sesji |
| Edycja tekstu i dopasowanie czcionek | Zachowano | Dotychczasowy silnik PDFManager; bez pełnej reimplementacji edytora KillerPDF |
| Notatki, tekst, podświetlenia, podkreślenia, przekreślenia | Działa | Dotychczasowe plus edycja treści notatek, Multiply |
| Linie, prostokąty, elipsy, strzałki, wielokąty | Działa | Wielokąt w tej wersji: pięciokąt w przeciągniętym prostokącie |
| Odręczne rysowanie | Działa | Adnotacja Ink; test silnika |
| Redakcja danych | Działa na obszarze strony | Nie usuwa automatycznie metadanych, załączników ani powiązanych kopii danych |
| Obrazy, podpisy graficzne, inicjały | Działa | Import i narysowanie przez własne okno; nie podpis cyfrowy |
| Znaki wodne / numery stron | Działa | Unicode, osobne wyjście, test zachowania metadanych i zakładek |
| Lokalny OCR całego dokumentu | Działa | Rzeczywisty Tesseract 5; testy ENG i POL |
| OCR strony / obszaru / do schowka | Działa | Wybór zakresu i tekstu; OCR tworzy nową kopię |
| Pobieranie dodatkowych modeli OCR | Działa dla PL/EN/UK | Oficjalne, przypięte modele z kontrolą integralności; brak katalogu wszystkich języków w GUI |
| Scalanie / dzielenie / wstawianie / wyodrębnianie / usuwanie | Działa | Dotychczasowe operacje stron; nowy merge dla obrazów i ZIP |
| Kolejność stron i obrót | Zachowano | Przeciąganie w Menedżerze stron |
| Upuszczenie folderu / ZIP do scalenia | Działa | Limit wejścia 512 MB; ZIP nie rozpakowuje dowolnych ścieżek na dysk |
| PNG / JPEG dla wielu wybranych stron | Działa | Parser zakresów; test obu formatów |
| Przycinanie / rozmiar strony | Działa | Marginesy w punktach; zmiana rozmiaru przenosi treść, nie pełną strukturę formularzy |
| Obrót / skalowanie / odbicie obrazu | Działa | Rastrowa kopia; test pikseli i pliku |
| Prostowanie skanu | Działa kątem | Nie wyznacza kąta przez rysowanie linii poziomu |
| Korekcja perspektywy | Działa | Cztery narożniki jako proporcje; kontrola wypukłości; test |
| Poziomy: black / white / gamma | Działa | Rastrowa kopia; test |
| Formularze tekstowe / checkbox / radio / combo | Działa | Okno pól AcroForm; nie nakładki kontrolek na stronie; test tekstu i checkbox |
| Comb fields | Częściowo | Wartość tekstowa zapisuje się; bez specjalnego edytora segmentów comb |
| Podpisy lokalnym certyfikatem | Działa | PKCS#12, pyHanko; test kryptograficzny |
| Certum SimplySign | Niezaimplementowane | Osobna integracja usługodawcy, lokalny provider/konto i weryfikacja na Windows |
| Weryfikacja podpisów | Działa lokalnie | Osobno integralność, poprawność i zaufanie; bez OCSP/CRL online |
| Drukowanie i podgląd | Działa przez Qt | Wydruk do PDF i zakres stron przetestowane; fizyczna drukarka nieweryfikowana |
| Wiele stron na arkuszu | Działa jako eksport układu wydruku | 1/2/4/6/9 stron, rastrowa kopia do wydruku; ustawienia marginesów Qt nie odtwarzają całego panelu KillerPDF |
| Save Flattened | Działa | Rasteryzacja z widocznymi adnotacjami; test |
| Wyszukiwanie i wyróżnianie | Działa | Bieżący PDF oraz folder/podfoldery; raport błędów plików |
| Column-aware text selection | Częściowo | Prostokątne kopiowanie i sortowanie PyMuPDF; bez gwarancji kolejności złożonych kolumn |
| Tryb nocny każdego dokumentu | Działa | Każdy widget osobno; drugi panel niezależny |
| Motywy / kolor tytułu / rozmiar wstążki | Działa we własnym zakresie | 2 motywy, 6 kolorów tytułu, 2 kolory wstążki, kompaktowy układ; nie 13 motywów KillerPDF |
| Dokowanie panelu po dowolnej stronie | Działa | Widok → Przenieś miniatury; lewa/prawa strona i regulowana szerokość |
| 19 języków UI | Nieprzeniesione | Oryginalne PL/EN/UK; nowe dialogi głównie PL |
| Skróty i F1 | Działa | Lista skrótów i Ctrl+Shift+K; bez graficznej mapy klawiatury |
| PDF z hasłem | Działa | Bezpieczny prompt; osobna odszyfrowana kopia robocza |
| Naprawa uszkodzonych PDF | Częściowo | Ponowny zapis dokumentów, które PyMuPDF potrafi odczytać |
| CLI wszystkich głównych eksportów i wydruku | Działa | 11 komend, kody wyjścia i licencja; eksport/druk przetestowane |
| Przetwarzanie wsadowe | Działa | CSV z błędami i sukcesami, bez udawania pełnego sukcesu |
| Porównanie PDF | Działa | Wizualne różnice stron i raport procentowy; bez mapy nakładek zmienionych regionów |
| Zakładki i linki | Działa w podstawowym zakresie | Dodawanie zakładek i nawigacja; bez kompletnego edytora hierarchii/linków |
| Załączniki PDF | Działa | Dodawanie/eksport, test |
| Standardy PDF/A / PDF/UA / preservation-safe pipeline KillerPDF.Engine | Nieprzeniesione | Nie dołączono GPL-owego silnika; brak niezależnej walidacji korpusu i gwarancji zgodności |
| Automatyczne aktualizacje z GitHub | Niezaimplementowane | Brak wskazanego repozytorium wydań PDFManagera i mechanizmu publikacji |
| Instalator i portable Windows | Skrypty przygotowane | EXE/Inno Setup wymagają uruchomienia i testów na Windows; brak gotowego binarium w paczce |

Dodatkowe funkcje FileCenter (faks, skaner, Inbox z urządzeniami, szafy,
foldery indeksowania Windows) nie należą do zakresu samego KillerPDF i
nie zostały dodane jako pozorne działające przyciski. Warstwa wizualna
używa własnych ikon i oznaczeń PDFManagera.

Wersja 0.5 dodaje bezpieczne kopie robocze, odzyskiwanie, kosz, panel czcionek,
przesuwanie/skalowanie nowych elementów, indeks PDF, anulowanie i automatyczny
import skanów oraz WIA. Zakres i ograniczenia opisuje ZMIANY_0.5.md.
