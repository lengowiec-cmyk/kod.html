# Zakres wersji 0.7 dla firmy spedycyjnej

| Pomysł | Wdrożenie |
|---|---|
| Gotowe stemple | Dziewięć własnych wzorów, edycja biblioteki, ramka, kolor, podgląd, data i pracownik |
| Bloki tekstu | Własna biblioteka i pola automatyczne; rozmiar czcionki, kolor, TTF/OTF |
| Profile transportowe | CMR, POD, zlecenie i faktura; własne pozycje i profile |
| Automatyczne nazwy | Schemat data/zlecenie/typ/kontrahent, walidacja nazw Windows, podpowiedź numeru z tekstu/OCR |
| Teczki zleceń | Utworzenie pięciu folderów, dołączanie dokumentów, ostatnie katalogi |
| Pakiet dokumentów | Ustalana kolejność, okładka, lista plików, zakładki i numeracja |
| Operacje zbiorcze | Stemple, numeracja, obrót, kompresja i kopie z nowymi nazwami; raport błędów |
| Kompletność | Ręczna lista sprawdzonego CMR/POD/faktury oraz przegląd braków teczek |
| Porównanie | PDF z widokiem oryginału, wersji zmienionej i czerwonych różnic |
| Trwała redakcja | Dostęp do narzędzia usuwającego treść, nie tylko zasłaniającego prostokątem |
| Rezerwacja Drive | Pracownik, wygasanie po 15 minutach, zwalnianie i próba odnawiania |
| Ochrona wspólnego zapisu | Kontrola wersji bazowej i publikacja osobnego pliku bez nadpisania oryginału |
| Stan zapisu | Trwała lista kolejki i pasek oczekujących wpisów/konfliktów |
| Praca offline | Zaszyfrowana trwała migawka, kolejka związana z kontem, ponawianie w tle |
| Historia i przywracanie | Lista wersji programu oraz rewizji Google; pobranie wcześniejszej jako nowej kopii |
| Ulubione | Własny pasek czterech najważniejszych działań i ostatnie foldery |
| Zapis i następny | Ctrl+Alt+N; przejście po potwierdzonym lokalnym zapisie albo trwałej migawce do kolejki, także w folderze API Drive |

Nie kopiowano kodu, ikon ani materiałów FileCenter lub KillerPDF.
Nie ma automatycznego scalania zmian dwóch PDF-ów, semantycznej analizy
umów ani atomowej rezerwacji całego Google Drive. Rezerwacja ma charakter
doradczy; zachowanie osobnych wersji chroni dokument niezależnie od niej.

Praca w zwykłym folderze synchronizowanym Google Drive Desktop nadal oznacza
zapis lokalny. Rezerwacje, kolejka i historia zespołowa korzystają z API Drive.
Własna konfiguracja OAuth oraz uprawnienia są wymagane. Szczegóły i ograniczenia
opisano w [README_0.7.md](README_0.7.md).
