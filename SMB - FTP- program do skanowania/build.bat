@echo off
REM ============================================================
REM  Automatyczny build EXE — Konfigurator skanowania Ricoh
REM  Uruchom jako zwykly uzytkownik (NIE jako administrator).
REM ============================================================

echo.
echo === Instalacja zaleznosci ===
pip install -r requirements.txt pyinstaller

echo.
echo === Czyszczenie poprzednich buildow ===
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q RicohScannerConfig.spec 2>nul

echo.
echo === Budowanie pliku EXE ===
pyinstaller --onefile --noconsole --name "RicohScannerConfig" ^
    --add-data "modules;modules" ^
    main.py

echo.
if exist "dist\RicohScannerConfig.exe" (
    echo ✔ Gotowe! Plik EXE: dist\RicohScannerConfig.exe
) else (
    echo ✖ Build nieudany — sprawdz komunikaty powyzej.
)

pause
