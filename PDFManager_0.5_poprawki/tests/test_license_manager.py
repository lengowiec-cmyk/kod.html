from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pdfmanager.licensing import secure_storage
from pdfmanager.licensing.license_key import LicenseKeyError, generate_license_key, load_private_key_for_signing
from pdfmanager.licensing.license_manager import LicenseManager, LicenseState
from tests.conftest import FakeWinReg

PRIVATE_KEY_PATH = None  # ustawione w fixture


@pytest.fixture
def private_key(test_signing_key):
    return test_signing_key


@pytest.fixture
def fake_registry():
    fake = FakeWinReg()
    with patch.object(secure_storage, "_registry", fake):
        yield fake


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, days: int) -> None:
        self.now += timedelta(days=days)


@pytest.fixture
def clock():
    return _Clock(datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def manager(fake_registry, tmp_path, clock):
    return LicenseManager(trial_file=tmp_path / "trial.dat", license_file=tmp_path / "license.dat", now_fn=clock)


def test_first_run_starts_full_trial(manager):
    status = manager.get_status()
    assert status.state == LicenseState.TRIAL
    assert status.days_remaining == 181
    assert status.is_blocked is False
    assert status.is_near_expiry is False


def test_trial_days_remaining_decreases_over_time(manager, clock):
    manager.get_status()  # uruchamia okres próbny
    clock.advance(170)
    status = manager.get_status()
    assert status.state == LicenseState.TRIAL
    assert status.days_remaining == 11


def test_trial_does_not_reset_on_repeated_checks(manager, clock):
    manager.get_status()
    clock.advance(100)
    manager.get_status()
    clock.advance(100)
    status = manager.get_status()
    # 200 dni od startu, nie 100 - drugi get_status() nie zrestartował licznika.
    assert status.days_remaining == 0
    assert status.state == LicenseState.EXPIRED


def test_trial_expires_after_six_calendar_months(manager, clock):
    manager.get_status()
    clock.advance(183)
    status = manager.get_status()
    assert status.state == LicenseState.EXPIRED
    assert status.days_remaining == 0
    assert status.is_blocked is True


def test_trial_near_expiry_flag(manager, clock):
    manager.get_status()
    clock.advance(176)  # zostaje 6 dni
    status = manager.get_status()
    assert status.days_remaining == 5
    assert status.is_near_expiry is True
    assert status.is_blocked is False


def test_trial_survives_loss_of_one_storage_location(manager, clock, fake_registry, tmp_path):
    manager.get_status()
    clock.advance(50)

    fake_registry.keys.clear()  # symuluje odinstalowanie/wyczyszczenie rejestru

    status = manager.get_status()
    # Plik przetrwał z oryginalną datą startu - licznik NIE wraca do 182.
    assert status.days_remaining == 181 - 50


def test_activate_with_valid_key_switches_to_licensed(manager, private_key):
    key = generate_license_key(private_key, 6)
    status = manager.activate(key)
    assert status.state == LicenseState.LICENSED
    assert status.days_remaining == 180  # 30 * 6


def test_activate_with_invalid_key_raises_and_leaves_state_unchanged(manager):
    before = manager.get_status()
    with pytest.raises(LicenseKeyError):
        manager.activate("klucz-ewidentnie-nieprawidlowy")
    after = manager.get_status()
    assert after.state == before.state
    assert after.days_remaining == before.days_remaining


def test_activated_license_expires_independently_of_trial(manager, private_key, clock):
    key = generate_license_key(private_key, 3)
    manager.activate(key)
    clock.advance(91)  # ponad 3*30 dni
    status = manager.get_status()
    assert status.state == LicenseState.EXPIRED
    assert status.days_remaining == 0


def test_reactivating_replaces_previous_license(manager, private_key, clock):
    manager.activate(generate_license_key(private_key, 3))
    clock.advance(10)
    manager.activate(generate_license_key(private_key, 24))
    status = manager.get_status()
    assert status.days_remaining == 30 * 24 - 0  # liczone od teraz, nie dodane do starej
