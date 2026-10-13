"""
Konfiguracja systemu Windows potrzebna do skanowania sieciowego:
- tworzenie konta użytkownika lokalnego,
- tworzenie folderu docelowego skanów,
- nadawanie uprawnień NTFS,
- udostępnianie folderu przez SMB,
- reguły Zapory Windows (SMB, ogólne zaufanie dla IP drukarki).

Wszystkie funkcje są idempotentne — bezpieczne do wielokrotnego uruchamiania
(np. przy ponownej konfiguracji) i nie proszą o żadne potwierdzenia.
"""

import os

from .system_utils import run_cmd


DEFAULT_SCAN_FOLDER = r"C:\SkanyRicoh"
DEFAULT_SHARE_NAME = "SkanyRicoh"


def create_local_user(username: str, password: str, logger) -> bool:
    """Tworzy (lub resetuje hasło) lokalnego użytkownika Windows dla skanera."""
    logger.section("Tworzenie konta użytkownika")

    # Uwaga: "net user ... /add" NIE przyjmuje flagi /y (nie istnieje dla
    # tego polecenia) — samo /add już działa bez potwierdzenia interaktywnego.
    out = run_cmd(f'net user {username} "{password}" /add')
    logger.info(out)

    # Rozpoznanie "konto już istnieje" po specyficznych komunikatach Windows
    # (kod błędu 2224 lub jednoznaczne frazy) — NIE po ogólnym słowie "błąd",
    # bo to maskowałoby inne, prawdziwe niepowodzenia (np. brak uprawnień).
    already_exists = any(x in out for x in [
        "2224",                       # kod błędu Windows dla "konto już istnieje"
        "już istnieje",
        "already exists",
    ])

    if already_exists:
        logger.info("Konto już istnieje — aktualizuję hasło")
        out2 = run_cmd(f'net user {username} "{password}"')
        logger.info(out2)
    elif "[BŁĄD]" in out or ("error" in out.lower() and "2224" not in out):
        logger.error(
            f"Nie udało się utworzyć konta '{username}' — sprawdź uprawnienia "
            f"administratora i komunikat powyżej."
        )
        return False

    # Hasło niewygasające — żeby drukarka nie utraciła dostępu po X dniach
    run_cmd(f'wmic useraccount where name="{username}" set PasswordExpires=false')
    logger.info(f"Konto '{username}' skonfigurowane (hasło nie wygasa)")
    return True


def create_scan_folder(folder: str, logger) -> bool:
    """Tworzy folder docelowy skanów, jeśli jeszcze nie istnieje."""
    logger.section("Tworzenie folderu skanów")
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
        logger.info(f"Folder utworzony: {folder}")
    else:
        logger.info(f"Folder już istnieje: {folder}")
    return True


def grant_ntfs_permissions(folder: str, username: str, logger,
                            extra_groups: list[str] = None) -> bool:
    """Nadaje pełne uprawnienia NTFS użytkownikowi skanera oraz opcjonalnym grupom
    (np. IIS_IUSRS dla FTP)."""
    logger.section("Uprawnienia NTFS")
    logger.info(run_cmd(f'icacls "{folder}" /grant {username}:(OI)(CI)F'))
    logger.info(run_cmd(f'icacls "{folder}" /grant "Users":(OI)(CI)M'))

    for group in (extra_groups or []):
        logger.info(run_cmd(f'icacls "{folder}" /grant "{group}":(OI)(CI)F'))

    return True


def create_smb_share(folder: str, share_name: str, username: str, logger) -> bool:
    """Udostępnia folder przez SMB z pełnymi prawami dla użytkownika skanera."""
    logger.section("Udostępnianie folderu przez SMB")

    # Usuń istniejący udział o tej nazwie, żeby konfiguracja była powtarzalna.
    # Uwaga: "net share ... /delete" NIE przyjmuje flagi /y (nie istnieje dla
    # tego polecenia) — samo /delete już działa bez potwierdzenia.
    run_cmd(f'net share {share_name} /delete')

    out = run_cmd(f'net share {share_name}="{folder}" /GRANT:{username},FULL')
    logger.info(out)

    # SMB1 bywa wymagane przez starsze modele Ricoh — włącz jako opcję zgodności
    logger.info("Sprawdzanie/włączanie SMB1 (kompatybilność ze starszymi urządzeniami)...")
    logger.info(run_cmd(
        "dism /online /Enable-Feature /FeatureName:SMB1Protocol /All /NoRestart /Quiet"
    ))

    return True


def configure_firewall_smb(device_ip: str, logger) -> bool:
    """Reguły Zapory Windows dla ruchu SMB (port 445), wszystkie profile sieci."""
    logger.section("Konfiguracja Zapory Windows — SMB")

    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Ricoh Scanner SMB" '
        f'dir=in action=allow protocol=TCP localport=445 '
        f'remoteip={device_ip} profile=any'
    ))
    logger.info(run_cmd(
        'netsh advfirewall firewall add rule name="Ricoh Scanner SMB (any)" '
        'dir=in action=allow protocol=TCP localport=445 profile=any'
    ))
    logger.info(run_cmd(
        'netsh advfirewall firewall set rule group="File and Printer Sharing" new enable=yes'
    ))
    return True


def trust_device_ip(device_ip: str, logger) -> bool:
    """
    Dodaje adres IP kserokopiarki jako w pełni zaufany w Zaporze Windows —
    zezwala na cały ruch przychodzący i wychodzący (TCP/UDP, wszystkie porty)
    z/do tego adresu. Zabezpiecza przed przypadkowym blokowaniem jakiegokolwiek
    kanału komunikacji (SNMP, powiadomienia, itd.), niezależnie od wybranego
    protokołu skanowania.
    """
    logger.section(f"Dodawanie {device_ip} do zaufanych adresów (Zapora Windows)")

    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Trusted - Ricoh Device (TCP In)" '
        f'dir=in action=allow protocol=TCP remoteip={device_ip} profile=any'
    ))
    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Trusted - Ricoh Device (UDP In)" '
        f'dir=in action=allow protocol=UDP remoteip={device_ip} profile=any'
    ))
    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Trusted - Ricoh Device (Out)" '
        f'dir=out action=allow protocol=any remoteip={device_ip} profile=any'
    ))
    return True


def configure_windows_for_smb(device_ip: str, username: str, password: str,
                               folder: str, share_name: str, logger) -> dict:
    """
    Pełna, jednoklikowa konfiguracja SMB. Zwraca słownik z danymi potrzebnymi
    do wpisu w książce adresowej Ricoh.
    """
    user_ok = create_local_user(username, password, logger)
    if not user_ok:
        logger.warning(
            "Tworzenie konta napotkało problem — kontynuuję konfigurację, ale "
            "SMB może nie działać poprawnie bez działającego konta użytkownika. "
            "Sprawdź komunikaty powyżej."
        )
    create_scan_folder(folder, logger)
    grant_ntfs_permissions(folder, username, logger)
    create_smb_share(folder, share_name, username, logger)
    configure_firewall_smb(device_ip, logger)
    trust_device_ip(device_ip, logger)

    from .system_utils import get_local_ip
    local_ip = get_local_ip()

    return {
        "protocol": "smb",
        "server": local_ip,
        "share": share_name,
        "path_display": f"\\\\{local_ip}\\{share_name}",
        "username": username,
        "password": password,
    }
