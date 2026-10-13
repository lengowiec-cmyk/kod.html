"""
Narzędzia systemowe współdzielone przez pozostałe moduły:
- uruchamianie komend Windows (odporne na zawieszenie),
- wykrywanie lokalnego IP i podsieci,
- sprawdzanie uprawnień administratora,
- skanowanie sieci LAN w poszukiwaniu urządzeń Ricoh,
- test dostępności portów TCP.
"""

import ctypes
import re
import socket
import subprocess
import sys
import concurrent.futures
from dataclasses import dataclass

import requests


# ─────────────────────────────────────────────────────────────
#  Uprawnienia administratora
# ─────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(script_path: str = None) -> bool:
    """
    Uruchamia ponownie bieżący proces z podniesionymi uprawnieniami (UAC).
    Zwraca True jeśli udało się zainicjować podniesienie (proces bieżący
    powinien się wtedy zakończyć), False w razie błędu.
    """
    try:
        if getattr(sys, "frozen", False):
            # Uruchomione jako skompilowany EXE (PyInstaller)
            executable = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            executable = sys.executable
            script = script_path or sys.argv[0]
            params = f'"{script}" ' + " ".join(f'"{a}"' for a in sys.argv[1:])

        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, None, 1
        )
        return ret > 32
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
#  Wykonywanie komend systemowych
# ─────────────────────────────────────────────────────────────

def run_cmd(cmd: str, timeout: int = 120) -> str:
    """
    Wykonuje polecenie w cmd.exe.
    - `input="\\n"` zapobiega zawieszeniu, jeśli komenda o coś zapyta
      (np. net share proszący o potwierdzenie).
    - `timeout` zabezpiecza przed trwałym zawieszeniem procesu.
    """
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, encoding="cp852", errors="replace",
            input="\n", timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        return output if output else f"[OK] Wykonano: {cmd[:70]}"
    except subprocess.TimeoutExpired:
        return f"[UWAGA] Przekroczono czas ({timeout}s): {cmd[:70]} — kontynuuję"
    except Exception as e:
        return f"[BŁĄD] {cmd[:70]}: {e}"


def run_powershell(script: str, timeout: int = 180) -> str:
    """Wykonuje skrypt PowerShell z pominięciem polityki wykonywania."""
    cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -Command "{script}"'
    return run_cmd(cmd, timeout=timeout)


# ─────────────────────────────────────────────────────────────
#  Sieć — lokalny adres IP i podsieć
# ─────────────────────────────────────────────────────────────

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_subnet_prefix(ip: str) -> str:
    """Zwraca prefiks /24, np. '192.168.1' dla '192.168.1.50'."""
    parts = ip.split(".")
    if len(parts) != 4:
        return ""
    return ".".join(parts[:3])


def validate_ip(ip: str) -> bool:
    pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if not re.match(pattern, ip):
        return False
    return all(0 <= int(part) <= 255 for part in ip.split("."))


def check_tcp_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def ping_host(ip: str, timeout_ms: int = 1500) -> bool:
    """Ping jednorazowy (Windows: ping -n 1). Zwraca True jeśli host odpowiedział."""
    out = run_cmd(f'ping -n 1 -w {timeout_ms} {ip}', timeout=int(timeout_ms / 1000) + 5)
    low = out.lower()
    if "ttl=" in low or "czas=" in low or "time=" in low:
        return True
    return False


# ─────────────────────────────────────────────────────────────
#  Skanowanie sieci — wykrywanie urządzeń Ricoh
# ─────────────────────────────────────────────────────────────

RICOH_SIGNATURES = ("ricoh", "web image monitor", "aficio", "savin", "lanier")


@dataclass
class DiscoveredDevice:
    ip: str
    title: str = ""


def scan_lan_for_ricoh(logger=None, timeout: float = 0.4,
                        max_workers: int = 80) -> list[DiscoveredDevice]:
    """
    Skanuje lokalną podsieć /24 i zwraca listę wykrytych urządzeń Ricoh
    (identyfikowanych po odpowiedzi HTTP na porcie 80 zawierającej sygnatury
    Web Image Monitor). W pełni automatyczne — bez interakcji użytkownika.
    """
    local_ip = get_local_ip()
    prefix = get_subnet_prefix(local_ip)
    if not prefix:
        if logger:
            logger.error("Nie można ustalić lokalnej podsieci do skanowania")
        return []

    if logger:
        logger.info(f"Skanowanie podsieci {prefix}.0/24 w poszukiwaniu urządzeń Ricoh...")

    found: list[DiscoveredDevice] = []

    def probe(host_num: int):
        ip = f"{prefix}.{host_num}"
        if not check_tcp_port(ip, 80, timeout=timeout):
            return
        try:
            r = requests.get(f"http://{ip}/", timeout=timeout + 0.6)
            content = r.text.lower()
            if any(sig in content for sig in RICOH_SIGNATURES):
                title_match = re.search(r"<title>(.*?)</title>", r.text, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else ""
                found.append(DiscoveredDevice(ip=ip, title=title))
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(probe, range(1, 255)))

    if logger:
        if found:
            for dev in found:
                logger.info(f"  ✔ Znaleziono: {dev.ip}  ({dev.title or 'Ricoh'})")
        else:
            logger.warning("  Nie znaleziono żadnego urządzenia Ricoh w sieci lokalnej")

    return found
