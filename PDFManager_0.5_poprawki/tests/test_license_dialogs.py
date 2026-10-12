from datetime import datetime, timezone
from unittest.mock import patch

from pdfmanager.licensing.license_key import generate_license_key, load_private_key_for_signing
from pdfmanager.licensing.license_key import PUBLIC_KEY_PATH
from pdfmanager.licensing.license_manager import LicenseManager, LicenseState
from pdfmanager.ui.license_dialogs import ActivationDialog, ExpiryWarningDialog


def _manager(tmp_path) -> LicenseManager:
    return LicenseManager(
        trial_file=tmp_path / "trial.dat",
        license_file=tmp_path / "license.dat",
        now_fn=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_activation_dialog_accepts_valid_key(qapp, tmp_path, test_signing_key):
    manager = _manager(tmp_path)
    dialog = ActivationDialog(manager)
    key = generate_license_key(test_signing_key, 6)
    dialog._key_edit.setPlainText(key)

    with patch("pdfmanager.ui.license_dialogs.QMessageBox.information"):
        dialog._on_activate()

    assert manager.get_status().state == LicenseState.LICENSED


def test_activation_dialog_rejects_invalid_key(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = ActivationDialog(manager)
    dialog._key_edit.setPlainText("to-jest-nieprawidlowy-klucz")

    with patch("pdfmanager.ui.license_dialogs.QMessageBox.critical") as mock_critical:
        dialog._on_activate()
        mock_critical.assert_called_once()

    assert manager.get_status().state == LicenseState.TRIAL


def test_activation_dialog_cancel_closes_without_activating(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = ActivationDialog(manager, allow_cancel=True)
    dialog._cancel_button.click()
    assert dialog.result() == dialog.DialogCode.Rejected


def test_activation_dialog_no_cancel_quits_application_instead(qapp, tmp_path):
    manager = _manager(tmp_path)
    dialog = ActivationDialog(manager, allow_cancel=False)

    with patch.object(qapp, "quit") as mock_quit:
        dialog._cancel_button.click()
        mock_quit.assert_called_once()


def test_expiry_warning_remind_later_does_not_set_flag(qapp):
    dialog = ExpiryWarningDialog(days_remaining=5)
    dialog._remind_later_button.click()
    assert dialog.enter_key_requested is False


def test_expiry_warning_enter_key_sets_flag(qapp):
    dialog = ExpiryWarningDialog(days_remaining=5)
    dialog._enter_key_button.click()
    assert dialog.enter_key_requested is True
