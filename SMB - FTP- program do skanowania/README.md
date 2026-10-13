# Konfigurator skanowania Ricoh (SMB / FTP)

Automatyczna konfiguracja skanowania sieciowego dla urządzeń Ricoh:
tworzy folder, konto, udział SMB lub serwer FTP (IIS), reguły Zapory
Windows oraz — jeśli podano dane administratora — wpis w książce
adresowej urządzenia. Wszystko po kliknięciu jednego przycisku.

## Struktura projektu

```
ricoh_scanner_config/
├── main.py                   punkt wejścia, interfejs GUI (PySide6)
├── modules/
│   ├── logger.py             logi do pliku + GUI
│   ├── system_utils.py       IP, admin, komendy systemowe, skan sieci
│   ├── windows_config.py     folder, konto, SMB, firewall
│   ├── ftp_config.py         instalacja i konfiguracja IIS FTP
│   └── ricoh_client.py       logowanie i konfiguracja Web Image Monitor
├── requirements.txt
├── build.bat                 automatyczny build do EXE
└── README.md
```

## Uruchomienie ze źródeł (do testów / rozwoju)

```
pip install -r requirements.txt
python main.py
```

Program sam poprosi o podniesienie uprawnień (UAC) przy kliknięciu
„Konfiguruj”, jeśli nie jest jeszcze uruchomiony jako administrator.

## Budowanie do pliku EXE

**Ważne:** budowanie uruchamiaj z terminala **bez** uprawnień
administratora — PyInstaller tego nie wymaga i wręcz przed tym ostrzega.

Automatycznie (zalecane):

```
build.bat
```

Ręcznie:

```
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --noconsole --name "RicohScannerConfig" main.py
```

Gotowy plik pojawi się w `dist\RicohScannerConfig.exe`.

Sam plik EXE, przy uruchomieniu, poprosi o uprawnienia administratora
przez UAC (logika w `system_utils.relaunch_as_admin`) — nie trzeba
uruchamiać go ręcznie jako Administrator.

## Jak działa konfiguracja

1. **Wykrycie urządzenia** — jeśli pole IP jest puste, program skanuje
   lokalną podsieć /24 i sam znajduje urządzenie Ricoh (po odpowiedzi
   HTTP z sygnaturami Web Image Monitor).
2. **Konfiguracja Windows** — tworzy konto `skaner`, folder
   `C:\SkanyRicoh`, nadaje uprawnienia NTFS, udostępnia przez SMB lub
   konfiguruje witrynę FTP w IIS (w zależności od wybranego protokołu).
3. **Zapora Windows** — otwiera potrzebne porty (445 dla SMB, 21 +
   zakres pasywny dla FTP) oraz dodaje adres IP urządzenia jako w pełni
   zaufany (cały ruch TCP/UDP), żeby żaden kanał komunikacji nie został
   przypadkowo zablokowany.
4. **Konfiguracja urządzenia Ricoh** — jeśli podano hasło administratora,
   program loguje się do Web Image Monitor i dodaje nowy wpis w książce
   adresowej (bez usuwania istniejących wpisów), a następnie próbuje
   dodać komputer do listy zaufanych adresów urządzenia (funkcja
   dostępna tylko na części modeli — jej brak nie przerywa konfiguracji).
5. **Testy weryfikacyjne (automatyczne, po konfiguracji)** — program sam
   sprawdza rzeczywisty stan systemu i wypisuje czytelną listę statusów:
   - czy folder skanów istnieje,
   - czy da się do niego zapisać (realny test zapisu pliku),
   - czy usługa SMB/FTP faktycznie odpowiada na porcie,
   - czy reguły Zapory Windows zostały utworzone,
   - czy urządzenie Ricoh odpowiada na ping,
   - czy sesja z urządzeniem nadal działa po dodaniu wpisu w książce
     adresowej.

   Każdy wynik jest oznaczony kolorem: zielony ✔ (przetestowano, działa),
   czerwony ✖ (przetestowano, nie działa) lub bursztynowy ✖ (nie da się
   zweryfikować automatycznie — np. faktyczne zeskanowanie strony z panelu
   drukarki zawsze wymaga ręcznego potwierdzenia).

6. **Raport końcowy** — dane logowania, ścieżka i wyniki testów są
   kopiowane do schowka oraz zapisywane w logu (`logs/config_*.log`).

## Wykluczenia Windows Defender (opcjonalne, wymaga świadomej zgody)

W GUI znajduje się odznaczony domyślnie checkbox „Dodaj folder skanów i
ten program do wykluczeń Windows Defender”. Jeśli zostanie **świadomie
zaznaczony** przez osobę obsługującą program, po zakończeniu głównej
konfiguracji wykonywane są dwie operacje przez oficjalny, udokumentowany
mechanizm PowerShell (`Add-MpPreference`) — dokładnie ten sam, którego
używają narzędzia administracyjne IT:

- dodanie folderu skanów do `-ExclusionPath` (żeby zapis każdego skanu
  nie był opóźniany przez skanowanie w czasie rzeczywistym),
- dodanie pliku programu do `-ExclusionProcess` (żeby sam konfigurator
  nie był poddawany powtórnej analizie przy każdym uruchomieniu).

**To nie jest ciche ani ukryte działanie:**
- checkbox jest domyślnie odznaczony — trzeba go świadomie zaznaczyć,
- funkcja wymaga uprawnień administratora (tak jak reszta programu),
- nic nie jest wyłączane globalnie — tylko konkretna ścieżka/proces
  dodawane do listy wykluczeń,
- wynik operacji (sukces/niepowodzenie) trafia do raportu końcowego,
- jeśli komputer używa innego antywirusu zamiast Windows Defender,
  krok jest automatycznie pomijany z odpowiednim komunikatem w logu.

Jeśli mimo wykluczeń Windows SmartScreen nadal ostrzega przed
uruchomieniem samego pliku EXE, to osobny mechanizm (reputacja pliku
niepodpisanego cyfrowo) — jedynym trwałym rozwiązaniem tego jest
podpisanie pliku certyfikatem code-signing, co wykracza poza zakres
automatycznej konfiguracji tego narzędzia.

## Rozbudowa

Każdy moduł jest niezależny i przyjmuje obiekt `logger` — łatwo dodać
kolejne protokoły (np. e-mail, WSD) lub inny serwer FTP (FileZilla)
jako nowy plik w `modules/` bez ingerencji w resztę kodu.
