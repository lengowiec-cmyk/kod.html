"""
Konfiguracja wbudowanego serwera FTP w Windows (rola IIS + FTP Server).

Zakres:
- automatyczna instalacja roli (Install-WindowsFeature na Server,
  DISM na Windows 10/11 klienckim, bez pytania o restart),
- utworzenie witryny FTP wskazującej na folder skanów,
- uwierzytelnianie Basic + autoryzacja dla konta skanera,
- tryb pasywny w ustalonym zakresie portów (wymagane dla NAT/firewall),
- reguły Zapory Windows dla portu kontrolnego i zakresu pasywnego.
"""

from .system_utils import run_cmd, run_powershell, get_local_ip, check_tcp_port
from .windows_config import create_local_user, create_scan_folder, grant_ntfs_permissions


FTP_SITE_NAME = "RicohScannerFTP"
FTP_PASSIVE_PORT_START = 50000
FTP_PASSIVE_PORT_END = 50100
FTP_CONTROL_PORT = 21

APPCMD = r'%windir%\system32\inetsrv\appcmd'


def install_ftp_role(logger) -> bool:
    """
    Instaluje rolę IIS + FTP Server. W pełni automatyczne:
    - próbuje Install-WindowsFeature (Windows Server),
    - w razie niepowodzenia przełącza się na DISM (Windows 10/11),
    - nie inicjuje restartu systemu,
    - po instalacji sam uruchamia usługę FTP.
    """
    logger.section("Instalacja roli IIS FTP Server")

    out = run_powershell(
        "Install-WindowsFeature -Name Web-Server,Web-Ftp-Server,"
        "Web-Mgmt-Console -IncludeManagementTools -Restart:$false",
        timeout=600
    )
    logger.info(out)

    needs_dism = any(x in out.lower() for x in [
        "not recognized", "nie jest rozpoznaw", "nie można odnaleźć",
        "is not recognized", "nierozpoznan", "unknown"
    ])

    if needs_dism:
        logger.info("Wykryto system kliencki (nie Server) — instalacja przez DISM...")
        features = [
            "IIS-WebServerRole", "IIS-WebServer", "IIS-CommonHttpFeatures",
            "IIS-FTPServer", "IIS-FTPSvc", "IIS-FTPExtensibility",
            "IIS-WebServerManagementTools", "IIS-ManagementConsole",
        ]
        for feat in features:
            logger.info(run_cmd(
                f'dism /online /Enable-Feature /FeatureName:{feat} /All /NoRestart /Quiet',
                timeout=300
            ))

    logger.info("Uruchamianie usługi Microsoft FTP Service...")
    run_cmd('sc config ftpsvc start= auto')

    started = False
    for attempt in range(3):
        out = run_cmd('net start ftpsvc')
        logger.info(out)
        low = out.lower()
        if any(x in low for x in [
            "already", "już", "started", "uruchomiono", "uruchomiona", "uruchomiono pomyślnie"
        ]):
            started = True
            break
        run_cmd('timeout /t 2')

    # Weryfikacja niezależna od języka komunikatu — sprawdź faktyczny stan usługi
    if not started:
        status_out = run_cmd('sc query ftpsvc')
        if "running" in status_out.lower() or "działa" in status_out.lower():
            started = True
            logger.info("Usługa FTP działa (zweryfikowano przez 'sc query').")

    if not started:
        logger.warning("Usługa FTP może wymagać ręcznego uruchomienia w services.msc")

    return started


def configure_ftp_site(folder: str, username: str, logger,
                        site_name: str = FTP_SITE_NAME,
                        port: int = FTP_CONTROL_PORT) -> bool:
    """
    Tworzy witrynę FTP w IIS wskazującą na folder skanów.
    Idempotentne — usuwa poprzednią witrynę o tej samej nazwie przed utworzeniem nowej.
    """
    logger.section("Konfiguracja witryny FTP w IIS")

    run_cmd(f'{APPCMD} delete site "{site_name}"')

    logger.info(run_cmd(
        f'{APPCMD} add site /name:"{site_name}" '
        f'/physicalPath:"{folder}" /bindings:ftp/*:{port}:'
    ))

    # SSL wyłączony — maksymalna kompatybilność ze starszymi urządzeniami Ricoh
    logger.info(run_cmd(
        f'{APPCMD} set config "{site_name}" '
        f'-section:system.applicationHost/sites '
        f'"/siteDefaults.ftpServer.security.ssl.controlChannelPolicy:SslAllow" '
        f'"/siteDefaults.ftpServer.security.ssl.dataChannelPolicy:SslAllow" /commit:apphost'
    ))

    # Autoryzacja dla konta skanera
    logger.info(run_cmd(
        f'{APPCMD} set config "{site_name}" '
        f'-section:system.ftpServer/security/authorization '
        f'"/+[accessType=\'Allow\',users=\'{username}\',permissions=\'Read,Write\']" '
        f'/commit:apphost'
    ))

    # Uwierzytelnianie Basic
    logger.info(run_cmd(
        f'{APPCMD} set config "{site_name}" '
        f'-section:system.ftpServer/security/authentication/basicAuthentication '
        f'/enabled:true /commit:apphost'
    ))

    # Tryb pasywny — stały zakres portów (potrzebny dla reguł zapory / NAT)
    logger.info(run_cmd(
        f'{APPCMD} set config '
        f'-section:system.applicationHost/sites '
        f'"/siteDefaults.ftpServer.firewallSupport.lowDataChannelPort:{FTP_PASSIVE_PORT_START}" '
        f'"/siteDefaults.ftpServer.firewallSupport.highDataChannelPort:{FTP_PASSIVE_PORT_END}" '
        f'/commit:apphost'
    ))

    local_ip = get_local_ip()
    logger.info(run_cmd(
        f'{APPCMD} set config '
        f'-section:system.applicationHost/sites '
        f'"/siteDefaults.ftpServer.firewallSupport.externalIp4Address:{local_ip}" '
        f'/commit:apphost'
    ))

    logger.info(run_cmd(f'{APPCMD} start site "{site_name}"'))
    logger.info(run_cmd('net stop ftpsvc & net start ftpsvc'))

    return True


def configure_firewall_ftp(device_ip: str, logger, port: int = FTP_CONTROL_PORT) -> bool:
    """Reguły Zapory Windows: port kontrolny FTP + zakres pasywny, wszystkie profile."""
    logger.section("Konfiguracja Zapory Windows — FTP")

    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Ricoh Scanner FTP Control" '
        f'dir=in action=allow protocol=TCP localport={port} '
        f'remoteip={device_ip} profile=any'
    ))
    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Ricoh Scanner FTP Passive" '
        f'dir=in action=allow protocol=TCP '
        f'localport={FTP_PASSIVE_PORT_START}-{FTP_PASSIVE_PORT_END} '
        f'remoteip={device_ip} profile=any'
    ))
    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Ricoh Scanner FTP Control (any)" '
        f'dir=in action=allow protocol=TCP localport={port} profile=any'
    ))
    logger.info(run_cmd(
        f'netsh advfirewall firewall add rule name="Ricoh Scanner FTP Passive (any)" '
        f'dir=in action=allow protocol=TCP '
        f'localport={FTP_PASSIVE_PORT_START}-{FTP_PASSIVE_PORT_END} profile=any'
    ))
    logger.info(run_cmd(
        'netsh advfirewall firewall add rule name="Microsoft FTP Service" '
        'dir=in action=allow program="%windir%\\system32\\inetsrv\\ftpsvc.dll" '
        'enable=yes profile=any'
    ))
    logger.info(run_cmd(
        'netsh advfirewall firewall set rule group="FTP Server" new enable=yes'
    ))
    logger.info(run_cmd(
        'netsh advfirewall firewall set rule group='
        '"World Wide Web Services (FTP Traffic-In)" new enable=yes'
    ))
    return True


def test_ftp_connectivity(device_ip: str, logger, port: int = FTP_CONTROL_PORT) -> bool:
    """Testy informacyjne dostępności portu FTP (lokalnie i od strony drukarki)."""
    logger.section("Testy połączenia FTP")

    local_ip = get_local_ip()
    local_ok = check_tcp_port(local_ip, port)
    logger.info(
        f"Usługa FTP lokalnie ({local_ip}:{port}): "
        f"{'OK' if local_ok else 'BRAK ODPOWIEDZI'}"
    )

    device_ok = check_tcp_port(device_ip, 80)
    logger.info(
        f"Urządzenie Ricoh ({device_ip}:80): "
        f"{'odpowiada' if device_ok else 'brak odpowiedzi (może być normalne)'}"
    )

    return local_ok


def configure_windows_for_ftp(device_ip: str, username: str, password: str,
                               folder: str, logger) -> dict:
    """
    Pełna, jednoklikowa konfiguracja FTP. Zwraca słownik z danymi potrzebnymi
    do wpisu w książce adresowej Ricoh.

    WAŻNE: FTP w IIS wymaga istniejącego konta lokalnego Windows i uprawnień
    NTFS do folderu — dokładnie tak samo jak SMB. Te kroki muszą się wykonać
    PRZED konfiguracją witryny FTP, inaczej autoryzacja w IIS (accessType=Allow
    dla użytkownika, który nie istnieje) nie zadziała i logowanie z drukarki
    zawsze się nie powiedzie.
    """
    user_ok = create_local_user(username, password, logger)
    if not user_ok:
        logger.warning(
            "Tworzenie konta napotkało problem — kontynuuję konfigurację, ale "
            "FTP może nie działać poprawnie bez działającego konta użytkownika."
        )
    create_scan_folder(folder, logger)
    grant_ntfs_permissions(folder, username, logger, extra_groups=["IIS_IUSRS"])

    install_ftp_role(logger)
    configure_ftp_site(folder, username, logger)
    configure_firewall_ftp(device_ip, logger)
    test_ftp_connectivity(device_ip, logger)

    local_ip = get_local_ip()

    return {
        "protocol": "ftp",
        "server": local_ip,
        "path": "/",
        "port": FTP_CONTROL_PORT,
        "path_display": f"ftp://{local_ip}/",
        "username": username,
        "password": password,
    }
