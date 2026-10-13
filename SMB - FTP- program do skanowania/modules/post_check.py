"""
Testy weryfikacyjne wykonywane automatycznie PO zakończeniu głównej
konfiguracji. Sprawdzają realny stan systemu (nie tylko czy komendy się
wykonały bez błędu), żeby użytkownik dostał jasny obraz "co faktycznie
działa", a co wymaga jego ręcznej uwagi.

Każdy test zwraca obiekt CheckResult z jednoznacznym statusem:
- PASS  (✔, zielony)  — zweryfikowano, działa
- FAIL  (✖, czerwony) — zweryfikowano, nie działa / brak odpowiedzi
- MANUAL (✖, żółty/czerwony w GUI) — nie da się zweryfikować automatycznie,
          wymaga ręcznego potwierdzenia (np. faktyczne zeskanowanie strony
          na urządzeniu)
"""

import os
from dataclasses import dataclass
from enum import Enum

from .system_utils import check_tcp_port, ping_host


class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    MANUAL = "manual"


@dataclass
class CheckResult:
    label: str
    status: CheckStatus
    detail: str = ""

    @property
    def icon(self) -> str:
        return "✔" if self.status == CheckStatus.PASS else "✖"

    def as_line(self) -> str:
        return f"{self.icon} {self.label}" + (f" — {self.detail}" if self.detail else "")


def check_folder_exists(folder: str) -> CheckResult:
    ok = os.path.isdir(folder)
    return CheckResult(
        label="Folder dostępny",
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        detail=folder if ok else f"nie znaleziono: {folder}",
    )


def check_folder_writable(folder: str) -> CheckResult:
    """Realny test zapisu — tworzy i usuwa tymczasowy plik w folderze."""
    test_file = os.path.join(folder, ".write_test_ricoh.tmp")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return CheckResult(label="Prawa zapisu do folderu", status=CheckStatus.PASS)
    except Exception as e:
        return CheckResult(
            label="Prawa zapisu do folderu",
            status=CheckStatus.FAIL,
            detail=str(e),
        )


def check_smb_service(local_ip: str) -> CheckResult:
    ok = check_tcp_port(local_ip, 445, timeout=3)
    return CheckResult(
        label="SMB działa",
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        detail="port 445 odpowiada" if ok else "port 445 nie odpowiada",
    )


def check_ftp_service(local_ip: str) -> CheckResult:
    ok = check_tcp_port(local_ip, 21, timeout=3)
    return CheckResult(
        label="FTP działa",
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        detail="port 21 odpowiada" if ok else "port 21 nie odpowiada",
    )


def check_firewall_rule_exists(rule_name_fragment: str) -> CheckResult:
    """Sprawdza, czy reguła zapory o podanej nazwie (fragmencie) istnieje."""
    from .system_utils import run_cmd
    out = run_cmd(
        f'netsh advfirewall firewall show rule name=all | findstr /I "{rule_name_fragment}"',
        timeout=20
    )
    ok = bool(out.strip()) and "[BŁĄD]" not in out and "[UWAGA]" not in out
    return CheckResult(
        label="Firewall OK",
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        detail="reguły zapory znalezione" if ok else "brak oczekiwanych reguł zapory",
    )


def check_device_ping(device_ip: str) -> CheckResult:
    ok = ping_host(device_ip)
    return CheckResult(
        label="Ricoh odpowiada (ping)",
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        detail=device_ip if ok else f"brak odpowiedzi z {device_ip}",
    )


def check_address_book_entry(ricoh_session, entry_added: bool) -> CheckResult:
    """
    Weryfikuje wpis w książce adresowej. Jeśli wpis nie został w ogóle
    dodany (np. brak hasła admina LUB próba POST się nie powiodła), zwraca
    MANUAL/FAIL odpowiednio — bo to co innego niż potwierdzony sukces.

    Uwaga: `entry_added` już odzwierciedla wynik faktycznej próby dodania
    wpisu (odpowiedź POST z addressBook.cgi) — jest to główne źródło prawdy.
    Dodatkowy test `verify_address_book_reachable` służy tylko do wykrycia
    sytuacji, w której urządzenie przestało odpowiadać PO operacji (np.
    zawiesiło się) — nie zastępuje wyniku samego dodania wpisu.
    """
    if ricoh_session is None:
        return CheckResult(
            label="Wpis w książce adresowej",
            status=CheckStatus.MANUAL,
            detail="nie skonfigurowano automatycznie (brak loginu administratora) — dodaj ręcznie",
        )

    if not entry_added:
        return CheckResult(
            label="Wpis w książce adresowej",
            status=CheckStatus.FAIL,
            detail="próba dodania wpisu nie powiodła się — sprawdź login/hasło administratora "
                   "lub dodaj wpis ręcznie",
        )

    reachable = ricoh_session.verify_address_book_reachable()
    return CheckResult(
        label="Wpis w książce dodany",
        status=CheckStatus.PASS if reachable else CheckStatus.FAIL,
        detail="" if reachable else "wpis prawdopodobnie dodany, ale urządzenie przestało odpowiadać po operacji",
    )


def check_scan_test_manual() -> CheckResult:
    """
    Faktyczne zeskanowanie testowej strony na urządzeniu i sprawdzenie, czy
    plik pojawił się w folderze, nie da się w pełni zautomatyzować bez
    fizycznej interakcji z panelem drukarki. Zawsze zwracane jako MANUAL —
    to jawna informacja dla użytkownika, a nie błąd konfiguracji.
    """
    return CheckResult(
        label="Test skanowania",
        status=CheckStatus.MANUAL,
        detail="wymaga ręcznego potwierdzenia — zeskanuj testową stronę z panelu urządzenia",
    )


def run_post_configuration_checks(protocol: str, folder: str, local_ip: str,
                                   device_ip: str, ricoh_session=None,
                                   address_book_added: bool = False,
                                   logger=None) -> list[CheckResult]:
    """
    Uruchamia pełny zestaw testów po zakończeniu konfiguracji i zwraca
    listę wyników w kolejności do wyświetlenia. Nie przerywa się na
    pierwszym niepowodzeniu — zbiera wszystkie wyniki naraz.
    """
    if logger:
        logger.section("Weryfikacja końcowa (testy po konfiguracji)")

    results: list[CheckResult] = []

    results.append(check_folder_exists(folder))
    results.append(check_folder_writable(folder))

    if protocol == "smb":
        results.append(check_smb_service(local_ip))
        results.append(check_firewall_rule_exists("Ricoh Scanner SMB"))
    else:
        results.append(check_ftp_service(local_ip))
        results.append(check_firewall_rule_exists("Ricoh Scanner FTP"))

    results.append(check_device_ping(device_ip))
    results.append(check_address_book_entry(ricoh_session, address_book_added))
    results.append(check_scan_test_manual())

    if logger:
        for r in results:
            if r.status == CheckStatus.PASS:
                logger.info(r.as_line())
            elif r.status == CheckStatus.FAIL:
                logger.error(r.as_line())
            else:
                logger.warning(r.as_line())

    return results
