"""Zarządzanie stanem licencji: 6-miesięczny okres próbny od pierwszego
uruchomienia, aktywacja kluczem (3/6/12/24 miesiące), wyliczanie liczby
pozostałych dni. Patrz `secure_storage.py` i `license_key.py` dla
mechanizmów leżących pod spodem oraz ich uczciwie opisanych ograniczeń.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QStandardPaths

from pdfmanager.licensing import secure_storage
from pdfmanager.licensing.license_key import LicenseKeyError, verify_license_key

TRIAL_DURATION_DAYS = 182  # ~6 miesięcy
WARNING_THRESHOLD_DAYS = 7
DAYS_PER_MONTH = 30  # uproszczenie przyjęte dla okresów licencji (nie dni kalendarzowych)

REGISTRY_KEY_PATH = r"Software\PDFManager\License"
TRIAL_VALUE_NAME = "trial"
LICENSE_VALUE_NAME = "license"


def _default_state_file_path(name: str) -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = str(Path.home() / ".pdfmanager")
    return Path(base) / f".{name}_state"


class LicenseState(Enum):
    TRIAL = "trial"
    LICENSED = "licensed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class LicenseStatus:
    state: LicenseState
    days_remaining: int
    expires_at: datetime

    @property
    def is_blocked(self) -> bool:
        return self.state == LicenseState.EXPIRED

    @property
    def is_near_expiry(self) -> bool:
        return not self.is_blocked and self.days_remaining <= WARNING_THRESHOLD_DAYS


class LicenseManager:
    def __init__(
        self,
        trial_file: Path | None = None,
        license_file: Path | None = None,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._trial_file = Path(trial_file) if trial_file is not None else _default_state_file_path("trial")
        self._license_file = Path(license_file) if license_file is not None else _default_state_file_path("license")
        self._now_fn = now_fn

    def _ensure_trial_started(self) -> datetime:
        records = secure_storage.read_dual(REGISTRY_KEY_PATH, TRIAL_VALUE_NAME, self._trial_file)
        timestamps = []
        for record in records:
            try:
                timestamps.append(datetime.fromisoformat(record["started_at"]))
            except (KeyError, ValueError):
                continue

        # Najwcześniejsza znaleziona data wygrywa — to utrudnia reset próby
        # przez usunięcie/ponowne zainstalowanie jednej z dwóch kopii stanu.
        started_at = min(timestamps) if timestamps else self._now_fn()

        secure_storage.write_dual(
            REGISTRY_KEY_PATH, TRIAL_VALUE_NAME, self._trial_file, {"started_at": started_at.isoformat()}
        )
        return started_at

    def _read_active_license_expiry(self) -> datetime | None:
        records = secure_storage.read_dual(REGISTRY_KEY_PATH, LICENSE_VALUE_NAME, self._license_file)
        expiries = []
        for record in records:
            try:
                expiries.append(datetime.fromisoformat(record["expires_at"]))
            except (KeyError, ValueError):
                continue
        return max(expiries) if expiries else None

    def activate(self, key_string: str) -> LicenseStatus:
        """Weryfikuje klucz i ustawia nową licencję liczoną od teraz.
        Zgłasza `LicenseKeyError`, jeśli klucz jest nieprawidłowy — stan
        pozostaje wtedy niezmieniony."""
        payload = verify_license_key(key_string)
        expires_at = self._now_fn() + timedelta(days=DAYS_PER_MONTH * payload.months)
        secure_storage.write_dual(
            REGISTRY_KEY_PATH, LICENSE_VALUE_NAME, self._license_file, {"expires_at": expires_at.isoformat()}
        )
        return self.get_status()

    def get_status(self) -> LicenseStatus:
        now = self._now_fn()

        license_expiry = self._read_active_license_expiry()
        if license_expiry is not None:
            days_remaining = max(0, (license_expiry - now).days)
            state = LicenseState.LICENSED if license_expiry > now else LicenseState.EXPIRED
            return LicenseStatus(state=state, days_remaining=days_remaining, expires_at=license_expiry)

        trial_started_at = self._ensure_trial_started()
        trial_expiry = trial_started_at + timedelta(days=TRIAL_DURATION_DAYS)
        days_remaining = max(0, (trial_expiry - now).days)
        state = LicenseState.TRIAL if trial_expiry > now else LicenseState.EXPIRED
        return LicenseStatus(state=state, days_remaining=days_remaining, expires_at=trial_expiry)


def get_default_license_manager() -> LicenseManager:
    return LicenseManager()
