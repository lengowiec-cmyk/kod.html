"""
Ricoh Scanner Config — automatyczna konfiguracja skanowania SMB/FTP dla
urządzeń Ricoh.

Uruchomienie:
    python main.py

Budowanie do EXE:
    pyinstaller --onefile --noconsole --name "RicohScannerConfig" main.py

Autor: wygenerowane z Claude (Anthropic) na podstawie wymagań użytkownika.
"""

import sys
import os
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QTextEdit, QGroupBox, QMessageBox, QFrame, QProgressBar, QCheckBox,
    QDialog, QListWidget, QListWidgetItem, QDialogButtonBox
)

from modules.logger import get_logger, get_app_directory
from modules import theme
from modules.system_utils import (
    is_admin, relaunch_as_admin, get_local_ip, validate_ip, scan_lan_for_ricoh
)
from modules.windows_config import (
    configure_windows_for_smb, DEFAULT_SCAN_FOLDER, DEFAULT_SHARE_NAME
)
from modules.ftp_config import configure_windows_for_ftp
from modules.ricoh_client import RicohSession, run_diagnostics
from modules.post_check import run_post_configuration_checks, CheckStatus
from modules.defender_config import configure_defender_trust


APP_TITLE = "Konfigurator skanowania Ricoh — SMB / FTP  |  © Artur Biel"
DEFAULT_USERNAME = "skaner"
DEFAULT_PASSWORD = "Skaner123!"


# ─────────────────────────────────────────────────────────────
#  Most sygnałów: wątek roboczy → GUI (Qt wymaga tego dla bezpieczeństwa wątków)
# ─────────────────────────────────────────────────────────────

class WorkerSignals(QObject):
    log_message = Signal(str)
    finished = Signal(bool, str, list)   # sukces, treść raportu, lista CheckResult
    device_found = Signal(str)           # wykryte IP w auto-detect
    devices_scanned = Signal(list)       # pełna lista DiscoveredDevice po skanowaniu (ręczny przycisk)
    progress = Signal(int)               # 0-100


# ─────────────────────────────────────────────────────────────
#  Dialog wyboru urządzenia (gdy skanowanie sieci znajdzie więcej niż jedno)
# ─────────────────────────────────────────────────────────────

class DeviceSelectionDialog(QDialog):
    """Lista znalezionych urządzeń Ricoh do ręcznego wyboru przez użytkownika."""

    def __init__(self, devices, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wybierz kserokopiarkę")
        self.setMinimumWidth(420)
        self.selected_ip = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info = QLabel(f"Znaleziono {len(devices)} urządzeń Ricoh w sieci. Wybierz właściwe:")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        for dev in devices:
            label = f"{dev.ip}"
            if dev.title:
                label += f"  —  {dev.title}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, dev.ip)
            self.list_widget.addItem(item)
        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(theme.STYLESHEET)

    def accept(self):
        current = self.list_widget.currentItem()
        if current:
            self.selected_ip = current.data(Qt.UserRole)
        super().accept()

    @staticmethod
    def choose(devices, parent=None):
        """Zwraca wybrane IP, albo None jeśli użytkownik anulował lub jest tylko 1 urządzenie."""
        if len(devices) == 1:
            return devices[0].ip
        if not devices:
            return None
        dialog = DeviceSelectionDialog(devices, parent)
        if dialog.exec() == QDialog.Accepted:
            return dialog.selected_ip
        return None


# ─────────────────────────────────────────────────────────────
#  Główne okno aplikacji
# ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(720, 640)

        self.logger = get_logger()
        self.signals = WorkerSignals()
        self.signals.log_message.connect(self._append_log)
        self.signals.finished.connect(self._on_finished)
        self.signals.device_found.connect(self._on_device_found)
        self.signals.devices_scanned.connect(self._on_devices_scanned)
        self.signals.progress.connect(self._on_progress)

        self.logger.set_gui_callback(
            lambda msg: self.signals.log_message.emit(msg)
        )

        self._build_ui()
        self._apply_style()

    # ── Budowa interfejsu ──────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(14)

        # ── Nagłówek z paskiem statusu jak panel diagnostyczny ──
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Konfigurator skanowania Ricoh")
        title.setFont(QFont(theme.FONT_DISPLAY, 19, QFont.DemiBold))
        title.setStyleSheet(f"color: {theme.TEXT_MAIN};")
        subtitle = QLabel("SMB / FTP · foldery · zapora · książka adresowa — jednym kliknięciem")
        subtitle.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        copyright_label = QLabel("© Artur Biel")
        copyright_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 10px; letter-spacing: 0.5px;"
        )
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_col.addWidget(copyright_label)
        header_row.addLayout(title_col, stretch=1)

        # Wskaźnik trybu (zwykły użytkownik / administrator) — jak lampka na panelu
        self.admin_badge = QLabel()
        self._update_admin_badge()
        self.admin_badge.setAlignment(Qt.AlignCenter)
        header_row.addWidget(self.admin_badge)

        root_layout.addLayout(header_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {theme.BORDER}; max-height: 1px; border: none;")
        root_layout.addWidget(divider)

        # ── Karta: urządzenie Ricoh ──
        device_box = QGroupBox("URZĄDZENIE RICOH")
        device_layout = QVBoxLayout(device_box)
        device_layout.setSpacing(10)

        ip_row = QHBoxLayout()
        ip_row.setSpacing(8)
        ip_label = QLabel("Adres IP")
        ip_label.setFixedWidth(110)
        ip_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        ip_row.addWidget(ip_label)
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("puste = automatyczne wykrywanie w sieci LAN")
        ip_row.addWidget(self.ip_input, stretch=1)
        self.btn_detect = QPushButton("🔍  Wykryj w sieci")
        self.btn_detect.setCursor(Qt.PointingHandCursor)
        self.btn_detect.clicked.connect(self._on_detect_clicked)
        ip_row.addWidget(self.btn_detect)
        device_layout.addLayout(ip_row)

        admin_row = QHBoxLayout()
        admin_row.setSpacing(8)
        user_label = QLabel("Login admin")
        user_label.setFixedWidth(110)
        user_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        admin_row.addWidget(user_label)
        self.admin_user_input = QLineEdit("admin")
        admin_row.addWidget(self.admin_user_input)
        pass_label = QLabel("Hasło")
        pass_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        admin_row.addWidget(pass_label)
        self.admin_pass_input = QLineEdit()
        self.admin_pass_input.setEchoMode(QLineEdit.Password)
        self.admin_pass_input.setPlaceholderText("puste, jeśli fabrycznie brak hasła")
        admin_row.addWidget(self.admin_pass_input)
        device_layout.addLayout(admin_row)

        root_layout.addWidget(device_box)

        # ── Karta: protokół (karty wyboru zamiast zwykłych radio) ──
        protocol_box = QGroupBox("PROTOKÓŁ SKANOWANIA")
        protocol_layout = QHBoxLayout(protocol_box)
        protocol_layout.setSpacing(10)

        self.radio_smb = QRadioButton("SMB — udział sieciowy Windows")
        self.radio_ftp = QRadioButton("FTP — wbudowany serwer Windows (IIS)")
        self.radio_smb.setChecked(True)
        self.radio_smb.setCursor(Qt.PointingHandCursor)
        self.radio_ftp.setCursor(Qt.PointingHandCursor)

        self.protocol_group = QButtonGroup(self)
        self.protocol_group.addButton(self.radio_smb)
        self.protocol_group.addButton(self.radio_ftp)

        protocol_layout.addWidget(self.radio_smb)
        protocol_layout.addWidget(self.radio_ftp)
        root_layout.addWidget(protocol_box)

        # ── Karta: opcjonalne wykluczenie Windows Defender ──
        defender_box = QGroupBox("WINDOWS DEFENDER (opcjonalnie)")
        defender_layout = QVBoxLayout(defender_box)
        defender_layout.setSpacing(4)

        self.chk_defender_exclusion = QCheckBox(
            "Dodaj folder skanów i ten program do wykluczeń Windows Defender"
        )
        self.chk_defender_exclusion.setCursor(Qt.PointingHandCursor)
        self.chk_defender_exclusion.setChecked(False)  # świadomy wybór, nie domyślne
        defender_layout.addWidget(self.chk_defender_exclusion)

        defender_hint = QLabel(
            "Zapobiega opóźnieniom przy zapisie skanów i ponownemu skanowaniu "
            "programu przy starcie. Używa oficjalnego mechanizmu Add-MpPreference — "
            "nic nie jest wyłączane ani ukrywane, tylko dodawana konkretna ścieżka "
            "do listy wykluczeń."
        )
        defender_hint.setWordWrap(True)
        defender_hint.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        defender_layout.addWidget(defender_hint)

        root_layout.addWidget(defender_box)

        # ── Przycisk główny ──
        self.btn_configure = QPushButton("⚙   KONFIGURUJ")
        self.btn_configure.setObjectName("primaryButton")
        self.btn_configure.setMinimumHeight(50)
        self.btn_configure.setCursor(Qt.PointingHandCursor)
        self.btn_configure.setFont(QFont(theme.FONT_DISPLAY, 12))
        self.btn_configure.clicked.connect(self._on_configure_clicked)
        root_layout.addWidget(self.btn_configure)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        root_layout.addWidget(self.progress_bar)

        # ── Konsola logów ──
        log_label = QLabel("PRZEBIEG KONFIGURACJI")
        log_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 600; "
            f"letter-spacing: 1px; margin-top: 4px;"
        )
        root_layout.addWidget(log_label)

        self.log_output = QTextEdit()
        self.log_output.setObjectName("logConsole")
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont(theme.FONT_MONO, 9))
        root_layout.addWidget(self.log_output, stretch=1)

    def _update_admin_badge(self):
        if is_admin():
            text = f'{theme.status_dot_html(theme.SUCCESS)} <span style="color:{theme.TEXT_MUTED};">Administrator</span>'
        else:
            text = f'{theme.status_dot_html(theme.WARNING)} <span style="color:{theme.TEXT_MUTED};">Wymaga UAC</span>'
        self.admin_badge.setText(text)
        self.admin_badge.setStyleSheet(
            f"background-color: {theme.BG_CARD}; border: 1px solid {theme.BORDER}; "
            f"border-radius: 14px; padding: 6px 14px; font-size: 12px;"
        )

    def _apply_style(self):
        self.setStyleSheet(theme.STYLESHEET)

    # ── Obsługa zdarzeń GUI ────────────────────────────────

    def _append_log(self, msg: str):
        self.log_output.append(msg)

    def _append_check_results(self, check_results: list):
        """Wypisuje wyniki testów końcowych w logu z kolorami (zielony/czerwony)."""
        self.log_output.append("")
        self.log_output.append("=== WYNIKI WERYFIKACJI ===")
        for r in check_results:
            if r.status == CheckStatus.PASS:
                color = theme.SUCCESS
            elif r.status == CheckStatus.FAIL:
                color = theme.DANGER
            else:
                color = theme.WARNING
            html_line = f'<span style="color:{color}; font-weight:600;">{r.as_line()}</span>'
            self.log_output.append(html_line)

    def _on_progress(self, value: int):
        pass  # zarezerwowane pod przyszłą rozbudowę (pasek z wartością %)

    def _on_device_found(self, ip: str):
        self.ip_input.setText(ip)

    def _on_detect_clicked(self):
        self.btn_detect.setEnabled(False)
        self.log_output.append("Szukam urządzeń Ricoh w sieci lokalnej...")

        def worker():
            devices = scan_lan_for_ricoh(self.logger)
            self.signals.log_message.emit(
                "Wyszukiwanie zakończone."
                if devices else "Nie znaleziono urządzeń."
            )
            if devices:
                self.signals.devices_scanned.emit(devices)
            self.btn_detect.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()

    def _on_devices_scanned(self, devices: list):
        """Wywoływane w wątku głównym GUI — bezpieczne miejsce na dialog wyboru."""
        if len(devices) == 1:
            self.ip_input.setText(devices[0].ip)
            return

        chosen_ip = DeviceSelectionDialog.choose(devices, parent=self)
        if chosen_ip:
            self.ip_input.setText(chosen_ip)
        else:
            self.log_output.append("Wybór urządzenia anulowany — pole IP pozostawione bez zmian.")

    def _on_configure_clicked(self):
        ip_scanner = self.ip_input.text().strip()
        admin_user = self.admin_user_input.text().strip() or "admin"
        admin_pass = self.admin_pass_input.text()
        protocol = "ftp" if self.radio_ftp.isChecked() else "smb"
        defender_exclusion_requested = self.chk_defender_exclusion.isChecked()

        if ip_scanner and not validate_ip(ip_scanner):
            QMessageBox.critical(self, "Błąd", f"Nieprawidłowy format IP: '{ip_scanner}'")
            return

        if not is_admin():
            reply = QMessageBox.question(
                self, "Wymagane uprawnienia administratora",
                "Konfiguracja systemu wymaga uprawnień administratora.\n"
                "Program zostanie uruchomiony ponownie z podniesionymi "
                "uprawnieniami (UAC). Kontynuować?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if relaunch_as_admin():
                    sys.exit(0)
                else:
                    QMessageBox.critical(
                        self, "Błąd",
                        "Nie udało się uzyskać uprawnień administratora."
                    )
            return

        # Jeśli IP nie podano, wykrywamy urządzenia TERAZ, w wątku głównym GUI —
        # żeby móc bezpiecznie pokazać dialog wyboru, jeśli znajdzie się więcej
        # niż jedno urządzenie. Wątek roboczy startuje dopiero z ustalonym IP.
        if not ip_scanner:
            self.btn_configure.setEnabled(False)
            self.log_output.clear()
            self.log_output.append("IP kserokopiarki nie podano — szukam automatycznie w sieci...")
            QApplication.processEvents()

            devices = scan_lan_for_ricoh(self.logger)

            if not devices:
                self.btn_configure.setEnabled(True)
                QMessageBox.critical(
                    self, "Błąd",
                    "Nie znaleziono żadnej kserokopiarki Ricoh w sieci.\n"
                    "Podaj adres IP ręcznie i spróbuj ponownie."
                )
                return

            if len(devices) > 1:
                chosen_ip = DeviceSelectionDialog.choose(devices, parent=self)
                if not chosen_ip:
                    self.btn_configure.setEnabled(True)
                    self.log_output.append("Wybór urządzenia anulowany — konfiguracja przerwana.")
                    return
                ip_scanner = chosen_ip
            else:
                ip_scanner = devices[0].ip

            self.ip_input.setText(ip_scanner)
            self.log_output.append(f"Wybrano urządzenie: {ip_scanner}")
            self.btn_configure.setEnabled(True)

        self.btn_configure.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log_output.clear()

        threading.Thread(
            target=self._run_configuration,
            args=(ip_scanner, admin_user, admin_pass, protocol,
                  defender_exclusion_requested),
            daemon=True
        ).start()

    # ── Logika konfiguracji (uruchamiana w osobnym wątku) ──

    def _run_configuration(self, ip_scanner: str, admin_user: str,
                            admin_pass: str, protocol: str,
                            defender_exclusion_requested: bool = False):
        try:
            logger = self.logger
            logger.section("START KONFIGURACJI")

            # Uwaga: wykrywanie IP i ewentualny wybór urządzenia (jeśli znaleziono
            # kilka) odbyły się już w _on_configure_clicked, w wątku głównym GUI —
            # tutaj ip_scanner jest zawsze ustalone i niepuste.

            local_ip = get_local_ip()
            logger.info(f"IP komputera: {local_ip}")
            logger.info(f"IP kserokopiarki: {ip_scanner}")
            logger.info(f"Protokół: {protocol.upper()}")

            if protocol == "smb":
                scan_config = configure_windows_for_smb(
                    device_ip=ip_scanner,
                    username=DEFAULT_USERNAME,
                    password=DEFAULT_PASSWORD,
                    folder=DEFAULT_SCAN_FOLDER,
                    share_name=DEFAULT_SHARE_NAME,
                    logger=logger,
                )
            else:
                scan_config = configure_windows_for_ftp(
                    device_ip=ip_scanner,
                    username=DEFAULT_USERNAME,
                    password=DEFAULT_PASSWORD,
                    folder=DEFAULT_SCAN_FOLDER,
                    logger=logger,
                )

            defender_result = None
            if defender_exclusion_requested:
                try:
                    defender_result = configure_defender_trust(
                        scan_folder=DEFAULT_SCAN_FOLDER,
                        logger=logger,
                        include_executable=True,
                    )
                except Exception as e:
                    logger.error(
                        f"Konfiguracja wykluczeń Defendera nie powiodła się: {e} "
                        f"— kontynuuję resztę konfiguracji."
                    )
                    defender_result = {
                        "defender_active": False,
                        "folder_excluded": False,
                        "exe_excluded": False,
                    }
            else:
                logger.info(
                    "Wykluczenie Windows Defender pominięte — opcja nie została "
                    "zaznaczona przez użytkownika."
                )

            ricoh_success = False
            ricoh_session = None
            # Ważne: puste hasło to WAŻNE hasło (wiele urządzeń Ricoh ma fabrycznie
            # ustawiony pusty ciąg jako hasło administratora) — próbujemy logowania
            # zawsze, dopóki podano login administratora, niezależnie od tego czy
            # pole hasła jest puste. Brakiem danych jest tylko pusty login.
            if admin_user:
                try:
                    logger.info(
                        f"Próba logowania do urządzenia Ricoh jako '{admin_user}' "
                        f"(hasło: {'puste' if not admin_pass else 'podane'})..."
                    )
                    ricoh_session = RicohSession(ip_scanner, admin_user, admin_pass, logger)
                    ricoh_session.login()

                    scan_share_path = scan_config.get("share") or scan_config.get("path", "/")
                    ricoh_success = ricoh_session.add_address_book_entry(
                        server=scan_config["server"],
                        path=scan_share_path,
                        username=scan_config["username"],
                        password=scan_config["password"],
                        protocol=scan_config["protocol"],
                        ftp_port=str(scan_config.get("port", 21)),
                    )
                    ricoh_session.add_trusted_ip(local_ip)

                    if not ricoh_success:
                        # Automatyczna konfiguracja nie trafiła w endpointy tego
                        # konkretnego modelu — zbieramy diagnostykę, żeby dobrać
                        # poprawne pola zamiast dalej zgadywać.
                        diag_path = os.path.join(
                            get_app_directory(), "ricoh_diagnostyka.txt"
                        )
                        run_diagnostics(ip_scanner, admin_user, admin_pass, logger, diag_path)
                except Exception as e:
                    logger.error(
                        f"Konfiguracja urządzenia Ricoh nie powiodła się: {e} "
                        f"— skonfiguruj książkę adresową ręcznie, używając danych z raportu."
                    )
                    ricoh_success = False
            else:
                logger.warning(
                    "Nie podano loginu administratora Ricoh — pomijam automatyczne "
                    "dodanie wpisu w książce adresowej. Skonfiguruj go ręcznie, "
                    "używając danych z raportu poniżej."
                )

            # ── Testy weryfikacyjne po zakończeniu konfiguracji ──
            check_results = run_post_configuration_checks(
                protocol=protocol,
                folder=DEFAULT_SCAN_FOLDER,
                local_ip=local_ip,
                device_ip=ip_scanner,
                ricoh_session=ricoh_session,
                address_book_added=ricoh_success,
                logger=logger,
            )

            logger.section("KONFIGURACJA ZAKOŃCZONA")

            report = self._build_report(scan_config, ip_scanner, local_ip,
                                         ricoh_success, check_results, defender_result)
            logger.info(f"\nPełny log zapisany w: {logger.get_log_path()}")

            self.signals.finished.emit(True, report, check_results)

        except Exception as e:
            self.logger.error(f"Nieoczekiwany błąd: {e}")
            self.signals.finished.emit(False, str(e), [])

    @staticmethod
    def _build_report(scan_config: dict, ip_scanner: str, local_ip: str,
                       ricoh_success: bool, check_results: list = None,
                       defender_result: dict = None) -> str:
        lines = [
            f"=== RAPORT KONFIGURACJI ({scan_config['protocol'].upper()}) ===",
            "",
            f"Adres skanera:      {scan_config['path_display']}",
            f"Login:              {scan_config['username']}",
            f"Hasło:              {scan_config['password']}",
            "",
            f"IP komputera:       {local_ip}",
            f"IP kserokopiarki:   {ip_scanner}",
            "",
            "Wpis w książce adresowej Ricoh: "
            + ("dodany automatycznie ✔" if ricoh_success
               else "wymaga ręcznej konfiguracji — użyj danych powyżej"),
        ]

        if defender_result is not None:
            lines.append("")
            if not defender_result.get("defender_active"):
                lines.append("Windows Defender: nieaktywny — wykluczenia pominięte")
            else:
                folder_status = "✔" if defender_result.get("folder_excluded") else "✖"
                exe_status = "✔" if defender_result.get("exe_excluded") else "✖"
                lines.append(f"Wykluczenie folderu skanów (Defender): {folder_status}")
                lines.append(f"Wykluczenie programu (Defender):      {exe_status}")

        if check_results:
            lines.append("")
            lines.append("=== WYNIKI WERYFIKACJI ===")
            for r in check_results:
                lines.append(r.as_line())

        return "\n".join(lines)

    def _on_finished(self, success: bool, report: str, check_results: list):
        self.btn_configure.setEnabled(True)
        self.progress_bar.setVisible(False)

        if success:
            QApplication.clipboard().setText(report)

            # Raport tekstowy (bez sekcji statusów - te idą kolorowo osobno)
            report_without_checks = report.split("=== WYNIKI WERYFIKACJI ===")[0].rstrip()
            self.log_output.append("\n" + report_without_checks)

            if check_results:
                self._append_check_results(check_results)

            failed_count = sum(1 for r in check_results if r.status == CheckStatus.FAIL)
            manual_count = sum(1 for r in check_results if r.status == CheckStatus.MANUAL)

            summary = "✔ Konfiguracja zakończona.\n✔ Dane skopiowane do schowka."
            if failed_count:
                summary += f"\n\n⚠ {failed_count} test(y) weryfikacyjne nie przeszły — sprawdź log."
            if manual_count:
                summary += f"\n⚠ {manual_count} krok(i) wymaga ręcznego potwierdzenia."

            QMessageBox.information(self, "Gotowe", summary)
        else:
            QMessageBox.critical(self, "Błąd konfiguracji", report)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
