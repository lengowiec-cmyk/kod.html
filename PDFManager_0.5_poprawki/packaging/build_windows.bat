@echo off
REM Buduje Menedzer PDF jako samodzielna aplikacje Windows (folder z .exe).
REM Uruchom NA WINDOWS, z katalogu glownego projektu, w aktywowanym
REM srodowisku wirtualnym projektu (.venv) z zainstalowanymi zaleznosciami:
REM
REM     pip install -r requirements.txt -r packaging\requirements-build.txt
REM     packaging\build_windows.bat
REM
REM Wynik: dist\PDFManager\PDFManager.exe
REM Instalator: po zbudowaniu skompiluj packaging\installer.iss w Inno Setup.

setlocal
cd /d "%~dp0\.."

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [BLAD] Nie znaleziono polecenia "pyinstaller". Zainstaluj zaleznosci:
    echo     pip install -r requirements.txt -r packaging\requirements-build.txt
    exit /b 1
)

pyinstaller packaging\pdfmanager.spec --noconfirm
if errorlevel 1 (
    echo [BLAD] Budowanie PyInstaller nie powiodlo sie - sprawdz komunikaty powyzej.
    exit /b 1
)

REM Oddzielna wersja konsolowa do CLI (pomoc, stdout/stderr i kody wyjscia).
pyinstaller packaging\pdfmanager_cli.spec --noconfirm
if errorlevel 1 (
    echo [BLAD] Budowanie PDFManagerCLI nie powiodlo sie.
    exit /b 1
)
xcopy /e /i /y dist\PDFManagerCLI dist\PDFManager\CLI >nul
if errorlevel 1 exit /b 1

REM Osobny aktualizator — klient nie jest programem administratora.
pyinstaller packaging\pdfmanager_updater.spec --noconfirm
if errorlevel 1 exit /b 1
copy /y dist\PDFManagerUpdater.exe dist\PDFManager\PDFManagerUpdater.exe >nul
if errorlevel 1 exit /b 1
python packaging\write_build_manifest.py
if errorlevel 1 exit /b 1

REM --- Podpisanie cyfrowe (opcjonalne) ------------------------------------
REM Gdy masz juz PRAWDZIWY certyfikat Code Signing (nie testowy), uzupelnij
REM dane nizej i odkomentuj wywolanie signtool. Bez tego plik .exe zostaje
REM niepodpisany - SmartScreen/Defender moga go ostrzegawczo oznaczac, patrz
REM packaging\BUILD_INSTRUCTIONS.md (jak zdobyc certyfikat i jak zglosic
REM falszywy alarm do Microsoft, jesli juz teraz plik jest blokowany).
REM
REM set CERT_PFX_PATH=C:\sciezka\do\certyfikatu.pfx
REM set CERT_PASSWORD=TWOJE_HASLO_CERTYFIKATU
REM signtool sign /f "%CERT_PFX_PATH%" /p "%CERT_PASSWORD%" /fd SHA256 ^
REM     /tr http://timestamp.digicert.com /td SHA256 dist\PDFManager\PDFManager.exe
REM if errorlevel 1 (
REM     echo [BLAD] Podpisywanie signtool nie powiodlo sie.
REM     exit /b 1
REM )
REM
REM Do LOKALNYCH testow podpisu (bez prawdziwego certyfikatu) mozesz uzyc:
REM     packaging\setup_dev_cert.ps1
REM To certyfikat testowy, zaufany tylko na Twoim koncie - nie rozwiazuje
REM SmartScreen/Defender u klientow.

echo.
echo Zbudowano: dist\PDFManager\PDFManager.exe
echo Aby utworzyc instalator: zainstaluj Inno Setup (https://jrsoftware.org/isinfo.php)
echo i skompiluj packaging\installer.iss (prawym przyciskiem myszy -^> Compile,
echo albo z linii polecen: ISCC.exe packaging\installer.iss).
echo.
echo Przypomnienie: zob. packaging\BUILD_INSTRUCTIONS.md w sprawie podpisu
echo Code Signing i zglaszania falszywych alarmow Defender.
endlocal
