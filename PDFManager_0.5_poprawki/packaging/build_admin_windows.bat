@echo off
setlocal
cd /d "%~dp0\.."
pyinstaller packaging\pdfmanager_admin.spec --noconfirm
if errorlevel 1 exit /b 1
echo Program wlasciciela: dist\PDFManagerAdmin.exe
endlocal
