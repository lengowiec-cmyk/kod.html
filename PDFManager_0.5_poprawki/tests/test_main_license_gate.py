from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from pdfmanager.licensing.license_manager import LicenseManager, LicenseState,LicenseStatus
from pdfmanager.main import _run_license_gate


def _expired_manager(tmp_path) -> LicenseManager:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = {"now": start}
    manager = LicenseManager(
        trial_file=tmp_path / "trial.dat", license_file=tmp_path / "license.dat", now_fn=lambda: clock["now"]
    )
    manager.get_status()
    clock["now"] = start + timedelta(days=200)  # dawno po 182 dniach
    return manager


def test_gate_passes_through_when_not_blocked(qapp, tmp_path):
    manager = LicenseManager(trial_file=tmp_path / "trial.dat", license_file=tmp_path / "license.dat")
    assert _run_license_gate(manager) is True


def test_gate_blocks_and_returns_false_when_user_quits(qapp, tmp_path):
    manager = _expired_manager(tmp_path)
    assert manager.get_status().state == LicenseState.EXPIRED

    with patch("pdfmanager.main.ActivationDialog") as mock_dialog_cls:
        instance = mock_dialog_cls.return_value
        instance.exec.return_value = instance.DialogCode.Rejected
        result = _run_license_gate(manager)

    assert result is False
    mock_dialog_cls.assert_called_once()
    _, kwargs = mock_dialog_cls.call_args
    assert kwargs["allow_cancel"] is False


def test_gate_returns_true_when_activation_accepted(qapp, tmp_path):
    manager = _expired_manager(tmp_path)

    with patch("pdfmanager.main.ActivationDialog") as mock_dialog_cls:
        instance = mock_dialog_cls.return_value
        instance.exec.return_value = instance.DialogCode.Accepted
        expired=manager.get_status()
        valid=LicenseStatus(LicenseState.LICENSED,30,expired.expires_at+timedelta(days=30))
        with patch.object(manager,'get_status',side_effect=[expired,valid]):result = _run_license_gate(manager)

    assert result is True
