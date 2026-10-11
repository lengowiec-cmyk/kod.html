import logging
import sys

from pdfmanager.logging_setup import configure_logging, get_logger, log_file_path


def test_log_dir_and_file_path_are_consistent(qapp):
    path = log_file_path()
    assert path.name == "log.txt"
    assert path.parent.name == "logs"


def test_configure_logging_creates_file_and_writes_startup_line(qapp):
    original_handlers = list(logging.getLogger().handlers)
    original_excepthook = sys.excepthook
    try:
        configure_logging()
        path = log_file_path()
        assert path.is_file()

        logger = get_logger("test")
        logger.info("komunikat testowy XYZ")
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = path.read_text(encoding="utf-8")
        assert "komunikat testowy XYZ" in content
        assert "Uruchomienie aplikacji" in content
    finally:
        # posprzataj, zeby nie zanieczyscic innych testow w tej samej sesji
        for handler in list(logging.getLogger().handlers):
            if handler not in original_handlers:
                logging.getLogger().removeHandler(handler)
                handler.close()
        sys.excepthook = original_excepthook


def test_uncaught_exception_hook_logs_to_file(qapp):
    original_handlers = list(logging.getLogger().handlers)
    original_excepthook = sys.excepthook
    try:
        configure_logging()
        path = log_file_path()
        try:
            raise ValueError("błąd testowy ABC")
        except ValueError:
            exc_type, exc_value, exc_tb = sys.exc_info()
            sys.excepthook(exc_type, exc_value, exc_tb)
        for handler in logging.getLogger().handlers:
            handler.flush()
        content = path.read_text(encoding="utf-8")
        assert "błąd testowy ABC" in content
        assert "CRITICAL" in content
    finally:
        for handler in list(logging.getLogger().handlers):
            if handler not in original_handlers:
                logging.getLogger().removeHandler(handler)
                handler.close()
        sys.excepthook = original_excepthook
