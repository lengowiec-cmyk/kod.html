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
import hashlib,re

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
    REMOTE_BLOCKED = "remote_blocked"


@dataclass(frozen=True)
class LicenseStatus:
    state: LicenseState
    days_remaining: int
    expires_at: datetime

    @property
    def is_blocked(self) -> bool:
        return self.state in (LicenseState.EXPIRED,LicenseState.REMOTE_BLOCKED)

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
        cleaned=re.sub(r'\s+','',key_string).strip()
        fingerprint=hashlib.sha256(cleaned.encode()).hexdigest() if cleaned.startswith('PDMR1.') else hashlib.sha256(cleaned.upper().replace('-','').encode()).hexdigest()
        used_file=self._license_file.with_name(self._license_file.name+'.used')
        records=secure_storage.read_dual(REGISTRY_KEY_PATH,'used_keys',used_file)
        used=set(value for record in records for value in record.get('fingerprints',[]))
        if fingerprint in used:raise LicenseKeyError('Ten kod został już wykorzystany na tej instalacji.')
        from pdfmanager.remote.storage import load_config,RemoteState
        if not cleaned.startswith('PDMR1.') and load_config() and RemoteState().blocked():raise LicenseKeyError('Zdalna blokada wymaga nowego kodu dla tej instalacji z programu administratora.')
        if cleaned.startswith('PDMR1.'):
            from pdfmanager.remote.storage import load_config,RemoteState
            from pdfmanager.remote.protocol import verify_activation
            try:
                config=load_config()
                if not config:raise ValueError('Instalacja nie ma konfiguracji administratora.')
                payload=verify_activation(cleaned,config,RemoteState().device(),now=self._now_fn().timestamp());days=payload['days']
            except Exception as exc:raise LicenseKeyError('Nieprawidłowy, wygasły lub przeznaczony dla innej instalacji kod administratora.') from exc
        else:days=DAYS_PER_MONTH*verify_license_key(cleaned).months
        expires_at = self._now_fn() + timedelta(days=days)
        secure_storage.write_dual(
            REGISTRY_KEY_PATH, LICENSE_VALUE_NAME, self._license_file, {"expires_at": expires_at.isoformat()}
        )
        used.add(fingerprint)
        secure_storage.write_dual(REGISTRY_KEY_PATH,'used_keys',used_file,{'fingerprints':sorted(used)})
        from pdfmanager.remote.storage import load_config,RemoteState
        if load_config():RemoteState().release()
        return self.get_status()

    def get_status(self) -> LicenseStatus:
        now = self._now_fn()
        from pdfmanager.remote.storage import load_config,RemoteState
        if load_config() and RemoteState().blocked():
            return LicenseStatus(LicenseState.REMOTE_BLOCKED,0,now)

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
