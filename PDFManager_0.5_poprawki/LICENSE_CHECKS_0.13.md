# Sprawdzenie mechanizmu licencji — PDFManager 0.13

## Zachowanie

Nowa instalacja rozpoczyna okres przy pierwszym uruchomieniu aplikacji i zapisuje datę końca sześciu miesięcy kalendarzowych. Przykład: 13 października → 13 kwietnia, o tej samej godzinie UTC. Dla dnia, którego nie ma w miesiącu końcowym, stosowany jest ostatni dzień tego miesiąca. Ponowne uruchomienie nie przedłuża terminu.

Przypomnienie pojawia się, gdy zostało nie więcej niż siedem dni, raz dziennie w danej sesji. W chwili wygaśnięcia program blokuje edycję i otwiera okno kodu. Podczas pracy sprawdza stan cyklicznie, z krótszym interwałem przy zbliżającym się terminie. Poprawny, nowy kod odblokowuje określony okres; błędny, ponownie wykorzystany lub przeznaczony dla innej instalacji jest odrzucany.

Istniejące instalacje zachowują wcześniejszy zapisany termin. Stary zapis zawierający jedynie początek okresu nadal oznacza 182 dni, aby aktualizacja nie przesuwała wcześniej ustalonego końca. Nowe instalacje otrzymują sześć miesięcy kalendarzowych. Stare kody miesięczne zachowują wcześniejszą zasadę 30 dni/miesiąc; kody z programu właściciela określają dokładną liczbę dni.

Podpisana blokada z programu właściciela jest sprawdzana dla sparowanej instalacji. Po odebraniu polecenia włącza blokadę i okno kodu. Poprawny kod właściciela może ją zwolnić. Bez połączenia i synchronizacji nowe polecenie nie dotrze natychmiast.

## Wykonane testy

`tests/test_license_boundaries_013.py` sprawdza początek i koniec okresu, miesiące o różnej długości, lata przestępne, granicę siedmiu dni z dokładnością do sekundy, ponowne uruchomienie, utratę pojedynczej kopii stanu, stary format 182 dni, cofnięcie zegara, błędne i wykorzystane kody oraz brak aktywnego zapisu.

Test rzeczywistego zegara Qt sprawdza przejście z ważnej do wygasłej licencji podczas otwartej sesji i odblokowanie po prawidłowym kodzie. Test zdalnej blokady używa prawdziwych podpisów Ed25519 z jednorazowym kluczem testowym. Sprawdzono również ponowną kontrolę stanu po oknie aktywacji oraz odrzucenie operacji pomocniczej i zapisu wyniku przy blokadzie.

Testy rejestru Windows używają atrapy `winreg` w środowisku Linux. Działanie zbudowanego EXE, prawdziwego rejestru, DPAPI i parowania dwóch komputerów wymaga sprawdzenia na Windows według checklisty. Prywatne klucze właściciela nie są częścią źródeł ani pełnego ZIP.

## Granice zabezpieczenia

Nie można uczciwie zapewnić stuprocentowej odporności lokalnego programu na administratora komputera, zmodyfikowanie plików programu lub całkowite usunięcie jego stanu. Mechanizm wykorzystuje podpisy, dwa miejsca zapisu, wykrywanie cofnięcia zegara i kontrolę kodów, ale nie jest zewnętrznym serwerem czasu ani sprzętowym zabezpieczeniem. Nie należy wyłączać zabezpieczeń systemu Windows ani synchronizować prywatnych kluczy w folderze dostępnym pracownikom.
