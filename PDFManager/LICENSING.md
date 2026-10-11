# Licencje zależności i wymagana decyzja przed wydaniem

Ten plik istnieje, bo w specyfikacji projektu wymagano jasnego
oświadczenia o kosztach/licencjach przed dystrybucją. **Nie został
jeszcze rozwiązany** — wymaga Twojej decyzji przed pierwszym
udostępnieniem komuś zainstalowanej wersji (instalatora z `packaging/`).

## Do rozstrzygnięcia: PyMuPDF (AGPL-3.0)

Silnik PDF (`pdfmanager/pdf_engine/`) używa biblioteki **PyMuPDF**, która
jest na licencji **AGPL-3.0**. Potwierdziłeś wcześniej, że aplikacja ma
być w przyszłości dystrybuowana/sprzedawana z zamkniętym kodem źródłowym
— to się wprost nie zgadza z AGPL, które wymaga: albo (a) udostępnienia
pełnego kodu źródłowego aplikacji na tej samej licencji, albo (b) wykupienia
komercyjnej licencji PyMuPDF od Artifex Software (wycena na zapytanie;
historycznie rzędu kilku tysięcy USD/rok, zależnie od modelu
dystrybucji) — patrz https://artifex.com/licensing/commercial

**Musisz wybrać jedną z opcji przed dystrybucją zbudowanego instalatora:**
1. Kupić komercyjną licencję PyMuPDF od Artifex.
2. Udostępnić kod źródłowy aplikacji publicznie na AGPL-3.0.
3. Zastąpić PyMuPDF inną biblioteką w warstwie renderowania/ekstrakcji
   (np. `pikepdf`, MPL-2.0, wolna dla zamknięto-kodowej dystrybucji) —
   wymaga przepisania `pdf_engine/render.py` i części `text_edit.py`;
   architektura (`TextEditEngine` jako wymienna warstwa abstrakcji) została
   zaprojektowana właśnie z myślą o takiej wymianie, ale sama wymiana nie
   została jeszcze wykonana.

Do czasu tej decyzji aplikacja jest bezpieczna do użytku **wewnętrznego/
osobistego** (nie dystrybuowanego) oraz do dalszego rozwoju.

## Pozostałe zależności (bezpieczne dla zamknięto-kodowej dystrybucji)

| Zależność | Licencja | Uwaga |
|---|---|---|
| PySide6 | LGPL-3.0 | Dynamiczne łączenie (standardowe użycie Pythona) jest zgodne z dystrybucją zamkniętego kodu; nie modyfikuj i nie linkuj statycznie bibliotek Qt. |
| fontTools | MIT | Bez ograniczeń. |
| DejaVu Sans (czcionka zastępcza) | Bitstream Vera + DejaVu changes | Wolna do osadzania, również komercyjnie — patrz `pdfmanager/resources/fonts/LICENSE_DEJAVU.txt`. |
| google-api-python-client, google-auth-oauthlib, google-auth-httplib2 | Apache-2.0 | Bez ograniczeń. |
| keyring | MIT | Bez ograniczeń. |
| LanguageTool (usługa zewnętrzna, nie zależność w kodzie) | LGPL-2.1 (silnik), publiczne API na zasadach languagetool.org | Aplikacja tylko woła REST API — nie linkuje kodu LanguageTool. Użytkownik końcowy godzi się na wysyłkę tekstu w oknie korekty (patrz `proofreading_dialog.py`). |
| PyInstaller (narzędzie budowania, nie część aplikacji) | GPL-2.0 z wyjątkiem bootloadera | Sam bootloader (dołączany do .exe) ma wyjątek licencyjny pozwalający na dystrybucję zamkniętego kodu — nie trzeba GPL-ować aplikacji z tego powodu. |

## Status pozostałych wymagań ze specyfikacji projektu

- Zweryfikowane funkcje: patrz podsumowania Etapów 1–6 w rozmowie (edycja
  tekstu, adnotacje, operacje na stronach, korekta PL/EN/UK, Google Dysk,
  skojarzenie z PDF w Windows, pakowanie) — wszystko przetestowane
  automatycznie (pytest), poza elementami wymagającymi realnego Windows
  i prawdziwych poświadczeń Google Cloud (patrz pamięć projektu / podsumowania).
- Koszt usług zewnętrznych: Google Drive API — bezpłatne w typowym użyciu
  osobistym (limity Google Cloud, zwykle nie wymagają płatności dla tej
  skali). LanguageTool — bezpłatne na publicznym API (ograniczone limitem
  zapytań) albo zupełnie bezpłatne przy samodzielnym hostowaniu.
