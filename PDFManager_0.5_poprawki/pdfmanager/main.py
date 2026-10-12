"""Punkt wejścia aplikacji Menedżer PDF."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from pdfmanager.app_settings import settings
from pdfmanager.i18n.translator import translator
from pdfmanager.licensing.license_manager import get_default_license_manager
from pdfmanager.logging_setup import configure_logging, get_logger
from pdfmanager.ui.license_dialogs import ActivationDialog
from pdfmanager.ui.main_window import APP_ICON_PATH, MainWindow
from pdfmanager.ui.theme import apply_theme


def _run_license_gate(license_manager) -> bool:
    """Sprawdzenie licencji PRZED pokazaniem głównego okna. Zwraca True,
    jeśli program może kontynuować; False, jeśli okres próbny/licencja
    wygasły i użytkownik zdecydował się zakończyć aplikację z okna
    blokady, nie wprowadzając klucza aktywacyjnego."""
    status = license_manager.get_status()
    if not status.is_blocked:
        return True
    dialog = ActivationDialog(license_manager, allow_cancel=False, message_key="license.blocked_message")
    from pdfmanager.licensing.license_manager import LicenseState
    if status.state==LicenseState.REMOTE_BLOCKED:
        from pdfmanager.remote.storage import RemoteState
        dialog._message_label.setText('Dostęp został zablokowany przez administratora. Wpisz nowy kod dostępu.\n'+RemoteState().read().get('reason',''))
    return dialog.exec() == dialog.DialogCode.Accepted


def main() -> int:
    if len(sys.argv)>2 and sys.argv[1]=='--pdf-worker':
        from pdfmanager.security.worker import main as worker_main
        return worker_main(sys.argv[2])
    if len(sys.argv)>1 and sys.argv[1].startswith('--'):
        from pdfmanager.cli import main as cli_main
        option=sys.argv[1][2:]
        return cli_main(['--help'] if option=='help' else [option,*sys.argv[2:]])
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import Qt
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setOrganizationName("PDFManager")
    app.setApplicationName("PDFManager")

    # Jak najwcześniej — zanim cokolwiek innego mogłoby zgłosić wyjątek —
    # żeby ewentualna awaria była widoczna w log.txt, a nie "znikała" bez
    # śladu (wersja .exe nie ma okna konsoli).
    configure_logging()
    logger = get_logger("main")
    logger.info("Wersja jezyka ustawien: %s, motyw: %s", settings.language, settings.theme)

    if APP_ICON_PATH.is_file():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    translator.set_language(settings.language)
    apply_theme(app, settings.theme)

    from pdfmanager.remote.client import sync_once
    sync_once()
    license_manager = get_default_license_manager()
    if not _run_license_gate(license_manager):
        return 0

    window = MainWindow(license_manager=license_manager)
    geometry = settings.window_geometry()
    if geometry is not None:
        window.restoreGeometry(geometry)
    window.show()

    # Ostrzeżenie o kończącej się licencji — sprawdzane przy KAŻDYM
    # uruchomieniu (a potem raz na dobę, patrz QTimer w MainWindow).
    window._check_license_and_warn()

    # Argumenty wiersza poleceń (ścieżki do plików PDF) — Windows przekazuje
    # je tak przy otwarciu pliku z Eksploratora (skojarzenie z PDF, Etap 6).
    # `resolve()` na wszelki wypadek, gdyby ścieżka była względna.
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".pdf"):
            window.open_document(str(Path(arg).resolve()))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
