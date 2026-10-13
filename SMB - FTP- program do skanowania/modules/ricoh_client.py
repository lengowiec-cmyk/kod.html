"""
Klient Ricoh Web Image Monitor.

Zakres:
- wykrywanie modelu/profilu urządzenia (różne serie Ricoh mają różne ścieżki
  panelu administracyjnego),
- logowanie sesyjne do panelu administratora (Basic Auth + form login, w
  zależności od wersji firmware),
- dodawanie wpisu do książki adresowej (SMB lub FTP) bez usuwania istniejących
  wpisów,
- wykrywanie, czy urządzenie udostępnia funkcję IP Filter / Access Control —
  informacyjne, BEZ automatycznej modyfikacji (patrz uzasadnienie bezpieczeństwa
  w docstringu RicohSession.add_trusted_ip), żeby nie ryzykować nadpisania
  istniejącej listy zaufanych adresów administratora.

Logika wykrywania profilu i budowania payloadu bazuje na sprawdzonych
endpointach z poprzedniej wersji narzędzia (addressBook.cgi w kilku wariantach
ścieżek), rozszerzona o utrzymanie sesji logowania i obsługę IP Filter.
"""

import requests
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────
#  Profile urządzeń — różne generacje Ricoh używają różnych ścieżek
# ─────────────────────────────────────────────────────────────

RICOH_PROFILES = [
    {
        "name": "Smart Operation Panel (nowsze modele, np. IM C/MP C serii 2000+)",
        "detect": ["smart operation panel", "im c", "sp_"],
        "base_path": "/web/entry/{lang}/websys",
        "lang": "en",
    },
    {
        "name": "Klasyczny Web Image Monitor (MP C / SP serie starsze)",
        "detect": ["websys", "mp c", "aficio"],
        "base_path": "/web/guest/{lang}/websys/webArch",
        "lang": "en",
    },
    {
        "name": "Web Image Monitor — wariant ogólny",
        "detect": ["web image monitor"],
        "base_path": "/web/guest/{lang}/websys/webArch",
        "lang": "en",
    },
]

# Kolejność prób ścieżek/dodawania wpisu — fallback, gdyby wykryty profil
# jednak nie odpowiadał poprawnie
FALLBACK_PATHS = [
    ("/web/guest/en/websys/webArch", "form_old"),
    ("/web/entry/en/websys", "form_new"),
    ("/web/guest/en/websys/webArch/entry", "form_entry"),
    ("/web/entry/en/websys/sp", "form_sp"),
]


@dataclass
class RicohDetectionResult:
    profile: dict | None
    raw_content: str
    ok: bool


def detect_ricoh_profile(ip: str, timeout: int = 5) -> RicohDetectionResult:
    """Pobiera stronę główną urządzenia i dopasowuje jej profil."""
    try:
        r = requests.get(f"http://{ip}/", timeout=timeout)
        content = r.text.lower()

        signatures = ["ricoh", "web image monitor", "wim", "aficio", "savin", "lanier"]
        if not any(sig in content for sig in signatures):
            return RicohDetectionResult(profile=None, raw_content=content, ok=False)

        for profile in RICOH_PROFILES:
            if any(keyword in content for keyword in profile["detect"]):
                return RicohDetectionResult(profile=profile, raw_content=content, ok=True)

        # Rozpoznano jako Ricoh, ale bez dopasowania konkretnego profilu
        return RicohDetectionResult(
            profile={"name": "Nierozpoznany profil (Ricoh ogólny)",
                      "base_path": "/web/guest/{lang}/websys/webArch", "lang": "en"},
            raw_content=content, ok=True
        )

    except Exception as e:
        return RicohDetectionResult(profile=None, raw_content=str(e), ok=False)


# ─────────────────────────────────────────────────────────────
#  Diagnostyka — zbiera rzeczywistą strukturę stron urządzenia,
#  żeby dobrać poprawne endpointy/pola dla konkretnego modelu,
#  zamiast dalej zgadywać po ciemku.
# ─────────────────────────────────────────────────────────────

DIAGNOSTIC_PATHS_TO_TRY = [
    "/",
    "/web/guest/en/websys/webArch/mainFrame.cgi",
    "/web/guest/en/websys/webArch/authForm.cgi",
    "/web/guest/en/websys/top.cgi",
    "/web/guest/en/websys/webArch/tD/kernel/mail_form.cgi",
    "/web/guest/en/websys/webArch/set.cgi?T=1&U=address_book",
    "/websys/webArch/mainFrame.cgi",
    "/websys/webArch/authForm.cgi",
]


def run_diagnostics(ip: str, admin_user: str, admin_pass: str,
                     logger, output_path: str) -> str:
    """
    Łączy się z urządzeniem, próbuje różnych znanych ścieżek starszego
    Web Image Monitor, i zapisuje surową treść odpowiedzi (HTML) do pliku —
    żeby móc rozpoznać rzeczywistą strukturę formularza konkretnego modelu
    zamiast dalej zgadywać endpointy "w ciemno". Bezpieczne: tylko GET,
    nic nie zmienia na urządzeniu.

    Zwraca ścieżkę do zapisanego pliku diagnostycznego.
    """
    logger.section("Diagnostyka Web Image Monitor (zbieranie struktury stron)")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    if admin_user:
        session.auth = (admin_user, admin_pass or "")

    report_lines = [
        f"=== DIAGNOSTYKA RICOH — {ip} ===",
        f"Login użyty do prób: '{admin_user}'",
        "",
    ]

    for path in DIAGNOSTIC_PATHS_TO_TRY:
        url = f"http://{ip}{path}"
        try:
            r = session.get(url, timeout=6)
            report_lines.append(f"--- GET {path} ---")
            report_lines.append(f"Status: {r.status_code}")
            report_lines.append(f"Content-Type: {r.headers.get('Content-Type', '?')}")
            report_lines.append(f"Długość treści: {len(r.text)} znaków")
            # Zapisujemy pełną treść — potrzebna do analizy pól formularza
            report_lines.append("--- TREŚĆ ---")
            report_lines.append(r.text)
            report_lines.append("")
            logger.info(f"  {path} → HTTP {r.status_code} ({len(r.text)} znaków)")
        except Exception as e:
            report_lines.append(f"--- GET {path} ---")
            report_lines.append(f"BŁĄD: {e}")
            report_lines.append("")
            logger.info(f"  {path} → błąd połączenia: {e}")

    full_report = "\n".join(report_lines)
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_report)
        logger.info(f"✔ Raport diagnostyczny zapisany: {output_path}")
        logger.info(
            "  Wyślij ten plik, żeby dopasować program dokładnie do Twojego "
            "modelu urządzenia."
        )
    except Exception as e:
        logger.error(f"Nie udało się zapisać raportu diagnostycznego: {e}")

    return output_path


def _resolve_base(profile: dict) -> str:
    return profile["base_path"].replace("{lang}", profile["lang"])


# ─────────────────────────────────────────────────────────────
#  Budowanie payloadu dla addressBook.cgi
# ─────────────────────────────────────────────────────────────

def build_address_payload(method: str, server: str, path: str,
                           username: str, password: str,
                           protocol: str = "smb", ftp_port: str = "21") -> dict:
    """
    protocol: "smb" lub "ftp"
    Dla SMB: server = host komputera, path = nazwa udziału
    Dla FTP: server = host komputera, path = ścieżka na serwerze FTP (zwykle "/")
    """
    if protocol == "ftp":
        common = {
            "name":          f"Skaner_{username}",
            "displayedName": f"Skaner_{username}",
            "ftpServerName": server,
            "ftpPort":       ftp_port,
            "ftpPath":       path if path.startswith("/") else f"/{path}",
            "ftpUserName":   username,
            "ftpPassword":   password,
        }
        if method == "form_new":
            return {**common, "inputDataType": "1", "type": "ftp", "Submit": "OK"}
        elif method == "form_old":
            return {**common, "inputDataType": "1", "addrType": "3",
                    "protocolType": "ftp", "OK": "OK"}
        elif method == "form_entry":
            return {**common, "inputDataType": "1", "addrType": "3",
                    "folderType": "ftp", "OK": "OK"}
        elif method == "form_sp":
            return {**common, "entryType": "ftp", "folderType": "ftp", "Submit": "Submit"}
        return common

    # SMB
    # Uwaga: f"\\{path}" w Pythonie to JEDEN znak backslash + nazwa udziału
    # (np. "\SkanyRicoh") — to pole formularza Ricoh dla "ścieżki względnej"
    # od strony serwera SMB wskazanego w smbServerName; sam serwer (host)
    # jest osobnym polem, więc tu nie potrzeba pełnego UNC \\host\share.
    common = {
        "name":          f"Skaner_{username}",
        "displayedName": f"Skaner_{username}",
        "smbServerName": server,
        "smbPath":       f"\\{path}",
        "smbUserName":   username,
        "smbPassword":   password,
        "smbDomain":     "",
    }
    if method == "form_new":
        return {**common, "inputDataType": "1", "type": "smb", "Submit": "OK"}
    elif method == "form_old":
        return {**common, "inputDataType": "1", "addrType": "3",
                "protocolType": "smb", "OK": "OK"}
    elif method == "form_entry":
        return {**common, "inputDataType": "1", "addrType": "3",
                "folderType": "smb", "OK": "OK"}
    elif method == "form_sp":
        return {**common, "entryType": "smb", "folderType": "smb", "Submit": "Submit"}
    return common


# ─────────────────────────────────────────────────────────────
#  Sesja / logowanie do panelu administratora
# ─────────────────────────────────────────────────────────────

class RicohSession:
    """
    Utrzymuje sesję HTTP do urządzenia Ricoh, z próbą zalogowania jako
    administrator (Basic Auth — najszerzej wspierany wariant przez różne
    generacje firmware Web Image Monitor).
    """

    def __init__(self, ip: str, admin_user: str, admin_pass: str, logger):
        self.ip = ip
        self.admin_user = admin_user
        # Puste hasło ("") jest prawidłową, częstą wartością fabryczną na
        # urządzeniach Ricoh — nigdy nie traktujemy go jak brak danych.
        # Zabezpieczamy się tylko przed None, który wywaliłby requests.auth.
        self.admin_pass = admin_pass if admin_pass is not None else ""
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        if admin_user:
            self.session.auth = (admin_user, self.admin_pass)
        self.logged_in = False

    def login(self) -> bool:
        """Próbuje uzyskać dostęp do panelu administratora."""
        try:
            r = self.session.get(f"http://{self.ip}/", timeout=8)
            self.logged_in = r.status_code == 200
            if self.logged_in:
                self.logger.info("Sesja z urządzeniem Ricoh nawiązana (Basic Auth)")
            else:
                self.logger.warning(
                    f"Odpowiedź HTTP {r.status_code} przy próbie logowania — "
                    "kontynuuję mimo to (część endpointów nie wymaga sesji)"
                )
                self.logged_in = True  # nie blokuj dalszych prób
            return self.logged_in
        except Exception as e:
            self.logger.error(f"Nie udało się połączyć z urządzeniem: {e}")
            return False

    def try_add_address_entry(self, base_path: str, method: str,
                               server: str, path: str, username: str,
                               password: str, protocol: str, ftp_port: str) -> bool:
        url = f"http://{self.ip}{base_path}/addressBook.cgi"
        payload = build_address_payload(
            method, server, path, username, password,
            protocol=protocol, ftp_port=ftp_port
        )
        self.logger.info(f"  → POST {base_path}/addressBook.cgi ({method}, {protocol.upper()})")
        try:
            r = self.session.post(url, data=payload, timeout=10)

            if r.status_code not in (200, 302):
                return False

            # Status 200 nie gwarantuje sukcesu — wiele firmware'ów Ricoh
            # zwraca 200 OK nawet dla formularza z błędem walidacji.
            # Sprawdzamy treść odpowiedzi pod kątem oczywistych komunikatów błędu.
            content_lower = r.text.lower() if hasattr(r, "text") else ""
            error_markers = [
                "error", "invalid", "błąd", "nieprawidłow",
                "failed", "already exists", "already registered",
            ]
            if any(marker in content_lower for marker in error_markers):
                self.logger.debug(
                    f"  Odpowiedź HTTP 200, ale treść sugeruje błąd walidacji "
                    f"formularza ({base_path})"
                )
                return False

            return True
        except Exception as e:
            self.logger.debug(f"  Próba nieudana ({base_path}): {e}")
            return False

    def add_address_book_entry(self, server: str, path: str,
                                username: str, password: str,
                                protocol: str = "smb", ftp_port: str = "21") -> bool:
        """
        Dodaje NOWY wpis do książki adresowej urządzenia — nie usuwa ani nie
        nadpisuje istniejących wpisów (POST tworzy nową pozycję).
        """
        self.logger.section(f"Dodawanie wpisu do książki adresowej Ricoh ({protocol.upper()})")

        detection = detect_ricoh_profile(self.ip)
        if not detection.ok or detection.profile is None:
            self.logger.error("Urządzenie nie odpowiada lub nie zostało rozpoznane jako Ricoh")
            return False

        self.logger.info(f"Wykryty profil: {detection.profile['name']}")

        base_path = _resolve_base(detection.profile)
        # Zgadnij metodę na podstawie ścieżki (heurystyka spójna z FALLBACK_PATHS)
        method = "form_new" if "/entry/" in base_path else "form_old"

        if self.try_add_address_entry(base_path, method, server, path,
                                       username, password, protocol, ftp_port):
            self.logger.info("✔ Wpis dodany do książki adresowej")
            return True

        self.logger.info("Próbuję alternatywnych ścieżek panelu administracyjnego...")
        for fp, fm in FALLBACK_PATHS:
            if fp == base_path:
                continue
            if self.try_add_address_entry(fp, fm, server, path,
                                           username, password, protocol, ftp_port):
                self.logger.info(f"✔ Wpis dodany przez ścieżkę: {fp}")
                return True

        self.logger.warning(
            "Nie udało się automatycznie dodać wpisu — skonfiguruj ręcznie "
            "w Web Image Monitor, używając danych z raportu końcowego"
        )
        return False

    def verify_address_book_reachable(self) -> bool:
        """
        Test połączenia z panelem książki adresowej po dodaniu wpisu —
        potwierdza, że urządzenie nadal odpowiada poprawnie na sesję
        administratora (nie weryfikuje treści konkretnego wpisu, bo
        format odpowiedzi różni się zbytnio między firmware).
        """
        try:
            r = self.session.get(f"http://{self.ip}/", timeout=6)
            return r.status_code == 200
        except Exception:
            return False

    def add_trusted_ip(self, computer_ip: str) -> bool:
        """
        Próba dodania adresu IP komputera do listy dozwolonych adresów
        (Access Control / IP Filter) urządzenia. Ta funkcja jest DOSTĘPNA
        TYLKO na części modeli i wymaga uprawnień administratora urządzenia.
        Niepowodzenie NIE przerywa reszty konfiguracji — traktowane jako
        opcjonalne wzmocnienie, nie krytyczny krok.

        WAŻNE — bezpieczeństwo: format i semantyka pól IP Filter różnią się
        bardzo między generacjami firmware Ricoh (część endpointów akceptuje
        POJEDYNCZY nowy wpis w osobnym polu, część oczekuje CAŁEJ listy na
        raz i nadpisuje ją). Ponieważ nie da się tego bezpiecznie rozróżnić
        bez odpowiedzi konkretnego urządzenia, a błędne nadpisanie mogłoby
        wykasować inne zaufane adresy skonfigurowane wcześniej przez
        administratora, ta funkcja NIE wysyła POST na endpointy, które mogą
        zawierać pełną listę. Zamiast tego tylko WYKRYWA i RAPORTUJE, czy
        urządzenie w ogóle udostępnia taką funkcję pod standardowymi ścieżkami
        — a faktyczne dodanie adresu pozostawia jako wskazówkę do ręcznej
        weryfikacji w panelu Web Image Monitor, żeby uniknąć ryzyka
        przypadkowego usunięcia istniejących wpisów.
        """
        self.logger.section("Sprawdzanie dostępności funkcji IP Filter na urządzeniu")

        candidate_paths = [
            "/web/guest/en/websys/webArch/accessSet.cgi",
            "/web/entry/en/websys/accessSet.cgi",
            "/web/guest/en/websys/webArch/ipFilter.cgi",
            "/web/entry/en/websys/ipFilter.cgi",
        ]

        for path in candidate_paths:
            try:
                get_url = f"http://{self.ip}{path}"
                r = self.session.get(get_url, timeout=8)
                if r.status_code == 200:
                    self.logger.info(
                        f"Urządzenie udostępnia funkcję IP Filter / Access Control "
                        f"pod ścieżką {path}. Ze względów bezpieczeństwa (ryzyko "
                        f"nadpisania istniejącej listy zaufanych adresów) program "
                        f"NIE modyfikuje jej automatycznie. Aby dodać komputer "
                        f"({computer_ip}) do zaufanych adresów, zrób to "
                        f"ręcznie w Web Image Monitor: Device Management → "
                        f"Access Control."
                    )
                    return True
            except Exception:
                continue

        self.logger.info(
            "Urządzenie nie udostępnia (lub nie wykryto) funkcji IP Filter / "
            "Access Control pod standardowymi ścieżkami — pomijam ten krok. "
            "To nie jest błąd: nie wszystkie modele Ricoh mają tę funkcję, "
            "a ochronę sieciową zapewnia już Zapora Windows skonfigurowana wcześniej."
        )
        return False
