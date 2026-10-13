import sys
import os
import time
import re
import json
import hashlib
import datetime
import locale
import socket
import ctypes
import subprocess
import threading
import base64
import getpass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
import urllib3

from PySide6.QtCore import Qt, Signal, QObject, QFileSystemWatcher, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QTextEdit, QGroupBox, QMessageBox, QComboBox, QCheckBox, QInputDialog
)

# Nowsze urządzenia Ricoh (seria IM / Smart Operation Panel) czasem wymuszają
# HTTPS z certyfikatem self-signed wygenerowanym przez samo urządzenie — to
# normalne dla sprzętu w sieci lokalnej, nie luka bezpieczeństwa per se, ale
# `requests` domyślnie zgłasza ostrzeżenie przy każdym takim połączeniu.
# Wyciszamy tylko to jedno ostrzeżenie (InsecureRequestWarning); reszta
# zachowań `requests` (np. weryfikacja połączeń do internetu) jest nietknięta.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

APP_VERSION = "2026-10-04 · SSL-FTP + lista SOAP (v16)"
APP_TITLE = "Ricoh Universal Fast Setup PRO — SMB / FTP"
APP_TITLE = f"{APP_TITLE} [{APP_VERSION}]"
COPYRIGHT_TITLE = "Copyright KSEROART Artur Biel"

# Kod dostępu do uruchomienia programu — przechowywany jako skrót SHA-256 z solą,
# nie jako jawny tekst (nie da się go odczytać zwykłym przeglądaniem pliku EXE).
_ACCESS_SALT = "KSEROART|Artur Biel|ricoh-scan"
_ACCESS_HASH = "07d3b7c74c0c3df4b245b202eebfe8df4715f17c0b2fc936d449b13ac1685a05"


def verify_access_code(code):
    return hashlib.sha256((_ACCESS_SALT + str(code).strip()).encode("utf-8")).hexdigest() == _ACCESS_HASH
TARGET_USER = "skaner"
TARGET_PASS = "skaner"
TARGET_FOLDER = r"C:\Skany"
SHARE_NAME = "skany"
FTP_PASSIVE_PORT_START = 50000
FTP_PASSIVE_PORT_END = 50100

RICOH_PROFILES = [
    {
        "name": "IM seria (nowe modele)",
        "detect": ["im c2000", "im c2500", "im c3000", "im c3500", "im c4500", "im c6000", "im 2702", "im c300"],
        "base_path": "/web/guest/{lang}/websys/webArch",
        "method": "form_new", "lang": "en"
    },
    {
        "name": "MP C seria (kolorowe)",
        "detect": ["mp c2003", "mp c2503", "mp c3003", "mp c3503", "mp c4503", "mp c2004", "mp c3004", "mp c305"],
        "base_path": "/web/guest/{lang}/websys/webArch",
        "method": "form_old", "lang": "en"
    },
    {
        "name": "MP mono seria",
        "detect": ["mp 2014", "mp 2554", "mp 3054", "mp 501", "mp 601", "mp 2001", "mp 2501"],
        "base_path": "/web/guest/{lang}/websys/webArch",
        "method": "form_old", "lang": "en"
    },
    {
        # base_path i method POTWIERDZONE analizą pliku HAR z rzeczywistej
        # sesji przeglądarki na Ricoh Aficio MP 161 — poprzednia wersja
        # (/web/entry/{lang}/websys/webArch) była BŁĘDNA, prawdziwy katalog
        # to /web/entry/{lang}/address/, a formularz zapisu to adrsSetUser.cgi
        # (nie addressBook.cgi jak zakładano dla innych profili).
        "name": "Aficio / MP 161/171/201 (stare, potwierdzone przez HAR)",
        "detect": ["mp 161", "mp 171", "mp 201", "aficio 1515", "aficio 161", "aficio 201"],
        "base_path": "/web/entry/{lang}/address",
        "method": "mp161_form", "lang": "pl",
        "save_endpoint": "adrsSetUser.cgi",
    }
]

FALLBACK_PATHS = [
    ("/web/guest/en/websys/webArch", "form_new"),
    ("/web/entry/pl/websys/webArch", "form_entry"),
    ("/web/entry/en/websys/webArch", "form_entry"),
    # Potwierdzona przez HAR ścieżka MP 161 (polska wersja panelu) — jako
    # fallback na wypadek gdyby detekcja profilu po treści strony głównej
    # zawiodła. Celowo BEZ angielskiego wariantu /web/entry/en/address:
    # sekwencja 3-etapowa (SetUser->EditPassword->SetUser) na złym
    # wariancie językowym potrafi "połowicznie" się powieść (kroki 1-2 OK,
    # krok 3 fail), zostawiając śmieciowy, niedokończony wpis na urządzeniu
    # zanim program w końcu trafi na poprawną ścieżkę.
    ("/web/entry/pl/address", "mp161_form"),
]


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


_DLOG_LOCK = threading.Lock()


def _app_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()


DETAILED_LOG_PATH = os.path.join(_app_dir(), "ricoh_log_szczegolowy.txt")


def dlog(msg):
    """Dopisuje linię z znacznikiem czasu do trwałego, szczegółowego logu
    (ricoh_log_szczegolowy.txt obok programu). Zapisuje WSZYSTKO, co program
    pokazuje w konsoli, plus pełny raport diagnostyczny."""
    try:
        with _DLOG_LOCK:
            if os.path.exists(DETAILED_LOG_PATH) and os.path.getsize(DETAILED_LOG_PATH) > 3_000_000:
                os.replace(DETAILED_LOG_PATH, DETAILED_LOG_PATH + ".old")
            with open(DETAILED_LOG_PATH, "a", encoding="utf-8") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for line in str(msg).splitlines() or [""]:
                    f.write(f"[{ts}] {line}\n")
    except Exception:
        pass


def _get_console_encoding():
    """Wykrywa realną stronę kodową aktywnej konsoli cmd.exe zamiast
    zakładać cp852 na sztywno (to strona kodowa TYLKO dla polskiego DOS —
    na EN-Windows jest to cp437, więc sztywne cp852 cicho psuje znaki
    diakrytyczne/nazwy kart sieciowych na innych wersjach językowych)."""
    try:
        result = subprocess.run("chcp", shell=True, capture_output=True, text=True, timeout=5)
        match = re.search(r"(\d{3,5})", result.stdout)
        if match:
            return f"cp{match.group(1)}"
    except Exception:
        pass
    return locale.getpreferredencoding(False) or "utf-8"


_CONSOLE_ENCODING = None


def run_cmd(cmd, timeout=60, powershell=False):
    """
    Wykonuje polecenie w cmd.exe. `input='\\n'` zapobiega zawieszeniu,
    jeśli komenda o coś zapyta interaktywnie (np. potwierdzenie).

    powershell=True wymusza kodowanie UTF-8 — natywne dla `-Command` w
    PowerShell 5.1+ i obowiązkowe dla PowerShell 7 (pwsh.exe), które
    domyślnie NIE używa strony kodowej cmd.exe. Używaj tej flagi dla
    wszystkich wywołań `powershell -Command "..."` w kodzie.
    """
    global _CONSOLE_ENCODING
    if powershell:
        encoding = "utf-8"
    else:
        if _CONSOLE_ENCODING is None:
            _CONSOLE_ENCODING = _get_console_encoding()
        encoding = _CONSOLE_ENCODING

    try:
        res = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            encoding=encoding, errors="replace", input="\n", timeout=timeout
        )
        return (res.stdout + res.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"[UWAGA] Przekroczono czas ({timeout}s): {cmd[:60]}"
    except Exception as e:
        return f"Błąd: {e}"


def run_cmd_with_code(cmd, timeout=60, powershell=False):
    """
    Wariant run_cmd(), który ZWRACA TEŻ KOD WYJŚCIA procesu (returncode) —
    (output_text, exit_code). Kod wyjścia to jedyny NIEZAWODNY, niezależny
    od języka/lokalizacji Windows sposób sprawdzenia, czy polecenie się
    powiodło: 0 = sukces, cokolwiek innego = błąd.

    BŁĄD ZNALEZIONY W CAŁYM PROGRAMIE: cała logika testów weryfikacyjnych
    (np. test_local_share_access) opierała się WYŁĄCZNIE na dopasowywaniu
    konkretnych fraz tekstowych w wyjściu komend (np. "błąd systemu") — ale
    prawdziwe komunikaty Windows różnią się w zależności od wersji językowej
    systemu i konkretnego kodu błędu (np. "System error 86", "błąd 1326",
    różne sformułowania na PL/EN Windows). Dopasowanie tekstu regularnie
    dawało fałszywe pozytywy: komenda faktycznie się nie powiodła (np. złe
    hasło przy `net use`), ale żadna ze sprawdzanych fraz nie pasowała do
    faktycznego komunikatu, więc test przechodził dalej i "sprawdzał zapis"
    na już przecież niezamontowanym udziale.
    """
    global _CONSOLE_ENCODING
    if powershell:
        encoding = "utf-8"
    else:
        if _CONSOLE_ENCODING is None:
            _CONSOLE_ENCODING = _get_console_encoding()
        encoding = _CONSOLE_ENCODING

    try:
        res = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            encoding=encoding, errors="replace", input="\n", timeout=timeout
        )
        return (res.stdout + res.stderr).strip(), res.returncode
    except subprocess.TimeoutExpired:
        return f"[UWAGA] Przekroczono czas ({timeout}s): {cmd[:60]}", -1
    except Exception as e:
        return f"Błąd: {e}", -1


def validate_ip(ip):
    """Sprawdza poprawność formatu adresu IPv4 (4 oktety 0-255)."""
    if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
        return False
    return all(0 <= int(part) <= 255 for part in ip.split("."))


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_local_hostname():
    """
    Zwraca nazwę NetBIOS/hostname komputera — POTWIERDZONE przechwyceniem
    ruchu SDMA (Wireshark), że oficjalne narzędzie Ricoh do zarządzania
    książką adresową buduje ścieżkę UNC z nazwą komputera
    (np. "\\\\ARTUR-LAPTOP\\skany"), NIE z adresem IP, w przeciwieństwie do
    tego, co zakładała wcześniejsza wersja kodu odtwarzająca formularze HTML.
    """
    try:
        return socket.gethostname()
    except Exception:
        return get_local_ip()


def list_local_ips():
    """
    Zwraca listę wszystkich lokalnych adresów IPv4 komputera (wszystkie
    karty sieciowe: Ethernet, Wi-Fi, VPN, adaptery wirtualne itd.) —
    potrzebne, żeby użytkownik mógł wskazać właściwy adres w sytuacji, gdy
    komputer ma kilka interfejsów naraz (np. aktywny VPN dodaje wirtualną
    kartę z innym zakresem adresów niż fizyczna sieć LAN z drukarką).
    Adres wykryty przez get_local_ip() (ten używany do połączenia z
    internetem) jest umieszczany na początku listy jako sugerowany domyślny.
    """
    ips = []
    try:
        hostname = socket.gethostname()
        # getaddrinfo zwraca też adresy IPv6 i duplikaty — filtrujemy do
        # unikalnych adresów IPv4.
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass

    default_ip = get_local_ip()
    if default_ip not in ips and default_ip != "127.0.0.1":
        ips.insert(0, default_ip)
    elif default_ip in ips:
        ips.remove(default_ip)
        ips.insert(0, default_ip)

    if not ips:
        ips = [default_ip]

    return ips


def get_network_interfaces_detailed(logger_cb=None):
    """
    Zwraca listę słowników {ip, netmask, subnet_prefix} dla każdej aktywnej
    karty sieciowej IPv4 komputera, na podstawie realnej maski podsieci
    (nie zgadywania /24). Krytyczne dla sytuacji, gdy komputer ma kilka
    kart w RÓŻNYCH podsieciach naraz (np. Wi-Fi w 192.168.0.0/24, Ethernet
    do drukarki w 192.168.1.0/24) — bez tego program przeszukiwał tylko
    jedną, domyślną podsieć i nigdy nie widział urządzeń podłączonych
    kablem w innej sieci.
    """
    interfaces = []
    try:
        out = run_cmd(
            'powershell -NoProfile -Command '
            '"Get-NetIPAddress -AddressFamily IPv4 | '
            'Where-Object {$_.IPAddress -notlike \'127.*\' -and $_.IPAddress -notlike \'169.254.*\'} | '
            'Select-Object IPAddress,PrefixLength,InterfaceAlias | ConvertTo-Json -Compress"',
            powershell=True, timeout=20
        )
        data = json.loads(out)
        if isinstance(data, dict):  # PowerShell zwraca dict (nie listę) dla 1 elementu
            data = [data]
        for entry in data:
            interfaces.append({
                "ip": entry["IPAddress"],
                "prefix_len": int(entry["PrefixLength"]),
                "alias": entry.get("InterfaceAlias", "?"),
            })
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        if logger_cb:
            logger_cb(f"  UWAGA: nieprawidłowa odpowiedź PowerShell (JSON): {e}")
    except Exception as e:
        if logger_cb:
            logger_cb(f"  UWAGA: nie udało się odczytać kart sieciowych: {e}")

    if not interfaces:
        # Fallback — przynajmniej jeden adres z list_local_ips(), zakładamy /24
        for ip in list_local_ips():
            interfaces.append({"ip": ip, "prefix_len": 24, "alias": "?"})

    return interfaces


def subnet_hosts_from_prefix(ip, prefix_len):
    """
    Zwraca listę adresów IP do przeskanowania w podsieci danej przez ip/prefix_len.
    Dla typowych sieci domowych/biurowych (/24 i większe, tj. prefix_len>=23)
    ograniczamy się do skanowania w rozsądnym czasie: dla /24 to 254 adresy,
    dla mniejszych masek (większe sieci, prefix_len<23) OGRANICZAMY do
    najbliższego /24 wokół adresu komputera, żeby skanowanie nie trwało
    wiecznie w bardzo dużych sieciach firmowych.
    """
    parts = ip.split(".")
    if prefix_len < 23:
        prefix_len = 24  # bezpieczny fallback dla bardzo dużych sieci

    if prefix_len >= 24:
        base = ".".join(parts[:3])
        return [f"{base}.{i}" for i in range(1, 255)]
    else:
        # /23: dwie sąsiednie podsieci /24
        base = ".".join(parts[:3])
        third_octet = int(parts[2])
        even_base = third_octet - (third_octet % 2)
        results = []
        for offset in (0, 1):
            b = ".".join(parts[:2] + [str(even_base + offset)])
            results.extend(f"{b}.{i}" for i in range(1, 255))
        return results


def scan_network_for_ricoh(logger_cb):
    interfaces = get_network_interfaces_detailed(logger_cb)

    if not interfaces:
        logger_cb("  Nie wykryto żadnej aktywnej karty sieciowej z adresem IPv4.")
        return []

    logger_cb(f"Wykryte karty sieciowe ({len(interfaces)}):")
    for iface in interfaces:
        logger_cb(f"  • {iface['alias']}: {iface['ip']}/{iface['prefix_len']}")

    all_hosts = []
    seen_subnets = set()
    for iface in interfaces:
        subnet_key = (".".join(iface["ip"].split(".")[:3]), iface["prefix_len"])
        if subnet_key in seen_subnets:
            continue
        seen_subnets.add(subnet_key)
        all_hosts.extend(subnet_hosts_from_prefix(iface["ip"], iface["prefix_len"]))

    found_ips = []

    def probe_http(ip, port=80):
        """Próbuje HTTP na danym porcie, zwraca treść strony albo None."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            reachable = sock.connect_ex((ip, port)) == 0
            sock.close()
            if not reachable:
                return None
            r = requests.get(f"http://{ip}/", timeout=0.8)
            return r.text
        except Exception:
            return None

    def probe_https(ip, port=443):
        """Próbuje HTTPS na danym porcie (verify=False — self-signed cert
        na urządzeniu w sieci lokalnej jest normalny), zwraca treść albo None."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            reachable = sock.connect_ex((ip, port)) == 0
            sock.close()
            if not reachable:
                return None
            r = requests.get(f"https://{ip}/", timeout=0.8, verify=False)
            return r.text
        except Exception:
            return None

    def check_ip(ip):
        # Najpierw HTTP (port 80) — starsze urządzenia (Aficio/MP) zwykle
        # tam odpowiadają. Jeśli port 80 nie odpowiada lub treść nie jest
        # rozpoznana jako Ricoh, próbujemy HTTPS (port 443) — nowsze
        # urządzenia (seria IM / Smart Operation Panel) często wymuszają
        # szyfrowane połączenie i mogą w ogóle nie nasłuchiwać na porcie 80.
        content = probe_http(ip)
        if content is None:
            content = probe_https(ip)

        if content and any(
            x in content.lower() for x in ["ricoh", "web image monitor", "wim", "aficio"]
        ):
            found_ips.append(ip)

    logger_cb(
        f"Skanowanie {len(seen_subnets)} podsieci "
        f"({len(all_hosts)} adresów łącznie, HTTP i HTTPS)..."
    )
    with ThreadPoolExecutor(max_workers=40) as executor:
        for ip in all_hosts:
            executor.submit(check_ip, ip)

    return found_ips


def set_network_private(logger_cb=print):
    """
    Przełącza profil aktywnego połączenia sieciowego z 'Public' na 'Private'.
    Windows domyślnie blokuje udostępnianie plików/drukarek w sieciach
    oznaczonych jako publiczne (np. świeżo podłączony kabel/Wi-Fi) —
    to często jedyny powód, dla którego SMB "nie działa", mimo poprawnej
    reszty konfiguracji.
    """
    logger_cb("--- Zmiana profilu sieci na 'Prywatna' (wymagane dla udostępniania plików) ---")
    out = run_cmd(
        'powershell -NoProfile -Command '
        '"Get-NetConnectionProfile | Where-Object {$_.NetworkCategory -eq \'Public\'} '
        '| Set-NetConnectionProfile -NetworkCategory Private"',
        powershell=True
    )
    logger_cb(f"  {out or '(brak sieci publicznych do zmiany — już Private/Domain)'}")


def enable_smb1_protocol(logger_cb=print):
    """
    Włącza SAM protokół SMBv1 (bez osłabiania uwierzytelniania) — starsze
    urządzenia Ricoh (Aficio, MP mono/C sprzed ok. 2012) potrafią mówić
    tylko tym dialektem SMB. To ograniczona, uzasadniona zmiana kompatybilności:
    włącza stary protokół transportu plików, ale NIE dotyka mechanizmu
    uwierzytelniania (NTLM) ani nie zezwala na dostęp bez hasła — te dwie
    rzeczy są dostępne wyłącznie jako osobna, opcjonalna akcja w GUI
    (sekcja "Zaawansowane / Diagnostyka starszych urządzeń"), wymagająca
    jawnej zgody użytkownika — patrz apply_legacy_auth_compatibility().
    """
    logger_cb("--- Włączanie protokołu SMBv1 (kompatybilność ze starszymi urządzeniami) ---")
    out = run_cmd(
        'powershell -NoProfile -Command '
        '"Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart"',
        powershell=True, timeout=180
    )
    logger_cb(f"  {out}")
    if "restart" in out.lower() or "ponown" in out.lower():
        logger_cb("  UWAGA: system może zasygnalizować potrzebę ponownego uruchomienia, "
                   "żeby zmiana w pełni zadziałała.")


def apply_legacy_auth_compatibility(logger_cb=print):
    """
    WYKONUJE zmiany w rejestrze osłabiające uwierzytelnianie SMB:
    - LmCompatibilityLevel=1 (akceptacja NTLMv1),
    - AllowInsecureGuestAuth=1 (dostęp do udziałów bez uwierzytelnienia).

    UWAGA: ta funkcja jest wywoływana WYŁĄCZNIE z GUI, przyciskiem w sekcji
    "Zaawansowane / Diagnostyka starszych urządzeń", i TYLKO po tym, jak
    użytkownik jawnie potwierdzi ostrzeżenie o ryzyku (QMessageBox.warning).
    Nigdy nie jest wywoływana automatycznie przez setup_windows_environment
    ani przy zwykłym przebiegu "KONFIGURUJ (1-KLIK)".

    Obie zmiany obniżają bezpieczeństwo CAŁEGO komputera (nie tylko
    komunikacji z drukarką):
    - NTLMv1 jest podatny na przechwycenie i złamanie hasła z ruchu
      sieciowego (narzędzia typu ntlmrelayx robią to rutynowo),
    - Insecure Guest Auth to mechanizm historycznie wykorzystywany przez
      robaki sieciowe (np. WannaCry) do rozprzestrzeniania się bez hasła.
    Rozważ cofnięcie tych zmian po zakończeniu pracy ze starym urządzeniem.
    """
    logger_cb("--- Włączanie trybu zgodności dla starszych urządzeń (NTLMv1 + Guest Auth) ---")
    logger_cb("  UWAGA: to obniża poziom bezpieczeństwa całego systemu Windows.")

    out1 = run_cmd(
        'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Lsa" '
        '/v LmCompatibilityLevel /t REG_DWORD /d 1 /f'
    )
    logger_cb(f"  {out1}")

    out2 = run_cmd(
        'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\LanmanWorkstation" '
        '/v AllowInsecureGuestAuth /t REG_DWORD /d 1 /f'
    )
    logger_cb(f"  {out2}")

    success = "[BŁĄD]" not in out1 and "[BŁĄD]" not in out2
    if success:
        logger_cb("  ✔ Tryb zgodności włączony. Zalecany restart usługi Serwer "
                   "(lub komputera) dla pewności, że zmiana w pełni obowiązuje.")
    else:
        logger_cb("  ✖ Nie udało się w pełni zastosować zmian — sprawdź uprawnienia administratora.")
    return success


def revert_legacy_auth_compatibility(logger_cb=print):
    """
    Przywraca bezpieczne wartości domyślne (cofnięcie apply_legacy_auth_compatibility).
    LmCompatibilityLevel=3 to bezpieczny domyślny poziom Windows (NTLMv2 only).
    """
    logger_cb("--- Przywracanie bezpiecznych ustawień uwierzytelniania ---")
    out1 = run_cmd(
        'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Lsa" '
        '/v LmCompatibilityLevel /t REG_DWORD /d 3 /f'
    )
    out2 = run_cmd(
        'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\LanmanWorkstation" '
        '/v AllowInsecureGuestAuth /t REG_DWORD /d 0 /f'
    )
    logger_cb(f"  {out1}")
    logger_cb(f"  {out2}")
    logger_cb("  ✔ Przywrócono bezpieczne ustawienia domyślne.")


def add_firewall_rule_idempotent(rule_name, port, remote_ip, logger_cb=print):
    """
    Usuwa istniejącą regułę o tej nazwie PRZED dodaniem nowej. `netsh` nie
    ma unikalności po `name` — bez tego kroku każde kolejne uruchomienie
    programu (np. z inną drukarką, innym IP) dokłada nową regułę zamiast
    zastąpić starą, więc po kilku konfiguracjach zapora ma kilka reguł
    o tej samej nazwie z martwymi, historycznymi adresami IP.

    BŁĄD ZNALEZIONY I NAPRAWIONY: brak jawnego `profile=any` — bez tego
    `netsh` tworzy regułę wyłącznie dla profilu sieci AKTYWNEGO w chwili
    tworzenia (Domain/Private/Public). Jeśli profil sieci zmieni się
    później (np. Windows przełączy sieć z Private na Domain po dołączeniu
    do domeny, albo po prostu inny profil jest aktywny niż podczas
    pierwszej konfiguracji), reguła przestaje obowiązywać mimo że nadal
    "istnieje" — co dokładnie pasuje do scenariusza "SMB skonfigurowany
    (reguła jest), ale skany i tak nie wpadają". Oficjalne narzędzie Ricoh
    (STFCT) opisuje dokładnie ten problem w swojej dokumentacji jako
    "communication port (TCP 445) on the computer side is blocked".
    """
    run_cmd(f'netsh advfirewall firewall delete rule name="{rule_name}"')
    out = run_cmd(
        f'netsh advfirewall firewall add rule name="{rule_name}" '
        f'dir=in action=allow protocol=TCP localport={port} remoteip={remote_ip} profile=any'
    )
    logger_cb(f"  {rule_name} (port {port}): {out}")
    return "[BŁĄD]" not in out


def setup_windows_environment(device_ip, protocol="smb", logger_cb=print):
    """
    Tworzy konto lokalne BEZ uprawnień administratora (zasada najmniejszych
    uprawnień — konto służy wyłącznie do zapisu w jednym folderze skanów),
    folder z uprawnieniami NTFS ograniczonymi do tego konta (nie 'Everyone'),
    profil sieci Private, protokół SMB1 dla starszych urządzeń, i reguły
    zapory ograniczone do adresu IP konkretnej drukarki (nie dla całej
    sieci/internetu).
    """
    set_network_private(logger_cb)
    enable_smb1_protocol(logger_cb)

    logger_cb("--- Tworzenie konta 'skany' (bez uprawnień administratora) ---")
    out, code = run_cmd_with_code(f'net user {TARGET_USER} "{TARGET_PASS}" /add')
    already_exists = code != 0 and any(x in out for x in ["2224", "już istnieje", "already exists"])
    if already_exists:
        logger_cb("  Konto już istnieje — aktualizuję hasło")
        run_cmd_with_code(f'net user {TARGET_USER} "{TARGET_PASS}"')
    elif code != 0:
        logger_cb(f"  ✖ Tworzenie konta NIE POWIODŁO SIĘ (kod: {code}): {out[:200]}")
    else:
        logger_cb(f"  ✔ Konto '{TARGET_USER}' utworzone pomyślnie.")

    # Hasło niewygasające — nowoczesny sposób (Set-LocalUser); WMIC jest
    # przestarzałe i usunięte z części nowych wersji Windows.
    run_cmd(f'powershell -NoProfile -Command "Set-LocalUser -Name \'{TARGET_USER}\' -PasswordNeverExpires $true"', powershell=True)

    # UWAGA BEZPIECZEŃSTWA: konto 'skany' celowo NIE jest dodawane do grupy
    # Administratorów. Do zapisu plików w jednym udostępnionym folderze
    # wystarczą uprawnienia NTFS/udziału nadane niżej — pełne uprawnienia
    # administratora systemu byłyby nieuzasadnionym ryzykiem: gdyby ktoś
    # poznał to hasło (zapisane jawnie w kodzie i kopiowane do schowka w
    # raporcie), dostałby kontrolę nad całym komputerem, nie tylko dostęp
    # do folderu skanów.

    logger_cb("--- Tworzenie folderu i uprawnień NTFS (tylko dla konta 'skany') ---")
    if not os.path.exists(TARGET_FOLDER):
        os.makedirs(TARGET_FOLDER)
    run_cmd(f'icacls "{TARGET_FOLDER}" /grant {TARGET_USER}:(OI)(CI)F')
    # Celowo NIE nadajemy praw grupie 'Everyone/Wszyscy' — pełny dostęp do
    # folderu skanów dla każdego urządzenia w sieci lokalnej to niepotrzebna
    # luka, zwłaszcza że skany mogą zawierać poufne dokumenty.

    if protocol == "smb":
        logger_cb("--- Konfiguracja Udziału Sieciowego (SMB) ---")
        run_cmd_with_code(f'net share {SHARE_NAME} /delete')
        share_out, share_code = run_cmd_with_code(
            f'net share {SHARE_NAME}="{TARGET_FOLDER}" /GRANT:{TARGET_USER},FULL'
        )
        if share_code == 0:
            logger_cb(f"  ✔ Udział '{SHARE_NAME}' utworzony pomyślnie.")
        else:
            logger_cb(f"  ✖ Utworzenie udziału '{SHARE_NAME}' NIE POWIODŁO SIĘ (kod: {share_code}): {share_out}")
        # Firewall ograniczony do adresu IP konkretnej drukarki — port SMB
        # (445) jest jednym z najczęściej atakowanych portów w sieciach
        # lokalnych (m.in. przez robaka WannaCry), więc nie otwieramy go
        # dla każdego adresu.
        add_firewall_rule_idempotent("Ricoh SMB Scan", 445, device_ip, logger_cb)
    else:
        logger_cb("--- Konfiguracja Zapory dla FTP (Port 21 + zakres pasywny) ---")
        add_firewall_rule_idempotent("Ricoh FTP Scan", 21, device_ip, logger_cb)
        # Zakres portów pasywnych — netsh nie obsługuje remoteip+range w
        # jednej idempotentnej funkcji jak wyżej (localport to zakres, nie
        # pojedynczy port), więc reguła jest budowana bezpośrednio, ale
        # nadal z usunięciem poprzedniej wersji przed dodaniem nowej.
        run_cmd(f'netsh advfirewall firewall delete rule name="Ricoh FTP Scan Passive"')
        out = run_cmd(
            f'netsh advfirewall firewall add rule name="Ricoh FTP Scan Passive" '
            f'dir=in action=allow protocol=TCP localport={FTP_PASSIVE_PORT_START}-{FTP_PASSIVE_PORT_END} '
            f'remoteip={device_ip} profile=any'
        )
        logger_cb(f"  Ricoh FTP Scan Passive: {out}")

    logger_cb("--- Wykluczenie folderu w Windows Defender ---")
    run_cmd(f'powershell -NoProfile -Command "Add-MpPreference -ExclusionPath \'{TARGET_FOLDER}\'"', powershell=True)

    logger_cb("")
    logger_cb("ℹ Konfiguracja podstawowa zakończona. Jeśli bardzo stare urządzenie")
    logger_cb("  (Aficio/MP sprzed ok. 2012) nadal nie może się połączyć mimo SMB1,")
    logger_cb("  sprawdź sekcję 'Zaawansowane / Diagnostyka starszych urządzeń' w GUI.")


def is_iis_ftp_installed(logger_cb=None):
    """
    Sprawdza, czy rola IIS-FTPServer jest już zainstalowana (przez
    Get-WindowsOptionalFeature) — pozwala uniknąć zbędnej, czasochłonnej
    reinstalacji przy każdym uruchomieniu programu.
    """
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command '
        '"(Get-WindowsOptionalFeature -Online -FeatureName IIS-FTPServer).State"',
        powershell=True, timeout=30
    )
    installed = code == 0 and "enabled" in out.lower()
    if logger_cb:
        logger_cb(f"  Rola IIS-FTPServer: {'zainstalowana' if installed else 'brak / wyłączona'}")
    return installed


def install_iis_ftp_role(logger_cb=print):
    """
    Włącza rolę Windows IIS wraz z serwerem FTP (IIS-WebServerRole,
    IIS-FTPServer, IIS-FTPSvc, IIS-FTPExtensibility) — wbudowany w system
    serwer FTP, bez zależności od zewnętrznych bibliotek Pythona (pyftpdlib).
    To trwała, systemowa usługa Windows, nie proces uruchamiany razem z tym
    programem — raz włączona, działa niezależnie od tego, czy ten program
    jest otwarty.

    Zwraca True jeśli rola jest gotowa do użycia (już była zainstalowana
    lub instalacja się powiodła).
    """
    if is_iis_ftp_installed(logger_cb):
        return True

    logger_cb("--- Instalowanie roli Windows: IIS FTP Server (może potrwać kilka minut) ---")
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command '
        '"Enable-WindowsOptionalFeature -Online -FeatureName '
        'IIS-WebServerRole,IIS-WebServer,IIS-CommonHttpFeatures,IIS-FTPServer,'
        'IIS-FTPSvc,IIS-FTPExtensibility,IIS-ManagementConsole -All -NoRestart"',
        powershell=True, timeout=600
    )
    if code != 0:
        logger_cb(f"  ✖ Instalacja roli IIS FTP nie powiodła się (kod: {code}): {out}")
        return False

    logger_cb("  ✔ Rola IIS FTP Server zainstalowana.")
    if "restartneeded" in out.lower() and "true" in out.lower():
        logger_cb("  UWAGA: system może zasygnalizować potrzebę ponownego uruchomienia.")
    return True


def configure_iis_ftp_site(folder, username, port=21,
                            passive_port_start=FTP_PASSIVE_PORT_START,
                            passive_port_end=FTP_PASSIVE_PORT_END,
                            external_ip=None,
                            logger_cb=print):
    """
    Tworzy (lub aktualizuje, jeśli już istnieje) witrynę FTP w IIS wskazującą
    na `folder`, z autoryzacją dla `username` (konto Windows TARGET_USER) i
    zezwoleniem na odczyt/zapis. Konfiguruje też tryb pasywny w stałym
    zakresie portów (potrzebne dla reguł zapory).

    Używa `appcmd.exe` (wbudowane narzędzie administracyjne IIS) — działa
    identycznie na każdej wersji Windows z zainstalowaną rolą IIS-FTPServer,
    bez potrzeby dodatkowych modułów PowerShell (WebAdministration bywa
    niedostępny na Windows klienckich, appcmd zawsze jest częścią IIS).
    """
    appcmd = r'%windir%\system32\inetsrv\appcmd.exe'
    site_name = "SkanerFTP"

    logger_cb(f"--- Konfiguracja witryny FTP w IIS (port {port}, folder {folder}) ---")

    # Usuń istniejącą witrynę o tej samej nazwie — idempotencja, żeby
    # ponowne uruchomienie programu nie tworzyło duplikatów/konfliktów.
    run_cmd_with_code(f'{appcmd} delete site "{site_name}"')

    # Witryny FTP z poprzednich wersji tego programu (np. 'RicohScannerFTP')
    # zajmowały port 21 i blokowały start nowej witryny (zdarzenie FTPSVC 13:
    # "powiązanie :21: jest już używane"). Własne usuwamy, cudze tylko zgłaszamy.
    sites_out, _ = run_cmd_with_code(f'{appcmd} list site')
    for line in sites_out.splitlines():
        m = re.search(r'SITE "([^"]+)".*bindings:([^,)]*)', line)
        if not m:
            continue
        other, bindings = m.group(1), m.group(2)
        if other == site_name or f"ftp/*:{port}:" not in bindings:
            continue
        if other in ("RicohScannerFTP",):
            run_cmd_with_code(f'{appcmd} delete site "{other}"')
            logger_cb(f"  Usunięto starą witrynę FTP '{other}' (zajmowała port {port}).")
        else:
            logger_cb(f"  ⚠ Inna witryna FTP '{other}' używa portu {port} — wyłącz ją lub usuń, "
                      f"inaczej drukarka połączy się z nią zamiast z '{site_name}'.")

    out, code = run_cmd_with_code(
        f'{appcmd} add site /name:"{site_name}" /bindings:ftp/*:{port}: '
        f'/physicalPath:"{folder}"'
    )
    if code != 0:
        logger_cb(f"  ✖ Utworzenie witryny FTP nie powiodło się (kod: {code}): {out}")
        return False
    logger_cb(f"  ✔ Witryna FTP '{site_name}' utworzona.")

    # Autoryzacja: zezwól TARGET_USER na odczyt i zapis w tej witrynie.
    auth_out, auth_code = run_cmd_with_code(
        f'{appcmd} set config "{site_name}" '
        f'-section:system.ftpServer/security/authorization '
        f'"/+[accessType=\'Allow\',users=\'{username}\',permissions=\'Read,Write\']" '
        f'/commit:apphost'
    )
    if auth_code != 0:
        logger_cb(f"  ✖ Konfiguracja autoryzacji FTP nie powiodła się (kod: {auth_code}): {auth_out}")
        return False

    # Uwierzytelnianie Basic, wyłączenie anonimowego i — KLUCZOWE — dopuszczenie
    # połączeń BEZ SSL. Log FTP pokazał: USER skaner -> 534 "SSL policy requires
    # SSL for control channel" — drukarka łączy się zwykłym FTP, więc serwer ją
    # odrzucał. Ustawienia FTP zapisujemy w system.applicationHost/sites
    # (stara ścieżka system.ftpServer/security/authentication... dawała
    # "Nieznana sekcja konfiguracyjna" i nigdy nie była stosowana).
    sec = f"/[name='{site_name}'].ftpServer.security"
    for label, setting in (
        ("Basic włączone", f"{sec}.authentication.basicAuthentication.enabled:True"),
        ("anonimowe wyłączone", f"{sec}.authentication.anonymousAuthentication.enabled:False"),
        ("SSL kanału sterowania: dozwolony (nie wymagany)", f"{sec}.ssl.controlChannelPolicy:SslAllow"),
        ("SSL kanału danych: dozwolony (nie wymagany)", f"{sec}.ssl.dataChannelPolicy:SslAllow"),
    ):
        o, c = run_cmd_with_code(
            f'{appcmd} set config -section:system.applicationHost/sites "{setting}" /commit:apphost'
        )
        logger_cb(f"  {'✔' if c == 0 else '✖'} {label}" + ("" if c == 0 else f" (kod {c}): {o[:150]}"))

    # Tryb pasywny w stałym zakresie portów — potrzebne, żeby reguła
    # zapory mogła otworzyć dokładnie ten zakres (bez tego IIS losuje
    # porty pasywne z całego dostępnego zakresu, co uniemożliwia sensowną
    # regułę firewalla).
    run_cmd_with_code(
        f'{appcmd} set config /section:system.applicationHost/sites '
        f'/siteDefaults.ftpServer.firewallSupport.lowDataChannelPort:{passive_port_start} '
        f'/siteDefaults.ftpServer.firewallSupport.highDataChannelPort:{passive_port_end} '
        f'/commit:apphost'
    )

    # KRYTYCZNE, WCZEŚNIEJ BRAKUJĄCE USTAWIENIE (potwierdzone oficjalną
    # dokumentacją Microsoft): externalIp4Address. Gdy klient FTP (drukarka)
    # negocjuje połączenie pasywne komendą PASV, serwer IIS odsyła w
    # odpowiedzi adres IP, pod którym klient ma nawiązać POŁĄCZENIE DANYCH
    # (czyli to, gdzie faktycznie popłynie przesyłany plik). Bez jawnego
    # ustawienia externalIp4Address, IIS może odesłać nieprawidłowy/wewnętrzny
    # adres — przez co LOGOWANIE się udaje (kanał kontrolny działa), ale
    # transfer samego pliku się nie udaje, bo drukarka próbuje połączyć się
    # pod złym adresem. To dokładnie pasuje do typowego objawu "FTP wydaje
    # się działać, ale skany i tak nie docierają". FileZilla Server robi to
    # automatycznie/inaczej, dlatego działała bez tej jawnej konfiguracji.
    if external_ip:
        ext_out, ext_code = run_cmd_with_code(
            f'{appcmd} set config /section:system.applicationHost/sites '
            f'"/siteDefaults.ftpServer.firewallSupport.externalIp4Address:{external_ip}" '
            f'/commit:apphost'
        )
        if ext_code == 0:
            logger_cb(f"  ✔ Zewnętrzny adres IP dla trybu pasywnego ustawiony: {external_ip}")
        else:
            logger_cb(f"  ✖ Nie udało się ustawić externalIp4Address (kod: {ext_code}): {ext_out}")
    else:
        logger_cb(
            "  UWAGA: brak podanego adresu IP komputera — tryb pasywny FTP może "
            "nie działać poprawnie (transfer plików, nie samo logowanie)."
        )

    # Uruchom witrynę (na wypadek gdyby appcmd add site jej nie wystartował
    # automatycznie) i upewnij się, że usługa FTP działa.
    run_cmd_with_code(f'{appcmd} start site "{site_name}"')
    run_cmd_with_code('sc config ftpsvc start= auto', powershell=False)
    svc_out, svc_code = run_cmd_with_code('net start ftpsvc')
    # Kod 2 = "usługa już uruchomiona" na wielu wersjach Windows — traktujemy
    # to jako sukces, nie błąd.
    already_running = "already" in svc_out.lower() or "już" in svc_out.lower()
    if svc_code == 0 or already_running:
        logger_cb("  ✔ Usługa Microsoft FTP Service działa.")
    else:
        logger_cb(f"  UWAGA: usługa FTP mogła się nie uruchomić (kod: {svc_code}): {svc_out}")

    time.sleep(3)  # usługa FTP potrzebuje chwili, zaraz po starcie stan bywa 'Unknown'
    st_out, _ = run_cmd_with_code(f'{appcmd} list site "{site_name}"')
    if "state:Started" in st_out:
        logger_cb(f"  ✔ Witryna FTP '{site_name}' skonfigurowana i uruchomiona (stan: Started).")
    else:
        logger_cb(f"  ⚠ Witryna '{site_name}' nie jest w stanie Started: {st_out.strip()}")
    return True


def configure_windows_ftp_server(folder, username, port=21, external_ip=None, logger_cb=print):
    """
    Punkt wejścia wysokiego poziomu: instaluje rolę IIS FTP (jeśli trzeba)
    i konfiguruje witrynę FTP wskazującą na folder skanów. Zastępuje
    poprzednie rozwiązanie oparte na zewnętrznej bibliotece pyftpdlib —
    wbudowany serwer FTP Windows jest trwałą usługą systemową (nie
    procesem powiązanym z czasem życia tego programu) i nie wymaga
    dodatkowej instalacji pakietów Pythona.

    external_ip: adres IP komputera używany w konfiguracji trybu pasywnego
    FTP (firewallSupport.externalIp4Address) — BEZ TEGO transfer plików
    może się nie udawać mimo poprawnego logowania (patrz komentarz w
    configure_iis_ftp_site).

    Zwraca True/False.
    """
    if not install_iis_ftp_role(logger_cb):
        return False
    return configure_iis_ftp_site(
        folder, username, port=port, external_ip=external_ip, logger_cb=logger_cb
    )


def create_desktop_shortcut(target_path, shortcut_name="Skany", logger_cb=print):
    """
    Tworzy skrót na Pulpicie ZALOGOWANEGO użytkownika (nie konta 'skany',
    tylko osoby faktycznie siedzącej przy komputerze) wskazujący na folder
    skanów. Używa PowerShell + WScript.Shell (COM) — dostępne w każdym
    Windows bez dodatkowych zależności Python (unikamy wymogu instalacji
    pywin32 tylko dla tej jednej funkcji).
    """
    logger_cb(f"--- Tworzenie skrótu '{shortcut_name}' na Pulpicie ---")

    current_user = getpass.getuser()
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        # Część konfiguracji Windows (np. OneDrive) przenosi realny Pulpit
        # gdzie indziej — spróbuj odczytać to z rejestru jako fallback.
        out = run_cmd(
            'powershell -NoProfile -Command '
            '"[Environment]::GetFolderPath(\'Desktop\')"',
            powershell=True
        )
        if out and os.path.isdir(out.strip()):
            desktop = out.strip()

    shortcut_path = os.path.join(desktop, f"{shortcut_name}.lnk")

    ps_script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{shortcut_path}'); "
        f"$sc.TargetPath = '{target_path}'; "
        f"$sc.IconLocation = 'shell32.dll,3'; "
        f"$sc.Description = 'Folder skanow z kserokopiarki'; "
        f"$sc.Save()"
    )
    out = run_cmd(f'powershell -NoProfile -Command "{ps_script}"', powershell=True)

    if os.path.exists(shortcut_path):
        logger_cb(f"  ✔ Skrót utworzony: {shortcut_path} (użytkownik: {current_user})")
        return True
    else:
        logger_cb(f"  UWAGA: nie udało się potwierdzić utworzenia skrótu: {out}")
        return False


def map_network_drive(drive_letter="S", share_name=SHARE_NAME, logger_cb=print):
    """
    Mapuje udostępniony folder jako trwały dysk sieciowy (np. S:) przez
    `net use`. /persistent:yes sprawia, że mapowanie przetrwa restart
    komputera — użytkownik zobaczy dysk w Eksploratorze bez dodatkowych
    kroków. Usuwa najpierw istniejące mapowanie tej litery (jeśli jest),
    żeby operacja była powtarzalna.

    Sprawdza kod wyjścia procesu (nie dopasowanie tekstu) — komunikaty
    Windows różnią się w zależności od wersji językowej systemu.
    """
    drive_letter = drive_letter.rstrip(":").upper()
    logger_cb(f"--- Mapowanie dysku sieciowego {drive_letter}: → \\\\localhost\\{share_name} ---")

    # Usuń istniejące mapowanie tej litery, jeśli już istnieje (idempotencja)
    run_cmd_with_code(f'net use {drive_letter}: /delete /y')

    out, code = run_cmd_with_code(
        f'net use {drive_letter}: \\\\localhost\\{share_name} /persistent:yes'
    )
    logger_cb(f"  {out}")

    if code == 0:
        logger_cb(f"  ✔ Dysk {drive_letter}: zmapowany pomyślnie.")
        return True
    else:
        logger_cb(f"  ✖ Mapowanie nieudane (kod wyjścia: {code}) — sprawdź, czy litera {drive_letter}: nie jest już zajęta.")
        return False


def check_port_reachability(ip, ports, logger_cb=print, timeout=2.0):
    """
    Testuje dostępność podanych portów TCP na danym adresie IP — szybki,
    jednoznaczny test PRZED wysłaniem właściwej konfiguracji, żeby wcześnie
    wychwycić np. urządzenie offline, złe IP, albo port zablokowany przez
    zaporę/router, zamiast dowiadywać się o tym dopiero w trakcie długiego
    procesu konfiguracji. Zwraca dict {port: bool}.
    """
    port_labels = {
        80: "HTTP", 443: "HTTPS", 445: "SMB", 21: "FTP",
    }
    results = {}
    logger_cb(f"--- Test dostępności portów na {ip} ---")
    for port in ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            reachable = sock.connect_ex((ip, port)) == 0
            sock.close()
        except Exception:
            reachable = False
        results[port] = reachable
        label = port_labels.get(port, str(port))
        status = "✔ otwarty" if reachable else "✖ niedostępny"
        logger_cb(f"  Port {port} ({label}): {status}")

    if not any(results.values()):
        diagnose_unreachable_ip(ip, logger_cb)

    return results


def diagnose_unreachable_ip(ip, logger_cb=print):
    """
    Wywoływana, gdy WSZYSTKIE testowane porty na danym IP są niedostępne —
    to zwykle nie jest problem konkretnego portu/zapory, tylko brak trasy
    routingu do tej podsieci (np. drukarka podłączona kablem Ethernet w
    innej sieci niż karta Wi-Fi, przez którą komputer łączy się z internetem).
    Uruchamia realny `ping` i `tracert` (krótki), żeby dać jednoznaczną
    odpowiedź zamiast zgadywania.
    """
    logger_cb("")
    logger_cb(f"--- Diagnostyka: dlaczego {ip} jest całkowicie niedostępny? ---")

    ping_out = run_cmd(f'ping -n 2 -w 800 {ip}', timeout=10)
    logger_cb(f"  ping {ip}:")
    for line in ping_out.splitlines():
        logger_cb(f"    {line}")

    low = ping_out.lower()
    if "nie można odnaleźć hosta docelowego" in low or "destination host unreachable" in low:
        logger_cb("")
        logger_cb("  ⚠ ROZPOZNANO PRZYCZYNĘ: brak trasy routingu do tej podsieci.")
        logger_cb("  Najczęstszy powód: drukarka jest podłączona kablem Ethernet do innej")
        logger_cb("  sieci niż ta, z którą łączy się komputer przez Wi-Fi (inny zakres IP).")
        logger_cb("  Sprawdź w GUI, w polu 'Karta sieciowa (IP komputera)', czy jest tam")
        logger_cb("  adres karty Ethernet w TEJ SAMEJ podsieci co IP drukarki (te same")
        logger_cb("  pierwsze 3 liczby adresu, np. 192.168.1.x). Jeśli karty Ethernet")
        logger_cb("  w ogóle nie ma na liście, zobacz sekcję 'Diagnostyka kart sieciowych'.")
    elif "upłynął limit czasu żądania" in low or "request timed out" in low:
        logger_cb("")
        logger_cb("  ⚠ Trasa do podsieci istnieje, ale urządzenie nie odpowiada na ping.")
        logger_cb("  Możliwe przyczyny: drukarka wyłączona/w trybie uśpienia, zły adres IP,")
        logger_cb("  albo urządzenie ma zablokowaną odpowiedź na ping (rzadkie).")
    logger_cb("")


def diagnose_network_interfaces(logger_cb=print):
    """
    Pełna diagnostyka stanu kart sieciowych — wywoływana z osobnego przycisku
    w GUI. Pokazuje wszystkie karty (również te bez adresu IP / odłączone),
    żeby jasno wskazać np. kartę Ethernet w stanie 'Media disconnected'
    (kabel niepodłączony / martwy port) lub 'Identyfikowanie...' (DHCP nie
    przydzielił adresu) — to najczęstsza przyczyna, dla której nawet ręczne
    wpisanie poprawnego IP drukarki nie pomaga: system w ogóle nie ma
    aktywnego interfejsu w tej sieci.
    """
    logger_cb("--- Diagnostyka kart sieciowych (wszystkie, również nieaktywne) ---")

    out = run_cmd(
        'powershell -NoProfile -Command '
        '"Get-NetAdapter | Select-Object Name,Status,LinkSpeed,MacAddress | Format-Table -AutoSize"',
        powershell=True, timeout=20
    )
    logger_cb(out)
    logger_cb("")

    interfaces = get_network_interfaces_detailed(logger_cb)
    if interfaces:
        logger_cb("Karty z przypisanym adresem IPv4:")
        for iface in interfaces:
            logger_cb(f"  • {iface['alias']}: {iface['ip']}/{iface['prefix_len']}")
    else:
        logger_cb("  ⚠ Żadna karta nie ma przypisanego adresu IPv4!")

    logger_cb("")
    logger_cb("Jeśli karta Ethernet (do drukarki) ma status inny niż 'Up', albo nie")
    logger_cb("pojawia się na liście adresów IPv4 powyżej — sprawdź fizycznie kabel,")
    logger_cb("port w switchu/routerze, oraz czy karta ma ustawione DHCP lub statyczny IP")
    logger_cb("w Ustawieniach sieciowych Windows (Panel sterowania → Centrum sieci).")


def detect_security_software(logger_cb=None):
    """
    Wykrywa zainstalowane produkty antywirusowe/zapory trzeciej strony przez
    standardowy rejestr WMI Security Center (ten sam, którego używa samo
    Centrum zabezpieczeń Windows). To WYŁĄCZNIE odczyt informacji — nie
    zmienia żadnych ustawień. Zwraca listę nazw wykrytych produktów.

    Świadomie NIE próbuje wyłączać ani konfigurować tych produktów — ich
    ruch sieciowy (IDS/firewall/ochrona przed atakami sieciowymi) blokujący
    komunikację z drukarką wymaga jawnej, ręcznej decyzji administratora
    w interfejsie tego konkretnego programu. Automatyczne, ciche wyłączanie
    cudzego oprogramowania zabezpieczającego to dokładnie ten mechanizm,
    którego używa złośliwe oprogramowanie do neutralizowania ochrony —
    nie robimy tego niezależnie od tego, kto i z jakich powodów uruchamia
    ten program.
    """
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command '
        '"Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | '
        'Select-Object -ExpandProperty displayName"',
        powershell=True, timeout=20
    )
    if code != 0 or not out.strip():
        if logger_cb:
            logger_cb("  Nie udało się odczytać listy zainstalowanego oprogramowania zabezpieczającego.")
        return []

    products = [line.strip() for line in out.splitlines() if line.strip()]
    if logger_cb:
        if products:
            logger_cb(f"  Wykryte oprogramowanie zabezpieczające: {', '.join(products)}")
        else:
            logger_cb("  Nie wykryto dodatkowego oprogramowania zabezpieczającego (poza Windows Defender).")
    return products


def build_security_software_exclusion_instructions(device_ip, products, logger_cb=print):
    """
    Na podstawie wykrytego oprogramowania zabezpieczającego wypisuje
    KONKRETNĄ, gotową do wykonania instrukcję dodania wykluczenia dla
    adresu IP drukarki — z dokładną ścieżką menu, tam gdzie to możliwe do
    ustalenia dla znanych produktów. To jest JEDYNY właściwy sposób
    rozwiązania sytuacji, gdy antywirus blokuje ruch sieciowy od drukarki:
    świadoma, ręczna decyzja administratora w interfejsie tego programu —
    nie automatyczna, cicha zmiana wykonana przez ten skrypt.
    """
    logger_cb("")
    logger_cb("--- Jak dodać wykluczenie dla IP drukarki w wykrytym oprogramowaniu ---")

    eset_names = [p for p in products if "eset" in p.lower() or "nod32" in p.lower()]
    if eset_names:
        logger_cb(f"  Wykryto: {', '.join(eset_names)}")
        logger_cb("")
        logger_cb("  ESET blokuje ruch sieciowy niezależnie od Zapory Windows — reguły")
        logger_cb("  netsh skonfigurowane przez ten program NIE wystarczą. Trzeba dodać")
        logger_cb(f"  adres IP drukarki ({device_ip}) do zaufanej strefy bezpośrednio w ESET:")
        logger_cb("")
        logger_cb("  1. Otwórz główne okno programu ESET (ikona na pasku zadań)")
        logger_cb("  2. Naciśnij klawisz F5, aby otworzyć Ustawienia zaawansowane")
        logger_cb("  3. Przejdź do: Ochrona dostępu do sieci → Zapora osobista")
        logger_cb("  4. Rozwiń i kliknij 'Edytuj' przy pozycji 'Strefy adresów IP'")
        logger_cb("  5. Wybierz 'Strefa zaufana' → kliknij 'Edytuj'")
        logger_cb(f"  6. W polu 'Adres zdalnego komputera' wpisz: {device_ip}")
        logger_cb("  7. Zatwierdź (OK, OK) i ewentualnie zrestartuj usługę skanowania")
        logger_cb("")
        logger_cb("  Jeśli mimo dodania do strefy zaufanej ESET nadal blokuje ruch,")
        logger_cb("  dodatkowo wyklucz ten adres z IDS (Wykrywanie włamań):")
        logger_cb("  Ustawienia zaawansowane (F5) → Zapora osobista → Zaawansowane →")
        logger_cb("  'Edytuj' przy 'Wyjątki IDS' → dodaj regułę zezwalającą dla tego IP.")
        logger_cb("")
        logger_cb("  Źródło (oficjalna dokumentacja ESET):")
        logger_cb("  https://support.eset.com/kb3218 (strefa zaufana)")
        logger_cb("  https://support.eset.com/kb2939 (wyjątki IDS)")
        return

    if products:
        logger_cb(f"  Wykryto: {', '.join(products)}")
        logger_cb(f"  Ten program nie ma gotowej instrukcji dla tego konkretnego produktu.")
        logger_cb(f"  Poszukaj w jego ustawieniach opcji typu 'Zapora' / 'Firewall' /")
        logger_cb(f"  'Ochrona sieci' i dodaj adres IP drukarki ({device_ip}) do listy")
        logger_cb(f"  zaufanych/wykluczonych adresów — dokładnie tak samo jak zrobiliśmy")
        logger_cb(f"  to już w Zaporze Windows.")
    else:
        logger_cb("  Nie wykryto dodatkowego oprogramowania zabezpieczającego blokującego ruch.")
        logger_cb("  Jeśli problem nadal występuje, sprawdź ustawienia routera/switcha.")


def check_network_profile(logger_cb=print):
    """
    Sprawdza aktywny(e) profil(e) sieci (Public/Private/Domain). To jest
    bezpośrednio powiązane z udokumentowanym problemem w oficjalnym
    narzędziu Ricoh (STFCT): reguły zapory utworzone bez jawnego
    profile=any obowiązują TYLKO dla profilu aktywnego w chwili ich
    tworzenia — jeśli profil się zmieni (np. po reconnect do sieci),
    reguła przestaje działać mimo że nadal "istnieje". Ten program już
    naprawił to (profile=any we wszystkich regułach), ale wykrycie
    obecnego profilu nadal pomaga zdiagnozować inne, pokrewne problemy
    (np. sam Windows może ograniczać udostępnianie plików w sieci
    publicznej niezależnie od reguł firewalla).
    """
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command '
        '"Get-NetConnectionProfile | Select-Object -ExpandProperty NetworkCategory"',
        powershell=True, timeout=15
    )
    if code != 0 or not out.strip():
        logger_cb("  Nie udało się odczytać profilu sieci.")
        return None

    profiles = [p.strip() for p in out.splitlines() if p.strip()]
    is_public = any("public" in p.lower() for p in profiles)
    logger_cb(f"  Aktywne profile sieci: {', '.join(profiles)}")
    if is_public:
        logger_cb("  ⚠ Sieć oznaczona jako 'Publiczna' — Windows domyślnie ogranicza")
        logger_cb("    udostępnianie plików w takiej sieci. Zalecane: Ustawienia →")
        logger_cb("    Sieć i Internet → Właściwości → ustaw jako 'Sieć prywatna'.")
    else:
        logger_cb("  ✔ Brak sieci w trybie 'Publicznym' blokującym udostępnianie.")
    return not is_public


def check_windows_service_running(service_name, display_name, logger_cb=print):
    """Sprawdza, czy dana usługa Windows (np. ftpsvc, LanmanServer) faktycznie
    działa — niezależnie od tego, czy jest tylko 'skonfigurowana'."""
    out, code = run_cmd_with_code(f'sc query {service_name}')
    running = code == 0 and "running" in out.lower()
    status = "✔ działa" if running else "✖ NIE działa"
    logger_cb(f"  {status}: usługa '{display_name}' ({service_name})")
    if not running:
        logger_cb(f"    → Napraw: Win+R → services.msc → znajdź '{display_name}' → Uruchom")
    return running


def check_firewall_rule_exists(rule_name, logger_cb=print):
    """Sprawdza, czy dana reguła zapory Windows istnieje i jest aktywna."""
    out, code = run_cmd_with_code(f'netsh advfirewall firewall show rule name="{rule_name}"')
    exists = code == 0 and "no rules match" not in out.lower() and "nie odnaleziono" not in out.lower()
    enabled = exists and ("enabled: yes" in out.lower() or "włączona: tak" in out.lower() or "yes" in out.lower())
    status = "✔ istnieje i aktywna" if enabled else ("✖ istnieje, ale WYŁĄCZONA" if exists else "✖ BRAK")
    logger_cb(f"  {status}: reguła zapory '{rule_name}'")
    return enabled


# ═══════════════════ Smart App Control — zarządzanie ═══════════════════
#
# Oficjalna dokumentacja Microsoft Learn potwierdza (stan na 2026):
#   https://learn.microsoft.com/en-us/windows/security/application-security/
#     application-control/app-control-for-business/appcontrol
#   "...set the VerifiedAndReputablePolicyState (DWORD) registry value under
#   HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy [...] After you change
#   the registry value, you must run CiTool.exe -r for the change to take
#   effect." Wartości: 0 = Off, 1 = Enforce, 2 = Evaluation.
#
# UWAGA (odpowiedź na punkt 17 polecenia): ten sam klucz jest używany w DWÓCH
# kontekstach dokumentacji Microsoft:
#   - zarządzanie flotą/organizacją (strona appcontrol.md, cytat powyżej) —
#     to jest metoda, którą implementujemy, bo dotyczy zmiany trwałego stanu
#     systemu (dokładnie to, o co prosi użytkownik);
#   - strona deweloperska "Test your app with Smart App Control" opisuje
#     TYMCZASOWE wyłączenie na czas testowania aplikacji przez dewelopera —
#     mechanizm identyczny technicznie, ale inny kontekst użycia. Nie zmienia
#     to implementacji (ten sam klucz, ta sama wartość 0, to samo CiTool -r),
#     więc stosujemy jedną wspólną funkcję dla obu przypadków.
#
# Ograniczenie: to USTAWIENIE REJESTRU rozpoznawane przez komponent Code
# Integrity jądra Windows — nie "oficjalne API" w sensie wywołania funkcji
# WinAPI, ale udokumentowany przez Microsoft sposób zarządzania tym stanem
# (identyczny z tym, którego używa IT do zarządzania flotą urządzeń).

SAC_REG_PATH = r"HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy"
SAC_REG_VALUE = "VerifiedAndReputablePolicyState"
SAC_STATE_LABELS = {0: "Off (wyłączony)", 1: "Enforce (wymuszony)", 2: "Evaluation (tryb oceny)"}


def is_windows_11():
    """Sprawdza wersję Windows (SAC/CiTool wymaga Windows 11, wprowadzone w 22H2)."""
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command "[System.Environment]::OSVersion.Version.Build"',
        powershell=True, timeout=10
    )
    if code != 0 or not out.strip().isdigit():
        return None  # nie udało się ustalić
    build = int(out.strip())
    # Windows 11 zaczyna się od build 22000; SAC/CiTool wymaga 22621+ (22H2).
    return build >= 22000


def get_smart_app_control_state(logger_cb=None):
    """
    Odczytuje HKLM\\SYSTEM\\CurrentControlSet\\Control\\CI\\Policy\\VerifiedAndReputablePolicyState
    (metoda udokumentowana przez Microsoft Learn — patrz nagłówek sekcji).

    Zwraca krotkę (state: int|None, label: str):
      state=0/1/2 — odczytana wartość (patrz SAC_STATE_LABELS dla opisu);
      state=None, label="missing_key"  — klucz CI\\Policy nie istnieje;
      state=None, label="missing_value"— klucz istnieje, ale brak wartości
                                          VerifiedAndReputablePolicyState;
      state=None, label="error: ..."   — błąd odczytu (np. brak dostępu).
    """
    ps_cmd = (
        'powershell -NoProfile -Command '
        '"$ErrorActionPreference=\'Stop\'; '
        f'try {{ $k = Get-Item -LiteralPath \'{SAC_REG_PATH}\' }} '
        'catch { Write-Output \'NOKEY\'; exit 0 }; '
        f'$v = Get-ItemProperty -LiteralPath \'{SAC_REG_PATH}\' -Name {SAC_REG_VALUE} -ErrorAction SilentlyContinue; '
        f'if ($null -eq $v) {{ Write-Output \'NOVALUE\' }} else {{ Write-Output $v.{SAC_REG_VALUE} }}"'
    )
    out, code = run_cmd_with_code(ps_cmd, powershell=True, timeout=15)
    out = out.strip()

    if code != 0:
        msg = f"error: polecenie odczytu zakończyło się kodem {code}: {out[:200]}"
        if logger_cb:
            logger_cb(f"  ✖ Błąd odczytu stanu Smart App Control: {msg}")
        return None, msg
    if out == "NOKEY":
        if logger_cb:
            logger_cb("  Klucz rejestru CI\\Policy nie istnieje — Smart App Control prawdopodobnie "
                      "nie był jeszcze skonfigurowany na tym komputerze (stan: Unknown).")
        return None, "missing_key"
    if out == "NOVALUE":
        if logger_cb:
            logger_cb(f"  Klucz CI\\Policy istnieje, ale brak wartości {SAC_REG_VALUE} (stan: Unknown).")
        return None, "missing_value"
    if not out.isdigit() or int(out) not in SAC_STATE_LABELS:
        msg = f"error: nieoczekiwana wartość w rejestrze: {out!r}"
        if logger_cb:
            logger_cb(f"  ✖ {msg}")
        return None, msg

    state = int(out)
    if logger_cb:
        logger_cb(f"  Smart App Control — stan odczytany z rejestru: {SAC_STATE_LABELS[state]}")
    return state, SAC_STATE_LABELS[state]


def find_citool_path(logger_cb=None):
    """
    Lokalizuje CiTool.exe. Standardowa lokalizacja to %SystemRoot%\\System32
    (dołączone do Windows od wersji 11 22H2 — patrz dokumentacja CiTool
    na Microsoft Learn). Sprawdzamy istnienie pliku zamiast zakładać na
    sztywno ścieżkę, zgodnie z wymogiem bezpiecznego wyszukania.
    Zwraca ścieżkę (str) albo None, jeśli narzędzia nie znaleziono.
    """
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = os.path.join(system_root, "System32", "CiTool.exe")
    if os.path.isfile(candidate):
        return candidate

    # Zapasowo: PATH (np. nietypowa instalacja/kontener).
    out, code = run_cmd_with_code('where CiTool.exe', timeout=10)
    if code == 0 and out.strip():
        first_line = out.strip().splitlines()[0].strip()
        if os.path.isfile(first_line):
            return first_line

    if logger_cb:
        logger_cb(f"  ✖ Nie znaleziono CiTool.exe (sprawdzono: {candidate} oraz PATH). "
                  f"Narzędzie jest częścią Windows 11 od wersji 22H2 — ta wersja Windows "
                  f"może go nie zawierać.")
    return None


def refresh_app_control_policies(logger_cb=print):
    """
    Uruchamia CiTool.exe --refresh (alias -r) — oficjalnie udokumentowana
    komenda wymagana po zmianie VerifiedAndReputablePolicyState, żeby zmiana
    zaczęła obowiązywać (patrz dokumentacja CiTool na Microsoft Learn,
    sekcja "Refresh the App Control policies on the system").
    Zwraca (success: bool, output: str).
    """
    citool = find_citool_path(logger_cb)
    if citool is None:
        return False, "CiTool.exe nie znalezione"

    out, code = run_cmd_with_code(f'"{citool}" --refresh', timeout=30)
    if code != 0:
        logger_cb(f"  ✖ CiTool.exe --refresh zakończyło się błędem (kod {code}): {out[:300]}")
        return False, out
    logger_cb(f"  ✔ CiTool.exe --refresh wykonane: {out.strip() or '(brak wyjścia — OK)'}")
    return True, out


def disable_smart_app_control(logger_cb=print):
    """
    Wykonuje PEŁNĄ, oficjalnie udokumentowaną przez Microsoft Learn sekwencję
    wyłączenia Smart App Control:
      1) sprawdza Windows 11,
      2) sprawdza uprawnienia administratora (odpowiedzialność wywołującego —
         GUI sprawdza to przed wywołaniem, ale sprawdzamy ponownie dla
         bezpieczeństwa przy wywołaniu z innego miejsca, np. CLI),
      3) odczytuje obecny stan; jeśli już 0 (Off) — kończy bez zmian,
      4) zapisuje VerifiedAndReputablePolicyState = 0 (REG_DWORD),
      5) uruchamia CiTool.exe --refresh,
      6) ponownie odczytuje stan i weryfikuje, że faktycznie wynosi 0.

    Zwraca słownik z jednoznacznym wynikiem:
      {"outcome": "already_off" | "success" | "error",
       "message": str, "needs_restart": bool, "final_state": int|None}

    "needs_restart": Microsoft Learn nie dokumentuje wymogu restartu dla tej
    operacji (CiTool --refresh ma odświeżyć politykę "na gorąco") — ustawiane
    na True tylko wtedy, gdy mimo poprawnego zapisu i refresh stan końcowy
    nadal nie wynosi 0 (silny sygnał, że pełne zastosowanie może wymagać
    ponownego uruchomienia systemu).
    """
    if not is_admin():
        return {"outcome": "error", "message": "Brak uprawnień administratora.",
                "needs_restart": False, "final_state": None}

    win11 = is_windows_11()
    if win11 is False:
        return {"outcome": "error",
                "message": "Ta funkcja wymaga Windows 11 (CiTool.exe jest częścią Windows 11 22H2+).",
                "needs_restart": False, "final_state": None}
    if win11 is None:
        logger_cb("  ⚠ Nie udało się jednoznacznie potwierdzić wersji Windows — kontynuuję ostrożnie.")

    logger_cb("--- Odczyt obecnego stanu Smart App Control ---")
    state, label = get_smart_app_control_state(logger_cb)

    if state == 0:
        return {"outcome": "already_off",
                "message": "Smart App Control jest już wyłączony (Off) — nic nie zmieniono.",
                "needs_restart": False, "final_state": 0}

    citool = find_citool_path(logger_cb)
    if citool is None:
        return {"outcome": "error",
                "message": "Nie znaleziono CiTool.exe — operacja przerwana przed zapisem rejestru "
                          "(nie zmieniono żadnego ustawienia).",
                "needs_restart": False, "final_state": state}

    logger_cb("--- Zapisuję VerifiedAndReputablePolicyState = 0 (Off) ---")
    ps_set = (
        'powershell -NoProfile -Command '
        f'"New-Item -Path \'{SAC_REG_PATH}\' -Force | Out-Null; '
        f'Set-ItemProperty -Path \'{SAC_REG_PATH}\' -Name {SAC_REG_VALUE} -Value 0 -Type DWord -Force"'
    )
    out, code = run_cmd_with_code(ps_set, powershell=True, timeout=20)
    if code != 0:
        low = out.lower()
        if "access" in low or "denied" in low or "odmowa" in low or "dostęp" in low:
            msg = f"Odmowa zapisu do rejestru (brak uprawnień lub odmowa UAC): {out[:300]}"
        else:
            msg = f"Błąd zapisu wartości rejestru (kod {code}): {out[:300]}"
        logger_cb(f"  ✖ {msg}")
        return {"outcome": "error", "message": msg, "needs_restart": False, "final_state": state}
    logger_cb("  ✔ Wartość rejestru zapisana.")

    logger_cb("--- Odświeżam polityki App Control (CiTool.exe --refresh) ---")
    refresh_ok, refresh_out = refresh_app_control_policies(logger_cb)
    if not refresh_ok:
        return {"outcome": "error",
                "message": f"Wartość rejestru została zapisana jako 0, ale CiTool.exe --refresh "
                          f"nie powiodło się: {refresh_out[:300]}. Zmiana może nie być jeszcze "
                          f"aktywna — spróbuj ponownie uruchomić komputer.",
                "needs_restart": True, "final_state": None}

    logger_cb("--- Weryfikacja: ponowny odczyt stanu ---")
    final_state, final_label = get_smart_app_control_state(logger_cb)

    if final_state == 0:
        return {"outcome": "success",
                "message": "Smart App Control został wyłączony i zweryfikowany (stan: Off).",
                "needs_restart": False, "final_state": 0}

    # Zapis i refresh się wykonały bez błędu, ale stan nadal nie jest 0 —
    # zgodnie z wymogiem punktu 11, NIE udajemy sukcesu.
    return {"outcome": "error",
            "message": "Operacja wykonana (zapis rejestru + CiTool --refresh), ale po weryfikacji "
                      f"stan nadal nie wynosi 0 (odczytano: {final_label}). Zmiana może wymagać "
                      "ponownego uruchomienia komputera, żeby w pełni zacząć obowiązywać.",
            "needs_restart": True, "final_state": final_state}



def check_windows_defender_exclusion(folder_path, logger_cb=print):
    """Sprawdza, czy folder skanów jest na liście wykluczeń Windows Defender
    (jeśli Defender aktywnie skanuje ten folder przy każdym zapisie, może to
    powodować zauważalne opóźnienia lub — w rzadkich przypadkach — cichą
    kwarantannę plików napływających z zewnętrznego urządzenia)."""
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command "(Get-MpPreference).ExclusionPath"',
        powershell=True, timeout=15
    )
    if code != 0:
        logger_cb("  UWAGA: nie udało się sprawdzić wykluczeń Windows Defender (może być wyłączony/zastąpiony innym AV).")
        return None
    excluded = folder_path.lower() in out.lower()
    status = "✔ folder jest wykluczony" if excluded else "○ folder NIE jest wykluczony (może być OK, ale warto sprawdzić)"
    logger_cb(f"  {status}: Windows Defender — {folder_path}")
    return excluded


def check_ntfs_write_permission(folder_path, username, logger_cb=print):
    """Sprawdza przez icacls, czy dane konto ma jawnie nadane prawo zapisu
    (F/M/W) do folderu — niezależnie od testu faktycznego zapisu (który
    testuje dostęp SIECIOWY, nie same uprawnienia NTFS na dysku)."""
    out, code = run_cmd_with_code(f'icacls "{folder_path}"')
    if code != 0:
        logger_cb(f"  ✖ Nie udało się odczytać uprawnień NTFS folderu {folder_path}")
        return False
    has_perm = username.lower() in out.lower() and any(
        p in out for p in ["(F)", "(M)", "(W)"]
    )
    status = "✔ ma prawo zapisu (NTFS)" if has_perm else "✖ BRAK jawnego prawa zapisu (NTFS)"
    logger_cb(f"  {status}: konto '{username}' → {folder_path}")
    if not has_perm:
        logger_cb(f"    → Napraw: icacls \"{folder_path}\" /grant {username}:(OI)(CI)F")
    return has_perm


def dump_ftp_log_tail(log_path, device_ip, logger_cb=print, max_lines=40):
    """Wypisuje ostatnie linie logu IIS FTP dotyczące drukarki (surowe, bez
    interpretacji). IIS zapisuje log z opóźnieniem ok. minuty, więc przy
    zatrzymaniu monitora pokazujemy to, co zdążyło trafić do pliku."""
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip() for l in f if device_ip in l]
    except Exception as e:
        logger_cb(f"  Nie można odczytać logu FTP: {e}")
        return
    if not lines:
        logger_cb("  W logu FTP nie ma jeszcze linii od drukarki (IIS zapisuje log z opóźnieniem ~1 min — "
                  "poczekaj i otwórz plik ręcznie): " + log_path)
        return
    logger_cb(f"  Ostatnie linie logu FTP od {device_ip} ({log_path}):")
    for l in lines[-max_lines:]:
        logger_cb("    " + l)


def get_smb_sessions_from_ip(device_ip):
    """Zwraca listę sesji SMB otwartych przez drukarkę (Get-SmbSession): użytkownik
    i wersja protokołu (np. 3.0 / 2.1 / 1.5). To dowód, że drukarka zalogowała się
    do udziału — nawet jeśli samo połączenie TCP trwało zbyt krótko, by zobaczyć je
    w netstat."""
    out, code = run_cmd_with_code(
        'powershell -NoProfile -Command "Get-SmbSession | Where-Object { $_.ClientComputerName -match \'' + device_ip + '\' } | '
        'ForEach-Object { \'użytkownik=\' + $_.ClientUserName + \'  protokół SMB=\' + $_.Dialect }"',
        powershell=True, timeout=15
    )
    if code != 0:
        return []
    return [l.strip() for l in out.splitlines() if l.strip().startswith("użytkownik")]


def find_ftp_log_file(logger_cb=None):
    """
    Znajduje najnowszy plik logu IIS FTP (format W3C) — domyślna lokalizacja
    to C:\\inetpub\\logs\\LogFiles\\FTPSVC<ID>\\, gdzie IIS NA STAŁE zapisuje
    każde połączenie FTP: logowania (w tym nieudane, kod 530), polecenia,
    błędy. To jest POTWIERDZONY, oficjalny mechanizm Microsoftu — znacznie
    bardziej wiarygodny niż zgadywanie, bo pokazuje DOKŁADNIE to, co
    urządzenie faktycznie zrobiło przy próbie połączenia.
    """
    base_dir = r"C:\inetpub\logs\LogFiles"
    if not os.path.isdir(base_dir):
        if logger_cb:
            logger_cb(f"  Katalog logów IIS nie istnieje: {base_dir}")
        return None

    ftpsvc_dirs = [
        d for d in os.listdir(base_dir)
        if d.upper().startswith("FTPSVC") and os.path.isdir(os.path.join(base_dir, d))
    ]
    if not ftpsvc_dirs:
        if logger_cb:
            logger_cb("  Nie znaleziono folderu logów FTPSVC — czy witryna FTP została uruchomiona choć raz?")
        return None

    newest_log = None
    newest_mtime = 0
    for d in ftpsvc_dirs:
        full_dir = os.path.join(base_dir, d)
        for fname in os.listdir(full_dir):
            if fname.lower().endswith(".log"):
                fpath = os.path.join(full_dir, fname)
                mtime = os.path.getmtime(fpath)
                if mtime > newest_mtime:
                    newest_mtime = mtime
                    newest_log = fpath

    if newest_log and logger_cb:
        logger_cb(f"  Znaleziono log FTP: {newest_log}")
    return newest_log


def get_active_connections_from_ip(device_ip, logger_cb=None):
    """
    Zwraca listę aktywnych połączeń TCP (netstat) od/do adresu IP drukarki —
    pozwala zobaczyć, czy urządzenie W OGÓLE nawiązuje połączenie z
    komputerem (np. port 21/445), zanim jeszcze dojdzie do kwestii
    logowania/zapisu. Jeśli nic się tu nie pojawia mimo próby skanowania,
    problem jest sieciowy/firewall, nie konfiguracyjny.
    """
    out, code = run_cmd_with_code(f'netstat -an | findstr {device_ip}', timeout=10)
    if code != 0 or not out.strip() or "[BŁĄD]" in out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def tail_new_lines(file_path, last_position):
    """
    Odczytuje tylko NOWE linie dodane do pliku od `last_position` (offset
    w bajtach) — pozwala śledzić rosnący plik logu "na żywo", bez
    każdorazowego odczytywania całego (potencjalnie dużego) pliku od nowa.
    Zwraca (nowe_linie: list[str], nowa_pozycja: int).
    """
    try:
        if not os.path.exists(file_path):
            return [], last_position
        size = os.path.getsize(file_path)
        if size < last_position:
            # Plik został zrotowany/skrócony — zacznij śledzenie od nowa.
            last_position = 0
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(last_position)
            new_content = f.read()
            new_position = f.tell()
        new_lines = [l for l in new_content.splitlines() if l.strip()]
        return new_lines, new_position
    except Exception:
        return [], last_position


def interpret_ftp_log_line(line, device_ip):
    """
    Interpretuje pojedynczą linię loga IIS FTP (format W3C) pod kątem
    adresu IP drukarki i typowych kodów statusu — zwraca czytelny opis
    PO POLSKU zamiast surowej linii W3C, albo None jeśli linia nie
    dotyczy tego urządzenia lub jest nagłówkiem/komentarzem (#).

    Kluczowe kody FTP widoczne w logu IIS:
      230 = logowanie udane, 530 = logowanie NIEUDANE (złe hasło/konto),
      150/226 = transfer pliku rozpoczęty/zakończony powodzeniem,
      550 = brak dostępu do pliku/folderu (uprawnienia NTFS).
    """
    if not line or line.startswith("#"):
        return None
    if device_ip not in line:
        return None

    parts = line.split()
    # Format W3C typowo: date time s-ip cs-method cs-uri-stem ... c-ip
    # sc-status ... — pozycje mogą się różnić wg konfiguracji logowania,
    # więc szukamy rozpoznawalnych wzorców zamiast sztywnych indeksów.
    if " 230 " in f" {line} " or line.endswith(" 230"):
        return f"✔ Logowanie UDANE z {device_ip}"
    if " 530 " in f" {line} " or line.endswith(" 530"):
        return f"✖ Logowanie NIEUDANE z {device_ip} — złe konto/hasło w książce adresowej drukarki!"
    if " 550 " in f" {line} " or line.endswith(" 550"):
        return f"✖ Odmowa dostępu do pliku/folderu (sprawdź uprawnienia NTFS) — {device_ip}"
    if "STOR" in parts:
        return f"📄 Drukarka WYSYŁA plik (komenda STOR) — {device_ip}"
    if " 226 " in f" {line} ":
        return f"✔ Transfer pliku ZAKOŃCZONY POWODZENIEM — {device_ip}"
    if "PASV" in parts:
        return f"🔌 Drukarka negocjuje połączenie pasywne (PASV) — {device_ip}"
    return f"ℹ {device_ip}: {line}"


def run_full_diagnostics(device_ip, local_ip, protocol, logger_cb=print):
    """
    Pełna diagnostyka na żywo — przechodzi PO KOLEI przez wszystkie
    najczęstsze przyczyny, dla których skany "nie wpadają do folderu",
    od najbardziej podstawowych (czy komputer w ogóle widzi drukarkę) po
    najbardziej subtelne (czy antywirus blokuje ruch, czy uprawnienia NTFS
    są poprawne). Każdy krok daje jednoznaczny ✔/✖ i, przy niepowodzeniu,
    konkretną podpowiedź co zrobić — zamiast zgadywania, które z wielu
    możliwych ustawień Windows akurat blokuje transfer.

    Zwraca listę (nazwa_testu, wynik_bool_lub_None) do ew. dalszego użycia.
    """
    results = []
    logger_cb("")
    logger_cb("╔" + "═" * 58 + "╗")
    logger_cb("║  DIAGNOSTYKA NA ŻYWO — szukanie przyczyny problemu       ║")
    logger_cb("╚" + "═" * 58 + "╝")

    # 1. Czy komputer w ogóle widzi drukarkę w sieci (routing/ping).
    logger_cb("")
    logger_cb("[1/9] Czy komputer widzi drukarkę w sieci?")
    port_results = check_port_reachability(device_ip, [80, 443], logger_cb)
    device_reachable = any(port_results.values())
    results.append(("Drukarka osiągalna w sieci", device_reachable))
    if not device_reachable:
        logger_cb("  → To jest PODSTAWOWA przyczyna — jeśli komputer nie widzi drukarki,")
        logger_cb("    żaden dalszy krok nie ma znaczenia. Sprawdź kabel/Wi-Fi, czy drukarka")
        logger_cb("    jest włączona, i czy oba urządzenia są w tej samej podsieci.")

    # 2. Karty sieciowe — czy wybrana karta faktycznie ma ten adres IP.
    logger_cb("")
    logger_cb("[2/9] Stan kart sieciowych komputera")
    interfaces = get_network_interfaces_detailed(logger_cb)
    ip_matches = any(iface["ip"] == local_ip for iface in interfaces)
    results.append(("Wybrany adres IP komputera aktywny", ip_matches))
    if not ip_matches:
        logger_cb(f"  ✖ Adres {local_ip} (użyty w konfiguracji) nie jest już przypisany")
        logger_cb(f"    do żadnej aktywnej karty sieciowej — mógł się zmienić (DHCP)!")
        logger_cb(f"    → Ustaw stałe IP (patrz okienko po zakończeniu konfiguracji) i")
        logger_cb(f"    uruchom konfigurację ponownie z aktualnym adresem.")
    else:
        logger_cb(f"  ✔ Adres {local_ip} nadal aktywny na jednej z kart sieciowych.")

    # 3. Profil sieci (Public/Private/Domain) — udokumentowana przez Ricoh
    #    przyczyna, dla której SMB bywa blokowane mimo poprawnej reguły zapory.
    logger_cb("")
    logger_cb("[3/9] Profil sieci (Publiczna/Prywatna/Domena)")
    profile_ok = check_network_profile(logger_cb)
    results.append(("Profil sieci nie blokuje udostępniania", profile_ok))

    # 4. Usługa systemowa (FTP lub SMB/Serwer plików).
    logger_cb("")
    logger_cb(f"[4/9] Usługa systemowa Windows ({protocol.upper()})")
    if protocol == "ftp":
        service_ok = check_windows_service_running("ftpsvc", "Microsoft FTP Service", logger_cb)
    else:
        service_ok = check_windows_service_running("LanmanServer", "Serwer (udostępnianie plików)", logger_cb)
    results.append((f"Usługa {protocol.upper()} działa", service_ok))

    # 4. Reguły zapory Windows.
    logger_cb("")
    logger_cb("[5/9] Reguły Zapory Windows")
    if protocol == "ftp":
        fw1 = check_firewall_rule_exists("Ricoh FTP Scan", logger_cb)
        fw2 = check_firewall_rule_exists("Ricoh FTP Scan Passive", logger_cb)
        firewall_ok = fw1 and fw2
    else:
        firewall_ok = check_firewall_rule_exists("Ricoh SMB Scan", logger_cb)
    results.append(("Reguły Zapory Windows aktywne", firewall_ok))
    if not firewall_ok:
        logger_cb("  → Uruchom ponownie główną konfigurację (KONFIGURUJ) — reguły")
        logger_cb("    zapory są tworzone automatycznie na tym etapie.")

    # 5. Antywirus/zapora trzeciej strony (np. ESET) — WYŁĄCZNIE wykrycie
    #    i wskazanie, gdzie ręcznie dodać wyjątek (patrz uzasadnienie przy
    #    detect_security_software — nie modyfikujemy cudzych produktów).
    logger_cb("")
    logger_cb("[6/9] Dodatkowe oprogramowanie zabezpieczające (antywirus/firewall)")
    security_products = detect_security_software(logger_cb)
    # UWAGA: to jest informacja, nie test sukces/porażka — obecność antywirusa
    # nie jest sama w sobie "błędem", więc celowo NIE trafia do listy
    # problemów w podsumowaniu (results). Zgłaszamy ją tylko jako ostrzeżenie
    # w logu, bo wymaga sprawdzenia ręcznie, a nie jest jednoznacznym ✖.
    if security_products:
        logger_cb("  ⚠ Wykryto dodatkowe zabezpieczenia — mogą blokować ruch NIEZALEŻNIE")
        logger_cb("    od Zapory Windows. Sprawdź sekcję ze szczegółową instrukcją niżej.")
    else:
        logger_cb("  ✔ Nie wykryto dodatkowego oprogramowania blokującego ruch.")

    # 6. Windows Defender — wykluczenie folderu (informacyjne, nie krytyczne).
    logger_cb("")
    logger_cb("[7/9] Windows Defender — wykluczenie folderu skanów")
    check_windows_defender_exclusion(TARGET_FOLDER, logger_cb)

    # 7. Uprawnienia NTFS folderu.
    logger_cb("")
    logger_cb("[8/9] Uprawnienia NTFS folderu skanów")
    ntfs_ok = check_ntfs_write_permission(TARGET_FOLDER, TARGET_USER, logger_cb)
    results.append(("Uprawnienia NTFS poprawne", ntfs_ok))

    # 8. Rzeczywisty test logowania i zapisu — to jest test OSTATECZNY,
    #    bo sprawdza wszystko naraz w praktyce (usługa+firewall+NTFS+auth).
    logger_cb("")
    logger_cb(f"[9/9] Rzeczywisty test logowania i zapisu ({protocol.upper()})")
    if protocol == "ftp":
        real_test_ok = test_local_ftp_access("127.0.0.1", 21, logger_cb)
    else:
        real_test_ok = test_local_share_access(SHARE_NAME, logger_cb)
    results.append(("Rzeczywisty zapis działa", real_test_ok))

    # Podsumowanie.
    logger_cb("")
    logger_cb("╔" + "═" * 58 + "╗")
    logger_cb("║  PODSUMOWANIE DIAGNOSTYKI                                 ║")
    logger_cb("╚" + "═" * 58 + "╝")
    failed = [name for name, ok in results if ok is False]
    if not failed:
        logger_cb("  ✔ Wszystkie testy przeszły pomyślnie — konfiguracja wygląda poprawnie.")
        logger_cb("")
        logger_cb("  Jeśli skany MIMO TO nie docierają, problem prawdopodobnie leży po")
        logger_cb("  stronie samej drukarki, nie komputera. Wg oficjalnej dokumentacji")
        logger_cb("  Ricoh, urządzenie pokazuje na panelu DWA różne komunikaty błędu")
        logger_cb("  PO PRÓBIE skanowania (nie wcześniej) — dotknij [Scan Files Status] →")
        logger_cb("  [Connection Error...] → [Current Address Book], a następnie sprawdź:")
        logger_cb("")
        logger_cb("  • Jeśli błąd dotyczy ŚCIEŻKI/ADRESU: w zakładce 'Folder' sprawdź,")
        logger_cb(f"    czy pole 'Path'/'Ścieżka' ma dokładnie poprawny adres komputera")
        logger_cb(f"    ({local_ip} dla FTP, lub nazwę komputera dla SMB) — literówka")
        logger_cb("    lub nieaktualny adres tutaj da błąd mimo poprawnej konfiguracji Windows.")
        logger_cb("")
        logger_cb("  • Jeśli błąd dotyczy LOGOWANIA: sprawdź, czy 'Login User Name' i")
        logger_cb(f"    'Login Password' w tym samym miejscu to dokładnie '{TARGET_USER}' / "
                   f"'{TARGET_PASS}'")
        logger_cb("    — literówka w haśle wpisanym na panelu drukarki (inna niż ta, którą")
        logger_cb("    zapisał ten program) da dokładnie taki błąd mimo poprawnej konfiguracji.")
    else:
        logger_cb(f"  ✖ Znaleziono {len(failed)} problem(y):")
        for name in failed:
            logger_cb(f"     • {name}")
        logger_cb("  Napraw powyższe punkty w podanej kolejności (od góry) — pierwszy")
        logger_cb("  nieudany test często powoduje kaskadowe niepowodzenie kolejnych.")

    return results


def _report_cmd(title, cmd, logger_cb, powershell=False, timeout=40, limit=3500):
    """Uruchamia polecenie diagnostyczne i loguje jego pełne wyjście."""
    out, code = run_cmd_with_code(cmd, powershell=powershell, timeout=timeout)
    logger_cb(f"--- {title} (kod wyjścia: {code}) ---")
    out = out.strip() or "(brak wyjścia)"
    if len(out) > limit:
        out = out[:limit] + "\n... (ucięto)"
    for line in out.splitlines():
        logger_cb("    " + line)


def collect_full_report(device_ip, local_ip, protocol, logger_cb=print, web_client=None):
    """
    PEŁNY RAPORT DIAGNOSTYCZNY — zbiera w jednym miejscu wszystko, co
    potrzebne do ustalenia, dlaczego skany nie docierają: system, sieć,
    konto, uprawnienia, usługi, zaporę, konfigurację IIS FTP, nasłuchujące
    porty, logi IIS/Windows (w tym nieudane logowania), Defendera/antywirus,
    rzeczywisty test FTP/SMB pod adresem, którego użyje drukarka, oraz
    zawartość książki adresowej drukarki.
    """
    appcmd = r'%windir%\system32\inetsrv\appcmd.exe'
    logger_cb("")
    logger_cb("#" * 70)
    logger_cb(f"# PEŁNY RAPORT DIAGNOSTYCZNY  (wersja programu: {APP_VERSION})")
    logger_cb(f"# drukarka={device_ip}  komputer={local_ip}  protokół={protocol.upper()}")
    logger_cb(f"# konto={TARGET_USER}  folder={TARGET_FOLDER}  udział={SHARE_NAME}")
    logger_cb("#" * 70)

    ps = dict(powershell=True)
    _report_cmd("System Windows",
        'powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem | Select Caption,Version,OSLanguage | Format-List | Out-String)"',
        logger_cb, **ps)
    logger_cb(f"Uprawnienia administratora: {is_admin()}")
    _report_cmd("Konfiguracja IP", "ipconfig /all", logger_cb)
    _report_cmd("Ping drukarki", f"ping -n 2 -w 800 {device_ip}", logger_cb)

    # --- konto i folder ---
    _report_cmd(f"Konto Windows '{TARGET_USER}'", f"net user {TARGET_USER}", logger_cb)
    _report_cmd("Uprawnienia NTFS folderu", f'icacls "{TARGET_FOLDER}"', logger_cb)
    _report_cmd("Udziały SMB", "net share", logger_cb)
    _report_cmd("Zapora — stan profili", "netsh advfirewall show allprofiles state", logger_cb)
    _report_cmd("Profil sieci",
        'powershell -NoProfile -Command "Get-NetConnectionProfile | Format-List Name,InterfaceAlias,NetworkCategory"',
        logger_cb, **ps)

    # --- usługi i porty ---
    for svc in ("ftpsvc", "LanmanServer", "W3SVC", "WAS"):
        _report_cmd(f"Usługa {svc}", f"sc query {svc}", logger_cb)
    _report_cmd("Porty nasłuchujące 21 / 445", 'netstat -ano | findstr ":21 :445"', logger_cb)
    _report_cmd(f"Połączenia z/do drukarki ({device_ip})", f"netstat -ano | findstr {device_ip}", logger_cb)

    # --- reguły zapory ---
    for rule in ("Ricoh FTP Scan", "Ricoh FTP Scan Passive", "Ricoh SMB Scan"):
        _report_cmd(f"Reguła zapory '{rule}'",
                    f'netsh advfirewall firewall show rule name="{rule}" verbose', logger_cb)

    # --- konfiguracja IIS FTP ---
    _report_cmd("IIS — lista witryn", f"{appcmd} list site", logger_cb)
    _report_cmd("IIS FTP — autoryzacja", f'{appcmd} list config "SkanerFTP" -section:system.ftpServer/security/authorization', logger_cb)
    _report_cmd("IIS FTP — tryb pasywny / zewnętrzny IP (siteDefaults)",
                f"{appcmd} list config -section:system.applicationHost/sites", logger_cb, limit=6000)

    # --- logi FTP ---
    log_path = find_ftp_log_file(logger_cb)
    if log_path:
        dump_ftp_log_tail(log_path, device_ip, logger_cb, max_lines=60)
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                tail = [l.rstrip() for l in f][-25:]
            logger_cb("--- Ostatnie 25 linii logu FTP (wszystkie adresy) ---")
            for l in tail:
                logger_cb("    " + l)
        except Exception as e:
            logger_cb(f"  Nie można odczytać logu: {e}")

    # --- dziennik zdarzeń Windows ---
    _report_cmd("Dziennik System — zdarzenia FTP/IIS (ostatnie 15)",
        'powershell -NoProfile -Command "Get-WinEvent -LogName System -MaxEvents 400 -ErrorAction SilentlyContinue | '
        'Where-Object { $_.ProviderName -match \'FTP|IIS|WAS\' } | Select-Object -First 15 | '
        'ForEach-Object { $_.TimeCreated.ToString(\'s\') + \' [\' + $_.Id + \'] \' + $_.ProviderName + \': \' + ($_.Message -replace \'\\s+\',\' \') }"',
        logger_cb, **ps, timeout=60)
    _report_cmd("Polityka inspekcji logowania (audyt)",
        'auditpol /get /category:"Logon/Logoff"', logger_cb)
    _report_cmd("Dziennik Security — logowania z adresu drukarki lub konta (4624/4625)",
        'powershell -NoProfile -Command "Get-WinEvent -FilterHashtable @{LogName=\'Security\';Id=4624,4625} -MaxEvents 300 -ErrorAction SilentlyContinue | '
        f'Where-Object {{ $_.Message -match \'{device_ip}\' -or $_.Message -match \'{TARGET_USER}\' }} | Select-Object -First 12 | '
        'ForEach-Object { $_.TimeCreated.ToString(\'s\') + \' [\' + $_.Id + \'] \' + ($_.Message -replace \'\\s+\',\' \').Substring(0,[Math]::Min(500,($_.Message -replace \'\\s+\',\' \').Length)) }"',
        logger_cb, **ps, timeout=90)
    logger_cb("  (Jeśli powyżej pusto, audyt logowania może być wyłączony — aby widzieć nieudane "
              "logowania FTP, włącz go poleceniem: auditpol /set /subcategory:\"Logon\" /success:enable /failure:enable)")

    # --- Defender / antywirus ---
    _report_cmd("Windows Defender — status",
        'powershell -NoProfile -Command "Get-MpComputerStatus | Format-List AMServiceEnabled,RealTimeProtectionEnabled,AntivirusEnabled"',
        logger_cb, **ps)
    _report_cmd("Windows Defender — ostatnie wykrycia (czy plik skanu nie trafił do kwarantanny)",
        'powershell -NoProfile -Command "Get-MpThreatDetection | Select-Object -First 5 | Format-List InitialDetectionTime,Resources,ThreatID"',
        logger_cb, **ps)
    products = detect_security_software(logger_cb)
    if products:
        logger_cb(f"  Wykryte oprogramowanie zabezpieczające: {', '.join(products)}")

    # --- rzeczywiste testy pod adresem, którego używa drukarka ---
    logger_cb("--- Test FTP/SMB pod adresem, z którego korzysta drukarka ---")
    if protocol == "ftp":
        test_local_ftp_access("127.0.0.1", 21, logger_cb)
        if local_ip and local_ip != "127.0.0.1":
            test_local_ftp_access(local_ip, 21, logger_cb)
    else:
        test_local_share_access(SHARE_NAME, logger_cb)
        unc_ip = f"\\\\{local_ip}\\{SHARE_NAME}"
        run_cmd_with_code(f'net use "{unc_ip}" /delete /y')
        _report_cmd(f"Logowanie do {unc_ip} jako '{TARGET_USER}' (jak drukarka)",
                    f'net use "{unc_ip}" /user:{TARGET_USER} "{TARGET_PASS}"', logger_cb)
        _report_cmd(f"Zawartość {unc_ip}", f'dir "{unc_ip}"', logger_cb)
        run_cmd_with_code(f'net use "{unc_ip}" /delete /y')

    # --- to, co drukarka naprawdę ma zapisane ---
    logger_cb("--- Zawartość książki adresowej drukarki (odczyt SOAP) ---")
    client = web_client or RicohWebClient(device_ip, "admin", "", logger_cb)
    try:
        client.dump_address_book(logger_cb)
    except Exception as e:
        logger_cb(f"  Błąd odczytu: {e}")

    logger_cb("#" * 70)
    logger_cb(f"# KONIEC RAPORTU — pełny log: {DETAILED_LOG_PATH}")
    logger_cb("#" * 70)


def rollback_configuration(logger_cb=print):
    """
    Cofa konfigurację wykonaną przez setup_windows_environment: usuwa
    konto, udział SMB, witrynę FTP w IIS, reguły zapory, wykluczenie
    Defendera. NIE usuwa samego folderu TARGET_FOLDER (mogą być w nim
    ważne zeskanowane pliki) ani zmiany profilu sieci Private (bezpieczny
    stan, nie ma potrzeby cofać). NIE wyłącza roli IIS-FTPServer — to
    zmiana na poziomie całego systemu, zbyt inwazyjna jak na zwykły
    rollback (i mogła zostać z innego powodu przez administratora).
    Bezpieczne do wielokrotnego wywołania — ignoruje błędy typu
    "reguła/konto nie istnieje".
    """
    logger_cb("--- Cofanie konfiguracji ---")
    run_cmd(f'net share {SHARE_NAME} /delete')
    run_cmd(f'net user {TARGET_USER} /delete')
    run_cmd(r'%windir%\system32\inetsrv\appcmd.exe delete site "SkanerFTP"')
    run_cmd('netsh advfirewall firewall delete rule name="Ricoh SMB Scan"')
    run_cmd('netsh advfirewall firewall delete rule name="Ricoh FTP Scan"')
    run_cmd('netsh advfirewall firewall delete rule name="Ricoh FTP Scan Passive"')
    run_cmd(
        f'powershell -NoProfile -Command "Remove-MpPreference -ExclusionPath \'{TARGET_FOLDER}\'"',
        powershell=True
    )
    logger_cb("✔ Konto, udział, witryna FTP, reguły zapory i wykluczenie Defendera usunięte.")
    logger_cb(f"  Folder {TARGET_FOLDER} NIE został usunięty (mogą być w nim ważne pliki).")


SETTINGS_PATH = Path.home() / ".ricoh_scanner_config.json"


def save_settings(ip, admin_user, protocol, selected_nic):
    """
    Zapisuje ostatnio użyte ustawienia (IP drukarki, login admina, protokół,
    wybrana karta sieciowa) do JSON w profilu użytkownika — żeby nie trzeba
    było wpisywać ich od nowa przy każdym uruchomieniu. Celowo NIE zapisuje
    hasła administratora drukarki na dysku w plaintext.
    """
    data = {"ip": ip, "admin_user": admin_user, "protocol": protocol, "nic": selected_nic}
    try:
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # brak zapisu ustawień nie jest błędem krytycznym


def load_settings():
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def test_local_ftp_access(host="127.0.0.1", port=21, logger_cb=print):
    """
    Testuje FAKTYCZNE połączenie FTP do lokalnie skonfigurowanej witryny IIS:
    logowanie kontem TARGET_USER/TARGET_PASS (to samo, którego użyje
    drukarka), zapis pliku testowego, odczyt listy plików, sprzątanie.
    Używa wbudowanego modułu `ftplib` — nie wymaga żadnych dodatkowych
    zależności.

    To jest znacznie pewniejszy test niż samo sprawdzenie, czy port 21
    odpowiada (`check_port_reachability`) — port może być otwarty, a mimo
    to logowanie/zapis mogą się nie udawać z wielu możliwych przyczyn
    (złe uprawnienia NTFS, zła konfiguracja autoryzacji FTP w IIS, tryb
    izolacji użytkowników przekierowujący do innego podfolderu, itp.).
    Wynik tego testu jednoznacznie mówi, na którym dokładnie etapie coś
    nie działa, zamiast zgadywania.
    """
    import ftplib

    logger_cb(f"--- Test rzeczywistego połączenia FTP ({host}:{port}) jako '{TARGET_USER}' ---")

    try:
        ftp = ftplib.FTP()
        ftp.connect(host, port, timeout=8)
        logger_cb("  ✔ Połączenie TCP z serwerem FTP nawiązane.")
    except Exception as e:
        logger_cb(f"  ✖ Nie można połączyć się z serwerem FTP: {e}")
        logger_cb("  Sprawdź, czy usługa 'Microsoft FTP Service' (ftpsvc) faktycznie działa")
        logger_cb("  (services.msc) i czy port nie jest blokowany przez firewall/antywirus.")
        return False

    try:
        ftp.login(TARGET_USER, TARGET_PASS)
        logger_cb(f"  ✔ Zalogowano jako '{TARGET_USER}'.")
    except ftplib.error_perm as e:
        logger_cb(f"  ✖ Logowanie nieudane: {e}")
        logger_cb(
            "  Możliwe przyczyny: konto lub hasło nieprawidłowe, uwierzytelnianie "
            "Basic wyłączone w konfiguracji witryny FTP w IIS, albo konto nie ma "
            "uprawnienia 'Read,Write' w autoryzacji tej witryny."
        )
        try:
            ftp.quit()
        except Exception:
            pass
        return False
    except Exception as e:
        logger_cb(f"  ✖ Błąd podczas logowania: {e}")
        try:
            ftp.quit()
        except Exception:
            pass
        return False

    try:
        # Sprawdź gdzie faktycznie ląduje po zalogowaniu — jeśli tryb
        # izolacji użytkowników jest inny niż zakładany, katalog roboczy
        # będzie inny niż "/", co wyjaśni dlaczego pliki "znikają".
        pwd = ftp.pwd()
        logger_cb(f"  Katalog po zalogowaniu: {pwd}")
        try:
            pasv_host, pasv_port = ftp.makepasv()
            logger_cb(f"  Tryb pasywny: serwer odsyła adres {pasv_host}:{pasv_port} "
                      f"(adres drukarki do transferu danych musi być osiągalny: powinien być to {host if host != '127.0.0.1' else 'IP komputera'})")
        except Exception as e:
            logger_cb(f"  ✖ Negocjacja trybu pasywnego (PASV) nie powiodła się: {e}")

        test_filename = "_test_ftp_dostepu.tmp"
        import io
        test_data = io.BytesIO(b"test dostepu FTP - plik mozna bezpiecznie usunac")
        ftp.storbinary(f"STOR {test_filename}", test_data)
        logger_cb("  ✔ Zapis pliku testowego przez FTP powiódł się.")

        files = ftp.nlst()
        if test_filename in files:
            logger_cb("  ✔ Plik testowy widoczny na liście — zapis potwierdzony.")
        else:
            logger_cb(
                f"  UWAGA: plik zapisany bez błędu, ale nie widać go na liście "
                f"katalogu ({files}) — możliwy nietypowy tryb izolacji użytkownika."
            )

        ftp.delete(test_filename)
        logger_cb("  ✔ Plik testowy usunięty — test zakończony sukcesem.")
        ftp.quit()
        return True
    except Exception as e:
        logger_cb(f"  ✖ Zapis/odczyt przez FTP nie powiódł się: {e}")
        logger_cb(
            "  Sprawdź uprawnienia NTFS folderu dla konta " + TARGET_USER + " "
            "oraz czy autoryzacja FTP w IIS ma zaznaczone 'Write', nie tylko 'Read'."
        )
        try:
            ftp.quit()
        except Exception:
            pass
        return False


def test_local_share_access(share_name=SHARE_NAME, logger_cb=print):
    """
    Testuje, czy udostępniony folder jest faktycznie dostępny przez konto
    'skany' (to samo, którego użyje drukarka) — łączy się przez `net use`
    z JAWNYMI poświadczeniami TARGET_USER/TARGET_PASS, próbuje zapisać
    plik testowy, po czym rozłącza mapowanie.

    WAŻNE: NIE testujemy dostępu jako bieżący zalogowany użytkownik
    Windows — udział ma celowo (ze względów bezpieczeństwa) uprawnienia
    NTFS ograniczone WYŁĄCZNIE do konta 'skany', więc nawet administrator
    komputera może nie mieć prawa zapisu przez zwykłe \\\\localhost\\share
    bez podania tych poświadczeń.

    BŁĄD ZNALEZIONY I NAPRAWIONY: poprzednia wersja sprawdzała sukces
    `net use` przez dopasowanie konkretnych fraz tekstowych ("błąd
    systemu" itp.) — ale rzeczywiste komunikaty Windows przy błędnym haśle
    (np. "System error 86", "błąd 1326") różnią się w zależności od wersji
    językowej systemu i nie zawsze zawierały żadną ze sprawdzanych fraz.
    Test wtedy fałszywie "przechodził dalej" mimo że `net use` się nie
    powiodło, i pokazywał sukces zapisu, który w rzeczywistości testował
    coś innego (np. stare, nieusunięte mapowanie) albo się cicho nie udawał
    bez informowania o prawdziwej przyczynie. Teraz sprawdzany jest kod
    wyjścia procesu (0 = sukces) — niezależny od języka/lokalizacji.
    """
    unc_base = fr"\\localhost\{share_name}"
    test_path = fr"{unc_base}\_test_dostepu.tmp"
    logger_cb(f"--- Test dostępu do udostępnionego folderu jako '{TARGET_USER}' ({unc_base}) ---")

    # Usuń ewentualne stare/konfliktowe mapowanie tej samej ścieżki UNC
    # (ignorujemy wynik — to tylko sprzątanie przed właściwą próbą)
    run_cmd_with_code(f'net use "{unc_base}" /delete /y')

    mount_out, mount_code = run_cmd_with_code(
        f'net use "{unc_base}" /user:{TARGET_USER} "{TARGET_PASS}"'
    )
    if mount_code != 0:
        logger_cb(f"  ✖ Nie udało się połączyć jako '{TARGET_USER}' (kod wyjścia: {mount_code})")
        logger_cb(f"  Komunikat systemu: {mount_out}")
        logger_cb(
            "  Możliwe przyczyny: profil sieci ustawiony na 'Publiczna', "
            "wyłączone udostępnianie plików w Ustawieniach sieciowych "
            "Windows, lub konto/hasło nieprawidłowe."
        )
        return False

    try:
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("test dostępu — plik może zostać bezpiecznie usunięty")
        # Sprawdzamy nie tylko że open()/write() nie rzuciło wyjątku, ale
        # że plik FAKTYCZNIE istnieje po zapisie — na wypadek gdyby system
        # plików cicho zignorował zapis bez wyjątku (rzadkie, ale możliwe
        # np. przy niektórych konfiguracjach redirectora SMB).
        if not os.path.exists(test_path):
            logger_cb("  ✖ Plik testowy nie istnieje po zapisie — zapis nie powiódł się cicho.")
            return False
        os.remove(test_path)
        logger_cb(f"  ✔ Zapis i odczyt jako '{TARGET_USER}' działa poprawnie — drukarka będzie mogła zapisywać.")
        return True
    except Exception as e:
        logger_cb(f"  ✖ Test nieudany mimo poprawnego połączenia: {e}")
        logger_cb("  Sprawdź uprawnienia NTFS folderu dla konta " + TARGET_USER + ".")
        return False
    finally:
        run_cmd_with_code(f'net use "{unc_base}" /delete /y')


# Flaga na poziomie modułu (nie instancji) — kontroluje, czy plik
# ricoh_soap_diagnostyka.txt ma zostać otwarty na czysto ("w") czy
# dopisany ("a"). Musi być globalna, bo _try_soap_add_user tworzy nową
# instancję RicohSoapClient dla każdej próby (http, https) — flaga na
# poziomie instancji gubiłaby się między próbami i nadpisywała wcześniejsze
# wyniki zamiast je zachować w jednym pliku.
_SOAP_DUMP_INITIALIZED = False


class RicohSoapClient:
    free_index_hint = None
    """
    Klient oficjalnego protokołu SOAP używanego przez Ricoh Smart Device
    Monitor for Admin do zarządzania książką adresową (namespace
    'http://www.ricoh.co.jp/xmlns/soap/rdh/udirectory', endpoint
    POST /DH/udirectory). To ZUPEŁNIE INNY, znacznie prostszy i bardziej
    niezawodny mechanizm niż odtwarzanie formularzy HTML webArch — POTWIERDZONY
    przechwyceniem prawdziwego ruchu sieciowego SDMA (Wireshark) oraz publicznie
    dostępnym, działającym modułem PowerShell 'RicohAddressBook' (autorstwa
    Alexander Krause / Matthew Desjardins, PowerShellGallery), którego
    implementację hasła (zwykły Base64, PES:Encoding puste) odtwarzamy tutaj.

    Preferowana ścieżka: jeśli ten protokół zadziała, jest szybszy i pewniejszy
    niż sekwencja 3-etapowa przez adrsSetUser.cgi/adrsEditPassword.cgi.
    """

    NAMESPACE = "http://www.ricoh.co.jp/xmlns/soap/rdh/udirectory"

    def __init__(self, ip, admin_user, admin_pass, log_cb, port=80, scheme="http", verify=True):
        self.ip = ip
        self.port = port
        self.scheme = scheme
        self.verify = verify
        self.admin_user = admin_user if admin_user else "admin"
        self.admin_pass = admin_pass if admin_pass is not None else ""
        self.log = log_cb
        self.session = requests.Session()
        self.endpoint = f"{scheme}://{ip}:{port}/DH/udirectory"

    def _soap_call(self, method, body_xml, timeout=8):
        """Wysyła żądanie SOAP i zwraca (status_code, text). Zapisuje pełną
        treść żądania i odpowiedzi do pliku diagnostycznego — dotychczasowa
        wersja logowała tylko krótkie komunikaty w konsoli, co utrudniało
        diagnozowanie niepowodzeń bez ponownego przechwytywania ruchu."""
        envelope = (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body>{body_xml}</s:Body></s:Envelope>'
        )
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{self.NAMESPACE}#{method}",
            "Accept": "*/*",
            "User-Agent": "RicohScannerConfig/1.0",
            "Cache-Control": "no-cache",
        }
        try:
            r = self.session.post(
                self.endpoint, data=envelope.encode("utf-8"),
                headers=headers, timeout=timeout, verify=self.verify
            )
            self._dump_soap_exchange(method, envelope, r.status_code, r.text, r.headers)
            return r.status_code, r.text
        except Exception as e:
            self.log(f"  ✖ Błąd żądania SOAP ({method}): {e}")
            self._dump_soap_exchange(method, envelope, None, str(e), {})
            return None, ""

    def _dump_soap_exchange(self, method, sent_xml, status, response_text, headers):
        """Dopisuje żądanie i odpowiedź SOAP do wspólnego pliku diagnostycznego
        obok programu, żeby dało się zdiagnozować niepowodzenie bez ponownego
        przechwytywania ruchu sieciowego.

        WAŻNE: flaga "czy plik już zainicjowany" musi być na poziomie MODUŁU
        (globalna), nie instancji klienta — _try_soap_add_user tworzy nową
        instancję RicohSoapClient dla każdej próby (http, potem https), więc
        flaga na poziomie instancji zawsze wynosiła False dla drugiej próby
        i NADPISYWAŁA wynik pierwszej próby zamiast dopisać go do pliku.
        """
        import datetime
        global _SOAP_DUMP_INITIALIZED
        try:
            app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
            diag_path = os.path.join(app_dir, "ricoh_soap_diagnostyka.txt")
            mode = "w" if not _SOAP_DUMP_INITIALIZED else "a"
            _SOAP_DUMP_INITIALIZED = True
            with open(diag_path, mode, encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"SOAP: {method} — {datetime.datetime.now().isoformat()}\n")
                f.write(f"Endpoint: {self.endpoint}\n")
                f.write(f"{'='*60}\n")
                f.write("--- Wysłane XML ---\n")
                f.write(sent_xml)
                f.write(f"\n\n--- Odpowiedź: HTTP {status} ---\n")
                for k, v in (headers.items() if headers else []):
                    f.write(f"{k}: {v}\n")
                f.write("--- Treść odpowiedzi ---\n")
                f.write(response_text)
                f.write("\n")
        except Exception as e:
            self.log(f"  UWAGA: nie udało się zapisać diagnostyki SOAP: {e}")

    def start_session(self):
        """
        Loguje się przez startSession — potwierdzony przez przechwycony ruch
        SDMA format: SCHEME=base64(BASIC);UID:UserName=base64(user);
        PWD:Password=base64(hasło);PES:Encoding= (puste — zgodnie z działającym
        modułem RicohAddressBook, który nie implementuje dodatkowego
        szyfrowania PES i mimo to działa poprawnie z urządzeniami Ricoh).
        Zwraca sessionId (string) albo None przy niepowodzeniu.
        """
        scheme_b64 = base64.b64encode(b"BASIC").decode("ascii")
        user_b64 = base64.b64encode(self.admin_user.encode("utf-8")).decode("ascii")
        pass_b64 = base64.b64encode(self.admin_pass.encode("utf-8")).decode("ascii")
        string_in = f"SCHEME={scheme_b64};UID:UserName={user_b64};PWD:Password={pass_b64};PES:Encoding="

        body = (
            f'<m:startSession xmlns:m="{self.NAMESPACE}">'
            f'<stringIn>{self._xml_escape(string_in)}</stringIn>'
            f'<timeLimit>30</timeLimit><lockMode>X</lockMode>'
            f'</m:startSession>'
        )
        status, text = self._soap_call("startSession", body)
        if status != 200:
            self.log(f"  ✖ startSession: HTTP {status}")
            return None

        m = re.search(r"<returnValue>([^<]*)</returnValue>", text)
        if not m or m.group(1) != "OK":
            fault = re.search(r"<faultstring>([^<]*)</faultstring>", text)
            if fault:
                self.log(f"  ✖ startSession odrzucone przez urządzenie: {fault.group(1)}")
            else:
                self.log(f"  ✖ startSession: nieoczekiwana odpowiedź (returnValue != OK)")
            return None

        sid_match = re.search(r"<stringOut>([^<]*)</stringOut>", text)
        if not sid_match:
            self.log("  ✖ startSession: brak sessionId (stringOut) w odpowiedzi")
            return None

        self.log("  ✔ Sesja SOAP nawiązana (startSession OK)")
        return sid_match.group(1)

    def find_next_free_index(self, session_id, max_entries=50):
        """
        Odczytuje istniejące wpisy książki adresowej DOKŁADNIE tak jak
        Smart Device Monitor (potwierdzone nagraniem ruchu na tym urządzeniu):
        1) searchObjects(fromClass=entry, whereAnd propName=all) -> lista ID,
        2) getObjectsProps(entry:ID...) z polami entryType/id/index.
        Zwraca najmniejszy wolny numer rejestracji (int) albo None, gdy
        odczyt się nie udał (wtedy NIE wolno zgadywać numeru).
        """
        ns = ('xmlns:soap-enc="http://schemas.xmlsoap.org/soap/encoding/" '
              'xmlns:itt="{itt}" xsi:type="soap-enc:Array" '
              'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
              'xmlns:t="{t}" ')
        def arr(tag, itt, t, arrtype, inner):
            return (f'<{tag} ' + ns.format(itt=itt, t=t) +
                    f'soap-enc:arrayType="{arrtype}">{inner}</{tag}>')
        xsd = "http://www.w3.org/2001/XMLSchema"
        common = "http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes"
        udir = "http://www.ricoh.co.jp/xmlns/schema/rdh/udirectory"
        empty_term = '<item><operator></operator><propName>{n}</propName><propVal></propVal><propVal2></propVal2></item>'
        body = (
            f'<m:searchObjects xmlns:m="{self.NAMESPACE}">'
            f'<sessionId>{self._xml_escape(session_id)}</sessionId>'
            + arr("selectProps", xsd, common, "itt:string[1]", "<item>id</item>") +
            '<fromClass>entry</fromClass><parentObjectId></parentObjectId><resultSetId></resultSetId>'
            + arr("whereAnd", udir, udir, "itt:queryTerm[1]", empty_term.format(n="all"))
            + arr("whereOr", udir, udir, "itt:queryTerm[1]", empty_term.format(n=""))
            + arr("orderBy", udir, udir, "itt:queryOrderBy[1]",
                  '<item><propName></propName><isDescending>false</isDescending></item>') +
            f'<rowOffset>0</rowOffset><rowCount>{max_entries}</rowCount><lastObjectId></lastObjectId>'
            + arr("queryOptions", common, common, "itt:property[1]",
                  '<item><propName></propName><propVal></propVal></item>') +
            '</m:searchObjects>'
        )
        status, text = self._soap_call("searchObjects", body)
        if status != 200:
            self.log(f"  Odczyt listy wpisów przez SOAP nie powiódł się (HTTP {status}).")
            return None
        ids = [i for i in re.findall(r"<propName>id</propName><propVal>(\d+)</propVal>", text) if int(i) < 4294967040]
        if not ids:
            self.log("  Książka adresowa (SOAP): brak wpisów — pierwszy wolny numer: 1.")
            return 1

        props = ["entryType", "id", "index"]
        body2 = (
            f'<m:getObjectsProps xmlns:m="{self.NAMESPACE}">'
            f'<sessionId>{self._xml_escape(session_id)}</sessionId>'
            + arr("objectIdList", xsd, common, f"itt:string[{len(ids)}]",
                  "".join(f"<item>entry:{i}</item>" for i in ids))
            + arr("selectProps", xsd, common, f"itt:string[{len(props)}]",
                  "".join(f"<item>{x}</item>" for x in props))
            + arr("options", common, common, "itt:property[1]",
                  '<item><propName></propName><propVal></propVal></item>') +
            '</m:getObjectsProps>'
        )
        status2, text2 = self._soap_call("getObjectsProps", body2)
        if status2 != 200:
            self.log(f"  Odczyt numerów wpisów (getObjectsProps) nie powiódł się (HTTP {status2}).")
            return None
        used = {int(x) for x in re.findall(r"<propName>index</propName><propVal>(\d+)</propVal>", text2)}
        n = 1
        while n in used:
            n += 1
        self.log(f"  Zajęte numery wpisów: {sorted(used) if used else '(brak)'} — nowy wpis dostanie numer {n}.")
        return n

    def list_entries(self, session_id, max_entries=50):
        """Zwraca listę słowników z TYM, co urządzenie faktycznie ma zapisane
        w książce adresowej (numer, nazwa, typ i parametry folderu) —
        odczyt tym samym zapytaniem co Smart Device Monitor."""
        xsd = "http://www.w3.org/2001/XMLSchema"
        common = "http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes"
        udir = "http://www.ricoh.co.jp/xmlns/schema/rdh/udirectory"
        def arr(tag, itt, t, arrtype, inner):
            return (f'<{tag} xmlns:soap-enc="http://schemas.xmlsoap.org/soap/encoding/" '
                    f'xmlns:itt="{itt}" xsi:type="soap-enc:Array" '
                    f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:t="{t}" '
                    f'soap-enc:arrayType="{arrtype}">{inner}</{tag}>')
        term = '<item><operator></operator><propName>{n}</propName><propVal></propVal><propVal2></propVal2></item>'
        body = (
            f'<m:searchObjects xmlns:m="{self.NAMESPACE}">'
            f'<sessionId>{self._xml_escape(session_id)}</sessionId>'
            + arr("selectProps", xsd, common, "itt:string[1]", "<item>id</item>") +
            '<fromClass>entry</fromClass><parentObjectId></parentObjectId><resultSetId></resultSetId>'
            + arr("whereAnd", udir, udir, "itt:queryTerm[1]", term.format(n="all"))
            + arr("whereOr", udir, udir, "itt:queryTerm[1]", term.format(n=""))
            + arr("orderBy", udir, udir, "itt:queryOrderBy[1]",
                  '<item><propName></propName><isDescending>false</isDescending></item>') +
            f'<rowOffset>0</rowOffset><rowCount>{max_entries}</rowCount><lastObjectId></lastObjectId>'
            + arr("queryOptions", common, common, "itt:property[1]",
                  '<item><propName></propName><propVal></propVal></item>') +
            '</m:searchObjects>'
        )
        status, text = self._soap_call("searchObjects", body)
        if status != 200:
            return None
        ids = [i for i in re.findall(r"<propName>id</propName><propVal>(\d+)</propVal>", text) if int(i) < 4294967040]
        if not ids:
            return []
        props = ["entryType", "id", "name", "index", "remoteFolder:type", "remoteFolder:serverName",
                 "remoteFolder:path", "remoteFolder:port", "remoteFolder:accountName"]
        body2 = (
            f'<m:getObjectsProps xmlns:m="{self.NAMESPACE}">'
            f'<sessionId>{self._xml_escape(session_id)}</sessionId>'
            + arr("objectIdList", xsd, common, f"itt:string[{len(ids)}]",
                  "".join(f"<item>entry:{i}</item>" for i in ids))
            + arr("selectProps", xsd, common, f"itt:string[{len(props)}]",
                  "".join(f"<item>{x}</item>" for x in props))
            + arr("options", common, common, "itt:property[1]",
                  '<item><propName></propName><propVal></propVal></item>') +
            '</m:getObjectsProps>'
        )
        status2, text2 = self._soap_call("getObjectsProps", body2)
        if status2 != 200:
            return None
        entries, cur = [], None
        for k, v in re.findall(r"<propName>([^<]*)</propName><propVal>([^<]*)</propVal>", text2):
            if k == "entryType":
                cur = {}
                entries.append(cur)
            if cur is not None:
                cur[k] = v
        return entries

    def terminate_session(self, session_id):
        body = (
            f'<m:terminateSession xmlns:m="{self.NAMESPACE}">'
            f'<sessionId>{self._xml_escape(session_id)}</sessionId>'
            f'</m:terminateSession>'
        )
        self._soap_call("terminateSession", body)

    @staticmethod
    def _xml_escape(s):
        return (
            s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;")
        )

    def put_user_entry(self, session_id, entry_name, protocol, local_ip,
                        local_hostname, share_name, folder_username, folder_password,
                        entry_index=1, tag_id=1):
        """
        Dodaje wpis użytkownika przez putObjects — POTWIERDZONY przechwyceniem
        prawdziwego żądania SDMA. Kluczowe: remoteFolder:path dla SMB to pełna
        ścieżka UNC z NAZWĄ KOMPUTERA (np. "\\\\ARTUR-LAPTOP\\skany"), nie
        adresem IP — SDMA używało hostname, nie IP, w przechwyconym ruchu.
        Hasło folderu to zwykły Base64 (potwierdzone przez działający,
        publiczny moduł RicohAddressBook — nie wymaga dodatkowego szyfrowania
        PES mimo pola PES:Encoding w startSession).
        """
        if protocol == "smb":
            unc_path = f"\\\\{local_hostname}\\{share_name}"
            folder_props = (
                f'<item><propName>remoteFolder:type</propName><propVal>smb</propVal></item>'
                f'<item><propName>remoteFolder:serverName</propName><propVal></propVal></item>'
                f'<item><propName>remoteFolder:path</propName><propVal>{self._xml_escape(unc_path)}</propVal></item>'
                f'<item><propName>remoteFolder:select</propName><propVal>private</propVal></item>'
                f'<item><propName>remoteFolder:accountName</propName><propVal>{self._xml_escape(folder_username)}</propVal></item>'
                f'<item><propName>remoteFolder:password</propName><propVal>{base64.b64encode(folder_password.encode("utf-8")).decode("ascii")}</propVal></item>'
            )
        else:
            # Struktura POTWIERDZONA pośrednio przez analizę prawdziwego
            # żądania HTML (adrsSetUser.cgi, folderProtocolIn=FTP_O) z
            # drugiego przechwyconego pliku pcapng: folderServerNameIn tam
            # to adres IP komputera (nie hostname jak dla SMB), a ścieżka
            # folderu jest pusta (FTP loguje się bezpośrednio do korzenia
            # udostępnionego katalogu FTP, nie do konkretnej podścieżki).
            folder_props = (
                f'<item><propName>remoteFolder:type</propName><propVal>ftp</propVal></item>'
                f'<item><propName>remoteFolder:serverName</propName><propVal>{self._xml_escape(local_ip)}</propVal></item>'
                f'<item><propName>remoteFolder:port</propName><propVal>21</propVal></item>'
                f'<item><propName>remoteFolder:characterEncoding</propName><propVal>us-ascii</propVal></item>'
                f'<item><propName>remoteFolder:path</propName><propVal></propVal></item>'
                f'<item><propName>remoteFolder:select</propName><propVal>private</propVal></item>'
                f'<item><propName>remoteFolder:accountName</propName><propVal>{self._xml_escape(folder_username)}</propVal></item>'
                f'<item><propName>remoteFolder:password</propName><propVal>{base64.b64encode(folder_password.encode("utf-8")).decode("ascii")}</propVal></item>'
            )

        # Liczba elementów <item> WEWNĄTRZ folder_props — potrzebna do
        # poprawnego obliczenia arrayType="itt:property[N]" poniżej.
        folder_props_count = folder_props.count("<item>")

        # BŁĄD ZNALEZIONY I NAPRAWIONY: poprzednia wersja miała długość
        # tablicy zaszytą na sztywno jako property[16] — to zgadzało się
        # przypadkiem dla SMB (6 pól folderowych + 16 stałych pól = 22, ale
        # poprzedni kod i tak ignorował rzeczywistą liczbę i wpisywał 16 na
        # sztywno — SERWER MIMO TO PRZYJĄŁ TO dla SMB, prawdopodobnie
        # ignorując deklarowaną długość / traktując ją jako wskazówkę, nie
        # twardy wymóg). Dla FTP jest 8 pól folderowych (dodatkowe 'port' i
        # 'characterEncoding' — POTWIERDZONE analizą prawdziwego żądania
        # HTML z drugiego przechwyconego pliku pcapng). Niemniej poprawne,
        # dynamicznie obliczone total_props jest bezpieczniejsze niż zgadywanie
        # — 6 pól podstawowych (entryType..tagId) + 5 flag (auth:..faxAux:) +
        # N pól folderowych + 5 flag końcowych (isDestination..ldap:).
        fixed_props_count = 16  # 6 (entryType..tagId) + 5 (auth:..faxAux:) + 5 (isDestination..ldap:)
        total_props = fixed_props_count + folder_props_count

        entry_item = (
            '<item xmlns:soap-enc="http://schemas.xmlsoap.org/soap/encoding/" '
            'xmlns:itt="http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes" '
            'xsi:type="soap-enc:Array" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:t="http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes" '
            f'soap-enc:arrayType="itt:property[{total_props}]">'
            f'<item><propName>entryType</propName><propVal>user</propVal></item>'
            f'<item><propName>name</propName><propVal>{self._xml_escape(entry_name)}</propVal></item>'
            f'<item><propName>longName</propName><propVal></propVal></item>'
            f'<item><propName>phoneticName</propName><propVal></propVal></item>'
            f'<item><propName>index</propName><propVal>{entry_index}</propVal></item>'
            f'<item><propName>tagId</propName><propVal>{tag_id}</propVal></item>'
            f'<item><propName>auth:</propName><propVal>false</propVal></item>'
            f'<item><propName>mail:</propName><propVal>false</propVal></item>'
            f'<item><propName>ifax:</propName><propVal>false</propVal></item>'
            f'<item><propName>fax:</propName><propVal>false</propVal></item>'
            f'<item><propName>faxAux:</propName><propVal>false</propVal></item>'
            f'{folder_props}'
            f'<item><propName>isDestination</propName><propVal>true</propVal></item>'
            f'<item><propName>isSender</propName><propVal>false</propVal></item>'
            f'<item><propName>password:</propName><propVal>false</propVal></item>'
            f'<item><propName>smtp:</propName><propVal>false</propVal></item>'
            f'<item><propName>ldap:</propName><propVal>false</propVal></item>'
            '</item>'
        )

        body = (
            f'<m:putObjects xmlns:m="{self.NAMESPACE}">'
            f'<sessionId>{self._xml_escape(session_id)}</sessionId>'
            f'<objectClass>entry</objectClass>'
            f'<parentObjectId></parentObjectId>'
            '<propListList xmlns:soap-enc="http://schemas.xmlsoap.org/soap/encoding/" '
            'xmlns:itt="http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes" '
            'xsi:type="soap-enc:Array" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:t="http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes" '
            'soap-enc:arrayType="itt:property[][1]">'
            f'{entry_item}'
            '</propListList>'
            '<options xmlns:soap-enc="http://schemas.xmlsoap.org/soap/encoding/" '
            'xmlns:itt="http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes" '
            'xsi:type="soap-enc:Array" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:t="http://www.ricoh.co.jp/xmlns/schema/rdh/commontypes" '
            'soap-enc:arrayType="itt:property[1]"><item><propName></propName><propVal></propVal></item></options>'
            f'</m:putObjects>'
        )

        status, text = self._soap_call("putObjects", body, timeout=10)
        if status != 200:
            # POTWIERDZONE: niektóre błędy (np. "duplikat") przychodzą jako
            # HTTP 500 z JAWNYM, czytelnym errorCode w treści SOAP Fault —
            # wyciągamy go, żeby wywołujący mógł rozróżnić PRAWDZIWY,
            # jednoznaczny błąd (np. UDIRECTORY_OBJECT_DUPLICATED — wpis pod
            # tym indeksem już istnieje) od niejasnych, nieopisanych błędów
            # (np. same kody liczbowe 74-79 widziane w innych próbach), gdzie
            # nie wiadomo, czy zapis faktycznie się nie udał.
            error_code_match = re.search(r"<errorCode>([^<]*)</errorCode>", text)
            error_code = error_code_match.group(1) if error_code_match else None
            if error_code:
                self.log(f"  ✖ putObjects: HTTP {status}, errorCode={error_code}")
            else:
                self.log(f"  ✖ putObjects: HTTP {status}")
            return False, text, error_code

        # POTWIERDZONE analizą realnej odpowiedzi (druga przechwycona sesja,
        # próba FTP): putObjects zwraca returnValue w DWÓCH różnych formatach
        # zależnie od wyniku:
        #   - sukces (przypadek SMB, wcześniej potwierdzony): zwykły tekst
        #     <returnValue>OK</returnValue>
        #   - błąd: TABLICA z kodem liczbowym, np.
        #     <returnValue arrayType="itt:string[1]"><item>74</item></returnValue>
        #     gdzie kod 0 oznacza sukces, każdy inny — konkretny błąd (zgodnie
        #     z biblioteką referencyjną Ricoh.NET, gdzie ten sam wzorzec jest
        #     konwertowany na liczbę i 0 traktowane jako brak błędu).
        # Poprzednia wersja sprawdzała TYLKO dokładne dopasowanie do "OK",
        # więc dla FTP (który zwrócił kod błędu w formie tablicy) nie
        # rozpoznawała ani sukcesu, ani nie wyciągała czytelnego kodu błędu.
        simple_match = re.search(r"<returnValue>([^<]*)</returnValue>", text)
        if simple_match and simple_match.group(1).strip() == "OK":
            self.log("  ✔ putObjects: OK — wpis zapisany przez SOAP API")
            return True, text, None

        array_match = re.search(
            r"<returnValue[^>]*>\s*<item>(\d+)</item>\s*</returnValue>", text
        )
        if array_match:
            # putObjects zwraca ID NOWO UTWORZONEGO obiektu (rosnące 72, 74, 75...
            # — potwierdzone zrzutami panelu: wpis powstaje za każdym razem).
            # To jest SUKCES, nie kod błędu.
            self.log(f"  ✔ putObjects: wpis zapisany (ID obiektu: {array_match.group(1)})")
            return True, text, None

        fault = re.search(r"<faultstring>([^<]*)</faultstring>", text)
        err_desc = re.search(r"<errorDescription>([^<]*)</errorDescription>", text)
        if err_desc:
            self.log(f"  ✖ putObjects odrzucone: {err_desc.group(1)}")
        elif fault:
            self.log(f"  ✖ putObjects odrzucone (SOAP Fault): {fault.group(1)}")
        else:
            self.log(f"  ✖ putObjects: nieoczekiwana odpowiedź (nie rozpoznano formatu returnValue)")
        return False, text, None

    def add_scan_user(self, entry_name, protocol, local_ip, local_hostname,
                       share_name, folder_username, folder_password):
        """
        Punkt wejścia wysokiego poziomu: startSession -> (odczyt wolnego
        indeksu) -> putObjects -> terminateSession.

        Każde wywołanie tworzy NOWY wpis pod pierwszym wolnym numerem
        indeksu (patrz find_next_free_index) — zamiast zawsze próbować
        zapisać pod indeksem 1, co przy drugim i kolejnych uruchomieniach
        programu groziło nadpisaniem już istniejącego wpisu zamiast
        utworzenia odrębnego nowego użytkownika w książce adresowej.

        Zwraca (success: bool, skip_fallback: bool).

        skip_fallback=True TYLKO gdy błąd jest JAWNIE rozpoznany jako
        "obiekt zduplikowany" (errorCode UDIRECTORY_OBJECT_DUPLICATED) —
        to jest PRAWDZIWY, jednoznaczny błąd: urządzenie odmawia zapisu,
        bo wpis pod tym indeksem już istnieje. W tym jedynym przypadku
        próba fallbacku HTML byłaby bezcelowa (trafiłaby w ten sam zajęty
        slot) i wywołujący powinien ją pominąć.

        Dla WSZYSTKICH innych niepowodzeń (w tym niejasnych kodów
        liczbowych 74-79 bez opisu, które mogą, ale nie muszą być
        fałszywym negatywem) skip_fallback=False — wywołujący powinien
        nadal spróbować fallbacku HTML, bo nie ma jednoznacznego dowodu,
        że zapis się powiódł.
        """
        session_id = self.start_session()
        if session_id is None:
            return False, False
        try:
            index = self.find_next_free_index(session_id)
            self.free_index_hint = index
            if index is None:
                index = 1
            # Urządzenia bez searchObjects: szukamy wolnego numeru metodą prób —
            # przy odrzuceniu zapisu bierzemy kolejny numer rejestracji.
            seen_error = None
            other_errors = 0
            for _ in range(60):
                success, _, error_code = self.put_user_entry(
                    session_id, entry_name, protocol, local_ip, local_hostname,
                    share_name, folder_username, folder_password,
                    entry_index=index
                )
                if success:
                    return True, False
                if error_code is None:
                    return False, False          # brak odpowiedzi urządzenia -> zapasowo HTML
                seen_error = error_code
                if error_code != "UDIRECTORY_OBJECT_DUPLICATED":
                    other_errors += 1
                    if other_errors >= 10:
                        break
                index += 1
            # Urządzenie ODPOWIADA i jawnie odrzuca zapis — NIE uruchamiamy HTML,
            # bo zapis HTML nadpisałby istniejący wpis (np. 001).
            self.log(f"  ✖ Urządzenie odrzuciło zapis nowego wpisu (errorCode={seen_error}).")
            return False, True
        finally:
            self.terminate_session(session_id)


class RicohWebClient:
    free_index_hint = None
    """
    Klient Web Image Monitor. Próbuje zarówno HTTP (starsze urządzenia,
    Aficio/MP) jak i HTTPS z verify=False (nowsze urządzenia serii IM ze
    Smart Operation Panel, które często wymuszają szyfrowane połączenie
    z certyfikatem self-signed wygenerowanym przez samo urządzenie —
    normalne w sieci lokalnej, stąd `verify=False` tylko dla komunikacji
    z tym jednym, znanym adresem IP drukarki, nie globalnie dla `requests`).
    """

    def __init__(self, ip, admin_user, admin_pass, log_cb):
        self.ip = ip
        self.admin_user = admin_user if admin_user else "admin"
        self.admin_pass = admin_pass if admin_pass is not None else ""
        self.log = log_cb
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        # Wypróbowywane schematy połączenia, w kolejności: najpierw HTTP
        # (szybsze, obsługuje starsze urządzenia), potem HTTPS z verify=False
        # dla nowszych urządzeń wymuszających szyfrowanie.
        self.schemes = ["http", "https"]

    def _build_payload(self, method, local_ip, protocol):
        # Warianty ogólne (starsze próby, zachowane jako fallback dla innych
        # niż MP 161 modeli, gdzie te nazwy pól mogą być bardziej trafne).
        # UWAGA: mp161_form NIE korzysta z tej metody — to wieloetapowy
        # przepływ (SetUser -> EditPassword -> SetUser), zaimplementowany
        # osobno w _push_mp161_address_entry() na podstawie realnej analizy
        # ruchu sieciowego (plik HAR) z przeglądarki.
        folder_path = f"\\{SHARE_NAME}" if protocol == "smb" else "/"
        payload = {
            "name": TARGET_USER,
            "displayedName": TARGET_USER,
            "smbServerName": local_ip if protocol == "smb" else "",
            "ftpServerName": local_ip if protocol == "ftp" else "",
            "smbPath": folder_path,
            "smbUserName": TARGET_USER,
            "smbPassword": TARGET_PASS,
            "ftpUserName": TARGET_USER,
            "ftpPassword": TARGET_PASS,
        }
        if method == "form_new":
            payload.update({"inputDataType": "1", "type": protocol, "Submit": "OK"})
        elif method == "form_old":
            payload.update({"inputDataType": "1", "addrType": "3", "protocolType": protocol, "OK": "OK"})
        elif method == "form_entry":
            payload.update({"inputDataType": "1", "addrType": "3", "folderType": protocol, "OK": "OK"})
        return payload

    def _fetch_address_list_state(self, session, base_url, base_path, verify):
        """
        Pobiera listę adresową tak jak przeglądarka (POTWIERDZONE w HAR):
        GET .../address/adrsList.cgi. Strona zawiera ukryte pole
        <input name="totalCount" value="N"> z liczbą wpisów (N=0 gdy lista
        pusta). Zwraca (total_count, existing_numbers) albo None gdy odczyt
        się nie udał.
        """
        list_url = f"{base_url}{base_path}/adrsList.cgi"
        try:
            r = session.get(list_url, timeout=6, verify=verify)
            self._dump_step_response(-1, "Lista adresowa (GET adrsList.cgi)", r, {})
            if r.status_code != 200 or self._is_login_page(r.text):
                self.log(f"  Odczyt listy adresowej: HTTP {r.status_code}")
                return None
            m = re.search(r'name="totalCount"\s+value="(\d+)"', r.text)
            if not m:
                self.log("  Odczyt listy adresowej: brak pola totalCount na stronie.")
                return None
            existing = set(re.findall(r'>\s*(\d{3})\s*<', r.text))
            return int(m.group(1)), existing
        except Exception as e:
            self.log(f"  UWAGA: nie udało się odczytać listy adresowej: {e}")
            return None

    def _fetch_free_entry_index(self, session, get_url, verify, fallback=None,
                                 base_url=None, base_path=None):
        """
        Pobiera formularz 'Dodaj użytkownika' i wyciąga rzeczywistą,
        podpowiedzianą przez serwer wartość entryIndexIn.

        KLUCZOWE (potwierdzone przez analizę HAR): to żądanie NIE może być
        okrojonym {"mode": "ADDUSER"} — serwer odrzuca to jako nieprawidłową
        nawigację ("Funkcja [Wstecz] w przeglądarce jest w tym momencie
        niedostępna"), bo oczekuje PEŁNEGO zestawu pól, jakie wysyła
        przeglądarka klikając 'Dodaj użytkownika' z widoku listy adresowej —
        w tym parametry stronicowania (totalCount, offset) i identyfikator
        klikniętego elementu listy. TE WARTOŚCI MUSZĄ ODZWIERCIEDLAĆ
        rzeczywisty stan listy (patrz _fetch_address_list_state) — stałe,
        zahardkodowane wartości działały tylko dopóki lista była pusta.
        """
        total_count = 0
        state = None
        if base_url is not None and base_path is not None:
            state = self._fetch_address_list_state(session, base_url, base_path, verify)
        if state is None:
            self.log("  ✖ Nie udało się odczytać listy adresowej — nie zgaduję numeru wpisu.")
            return fallback
        total_count, existing = state
        self.log(f"  Aktualny stan książki adresowej: {total_count} wpis(ów).")

        full_payload = {
            "mode": "ADDUSER",
            "pageSpecifiedIn": "",
            "pageNumberIn": "1",
            "searchSpecifyModeIn": "",
            "outputSpecifyModeIn": "DEFAULT",
            "entryIndexIn": "",
            "entryNameIn": "",
            "entryFilterIn": "ALL_O",
            "searchItemIn": "SEARCH_INDEX_O",
            "searchDataIn": "",
            "pages": "",
            "listCountIn": "10",
            "totalCount": str(total_count),
            "offset": "0",
        }
        try:
            r = session.post(get_url, data=full_payload, timeout=6, verify=verify)
            self._dump_step_response(0, "GetUser ADDUSER (pobranie numeru wpisu)", r, full_payload)
            if r.status_code == 200:
                if self._is_login_page(r.text):
                    self.log("  UWAGA: pobranie numeru wpisu trafiło na stronę logowania — sesja już wtedy nieważna!")
                elif "wstecz" in r.text.lower() and "niedostępn" in r.text.lower():
                    self.log("  UWAGA: serwer odrzucił żądanie jako nieprawidłową nawigację")
                m = re.search(
                    r'name="entryIndexIn"\s+value="(\d+)"', r.text
                )
                if m:
                    return m.group(1)
                else:
                    self.log("  UWAGA: urządzenie nie podało wolnego numeru wpisu (entryIndexIn)")
        except Exception as e:
            self.log(f"  UWAGA: błąd pobierania numeru wpisu: {e}")
        return fallback

    @staticmethod
    def _is_login_page(text):
        """
        Wykrywa, czy odpowiedź to strona logowania (sesja wygasła/nieważna),
        a nie faktyczny wynik żądanej operacji. KLUCZOWE odkrycie: MP 161
        potrafi odesłać stronę logowania z HTTP 200 i BEZ żadnego słowa
        "error" — więc samo sprawdzenie statusu i braku słów błędu nie
        wystarcza, trzeba jawnie sprawdzić czy to nie jest znowu formularz
        logowania (potwierdzone rzeczywistą odpowiedzią serwera przechwyconą
        podczas testów).
        """
        low = text.lower()
        return (
            'action="login.cgi"' in low
            or ">logowanie<" in low
            or ">login<" in low
        )

    def _push_mp161_address_entry(self, session, base_url, base_path, local_ip, protocol, verify):
        """
        Sekwencja zapisu wpisu w książce adresowej dla Ricoh Aficio MP 161 —
        POTWIERDZONA analizą pliku HAR z przechwyconej sesji przeglądarki
        (3 kroki, dokładnie w tej kolejności, każdy krok wymagany):

        1. adrsSetUser.cgi (inputSpecifyModeIn=SESSION) — zakłada wpis z
           podstawowymi danymi (nazwa, protokół, login autoryzacji folderu),
           BEZ hasła i BEZ ścieżki. To "otwiera sesję edycji" dla kroku 2.
        2. adrsEditPassword.cgi (inputSpecifyMode=FIX) — dopiero tutaj
           zapisywane jest hasło, zakodowane w Base64 (dokładnie jak w
           login.cgi), w polach passwordIn i passwordConfirmIn.
        3. adrsSetUser.cgi (inputSpecifyModeIn=WRITE) — finalny zapis,
           tym razem Z pełną ścieżką UNC w folderPathNameIn
           (np. "\\\\192.168.1.50\\skany" — PEŁNA ścieżka UNC, nie sama
           nazwa udziału, jak błędnie zakładała wcześniejsza wersja kodu).

        Zwraca True jeśli wszystkie 3 kroki zakończyły się sukcesem.
        """
        addr_url = f"{base_url}{base_path}/adrsSetUser.cgi"
        get_url = f"{base_url}{base_path}/adrsGetUser.cgi"
        pass_url = f"{base_url}{base_path}/adrsEditPassword.cgi"

        protocol_value = "SMB_O" if protocol == "smb" else "FTP_O"
        entry_name = TARGET_USER
        # folderPathNameIn to PEŁNA ścieżka UNC (potwierdzone przez HAR:
        # "\\SURFACE\sssss"), nie sama nazwa udziału.
        unc_path = f"\\\\{local_ip}\\{SHARE_NAME}" if protocol == "smb" else ""

        # Numer wolnego slotu (entryIndexIn) MUSI pochodzić z serwera, nie
        # być zgadywany na sztywno jako "001" — w oryginalnym formularzu
        # (adrsGetUser.cgi w trybie ADDUSER) serwer sam podpowiada wolny
        # numer w polu entryIndexIn (np. "002", jeśli "001" jest zajęty
        # przez inny wpis lub zarezerwowany). Wysłanie złego/zajętego numeru
        # może tłumaczyć, dlaczego serwer odpowiadał HTTP 200 (bez słowa
        # "error") ale nic nie zostawało trwale zapisane w książce adresowej.
        if self.free_index_hint is not None:
            # Numer ustalony odczytem listy przez SOAP (jak SDMA) — wiarygodny.
            entry_index = f"{int(self.free_index_hint):03d}"
            self.log(f"  Używam wolnego numeru wpisu ustalonego przez SOAP: {entry_index}")
        else:
            # Strona listy HTML zwracała totalCount=0 mimo istniejących wpisów
            # (log: "Aktualny stan: 0 wpisów", a wpis SMB był na urządzeniu) —
            # zgadywanie numeru nadpisywało użytkownika. Bez wiarygodnego
            # odczytu przez SOAP niczego nie zapisujemy.
            entry_index = None
        if not entry_index:
            self.log("  ✖ Nie ustalono wolnego numeru wpisu — przerywam, żeby nie nadpisać istniejącego użytkownika.")
            return False
        self.log(f"  Numer wolnego wpisu pobrany z urządzenia: {entry_index}")

        common_fields = {
            "mode": "ADDUSER",
            "pageSpecifiedIn": "",
            "pageNumberIn": "",
            "searchSpecifyModeIn": "",
            "outputSpecifyModeIn": "",
            "entryIndexIn": entry_index,
            "entryNameIn": entry_name,
            "userCodeIn": "",
            "smtpAuthAccountIn": "AUTH_SYSTEM_O",
            "folderAuthAccountIn": "AUTH_ASSIGNMENT_O",
            "folderAuthUserNameIn": TARGET_USER,
            "ldapAuthAccountIn": "AUTH_SYSTEM_O",
            "entryUseIn": "ENTRYUSE_TO_O",
            "faxDestIn": "",
            "mailAddressIn": "",
            "folderProtocolIn": protocol_value,
        }
        if protocol == "ftp":
            # Bez tych pól wpis FTP powstawał pusty (bez serwera i portu).
            common_fields["folderPortNoIn"] = "21"
            common_fields["folderServerNameIn"] = local_ip

        # --- Krok 1: SESSION — zakłada wpis, bez hasła i ścieżki ---
        step1 = {
            **common_fields,
            "inputSpecifyModeIn": "SESSION",
            "wayFrom": "adrsGetUser.cgi#AUTH_INFO_C?outputSpecifyModeIn=SETTINGS",
            "wayTo": "adrsEditPassword.cgi?inputSpecifyMode=NONE&kind=FOLDER",
            "folderPathNameIn": "",
        }
        try:
            r1 = session.post(addr_url, data=step1, timeout=6, verify=verify)
        except Exception as e:
            self.log(f"  ✖ Krok 1/3 (SetUser SESSION) nieudany: {e}")
            return False
        self._dump_step_response(1, "SetUser SESSION", r1, step1)
        if r1.status_code != 200:
            self.log(f"  ✖ Krok 1/3 (SetUser SESSION): HTTP {r1.status_code}")
            return False
        if self._is_login_page(r1.text):
            self.log("  ✖ Krok 1/3: sesja nieważna — serwer odesłał stronę logowania zamiast wyniku")
            return False
        if "timeout" in r1.text.lower() or "limit sesji" in r1.text.lower() or "limit czasu" in r1.text.lower():
            self.log("  ✖ Krok 1/3: TIMEOUT sesji już na tym etapie (najwcześniejszy możliwy krok)")
            return False
        self.log("  ✔ Krok 1/3: podstawowe dane wpisu zapisane")

        # --- Krok 2: zapis hasła (Base64, tak jak login.cgi) ---
        # WAŻNE: to hasło KONTA WINDOWS TARGET_USER ('skaner') używanego do
        # autoryzacji dostępu do udostępnionego folderu — NIE hasło
        # administratora drukarki (self.admin_pass), które służy tylko do
        # zalogowania się do panelu Web Image Monitor.
        password_b64 = base64.b64encode(TARGET_PASS.encode("utf-8")).decode("ascii")
        step2 = {
            "mode": "ADDUSER",
            "kind": "FOLDER",
            "inputSpecifyMode": "FIX",
            "wayFrom": "adrsEditPassword.cgi?inputSpecifyMode=NONE&kind=FOLDER",
            "wayTo": "adrsGetUser.cgi#AUTH_INFO_C?outputSpecifyModeIn=SETTINGS",
            "pageSpecifiedIn": "",
            "pageNumberIn": "",
            "searchSpecifyModeIn": "",
            "outputSpecifyModeIn": "",
            "passwordInwk": "",
            "passwordIn": password_b64,
            "passwordConfirmInwk": "",
            "passwordConfirmIn": password_b64,
        }
        try:
            r2 = session.post(pass_url, data=step2, timeout=6, verify=verify)
        except Exception as e:
            self.log(f"  ✖ Krok 2/3 (EditPassword FIX) nieudany: {e}")
            return False
        self._dump_step_response(2, "EditPassword FIX", r2, step2)
        if r2.status_code != 200:
            self.log(f"  ✖ Krok 2/3 (EditPassword FIX): HTTP {r2.status_code}")
            return False
        if self._is_login_page(r2.text):
            self.log("  ✖ Krok 2/3: sesja nieważna — serwer odesłał stronę logowania zamiast wyniku")
            return False
        if "timeout" in r2.text.lower() or "limit sesji" in r2.text.lower() or "limit czasu" in r2.text.lower():
            self.log("  ✖ Krok 2/3: TIMEOUT sesji na etapie zapisu hasła")
            return False
        self.log("  ✔ Krok 2/3: hasło folderu zapisane")

        # --- Krok 3: WRITE — finalny zapis z pełną ścieżką UNC ---
        step3 = {
            **common_fields,
            "inputSpecifyModeIn": "WRITE",
            "wayFrom": "adrsGetUser.cgi?outputSpecifyModeIn=SETTINGS",
            "wayTo": "adrsGetUser.cgi?outputSpecifyModeIn=DEFAULT&mode=ADDUSER",
            "folderPathNameIn": unc_path,
        }
        try:
            r3 = session.post(addr_url, data=step3, timeout=6, verify=verify)
        except Exception as e:
            self.log(f"  ✖ Krok 3/3 (SetUser WRITE) nieudany: {e}")
            return False

        # Zapisujemy PEŁNĄ treść odpowiedzi kroku 3 do pliku diagnostycznego,
        # niezależnie od tego czy wygląda na sukces czy porażkę — odpowiedź
        # HTTP 200 bez słów "error"/"błąd" NIE gwarantuje, że wpis faktycznie
        # zapisał się trwale (może to być np. strona z komunikatem
        # "brakujące wymagane pole" sformułowanym inaczej, albo strona
        # sesji roboczej, która nigdy nie została "zatwierdzona" na stałe).
        self._dump_step_response(3, "SetUser WRITE", r3, step3)

        if self._is_login_page(r3.text):
            self.log(
                "  ✖ Krok 3/3: sesja WYGASŁA W TRAKCIE sekwencji — serwer "
                "odesłał stronę logowania zamiast wyniku zapisu."
            )
            return False
        if "timeout" in r3.text.lower() or "limit sesji" in r3.text.lower() or "limit czasu" in r3.text.lower():
            self.log(
                "  ✖ Krok 3/3: TIMEOUT sesji (serwer zwrócił 'Minął czas "
                "limitu sesji') — sesja wygasła między krokami mimo HTTP 200."
            )
            return False

        # BŁĄD ZNALEZIONY I NAPRAWIONY: strona odpowiedzi ZAWSZE zawiera
        # stały nagłówek szablonu ">Błąd<" w sekcji "responseMessage" na
        # samej górze — to etykieta typu komunikatu (nawet przy SUKCESIE
        # operacji), nie sam wynik. Poprzednia wersja szukała słowa "błąd"
        # GDZIEKOLWIEK na stronie i fałszywie rozpoznawała ten stały
        # nagłówek jako niepowodzenie, mimo że DRUGI, właściwy komunikat
        # niżej na stronie brzmiał "Ustawienia urządzenia zostały
        # zaktualizowane" (POTWIERDZONE analizą realnej odpowiedzi serwera
        # z przechwyconego ruchu — próba FTP, która finalnie się powiodła,
        # ale program błędnie zgłosił ją jako nieudaną).
        success_markers = ["zaktualizowane", "zostały zapisane", "zostało zapisane", "updated successfully"]
        if r3.status_code == 200 and any(m in r3.text.lower() for m in success_markers):
            self.log("  ✔ Krok 3/3: serwer potwierdził aktualizację ustawień")
            return True

        fail_markers = ["error", "invalid", "nieprawidłow"]
        if r3.status_code == 200 and not any(m in r3.text.lower() for m in fail_markers):
            self.log("  ✔ Krok 3/3: serwer odpowiedział bez oczywistego błędu (weryfikacja treści w pliku diagnostycznym)")
            return True

        self.log(f"  ✖ Krok 3/3 (SetUser WRITE): HTTP {r3.status_code} lub treść sugeruje błąd")
        return False

    def _dump_step_response(self, step_num, step_name, response, sent_payload):
        """
        Dopisuje pełną treść odpowiedzi danego kroku sekwencji do WSPÓLNEGO
        pliku diagnostycznego (wszystkie 3 kroki w jednym pliku, z
        timestampem każdego) — 'HTTP 200 bez słowa error' okazał się
        niewystarczającym dowodem trwałego zapisu (potwierdzone: serwer
        odsyłał komunikat "Minął czas limitu sesji" z HTTP 200 i bez
        żadnego z sprawdzanych wcześniej słów kluczowych błędu). Zbieranie
        WSZYSTKICH kroków w jednym pliku z czasem pozwala zmierzyć, ile
        faktycznie mija między krokami i na którym dokładnie ginie sesja.
        """
        import datetime
        try:
            app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
            diag_path = os.path.join(app_dir, "ricoh_diagnostyka_krokow.txt")
            # UWAGA: -1 (odczyt listy adresowej) jest teraz PIERWSZYM krokiem
            # wykonywanym w całej sekwencji (przed krokiem 0) — to on musi
            # otworzyć plik na czysto, inaczej krok 0 by go później nadpisał
            # i skasował diagnostykę próby odczytu listy.
            mode = "w" if step_num == -1 else "a"
            with open(diag_path, mode, encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"KROK {step_num}: {step_name} — {datetime.datetime.now().isoformat()}\n")
                f.write(f"{'='*60}\n")
                f.write("--- Wysłane dane ---\n")
                for k, v in sent_payload.items():
                    f.write(f"{k} = {v}\n")
                f.write(f"\n--- Odpowiedź: HTTP {response.status_code} ---\n")
                f.write(f"URL: {response.url}\n")
                f.write("--- Nagłówki ---\n")
                for k, v in response.headers.items():
                    f.write(f"{k}: {v}\n")
                f.write("--- Treść (pełna) ---\n")
                f.write(response.text)
                f.write("\n")
            self.log(f"  (Odpowiedź kroku {step_num} dopisana do: {diag_path})")
        except Exception as e:
            self.log(f"  UWAGA: nie udało się zapisać pliku diagnostycznego kroku {step_num}: {e}")

    def _login_payload_variants(self):
        """
        Buduje warianty payloadu logowania. Starsze urządzenia (potwierdzone
        na Ricoh Aficio MP 161 przez analizę rzeczywistej strony logowania)
        wymagają loginu/hasła zakodowanego w Base64 — dokładnie tak, jak robi
        to JavaScript (funkcja base64encode()) na oryginalnej stronie
        logowania, zamiast wysyłania ich jawnym tekstem. Zwracamy oba
        warianty (Base64 i jawny tekst), żeby obsłużyć różne generacje
        firmware bez zgadywania z góry, którego użyć.
        """
        userid_b64 = base64.b64encode(self.admin_user.encode("utf-8")).decode("ascii")
        password_b64 = base64.b64encode(self.admin_pass.encode("utf-8")).decode("ascii")

        return [
            {  # Wariant Base64 — potwierdzony na starszych urządzeniach (MP 161)
                "userid_work": "", "userid": userid_b64,
                "password_work": "", "password": password_b64,
                "open": "",
            },
            {  # Wariant jawny — dla innych/nowszych generacji firmware
                "userid": self.admin_user,
                "password": self.admin_pass,
                "open": "",
            },
        ]

    def _detect_base_url(self):
        """
        Próbuje po kolei HTTP i HTTPS, zwraca pierwszy działający base_url
        oraz treść strony głównej (do wykrycia profilu urządzenia).
        HTTPS używa verify=False — świadomie, tylko dla tego jednego,
        znanego adresu IP drukarki w sieci lokalnej (nie zmienia to
        weryfikacji certyfikatów dla żadnych innych połączeń w programie).
        """
        for scheme in self.schemes:
            url = f"{scheme}://{self.ip}"
            try:
                verify = False if scheme == "https" else True
                r = self.session.get(url, timeout=4, verify=verify)
                if r.status_code == 200:
                    return url, r.text, scheme
            except Exception:
                continue
        return None, "", None

    @staticmethod
    def _extract_hidden_fields(html):
        """
        Wyciąga wszystkie pola `<input type="hidden" name="..." value="...">`
        z podanego HTML. Wiele starszych CGI-aplikacji Ricoh (webArch) wymaga
        w POST tokenu sesji/CSRF przekazanego właśnie w takim ukrytym polu —
        bez niego serwer może po cichu odrzucić zapis, mimo że reszta danych
        (login, hasło, ścieżka) jest poprawna. Zwraca dict {name: value}.
        Odporne na różną kolejność atrybutów w tagu (name przed value i na
        odwrót) i na single/double quotes.
        """
        fields = {}
        # Dowolna kolejność atrybutów: type="hidden" ... name="x" ... value="y"
        # Szukamy każdego <input ...> zawierającego type="hidden", potem
        # osobno wyciągamy z tego samego tagu name= i value=.
        for tag in re.findall(r'<input\b[^>]*>', html, re.IGNORECASE):
            if not re.search(r'type\s*=\s*["\']hidden["\']', tag, re.IGNORECASE):
                continue
            name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
            value_match = re.search(r'value\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if name_match:
                fields[name_match.group(1)] = value_match.group(1) if value_match else ""
        return fields

    def _fetch_hidden_fields(self, url, verify):
        """Wrapper zachowujący kompatybilność wsteczną — deleguje do
        _fetch_hidden_fields_with używając self.session."""
        return self._fetch_hidden_fields_with(self.session, url, verify)

    def _fetch_hidden_fields_with(self, session, url, verify):
        """
        Pobiera stronę pod danym URL (GET) przez PODANĄ sesję i zwraca
        ukryte pola formularza znalezione na niej. Przyjmowanie sesji jako
        parametru (zamiast zawsze self.session) jest kluczowe — pozwala
        wywołującemu użyć świeżej, izolowanej sesji per próba logowania,
        żeby cookies z jednej nieudanej kombinacji ścieżka+wariant nie
        zanieczyszczały kolejnej próby.
        """
        try:
            r = session.get(url, timeout=4, verify=verify)
            if r.status_code != 200:
                return {}
            fields = self._extract_hidden_fields(r.text)
            if fields:
                self.log(f"  Znaleziono {len(fields)} ukrytych pól formularza na {url}")
            return fields
        except Exception:
            return {}

    def dump_address_book(self, logger_cb=print):
        """Loguje zawartość książki adresowej tak, jak widzi ją urządzenie."""
        for scheme in ("http",):
            try:
                sc = RicohSoapClient(self.ip, self.admin_user, self.admin_pass, lambda m: None,
                                     port=80, scheme=scheme, verify=True)
                sid = sc.start_session()
                if sid is None:
                    logger_cb("  Nie udało się nawiązać sesji SOAP — brak odczytu książki adresowej.")
                    return
                try:
                    entries = sc.list_entries(sid)
                finally:
                    sc.terminate_session(sid)
                if entries is None:
                    logger_cb("  Odczyt książki adresowej przez SOAP nie powiódł się.")
                    return
                if not entries:
                    logger_cb("  Książka adresowa jest pusta.")
                for e in entries:
                    logger_cb("  WPIS " + ", ".join(f"{k}={v}" for k, v in e.items() if v != ""))
                return
            except Exception as ex:
                logger_cb(f"  Błąd odczytu książki adresowej: {ex}")

    def _try_soap_add_user(self, local_ip, protocol):
        """
        Próbuje dodać wpis przez oficjalny protokół SOAP (RicohSoapClient).
        Próbuje HTTP i HTTPS, tak jak reszta klienta.

        Zwraca (success: bool, skip_fallback: bool) — patrz docstring
        RicohSoapClient.add_scan_user() po wyjaśnienie, dlaczego to
        rozróżnienie jest konieczne (zapobiega podwójnemu wpisowi TYLKO
        gdy urządzenie jawnie potwierdza "duplikat", nie dla każdego
        niejasnego błędu — np. MP 161).

        KRYTYCZNE: każda próba (per schemat http/https) jest opakowana w
        try/except łapiący KAŻDY wyjątek, nie tylko sygnalizowane False.
        Bez tego, jeśli cokolwiek w głębi RicohSoapClient rzuci wyjątek
        (np. nietypowa odpowiedź serwera, błąd sieci w nieoczekiwanym
        miejscu) — wcześniejsza wersja pozwalała temu wyjątkowi przerwać
        CAŁĄ metodę push_address_book, przez co program NIGDY nie docierał
        do fallbacku HTML (sekwencji adrsSetUser.cgi), mimo że ten fallback
        mógłby zadziałać.
        """
        local_hostname = get_local_hostname()

        self.log(
            f" W książce adresowej zostanie wpisane logowanie do folderu "
            f"({protocol.upper()}): login='{TARGET_USER}', hasło='{TARGET_PASS}' "
            f"— dokładnie te same dane, co konto Windows utworzone na tym komputerze."
        )

        any_skip_fallback = False
        for scheme in self.schemes:
            verify = False if scheme == "https" else True
            try:
                soap_client = RicohSoapClient(
                    self.ip, self.admin_user, self.admin_pass, self.log,
                    port=(443 if scheme == "https" else 80), scheme=scheme, verify=verify
                )
                success, skip_fallback = soap_client.add_scan_user(
                    entry_name=TARGET_USER,
                    protocol=protocol,
                    local_ip=local_ip,
                    local_hostname=local_hostname,
                    share_name=SHARE_NAME,
                    folder_username=TARGET_USER,
                    folder_password=TARGET_PASS,
                )
                any_skip_fallback = any_skip_fallback or skip_fallback
                if soap_client.free_index_hint is not None:
                    self.free_index_hint = soap_client.free_index_hint
                if success:
                    return True, True
            except Exception as e:
                self.log(f"  ✖ Nieoczekiwany błąd podczas próby SOAP ({scheme}): {e}")
                continue
        return False, any_skip_fallback

    def push_address_book(self, local_ip, protocol="smb"):
        global _SOAP_DUMP_INITIALIZED
        _SOAP_DUMP_INITIALIZED = False  # nowy przebieg -> nowy plik diagnostyczny SOAP

        pass_info = "puste" if not self.admin_pass else "podane"
        self.log(f"Łączenie z Ricoh {self.ip} jako '{self.admin_user}' (hasło: {pass_info})...")

        # ── PRIORYTET: oficjalny protokół SOAP (jak Smart Device Monitor) ──
        # POTWIERDZONY przechwyceniem prawdziwego ruchu sieciowego SDMA
        # (Wireshark) — znacznie prostszy i bardziej niezawodny niż
        # odtwarzanie formularzy HTML webArch. Próbowany jako pierwszy;
        # jeśli się nie powiedzie (np. starszy model bez tego API), kod
        # spada do logiki HTML poniżej jako fallback.
        self.log(" Próba przez oficjalny protokół SOAP (jak Smart Device Monitor)...")
        try:
            soap_success, soap_skip_fallback = self._try_soap_add_user(local_ip, protocol)
        except Exception as e:
            # Druga, zewnętrzna warstwa ochronna — na wypadek wyjątku poza
            # samą pętlą prób (np. w get_local_hostname()) — żeby FTP/SMB
            # ZAWSZE dotarło do próby fallbacku HTML poniżej, niezależnie
            # od tego, co dokładnie poszło nie tak w SOAP.
            self.log(f" ✖ Nieoczekiwany błąd w module SOAP: {e} — przechodzę do fallbacku HTML.")
            soap_success, soap_skip_fallback = False, False
        if soap_success:
            return True

        # ── ZABEZPIECZENIE PRZED PODWÓJNYM WPISEM ──
        # NAPRAWIONE (poprzednia wersja była zbyt agresywna i blokowała
        # SMB, który miał zupełnie INNY, niejasny powód niepowodzenia):
        # pomijamy fallback HTML TYLKO gdy urządzenie JAWNIE potwierdza
        # "duplikat" (errorCode UDIRECTORY_OBJECT_DUPLICATED) — to jedyny
        # przypadek, gdzie wiemy NA PEWNO, że wpis już istnieje pod danym
        # indeksem i próba HTML trafiłaby w ten sam, zajęty slot. Dla
        # wszystkich innych niepowodzeń (w tym niejasnych kodów liczbowych
        # 74-79 bez opisu) nadal próbujemy fallbacku HTML — nie mamy
        # jednoznacznego dowodu "już zapisane", więc bezpieczniej spróbować.
        self.log(" Protokół SOAP nie zadziałał — przechodzę na odtwarzanie formularzy HTML...")

        try:
            base_url, page_content, scheme = self._detect_base_url()
            if base_url is None:
                self.log(" Błąd połączenia z urządzeniem Ricoh: brak odpowiedzi na HTTP i HTTPS")
                return False

            verify = False if scheme == "https" else True
            self.log(f" Połączono przez {scheme.upper()}")
            content = page_content.lower()

            matched_profile = None
            for p in RICOH_PROFILES:
                if any(k in content for k in p["detect"]):
                    matched_profile = p
                    break

            paths_to_try = []
            if matched_profile:
                self.log(f" Wykryto profil kserokopiarki: {matched_profile['name']}")
                base = matched_profile["base_path"].replace("{lang}", matched_profile["lang"])
                paths_to_try.append((base, matched_profile["method"]))

            # Dopisz fallbacki pomijając duplikaty tego, co już wykryty
            # profil ustawił jako pierwszą próbę — próbowanie tej samej
            # ścieżki drugi raz nic nie wnosi, a dla sekwencji wieloetapowych
            # (mp161_form) niepotrzebnie powtarza operacje na urządzeniu.
            for fp in FALLBACK_PATHS:
                if fp not in paths_to_try:
                    paths_to_try.append(fp)

            login_variants = self._login_payload_variants()

            # Logowanie (login.cgi/authForm.cgi) na starszych urządzeniach
            # (potwierdzone na MP 161) żyje pod /websys/webArch/, w INNYM
            # katalogu niż zarządzanie książką adresową (/address/) —
            # dlatego login zawsze próbujemy pod tą stałą listą ścieżek,
            # niezależnie od tego, gdzie leży formularz zapisu dla wykrytej
            # metody. Dla profili "starego typu" (form_new/form_old/
            # form_entry) login i zapis historycznie dzieliły tę samą
            # ścieżkę — zachowane jako pierwsza próba dla kompatybilności.
            login_paths_to_try = []
            # Priorytet: ścieżka POTWIERDZONA przez rzeczywisty plik HAR
            # (/web/guest/pl/websys/webArch/login.cgi) zawsze pierwsza —
            # wcześniejsza kolejność (najpierw fallbacki, w tym angielski
            # wariant z innego profilu) prowadziła do sytuacji, gdzie
            # program logował się przez NIEPOTWIERDZONĄ ścieżkę, dostawał
            # HTTP 200 (pozornie "zalogowano"), ale sesja nie była w pełni
            # poprawna — co ujawniało się dopiero przy finalnym zapisie
            # (krok 3 dostawał z powrotem stronę logowania).
            login_paths_to_try.append(("/web/guest/pl/websys/webArch", "login_here"))
            for base_path, method in paths_to_try:
                if method != "mp161_form" and (base_path, "login_here") not in login_paths_to_try:
                    login_paths_to_try.append((base_path, "login_here"))
            for lang in ("pl", "en"):
                candidate = (f"/web/guest/{lang}/websys/webArch", "login_here")
                if candidate not in login_paths_to_try:
                    login_paths_to_try.append(candidate)
                candidate2 = (f"/web/entry/{lang}/websys/webArch", "login_here")
                if candidate2 not in login_paths_to_try:
                    login_paths_to_try.append(candidate2)

            for login_base_path, _ in login_paths_to_try:
                login_url = f"{base_url}{login_base_path}/login.cgi"

                for variant in login_variants:
                    # Świeża sesja per próba — kluczowe: `requests.Session()`
                    # trzyma cookies między wywołaniami. Bez tego, nieudana
                    # próba logowania na ŹLE dopasowanej ścieżce mogła ustawić
                    # błędne/wygasłe ciasteczko sesyjne, które psuło KOLEJNĄ,
                    # potencjalnie poprawną kombinację ścieżka+wariant.
                    attempt_session = requests.Session()
                    attempt_session.headers.update(self.session.headers)

                    login_hidden_fields = self._fetch_hidden_fields_with(
                        attempt_session, f"{base_url}{login_base_path}/authForm.cgi", verify
                    )
                    full_payload = {**login_hidden_fields, **variant}
                    try:
                        res = attempt_session.post(login_url, data=full_payload, timeout=4, verify=verify)
                    except Exception:
                        continue

                    # Poszerzony zestaw znaczników błędu (oryginał sprawdzał
                    # tylko angielskie "invalid" — dodano polskie warianty,
                    # bo panel MP 161 bywa w języku polskim).
                    login_failed_markers = ["invalid", "błąd", "error", "nieprawidłow"]
                    still_on_login_page = self._is_login_page(res.text)
                    login_ok = (
                        res.status_code in (200, 302)
                        and not still_on_login_page
                        and not any(m in res.text.lower() for m in login_failed_markers)
                    )
                    if not login_ok:
                        if still_on_login_page:
                            self.log("  (odpowiedź to nadal strona logowania — dane odrzucone)")
                        continue

                    self.log(" ✔ Zalogowano pomyślnie do panelu WIM Ricoh!")

                    # Sesja jest teraz zalogowana (attempt_session ma ważne
                    # cookie) — próbujemy WSZYSTKICH znanych ścieżek/metod
                    # zapisu książki adresowej z tą samą, już-zalogowaną
                    # sesją, zamiast logować się od nowa dla każdej.
                    for save_base_path, method in paths_to_try:
                        if method == "mp161_form":
                            # Sekwencja 3-etapowa POTWIERDZONA analizą HAR
                            # (SetUser SESSION -> EditPassword FIX -> SetUser
                            # WRITE) — zbyt złożona na prosty jednorazowy POST,
                            # więc ma dedykowaną metodę.
                            self.log(" Zapisywanie wpisu (sekwencja MP 161: 3 kroki)...")
                            success = self._push_mp161_address_entry(
                                attempt_session, base_url, save_base_path,
                                local_ip, protocol, verify
                            )
                            if success:
                                self.log(" ✔ Użytkownik dodany do książki adresowej (adrsSetUser.cgi)!")
                                return True
                            continue

                        # Endpoint zapisu dla pozostałych, starszych profili
                        # (historyczne, mniej pewne nazwy pól).
                        save_file = "addressBook.cgi"
                        addr_url = f"{base_url}{save_base_path}/{save_file}"

                        # To samo dla formularza książki adresowej — pobierz go
                        # GET-em przed wysłaniem POST, żeby dołączyć ewentualne
                        # ukryte pola (token, numer wpisu itd.) wygenerowane
                        # specjalnie dla tej sesji/wizyty. Ta sama attempt_session,
                        # żeby zachować ciasteczko sesyjne z udanego logowania.
                        addr_hidden_fields = self._fetch_hidden_fields_with(attempt_session, addr_url, verify)
                        payload = {**addr_hidden_fields, **self._build_payload(method, local_ip, protocol)}

                        try:
                            post_res = attempt_session.post(addr_url, data=payload, timeout=6, verify=verify)
                        except Exception:
                            continue

                        post_failed_markers = ["error", "błąd", "invalid", "nieprawidłow"]
                        if post_res.status_code == 200 and not any(
                            m in post_res.text.lower() for m in post_failed_markers
                        ):
                            self.log(f" ✔ Użytkownik dodany do książki adresowej ({save_file})!")
                            return True

            self.log(" ⚠ Nie udało się automatycznie zapisać wpisu w WIM. Dodaj użytkownika ręcznie.")
            return False
        except Exception as e:
            self.log(f" Błąd połączenia z urządzeniem Ricoh: {e}")
            return False


def run_configuration(copier_ip, protocol, local_ip, map_drive, admin_user, admin_pass,
                      logger_cb=print, include_report=True):
    """
    Pełna konfiguracja (wspólna dla okna GUI i trybu CMD): środowisko Windows,
    serwer FTP (IIS) dla FTP, skrót, mapowanie dysku, wpis w książce adresowej
    drukarki, wykrycie antywirusa i raport diagnostyczny.
    Zwraca (success_wpis_w_ksiazce, tekst_raportu, slownik_podsumowania).
    """
    logger_cb(f"IP komputera (wybrana karta sieciowa): {local_ip}")
    setup_windows_environment(copier_ip, protocol, logger_cb)

    if protocol == "ftp":
        ftp_ok = configure_windows_ftp_server(
            TARGET_FOLDER, TARGET_USER, port=21, external_ip=local_ip, logger_cb=logger_cb
        )
        if not ftp_ok:
            logger_cb(
                " ✖ Konfiguracja wbudowanego serwera FTP (IIS) nie powiodła się — "
                "sprawdź komunikaty powyżej. Sprawdź czy masz uprawnienia "
                "administratora i czy komputer nie jest zbyt ograniczoną edycją Windows."
            )
        time.sleep(2)  # chwila na pełny restart usługi po appcmd
        test_local_ftp_access("127.0.0.1", 21, logger_cb)

    create_desktop_shortcut(TARGET_FOLDER, "Skany", logger_cb)

    if map_drive and protocol == "smb":
        map_network_drive("S", SHARE_NAME, logger_cb)
    elif map_drive and protocol == "ftp":
        logger_cb(" UWAGA: mapowanie dysku (net use) działa tylko dla SMB — pominięto, bo wybrano protokół FTP.")

    client = RicohWebClient(copier_ip, admin_user, admin_pass, logger_cb)
    success = client.push_address_book(local_ip, protocol)

    security_products = detect_security_software(logger_cb)
    build_security_software_exclusion_instructions(copier_ip, security_products, logger_cb)

    if include_report:
        collect_full_report(copier_ip, local_ip, protocol, logger_cb, web_client=client)

    destination = f"\\\\{local_ip}\\{SHARE_NAME}" if protocol == "smb" else f"ftp://{local_ip}/"
    report = (
        f"\n========================================\n"
        f" KONFIGURACJA ZAKOŃCZONA\n"
        f" Użytkownik: {TARGET_USER} | Hasło: {TARGET_PASS}\n"
        f" Folder skanów: {TARGET_FOLDER}\n"
        f" Ścieżka docelowa: {destination}\n"
        f" Status Kserokopiarki: {'SUKCES (Wpis w książce gotowy)' if success else 'SKONFIGURUJ RĘCZNIE W WIM'}\n"
        f"========================================"
    )
    summary = {"folder_path": TARGET_FOLDER, "destination": destination,
               "local_ip": local_ip, "protocol": protocol}
    return success, report, summary


class LoggingTextEdit(QTextEdit):
    """Konsola, która każdą dopisywaną linię zapisuje też do szczegółowego logu."""
    def append(self, text):
        dlog(text)
        super().append(text)


class WorkerSignals(QObject):
    log = Signal(str)
    finished = Signal(bool, str)
    ips_found = Signal(list)
    scan_finished = Signal()
    sac_result = Signal(dict)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(COPYRIGHT_TITLE)
        self.setMinimumSize(620, 600)
        self.resize(630, 800)
        dlog("=" * 70)
        dlog(f"START PROGRAMU  WERSJA={APP_VERSION}  admin={is_admin()}  exe={sys.executable}  python={sys.version.split()[0]}")
        self.signals = WorkerSignals()
        self.signals.log.connect(self._append_log)
        self.signals.sac_result.connect(self._on_sac_result)
        self.signals.finished.connect(self._on_finished)
        self.signals.ips_found.connect(self._set_ips)
        self.signals.scan_finished.connect(self._on_scan_finished)
        self._last_summary = None
        self._build_ui()
        self._load_saved_settings()
        self._setup_scan_folder_watcher()

    def _setup_scan_folder_watcher(self):
        """
        Obserwuje TARGET_FOLDER i powiadamia w konsoli, gdy pojawi się nowy
        plik — to jedyny namacalny dowód, że drukarka faktycznie zapisuje
        skany (automatyczna konfiguracja książki adresowej bywa niepewna
        na starszych/nietypowych modelach, więc realny plik > sam status
        "konfiguracja zakończona").
        """
        if not os.path.isdir(TARGET_FOLDER):
            os.makedirs(TARGET_FOLDER, exist_ok=True)
        self.fs_watcher = QFileSystemWatcher([TARGET_FOLDER])
        self._known_files = set(os.listdir(TARGET_FOLDER)) if os.path.isdir(TARGET_FOLDER) else set()
        self.fs_watcher.directoryChanged.connect(self._on_scan_folder_changed)

    def _on_scan_folder_changed(self, path):
        try:
            current_files = set(os.listdir(path))
        except OSError:
            return
        new_files = current_files - self._known_files
        self._known_files = current_files
        for f in new_files:
            self.console.append(f"📄 Wykryto nowy plik w folderze skanów: {f}")
        if new_files:
            QApplication.alert(self)  # miganie ikony na pasku zadań

    def _load_saved_settings(self):
        """Wypełnia pola ostatnio użytymi wartościami (bez hasła — celowo
        nigdy nie zapisywanego na dysk)."""
        settings = load_settings()
        if not settings:
            return
        if settings.get("ip"):
            self.ip_input.addItem(settings["ip"])
            self.ip_input.setCurrentText(settings["ip"])
        if settings.get("admin_user"):
            self.admin_user.setText(settings["admin_user"])
        if settings.get("protocol") == "ftp":
            self.radio_ftp.setChecked(True)
        nic = settings.get("nic")
        if nic:
            idx = self.nic_selector.findText(nic)
            if idx >= 0:
                self.nic_selector.setCurrentIndex(idx)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        title = QLabel(APP_TITLE)
        title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(title)

        dev_box = QGroupBox("Kserokopiarka Ricoh")
        dev_layout = QVBoxLayout(dev_box)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("IP Urządzenia:"))
        self.ip_input = QComboBox()
        self.ip_input.setEditable(True)  # nadal można wpisać IP ręcznie
        self.ip_input.lineEdit().setPlaceholderText("Wpisz IP lub kliknij Wykryj")
        self.ip_input.lineEdit().returnPressed.connect(self._on_confirm_ip_clicked)
        h1.addWidget(self.ip_input, stretch=1)

        self.btn_confirm_ip = QPushButton("✓ Ustaw IP")
        self.btn_confirm_ip.setToolTip("Zatwierdź ręcznie wpisany adres IP (albo naciśnij Enter w polu)")
        self.btn_confirm_ip.clicked.connect(self._on_confirm_ip_clicked)
        h1.addWidget(self.btn_confirm_ip)

        self.btn_scan = QPushButton("🔍 Wykryj w sieci")
        self.btn_scan.clicked.connect(self._auto_detect_ip)
        h1.addWidget(self.btn_scan)
        dev_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Login Admin:"))
        self.admin_user = QLineEdit("admin")
        h2.addWidget(self.admin_user)

        h2.addWidget(QLabel("Hasło Admin:"))
        self.admin_pass = QLineEdit()
        self.admin_pass.setEchoMode(QLineEdit.Password)
        self.admin_pass.setPlaceholderText("(domyślnie puste)")
        h2.addWidget(self.admin_pass)
        dev_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Karta sieciowa (IP komputera):"))
        self.nic_selector = QComboBox()
        self._populate_nic_selector()
        h3.addWidget(self.nic_selector, stretch=1)
        self.btn_refresh_nics = QPushButton("↻")
        self.btn_refresh_nics.setFixedWidth(32)
        self.btn_refresh_nics.setToolTip("Odśwież listę kart sieciowych")
        self.btn_refresh_nics.clicked.connect(self._populate_nic_selector)
        h3.addWidget(self.btn_refresh_nics)
        self.btn_diagnose_nics = QPushButton("🩺 Diagnostyka kart sieciowych")
        self.btn_diagnose_nics.setToolTip(
            "Sprawdź, czy karta Ethernet do drukarki jest w ogóle aktywna "
            "i ma przypisany adres IP."
        )
        self.btn_diagnose_nics.clicked.connect(self._on_diagnose_nics_clicked)
        h3.addWidget(self.btn_diagnose_nics)
        dev_layout.addLayout(h3)

        nic_hint = QLabel(
            "Wybierz właściwy adres, jeśli komputer ma kilka kart sieciowych "
            "(np. Wi-Fi + Ethernet do drukarki w innej podsieci). Skanowanie "
            "sieci przeszukuje teraz WSZYSTKIE aktywne karty automatycznie — "
            "jeśli mimo to drukarka nie zostanie znaleziona, użyj przycisku "
            "diagnostyki powyżej."
        )
        nic_hint.setWordWrap(True)
        nic_hint.setStyleSheet("color: #6c757d; font-size: 11px;")
        nic_hint.setMinimumHeight(48)  # miejsce na zawinięty tekst (3 linie) - bez tego bywa ucinany
        dev_layout.addWidget(nic_hint)

        layout.addWidget(dev_box)

        proto_box = QGroupBox("Protokół skanowania")
        proto_layout = QVBoxLayout(proto_box)

        proto_radio_row = QHBoxLayout()
        self.radio_smb = QRadioButton("SMB (Udział sieciowy Windows)")
        self.radio_ftp = QRadioButton("FTP (Gdy SMB jest blokowane w danej sieci)")
        self.radio_smb.setChecked(True)
        proto_radio_row.addWidget(self.radio_smb)
        proto_radio_row.addWidget(self.radio_ftp)
        proto_layout.addLayout(proto_radio_row)

        options_row = QHBoxLayout()
        self.chk_map_drive = QCheckBox("Zmapuj folder jako Dysk S:")
        self.chk_map_drive.setToolTip(
            r"net use S: \\localhost\skany /persistent:yes — dysk będzie "
            r"widoczny w Eksploratorze i przetrwa restart komputera."
        )
        options_row.addWidget(self.chk_map_drive)

        self.btn_check_ports = QPushButton("🔌 Sprawdź porty przed konfiguracją")
        self.btn_check_ports.clicked.connect(self._on_check_ports_clicked)
        options_row.addWidget(self.btn_check_ports)
        proto_layout.addLayout(options_row)

        layout.addWidget(proto_box)

        # ── Sekcja zaawansowana: diagnostyka starszych urządzeń ──
        # Celowo wizualnie oddzielona i wyciszona (jaśniejszy tekst, mniejsza
        # ranga) — to nie jest krok zwykłego przebiegu konfiguracji, tylko
        # świadomie wybierana opcja awaryjna.
        legacy_box = QGroupBox("⚠ Zaawansowane / Diagnostyka starszych urządzeń (Aficio / MP)")
        legacy_layout = QVBoxLayout(legacy_box)

        legacy_info = QLabel(
            "Użyj TYLKO jeśli bardzo stare urządzenie (sprzed ok. 2012) nie może się\n"
            "połączyć mimo włączonego SMB1. Włącza NTLMv1 i logowanie gościa —\n"
            "obniża to bezpieczeństwo całego komputera, nie tylko połączenia z drukarką."
        )
        legacy_info.setStyleSheet("color: #6c757d; font-size: 11px;")
        legacy_layout.addWidget(legacy_info)

        legacy_btn_row = QHBoxLayout()
        self.btn_legacy_enable = QPushButton("Włącz obsługę starszych urządzeń")
        self.btn_legacy_enable.clicked.connect(self._on_legacy_enable_clicked)
        legacy_btn_row.addWidget(self.btn_legacy_enable)

        self.btn_legacy_revert = QPushButton("Przywróć bezpieczne ustawienia")
        self.btn_legacy_revert.clicked.connect(self._on_legacy_revert_clicked)
        legacy_btn_row.addWidget(self.btn_legacy_revert)
        legacy_layout.addLayout(legacy_btn_row)

        layout.addWidget(legacy_box)

        # ── Sekcja: Smart App Control (Windows) ──
        # Przycisk FAKTYCZNIE wyłącza SAC (zapis rejestru VerifiedAndReputable-
        # PolicyState=0 + CiTool.exe --refresh, metoda udokumentowana przez
        # Microsoft Learn — patrz disable_smart_app_control). Widoczny i
        # aktywny tylko dla administratora; każda operacja wymaga jawnego
        # potwierdzenia w oknie ostrzeżenia (patrz _on_sac_disable_clicked).
        sac_box = QGroupBox("⚠ Smart App Control (Inteligentna kontrola aplikacji)")
        sac_layout = QVBoxLayout(sac_box)
        sac_info = QLabel(
            "Smart App Control to funkcja zabezpieczeń CAŁEGO systemu Windows.\n"
            "Przycisk poniżej TRWALE ją wyłączy (po Twoim potwierdzeniu) — zapisze\n"
            "ustawienie w rejestrze systemowym i odświeży polityki poleceniem CiTool."
        )
        sac_info.setStyleSheet("color: #6c757d; font-size: 11px;")
        sac_info.setWordWrap(True)
        sac_layout.addWidget(sac_info)
        self.btn_sac_disable = QPushButton("Wyłącz Smart App Control")
        self.btn_sac_disable.clicked.connect(self._on_sac_disable_clicked)
        self.btn_sac_disable.setEnabled(is_admin())
        if not is_admin():
            self.btn_sac_disable.setToolTip("Dostępne tylko przy uruchomieniu programu jako Administrator.")
        sac_layout.addWidget(self.btn_sac_disable)
        layout.addWidget(sac_box)

        run_row = QHBoxLayout()

        self.btn_run = QPushButton("⚡ KONFIGURUJ (1-KLIK)")
        self.btn_run.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.btn_run.setFixedHeight(45)
        self.btn_run.setStyleSheet("background-color: #0d6efd; color: white; border-radius: 4px;")
        self.btn_run.clicked.connect(self._start_process)
        run_row.addWidget(self.btn_run, stretch=2)

        self.btn_test_share = QPushButton("🧪 Testuj udostępnianie")
        self.btn_test_share.setFixedHeight(45)
        self.btn_test_share.clicked.connect(self._on_test_share_clicked)
        run_row.addWidget(self.btn_test_share, stretch=1)

        self.btn_rollback = QPushButton("↩ Cofnij konfigurację")
        self.btn_rollback.setFixedHeight(45)
        self.btn_rollback.setToolTip(
            "Usuwa konto, udział SMB, reguły zapory i wykluczenie Defendera. "
            "Folder ze skanami NIE zostanie usunięty."
        )
        self.btn_rollback.clicked.connect(self._on_rollback_clicked)
        run_row.addWidget(self.btn_rollback, stretch=1)

        layout.addLayout(run_row)

        self.btn_full_diagnostics = QPushButton("🩺 DIAGNOSTYKA NA ŻYWO — dlaczego skany nie wpadają do folderu?")
        self.btn_full_diagnostics.setFixedHeight(40)
        self.btn_full_diagnostics.setStyleSheet(
            "background-color: #6f42c1; color: white; border-radius: 4px; font-weight: bold;"
        )
        self.btn_full_diagnostics.setToolTip(
            "Przechodzi po kolei przez wszystkie najczęstsze przyczyny, dla których "
            "skany nie docierają do folderu: sieć, usługę Windows, zaporę, antywirus, "
            "Defendera, uprawnienia NTFS i rzeczywisty test zapisu."
        )
        self.btn_full_diagnostics.clicked.connect(self._on_full_diagnostics_clicked)
        layout.addWidget(self.btn_full_diagnostics)

        self.btn_live_monitor = QPushButton("📡 ROZPOCZNIJ MONITOROWANIE SKANOWANIA NA ŻYWO")
        self.btn_live_monitor.setFixedHeight(40)
        self.btn_live_monitor.setStyleSheet(
            "background-color: #198754; color: white; border-radius: 4px; font-weight: bold;"
        )
        self.btn_live_monitor.setToolTip(
            "Obserwuje na żywo: log IIS FTP, nowe połączenia sieciowe od drukarki "
            "i nowe pliki w folderze skanów. Uruchom PRZED naciśnięciem [Skanuj] "
            "na panelu drukarki, żeby zobaczyć dokładnie, na którym etapie transfer "
            "się zatrzymuje."
        )
        self.btn_live_monitor.clicked.connect(self._on_toggle_live_monitor)
        layout.addWidget(self.btn_live_monitor)

        self.btn_full_report = QPushButton("📋 ZBIERZ PEŁNY RAPORT DIAGNOSTYCZNY (do wysłania)")
        self.btn_full_report.setFixedHeight(40)
        self.btn_full_report.setStyleSheet(
            "background-color: #0d6efd; color: white; border-radius: 4px; font-weight: bold;"
        )
        self.btn_full_report.clicked.connect(self._on_full_report_clicked)
        layout.addWidget(self.btn_full_report)

        self._live_monitor_timer = None
        self._live_monitor_state = {}

        self.console = LoggingTextEdit()
        self.console.setReadOnly(True)
        layout.addWidget(self.console)

    def _append_log(self, txt):
        self.console.append(txt)

    def _on_confirm_ip_clicked(self):
        """
        Zatwierdza ręcznie wpisany adres IP: sprawdza poprawność formatu,
        dodaje go do listy (jeśli jeszcze go tam nie ma) i daje wyraźne
        potwierdzenie w konsoli — żeby było jasne, że program "zauważył"
        wpisaną wartość, zanim klikniesz KONFIGURUJ.
        """
        ip = self.ip_input.currentText().strip()
        if not ip:
            QMessageBox.warning(self, "Brak adresu IP", "Wpisz adres IP kserokopiarki w polu powyżej.")
            return

        if not validate_ip(ip):
            QMessageBox.critical(
                self, "Nieprawidłowy adres IP",
                f"'{ip}' nie wygląda na poprawny adres IPv4 (oczekiwany format: 192.168.1.100)."
            )
            return

        if self.ip_input.findText(ip) < 0:
            self.ip_input.addItem(ip)
        self.ip_input.setCurrentText(ip)
        self.console.append(f"✓ Ustawiono adres IP kserokopiarki: {ip}")

    def _set_ips(self, ips):
        """Wypełnia QComboBox wszystkimi znalezionymi adresami IP, żeby
        użytkownik mógł wybrać właściwe urządzenie, gdy w sieci jest
        więcej niż jedna kserokopiarka Ricoh."""
        self.ip_input.clear()
        self.ip_input.addItems(ips)
        if ips:
            self.ip_input.setCurrentIndex(0)

    def _populate_nic_selector(self):
        """Wypełnia rozwijaną listę wszystkimi lokalnymi adresami IP komputera
        (wszystkie karty sieciowe), z sugerowanym domyślnym adresem na górze."""
        current = self.nic_selector.currentText() if self.nic_selector.count() else None
        self.nic_selector.clear()
        ips = list_local_ips()
        self.nic_selector.addItems(ips)
        if current and current in ips:
            self.nic_selector.setCurrentText(current)
        elif ips:
            self.nic_selector.setCurrentIndex(0)

    def _on_diagnose_nics_clicked(self):
        self.console.append("")

        def worker():
            diagnose_network_interfaces(lambda msg: self.signals.log.emit(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_ports_clicked(self):
        target_ip = self.ip_input.currentText().strip()
        if not target_ip:
            QMessageBox.warning(self, "Brak adresu IP", "Najpierw podaj lub wykryj IP kserokopiarki.")
            return

        protocol = "smb" if self.radio_smb.isChecked() else "ftp"
        ports = [80, 443, 445 if protocol == "smb" else 21]

        self.btn_check_ports.setEnabled(False)
        self.console.append("")

        def worker():
            results = check_port_reachability(target_ip, ports, lambda msg: self.signals.log.emit(msg))

            web_ok = results.get(80) or results.get(443)
            proto_port = 445 if protocol == "smb" else 21
            if not web_ok:
                self.signals.log.emit(
                    "  ⚠ Ani port 80, ani 443 nie odpowiada — sprawdź adres IP i czy "
                    "urządzenie jest włączone."
                )
            if not results.get(proto_port):
                self.signals.log.emit(
                    f"  ⚠ Port {proto_port} ({protocol.upper()}) nie jest jeszcze "
                    f"otwarty na tym komputerze — to normalne PRZED kliknięciem "
                    f"KONFIGURUJ (reguła zapory jeszcze nie istnieje)."
                )
            self.signals.scan_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_scan_finished(self):
        """Wspólny handler zakończenia dowolnej krótkiej operacji w tle
        (skanowanie sieci / test portów / test udostępniania / rollback) —
        odblokowuje odpowiednie przyciski. Bezpieczne wywołanie na
        już-włączonym przycisku nie robi nic złego."""
        self.btn_scan.setEnabled(True)
        self.btn_check_ports.setEnabled(True)
        self.btn_test_share.setEnabled(True)
        self.btn_rollback.setEnabled(True)
        self.btn_full_diagnostics.setEnabled(True)
        self.btn_full_report.setEnabled(True)

    def _auto_detect_ip(self):
        self.btn_scan.setEnabled(False)
        self.console.clear()

        def worker():
            ips = scan_network_for_ricoh(lambda msg: self.signals.log.emit(msg))
            if ips:
                self.signals.log.emit(
                    f" Znaleziono {len(ips)} urządzeń Ricoh: {', '.join(ips)}"
                )
                self.signals.ips_found.emit(ips)
            else:
                self.signals.log.emit(" Brak automatycznie wykrytych urządzeń Ricoh. Podaj IP ręcznie.")
            self.signals.scan_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _start_process(self):
        if not is_admin():
            QMessageBox.warning(self, "Brak uprawnień", "Uruchom program jako Administrator!")
            return

        copier_ip = self.ip_input.currentText().strip()
        if not copier_ip:
            QMessageBox.critical(self, "Błąd", "Podaj adres IP kserokopiarki!")
            return
        if not validate_ip(copier_ip):
            QMessageBox.critical(
                self, "Nieprawidłowy adres IP",
                f"'{copier_ip}' nie wygląda na poprawny adres IPv4 (oczekiwany format: 192.168.1.100)."
            )
            return

        selected_nic_ip = self.nic_selector.currentText().strip() or get_local_ip()
        map_drive = self.chk_map_drive.isChecked()

        self.btn_run.setEnabled(False)
        self.console.clear()
        protocol = "smb" if self.radio_smb.isChecked() else "ftp"
        threading.Thread(
            target=self._worker,
            args=(copier_ip, protocol, selected_nic_ip, map_drive),
            daemon=True
        ).start()

    def _worker(self, copier_ip, protocol, local_ip, map_drive):
        try:
            success, report, summary = run_configuration(
                copier_ip, protocol, local_ip, map_drive,
                self.admin_user.text().strip(), self.admin_pass.text(),
                lambda msg: self.signals.log.emit(msg)
            )
            self._last_summary = summary
            self.signals.finished.emit(True, report)
        except Exception as e:
            self.signals.finished.emit(False, str(e))

    def _on_test_share_clicked(self):
        self.btn_test_share.setEnabled(False)
        protocol = "ftp" if self.radio_ftp.isChecked() else "smb"

        def worker():
            if protocol == "ftp":
                self.signals.log.emit("\n--- Test lokalnego dostępu przez FTP ---")
                test_local_ftp_access("127.0.0.1", 21, lambda msg: self.signals.log.emit(msg))
            else:
                self.signals.log.emit("\n--- Test lokalnego dostępu do udostępnionego folderu (SMB) ---")
                test_local_share_access(SHARE_NAME, lambda msg: self.signals.log.emit(msg))
            self.signals.scan_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_legacy_enable_clicked(self):
        if not is_admin():
            QMessageBox.warning(self, "Brak uprawnień", "Uruchom program jako Administrator!")
            return

        reply = QMessageBox.warning(
            self,
            "Obniżenie bezpieczeństwa systemu — potwierdź świadomie",
            "Zamierzasz włączyć NTLMv1 oraz logowanie gościa (Insecure Guest Auth) "
            "w Windows.\n\n"
            "SKUTKI:\n"
            "• NTLMv1 jest podatny na przechwycenie i złamanie hasła z ruchu "
            "sieciowego.\n"
            "• Insecure Guest Auth pozwala na dostęp do udziałów SMB bez żadnego "
            "uwierzytelnienia — mechanizm wykorzystywany historycznie przez robaki "
            "sieciowe (np. WannaCry) do rozprzestrzeniania się.\n\n"
            "Te zmiany dotyczą CAŁEGO komputera, nie tylko połączenia z drukarką.\n"
            "Użyj tylko jeśli bardzo stare urządzenie (sprzed ok. 2012) faktycznie "
            "tego wymaga, i rozważ przywrócenie bezpiecznych ustawień (przycisk "
            "obok) zaraz po zakończeniu pracy z tym urządzeniem.\n\n"
            "Czy na pewno chcesz kontynuować?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.console.append("Anulowano włączanie trybu zgodności dla starszych urządzeń.")
            return

        self.console.append("")
        threading.Thread(
            target=apply_legacy_auth_compatibility,
            args=(lambda msg: self.signals.log.emit(msg),),
            daemon=True
        ).start()

    def _on_sac_disable_clicked(self):
        if not is_admin():
            QMessageBox.warning(self, "Brak uprawnień", "Uruchom program jako Administrator!")
            return

        # Krok 3/4: odczyt obecnego stanu PRZED jakąkolwiek decyzją o zmianie
        # (HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState
        # — metoda udokumentowana na Microsoft Learn, patrz komentarz przy
        # get_smart_app_control_state).
        self.console.append("")
        state, label = get_smart_app_control_state(lambda msg: self.console.append(msg))

        # Krok 5: jeśli już 0 — poinformuj i nic nie zmieniaj.
        if state == 0:
            QMessageBox.information(
                self, "Smart App Control",
                "Smart App Control jest już wyłączony (stan: Off).\n\nNiczego nie zmieniono."
            )
            return

        state_txt = {
            None: f"nieznany ({label})",
        }.get(state, SAC_STATE_LABELS.get(state, f"nieznany ({label})"))

        # Krok 6/7: wyraźne ostrzeżenie + wymagane jawne potwierdzenie.
        # Zabezpieczenie przed przypadkowym kliknięciem (pkt 16): domyślny
        # przycisk to "Nie", a treść jednoznacznie nazywa operację.
        reply = QMessageBox.warning(
            self,
            "Smart App Control — obniżenie poziomu ochrony systemu",
            "Smart App Control (Inteligentna kontrola aplikacji) to funkcja "
            "zabezpieczeń Windows chroniąca CAŁY komputer przed niezweryfikowanym "
            "i złośliwym oprogramowaniem — nie tylko ten program.\n\n"
            f"Obecny stan: {state_txt}.\n\n"
            "Program ZAPISZE wartość 0 w rejestrze systemowym "
            "(HKLM\\SYSTEM\\CurrentControlSet\\Control\\CI\\Policy\\"
            "VerifiedAndReputablePolicyState) i uruchomi CiTool.exe --refresh, "
            "żeby zmiana zaczęła obowiązywać — zgodnie z oficjalną dokumentacją "
            "Microsoft. To TRWALE obniża ochronę systemu, dopóki nie włączysz "
            "funkcji ponownie.\n\n"
            "Czy na pewno chcesz WYŁĄCZYĆ Smart App Control na tym komputerze?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.console.append("Anulowano — Smart App Control pozostaje bez zmian.")
            return

        self.btn_sac_disable.setEnabled(False)
        self.console.append("")

        def worker():
            result = disable_smart_app_control(lambda msg: self.signals.log.emit(msg))
            self.signals.sac_result.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_sac_result(self, result):
        self.btn_sac_disable.setEnabled(is_admin())
        outcome = result.get("outcome")
        message = result.get("message", "")
        needs_restart = result.get("needs_restart", False)

        if outcome == "success":
            text = message
            if needs_restart:
                text += "\n\nZalecany jest ponowny restart komputera."
            else:
                text += "\n\nPonowne uruchomienie komputera NIE jest wymagane."
            QMessageBox.information(self, "Smart App Control — wyłączony", text)
        elif outcome == "already_off":
            QMessageBox.information(self, "Smart App Control", message)
        else:  # "error"
            text = message
            if needs_restart:
                text += "\n\nSpróbuj ponownie uruchomić komputer i powtórzyć operację."
            QMessageBox.critical(self, "Smart App Control — błąd", text)


    def _on_legacy_revert_clicked(self):
        if not is_admin():
            QMessageBox.warning(self, "Brak uprawnień", "Uruchom program jako Administrator!")
            return
        self.console.append("")
        threading.Thread(
            target=revert_legacy_auth_compatibility,
            args=(lambda msg: self.signals.log.emit(msg),),
            daemon=True
        ).start()

    def _on_full_diagnostics_clicked(self):
        """
        Uruchamia pełną diagnostykę na żywo (run_full_diagnostics) w osobnym
        wątku — przechodzi po kolei przez wszystkie najczęstsze przyczyny,
        dla których skany nie docierają do folderu, zamiast ręcznego
        zgadywania które z wielu ustawień Windows akurat blokuje transfer.
        """
        device_ip = self.ip_input.currentText().strip()
        if not device_ip or not validate_ip(device_ip):
            QMessageBox.warning(
                self, "Brak adresu IP",
                "Wpisz lub wykryj poprawny adres IP kserokopiarki przed uruchomieniem diagnostyki."
            )
            return

        selected_nic_ip = self.nic_selector.currentText().strip() or get_local_ip()
        protocol = "ftp" if self.radio_ftp.isChecked() else "smb"

        self.btn_full_diagnostics.setEnabled(False)
        self.console.append("")

        def worker():
            run_full_diagnostics(
                device_ip, selected_nic_ip, protocol,
                lambda msg: self.signals.log.emit(msg)
            )
            build_security_software_exclusion_instructions(
                device_ip, detect_security_software(), lambda msg: self.signals.log.emit(msg)
            )
            self.signals.scan_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_full_report_clicked(self):
        device_ip = self.ip_input.currentText().strip()
        if not device_ip or not validate_ip(device_ip):
            QMessageBox.warning(self, "Brak adresu IP", "Wpisz lub wykryj poprawny adres IP kserokopiarki.")
            return
        local_ip = self.nic_selector.currentText().strip() or get_local_ip()
        protocol = "ftp" if self.radio_ftp.isChecked() else "smb"
        client = RicohWebClient(device_ip, self.admin_user.text().strip(), self.admin_pass.text(),
                                lambda m: self.signals.log.emit(m))
        self.btn_full_report.setEnabled(False)
        self.console.append(f"📋 Zbieram pełny raport — poczekaj (do ok. 1–2 min). Zapis: {DETAILED_LOG_PATH}")

        def worker():
            collect_full_report(device_ip, local_ip, protocol,
                                lambda m: self.signals.log.emit(m), web_client=client)
            self.signals.scan_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_toggle_live_monitor(self):
        """
        Przełącza monitorowanie na żywo (start/stop). Działa przez QTimer
        (nie osobny wątek) — co 2 sekundy sprawdza nowe linie w logu IIS
        FTP, nowe połączenia TCP od drukarki i wypisuje czytelne komunikaty
        w konsoli, żeby było widać dokładnie, na którym etapie transfer
        skanu się zatrzymuje (jeśli w ogóle do czegoś dochodzi).
        """
        if self._live_monitor_timer is not None:
            self._stop_live_monitor()
            return

        device_ip = self.ip_input.currentText().strip()
        if not device_ip or not validate_ip(device_ip):
            QMessageBox.warning(
                self, "Brak adresu IP",
                "Wpisz lub wykryj poprawny adres IP kserokopiarki przed uruchomieniem monitorowania."
            )
            return

        protocol = "ftp" if self.radio_ftp.isChecked() else "smb"

        self.console.append("")
        self.console.append("═" * 60)
        self.console.append("📡 MONITOROWANIE NA ŻYWO ROZPOCZĘTE")
        self.console.append(f"   Obserwuję ruch od {device_ip} — teraz naciśnij [Skanuj] na panelu drukarki.")
        self.console.append("═" * 60)

        ftp_log_path = find_ftp_log_file(lambda msg: self.console.append(msg)) if protocol == "ftp" else None

        self._live_monitor_state = {
            "device_ip": device_ip,
            "protocol": protocol,
            "ftp_log_path": ftp_log_path,
            "ftp_log_position": os.path.getsize(ftp_log_path) if ftp_log_path and os.path.exists(ftp_log_path) else 0,
            "known_connections": set(),
            "known_files": set(os.listdir(TARGET_FOLDER)) if os.path.isdir(TARGET_FOLDER) else set(),
            "last_activity": "(jeszcze brak aktywności)",
        }

        self._live_monitor_timer = QTimer(self)
        self._live_monitor_timer.timeout.connect(self._live_monitor_tick)
        self._live_monitor_timer.start(1000)  # co 1 sekundę

        self.btn_live_monitor.setText("⏹ ZATRZYMAJ MONITOROWANIE")
        self.btn_live_monitor.setStyleSheet(
            "background-color: #dc3545; color: white; border-radius: 4px; font-weight: bold;"
        )

    def _stop_live_monitor(self):
        st = self._live_monitor_state or {}
        if st.get("device_ip"):
            sess = get_smb_sessions_from_ip(st["device_ip"])
            self.console.append("  Sesje SMB od drukarki: " + ("; ".join(sess) if sess else "brak (drukarka nie logowała się do udziału SMB)"))
        if st.get("ftp_log_path"):
            dump_ftp_log_tail(st["ftp_log_path"], st["device_ip"], lambda m: self.console.append(m))
        if self._live_monitor_timer is not None:
            self._live_monitor_timer.stop()
            self._live_monitor_timer = None
        self.console.append("📡 Monitorowanie zatrzymane.")
        self.btn_live_monitor.setText("📡 ROZPOCZNIJ MONITOROWANIE SKANOWANIA NA ŻYWO")
        self.btn_live_monitor.setStyleSheet(
            "background-color: #198754; color: white; border-radius: 4px; font-weight: bold;"
        )

    def _live_monitor_tick(self):
        """Wywoływane cyklicznie (co 2s) przez QTimer — sprawdza wszystkie
        źródła sygnału naraz i wypisuje TYLKO nowe, niewidziane wcześniej
        zdarzenia (żeby konsola nie zapętlała się powtarzaniem tego samego)."""
        state = self._live_monitor_state
        device_ip = state["device_ip"]

        # 1. Nowe linie w logu IIS FTP (jeśli protokół to FTP i log istnieje).
        if state.get("ftp_log_path"):
            new_lines, new_pos = tail_new_lines(state["ftp_log_path"], state["ftp_log_position"])
            state["ftp_log_position"] = new_pos
            for line in new_lines:
                interpreted = interpret_ftp_log_line(line, device_ip)
                if interpreted:
                    self.console.append(f"  {interpreted}")
                    state["last_activity"] = interpreted

        # 2. Nowe/zmienione połączenia TCP od adresu drukarki.
        connections = get_active_connections_from_ip(device_ip)
        new_connections = set(connections) - state["known_connections"]
        for conn in new_connections:
            self.console.append(f"  🔌 Nowe połączenie sieciowe: {conn}")
            state["last_activity"] = f"połączenie: {conn}"
        state["known_connections"] = set(connections)

        # 2b. Sesje SMB od drukarki (logowanie do udziału).
        for sess in get_smb_sessions_from_ip(device_ip):
            if sess not in state.setdefault("known_smb", set()):
                state["known_smb"].add(sess)
                self.console.append(f"  🗂 Drukarka zalogowała się do udziału SMB: {sess}")
                state["last_activity"] = f"SMB: {sess}"

        # 3. Nowe pliki w folderze docelowym — ostateczny dowód sukcesu.
        if os.path.isdir(TARGET_FOLDER):
            current_files = set(os.listdir(TARGET_FOLDER))
            new_files = current_files - state["known_files"]
            for f in new_files:
                try:
                    size_kb = os.path.getsize(os.path.join(TARGET_FOLDER, f)) / 1024
                except OSError:
                    size_kb = 0
                self.console.append(f"  📄✔ NOWY PLIK W FOLDERZE: {f} ({size_kb:.0f} KB) — TRANSFER ZAKOŃCZONY SUKCESEM!")
                state["last_activity"] = f"plik zapisany: {f}"
                QApplication.alert(self)
            state["known_files"] = current_files

    def _on_rollback_clicked(self):
        if not is_admin():
            QMessageBox.warning(self, "Brak uprawnień", "Uruchom program jako Administrator!")
            return

        reply = QMessageBox.question(
            self,
            "Cofnąć konfigurację?",
            f"Zostaną usunięte: konto '{TARGET_USER}', udział SMB, witryna FTP, "
            "reguły zapory i wykluczenie Defendera.\n\n"
            f"Folder {TARGET_FOLDER} NIE zostanie usunięty — pliki skanów "
            "pozostaną nietknięte.\n\nKontynuować?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.btn_rollback.setEnabled(False)
        self.console.append("")

        def worker():
            rollback_configuration(lambda msg: self.signals.log.emit(msg))
            self.signals.scan_finished.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _on_finished(self, success, msg):
        self.btn_run.setEnabled(True)
        self.console.append(msg)
        if success:
            QApplication.clipboard().setText(msg)
            self._show_post_setup_summary()
        else:
            QMessageBox.critical(self, "Błąd", f"Błąd podczas konfiguracji: {msg}")

    def _show_post_setup_summary(self):
        """
        Osobne, czytelne okienko podsumowujące na koniec konfiguracji —
        pokazuje dwie najważniejsze rzeczy do zapamiętania:
        1) gdzie fizycznie znajduje się udostępniony folder ze skanami,
        2) jaki adres IP warto ustawić na STAŁE w komputerze — bez tego,
           jeśli komputer ma adres z DHCP, router może przy następnym
           uruchomieniu przydzielić inny adres, a wpis w książce adresowej
           drukarki (wskazujący na obecny adres) przestanie działać.
        """
        info = self._last_summary
        if not info:
            return

        folder_line = f"📁 Folder udostępniony znajduje się w:\n   {info['folder_path']}\n"
        path_line = f"\n🔗 Ścieżka widoczna z sieci:\n   {info['destination']}\n"
        ip_line = (
            f"\n🌐 Ustaw stałe (statyczne) IP w komputerze na:\n   {info['local_ip']}\n\n"
            f"To WAŻNE: jeśli komputer ma adres przydzielany automatycznie (DHCP),\n"
            f"router może przy kolejnym uruchomieniu przydzielić INNY adres —\n"
            f"wtedy wpis w książce adresowej drukarki przestanie działać, bo\n"
            f"będzie wskazywał na nieaktualny adres IP.\n\n"
            f"Jak ustawić stały adres: Panel sterowania → Centrum sieci →\n"
            f"Zmień ustawienia karty sieciowej → kliknij prawym na kartę →\n"
            f"Właściwości → 'Protokół internetowy w wersji 4 (TCP/IPv4)' →\n"
            f"Właściwości → 'Użyj następującego adresu IP' → wpisz {info['local_ip']}\n"
            f"(oraz maskę/bramę zgodną z resztą sieci — sprawdź je poleceniem\n"
            f"'ipconfig' przed zmianą, żeby nie zerwać połączenia z siecią)."
        )

        QMessageBox.information(
            self, "Konfiguracja zakończona — zapamiętaj to",
            folder_line + path_line + ip_line +
            "\n\n(Pełny raport z hasłem konta skopiowany do schowka — "
            "wyczyść go po wklejeniu, jeśli komputer jest współdzielony.)"
        )

    def closeEvent(self, event):
        """Zapisuje ustawienia przy zamykaniu okna, żeby nie trzeba było
        wpisywać IP/loginu od nowa przy następnym uruchomieniu.

        UWAGA: wbudowany serwer FTP (usługa Windows IIS) CELOWO nie jest
        tu zatrzymywany — to trwała usługa systemowa, niezależna od tego
        programu. Ma dalej działać (i przyjmować pliki od drukarki) także
        po zamknięciu tego okna."""
        if self._live_monitor_timer is not None:
            self._live_monitor_timer.stop()
        protocol = "ftp" if self.radio_ftp.isChecked() else "smb"
        save_settings(
            ip=self.ip_input.currentText().strip(),
            admin_user=self.admin_user.text().strip(),
            protocol=protocol,
            selected_nic=self.nic_selector.currentText().strip(),
        )
        event.accept()


def ask_access_code(max_attempts=3):
    """Okno z prośbą o kod dostępu (wpisywany jako hasło — kropki). Zwraca True
    tylko po podaniu poprawnego kodu; anulowanie lub 3 błędne próby kończą program."""
    for attempt in range(1, max_attempts + 1):
        code, ok = QInputDialog.getText(
            None, COPYRIGHT_TITLE, "Podaj kod dostępu do uruchomienia programu:",
            QLineEdit.Password
        )
        if not ok:
            return False
        if verify_access_code(code):
            return True
        dlog(f"Nieudana próba kodu dostępu ({attempt}/{max_attempts})")
        QMessageBox.warning(None, COPYRIGHT_TITLE,
                            f"Nieprawidłowy kod. Pozostało prób: {max_attempts - attempt}.")
    return False


# ═════════════ TRYB TEKSTOWY (CMD) ═════════════
def _cli_attach_console():
    """Przygotowuje wyjście tekstowe. W EXE zbudowanym jako konsolowe (zalecane,
    jeden plik) CMD sam czeka na zakończenie programu, a wyjście i wejście działają
    od razu — ustawiamy tylko UTF-8. W EXE okienkowym (--noconsole) dołączamy się
    do konsoli procesu nadrzędnego (wtedy CMD nie czeka na koniec pracy)."""
    if os.name != "nt":
        return True
    try:
        k = ctypes.windll.kernel32
        if sys.stdout is not None and sys.stdin is not None:
            k.SetConsoleOutputCP(65001)
            for stream in (sys.stdout, sys.stderr):
                try:
                    stream.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            return True
        if not k.AttachConsole(-1):          # -1 = konsola procesu nadrzędnego (cmd)
            if not k.AllocConsole():
                return False
        k.SetConsoleOutputCP(65001)
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
        return True
    except Exception:
        return False


def _hide_own_console():
    """Tryb graficzny w EXE konsolowym: jeśli konsolę utworzyło dwukrotne kliknięcie
    (nikt poza tym programem nie jest do niej podłączony), ukrywamy ją i odłączamy.
    Uruchomienie z istniejącego CMD (jest tam jeszcze cmd.exe) zostawia okno w spokoju."""
    if os.name != "nt":
        return
    try:
        k = ctypes.windll.kernel32
        buf = (ctypes.c_uint * 8)()
        n = k.GetConsoleProcessList(buf, 8)
        # onefile = proces startowy + proces Pythona => 2; z CMD dochodzi cmd.exe => 3+
        if 0 < n <= 2:
            hwnd = k.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
            k.FreeConsole()
    except Exception:
        pass


def _cli_out(msg):
    print(msg)
    dlog(msg)


def _cli_ask(prompt, default=None, secret=False):
    suffix = f" [{default}]" if default not in (None, "") else ""
    try:
        if secret:
            import getpass
            val = getpass.getpass(f"{prompt}{suffix}: ")
        else:
            val = input(f"{prompt}{suffix}: ")
    except EOFError:
        val = ""
    val = val.strip()
    return val if val else (default or "")


CLI_EPILOG = """
Przykłady (uruchamiaj w CMD jako Administrator):
  RicohScannerConfig.exe configure --protocol smb --printer-ip 192.168.1.237 --code KOD
  RicohScannerConfig.exe configure --protocol ftp --printer-ip 192.168.1.237 --local-ip 192.168.1.200 --code KOD
  RicohScannerConfig.exe detect --code KOD
  RicohScannerConfig.exe list --printer-ip 192.168.1.237 --code KOD
  RicohScannerConfig.exe test --protocol ftp --code KOD
  RicohScannerConfig.exe diagnose --protocol smb --printer-ip 192.168.1.237 --code KOD
  RicohScannerConfig.exe rollback --yes --code KOD
  RicohScannerConfig.exe wizard          (pytania krok po kroku)
Kod dostępu można podać też w zmiennej środowiskowej RICOH_SCAN_CODE.
Kody wyjścia: 0 = OK, 1 = błąd operacji, 2 = brak uprawnień administratora, 3 = zły kod, 4 = błędne argumenty.
"""


def build_cli_parser():
    import argparse
    p = argparse.ArgumentParser(
        prog="RicohScannerConfig.exe",
        description=f"{COPYRIGHT_TITLE} — konfiguracja skanowania Ricoh (SMB / FTP) w trybie tekstowym.",
        epilog=CLI_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    code_parent = argparse.ArgumentParser(add_help=False)
    # SUPPRESS: wartość podana przed lub po nazwie polecenia nie jest nadpisywana domyślną
    code_parent.add_argument("--code", default=argparse.SUPPRESS,
                             help="kod dostępu (albo zmienna RICOH_SCAN_CODE)")
    p.add_argument("--code", default=argparse.SUPPRESS, help="kod dostępu (albo zmienna RICOH_SCAN_CODE)")
    sub = p.add_subparsers(dest="command")
    _orig_add = sub.add_parser
    sub.add_parser = lambda name, **kw: _orig_add(name, parents=[code_parent], **kw)

    def common(sp, need_proto=True, need_ip=True):
        if need_proto:
            sp.add_argument("--protocol", choices=["smb", "ftp"], required=True, help="smb albo ftp")
        if need_ip:
            sp.add_argument("--printer-ip", required=True, help="adres IP kserokopiarki")
        sp.add_argument("--local-ip", help="adres IP tego komputera (domyślnie wykrywany automatycznie)")
        sp.add_argument("--admin-user", default="admin", help="login administratora drukarki (domyślnie admin)")
        sp.add_argument("--admin-pass", default="", help="hasło administratora drukarki (domyślnie puste)")

    c = sub.add_parser("configure", help="pełna konfiguracja (komputer + wpis w drukarce)")
    common(c)
    c.add_argument("--map-drive", action="store_true", help="zmapuj folder jako dysk S: (tylko SMB)")
    c.add_argument("--skip-report", action="store_true", help="pomiń pełny raport diagnostyczny na końcu")
    sub.add_parser("detect", help="wyszukaj kserokopiarki Ricoh w sieci")
    d = sub.add_parser("diagnose", help="pełny raport diagnostyczny"); common(d)
    t = sub.add_parser("test", help="test zapisu do folderu (FTP albo SMB)"); common(t, need_ip=False)
    l = sub.add_parser("list", help="wypisz wpisy w książce adresowej drukarki"); common(l, need_proto=False)
    r = sub.add_parser("rollback", help="cofnij konfigurację na komputerze")
    r.add_argument("--yes", action="store_true", help="bez pytania o potwierdzenie")
    sub.add_parser("wizard", help="konfiguracja krok po kroku (pytania w CMD)")
    return p


def _cli_resolve_local_ip(args):
    return getattr(args, "local_ip", None) or get_local_ip()


def cli_main(argv):
    """Punkt wejścia trybu tekstowego. Zwraca kod wyjścia procesu."""
    has_console = _cli_attach_console()
    parser = build_cli_parser()
    if not argv or argv == ["--cli"]:
        argv = ["wizard"]
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 4
    if not args.command:
        parser.print_help()
        return 4

    dlog("=" * 70)
    dlog(f"START (CMD)  WERSJA={APP_VERSION}  polecenie={args.command}")
    print(f"\n{COPYRIGHT_TITLE}  —  tryb tekstowy  [{APP_VERSION}]\n")

    # --- kod dostępu ---
    code = getattr(args, "code", None) or os.environ.get("RICOH_SCAN_CODE")
    if not code:
        if not sys.stdin or not sys.stdin.isatty():
            print("Brak kodu dostępu. Użyj --code KOD albo zmiennej RICOH_SCAN_CODE.")
            return 3
        code = _cli_ask("Podaj kod dostępu", secret=True)
    if not verify_access_code(code):
        dlog("Nieudana próba kodu dostępu (CMD)")
        print("Nieprawidłowy kod dostępu.")
        return 3

    cmd = args.command
    if cmd == "detect":
        ips = scan_network_for_ricoh(_cli_out)
        print("\nZnalezione urządzenia Ricoh:" if ips else "\nNie znaleziono urządzeń Ricoh.")
        for ip in ips:
            print(f"  {ip}")
        return 0 if ips else 1

    if cmd == "test":
        ok = (test_local_ftp_access("127.0.0.1", 21, _cli_out) if args.protocol == "ftp"
              else test_local_share_access(SHARE_NAME, _cli_out))
        return 0 if ok else 1

    if cmd == "list":
        RicohWebClient(args.printer_ip, args.admin_user, args.admin_pass, _cli_out).dump_address_book(_cli_out)
        return 0

    # polecenia zmieniające system wymagają administratora
    if not is_admin():
        print("Ta operacja wymaga uprawnień administratora — uruchom CMD jako Administrator.")
        return 2

    if cmd == "rollback":
        if not args.yes and _cli_ask(f"Usunąć konto '{TARGET_USER}', udział, witrynę FTP i reguły zapory? (t/n)", "n").lower() not in ("t", "y", "tak"):
            print("Anulowano.")
            return 0
        rollback_configuration(_cli_out)
        return 0

    if cmd == "diagnose":
        collect_full_report(args.printer_ip, _cli_resolve_local_ip(args), args.protocol, _cli_out,
                            web_client=RicohWebClient(args.printer_ip, args.admin_user, args.admin_pass, _cli_out))
        return 0

    if cmd == "wizard":
        protocol = ""
        while protocol not in ("smb", "ftp"):
            protocol = _cli_ask("Protokół skanowania (smb / ftp)", "smb").lower()
        printer_ip = _cli_ask("Adres IP kserokopiarki (Enter = wyszukaj w sieci)")
        if not printer_ip:
            found = scan_network_for_ricoh(_cli_out)
            if not found:
                print("Nie znaleziono kserokopiarki — podaj adres IP ręcznie.")
                return 1
            for n, ip in enumerate(found, 1):
                print(f"  {n}. {ip}")
            pick = _cli_ask("Numer urządzenia", "1")
            printer_ip = found[max(0, min(len(found) - 1, int(pick) - 1 if pick.isdigit() else 0))]
        if not validate_ip(printer_ip):
            print(f"Nieprawidłowy adres IP: {printer_ip}")
            return 4
        ips = list_local_ips()
        local_ip = _cli_ask("Adres IP tego komputera (karta sieciowa)", ips[0] if ips else get_local_ip())
        admin_user = _cli_ask("Login administratora drukarki", "admin")
        admin_pass = _cli_ask("Hasło administratora drukarki (Enter = puste)", "", secret=True)
        map_drive = protocol == "smb" and _cli_ask("Zmapować folder jako dysk S:? (t/n)", "n").lower() in ("t", "y", "tak")
        include_report = True
    else:  # configure
        protocol, printer_ip = args.protocol, args.printer_ip
        local_ip = _cli_resolve_local_ip(args)
        admin_user, admin_pass = args.admin_user, args.admin_pass
        map_drive, include_report = args.map_drive, not args.skip_report
        if not validate_ip(printer_ip):
            print(f"Nieprawidłowy adres IP: {printer_ip}")
            return 4

    print(f"\nKonfiguruję: protokół={protocol.upper()}  drukarka={printer_ip}  komputer={local_ip}\n")
    success, report, _ = run_configuration(printer_ip, protocol, local_ip, map_drive,
                                           admin_user, admin_pass, _cli_out, include_report)
    _cli_out(report)
    print("\nZmień adres IP tego komputera na STAŁY (" + local_ip + "), aby wpis w drukarce nie przestał działać.")
    return 0 if success else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(cli_main(sys.argv[1:]))   # tryb tekstowy (CMD)
    _hide_own_console()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if not ask_access_code():
        sys.exit(0)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
