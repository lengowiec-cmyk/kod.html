; Skrypt Inno Setup dla instalatora Menedzera PDF.
;
; Wymaga NAJPIERW zbudowania aplikacji przez PyInstaller
; (packaging\build_windows.bat), tak by istnial katalog
; ..\dist\PDFManager z plikiem PDFManager.exe.
;
; Kompilacja: zainstaluj Inno Setup (https://jrsoftware.org/isinfo.php)
; na Windows, otworz ten plik w Inno Setup Compiler i wybierz
; Build > Compile (albo z linii polecen: ISCC.exe packaging\installer.iss).
;
; Jezyk ukrainski instalatora (ponizej, [Languages]) wymaga pliku
; Ukrainian.isl - jesli Twoja instalacja Inno Setup go nie zawiera,
; pobierz go ze strony tlumaczen Inno Setup albo usun ta linie (sam
; PROGRAM pozostaje w pelni trojjezyczny niezaleznie od jezyka instalatora).

#define MyAppName "Menedzer PDF"
#define MyAppVersion "0.6.0"
#define MyAppPublisher "PDFManager"
#define MyAppExeName "PDFManager.exe"

[Setup]
AppId={{46C8A9BB-D1D3-4B2E-9C63-5A88FFE537F7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
SetupIconFile=pdfmanager.ico
OutputDir=installer_output
OutputBaseFilename=PDFManager-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
; Instalacja per-uzytkownik (bez uprawnien administratora) - zgodnie z tym,
; ze rejestracja skojarzenia z PDF (patrz [Registry] nizej) i tak dziala
; tylko w HKEY_CURRENT_USER.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
#if FileExists(AddBackslash(CompilerPath) + "Languages\Ukrainian.isl")
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
#endif

[Files]
Source: "..\dist\PDFManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#if DirExists(SourcePath + "..\dist\PDFManagerCLI")
Source: "..\dist\PDFManagerCLI\*"; DestDir: "{app}\CLI"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Odinstaluj {#MyAppName}"; Filename: "{uninstallexe}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "associate"; Description: "Zarejestruj jako opcje otwierania plikow PDF (wyboru domyslnej aplikacji potwierdzasz pozniej w Ustawieniach Windows)"; GroupDescription: "Skojarzenia plikow:"

[Registry]
; To samo, co robi w aplikacji funkcja register_application()
; (pdfmanager/windows/file_association.py) - zgloszenie programu jako
; opcji dla plikow .pdf. NIE ustawia go jako domyslnego - Windows (od
; wersji 8) wymaga, by to osobiscie potwierdzil uzytkownik w Ustawieniach
; > Aplikacje > Aplikacje domyslne (patrz w aplikacji: Ustawienia >
; "Otwieraj wszystkie pliki PDF domyslnie").
Root: HKCU; Subkey: "Software\Classes\PDFManager.Document"; ValueType: string; ValueName: ""; ValueData: "Dokument PDF (Menedzer PDF)"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\PDFManager.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\PDFManager.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"",0"; Tasks: associate
Root: HKCU; Subkey: "Software\PDFManager\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Menedzer PDF"; Tasks: associate
Root: HKCU; Subkey: "Software\PDFManager\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Przegladanie, edycja i zarzadzanie dokumentami PDF"; Tasks: associate
Root: HKCU; Subkey: "Software\PDFManager\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "PDFManager.Document"; Tasks: associate
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PDFManager"; ValueData: "Software\PDFManager\Capabilities"; Tasks: associate

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
