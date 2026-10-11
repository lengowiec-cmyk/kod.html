<#
.SYNOPSIS
    NARZĘDZIE DEWELOPERSKIE — tworzy lokalny certyfikat testowy do podpisywania
    kodu i podpisuje nim zbudowany PDFManager.exe, żeby programista mógł
    sprawdzić podpisany plik na WŁASNYM komputerze podczas pracy nad projektem.

.OPIS
    Certyfikat trafia WYŁĄCZNIE do magazynu wydawców bieżącego użytkownika
    (Cert:\CurrentUser\TrustedPublisher). Ten skrypt:
      - NIE wymaga uprawnień administratora,
      - NIE dotyka Cert:\LocalMachine\Root (żadnego "nowego urzędu certyfikacji"),
      - NIE zmienia ustawień Windows Defender.

    To jest certyfikat TESTOWY, zaufany tylko na tym koncie, na tym komputerze.
    NIE rozwiązuje ostrzeżeń SmartScreen/Defender u Twoich klientów — do tego
    potrzebny jest prawdziwy certyfikat Code Signing od uznanego wydawcy albo
    usługa Microsoft Trusted Signing. Patrz packaging\BUILD_INSTRUCTIONS.md.

.PARAMETER ExePath
    Ścieżka do pliku .exe do podpisania. Domyślnie: dist\PDFManager\PDFManager.exe
    względem katalogu głównego projektu (ustalanego dynamicznie z $PSScriptRoot,
    niezależnie od tego, skąd skrypt jest uruchamiany).

.PARAMETER CertSubject
    Nazwa (Subject) certyfikatu testowego. Pozwala ponownie użyć tego samego
    certyfikatu przy kolejnych uruchomieniach skryptu, zamiast tworzyć nowy.

.PRZYKŁAD
    .\setup_dev_cert.ps1
    .\setup_dev_cert.ps1 -ExePath "C:\inna\sciezka\PDFManager.exe"
#>

param(
    [string]$ExePath = $(Join-Path (Split-Path $PSScriptRoot -Parent) "dist\PDFManager\PDFManager.exe"),
    [string]$CertSubject = "CN=PDFManager Dev Test Certificate",
    [int]$ValidityYears = 3
)

$ErrorActionPreference = "Stop"

function Write-Step($text) { Write-Host $text -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host $text -ForegroundColor Green }
function Write-Warn($text) { Write-Host $text -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host $text -ForegroundColor Red }

Write-Host "=== Lokalny certyfikat testowy (tylko do pracy deweloperskiej) ===" -ForegroundColor Cyan
Write-Host ""

# 1. Sprawdzenie pliku .exe PRZED tworzeniem czegokolwiek.
if (-not (Test-Path $ExePath)) {
    Write-Err "BŁĄD: nie znaleziono pliku .exe w: $ExePath"
    Write-Warn "Najpierw zbuduj aplikację (packaging\build_windows.bat) albo podaj"
    Write-Warn "poprawną ścieżkę parametrem -ExePath."
    exit 1
}
Write-Ok "Znaleziono plik do podpisania: $ExePath"
Write-Host ""

# 2. Ponowne użycie istniejącego certyfikatu testowego, jeśli już istnieje
#    (żeby kolejne uruchomienia nie mnożyły certyfikatów w magazynie).
Write-Step "Sprawdzanie, czy certyfikat testowy już istnieje..."
$existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -eq $CertSubject } |
    Select-Object -First 1

if ($existing) {
    Write-Ok "Znaleziono istniejący certyfikat testowy (odcisk: $($existing.Thumbprint))."
    $cert = $existing
} else {
    Write-Step "Generowanie nowego certyfikatu testowego ($CertSubject)..."
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $CertSubject `
        -CertStoreLocation Cert:\CurrentUser\My `
        -KeyUsage DigitalSignature `
        -FriendlyName "PDFManager Dev Test Certificate" `
        -NotAfter (Get-Date).AddYears($ValidityYears)
    Write-Ok "Utworzono certyfikat (odcisk: $($cert.Thumbprint))."
}
Write-Host ""

# 3. Dodanie do Cert:\CurrentUser\TrustedPublisher — WYŁĄCZNIE bieżący
#    użytkownik, żadnego Root CA, żadnych uprawnień administratora.
Write-Step "Dodawanie certyfikatu do Cert:\CurrentUser\TrustedPublisher..."
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
    [System.Security.Cryptography.X509Certificates.StoreName]::TrustedPublisher,
    [System.Security.Cryptography.X509Certificates.StoreLocation]::CurrentUser
)
$store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
try {
    $store.Add($cert)
    Write-Ok "Certyfikat jest teraz w Cert:\CurrentUser\TrustedPublisher."
} finally {
    $store.Close()
}
Write-Host ""

# 4. Podpisanie pliku .exe (Set-AuthenticodeSignature — nie wymaga instalowania
#    Windows SDK/signtool.exe, w przeciwieństwie do narzędzia signtool).
Write-Step "Podpisywanie: $ExePath"
try {
    Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert `
        -TimestampServer "http://timestamp.digicert.com" | Out-Null
} catch {
    Write-Warn "Znakowanie czasem (TimestampServer) nie powiodło się — podpisuję bez niego."
    Set-AuthenticodeSignature -FilePath $ExePath -Certificate $cert | Out-Null
}

$verify = Get-AuthenticodeSignature -FilePath $ExePath
Write-Host ""
Write-Host "Status podpisu: $($verify.Status)" -ForegroundColor $(if ($verify.Status -eq "Valid") { "Green" } else { "Yellow" })
Write-Host "Podpisujący:    $($verify.SignerCertificate.Subject)"
Write-Host ""

if ($verify.Status -ne "Valid") {
    Write-Warn "Status inny niż 'Valid' jest OCZEKIWANY dla certyfikatu self-signed —"
    Write-Warn "łańcuch zaufania kończy się na Twoim własnym magazynie, nie na"
    Write-Warn "publicznym urzędzie certyfikacji. Do lokalnych testów to wystarcza."
}

Write-Host ""
Write-Warn "PAMIĘTAJ: to podpis TESTOWY, zaufany tylko na tym koncie, na tym komputerze."
Write-Warn "Przed wysłaniem aplikacji do klientów użyj prawdziwego certyfikatu Code"
Write-Warn "Signing (patrz packaging\BUILD_INSTRUCTIONS.md)."
