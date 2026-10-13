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
import hashlib,re,math,calendar

from PySide6.QtCore import QStandardPaths

from pdfmanager.licensing import secure_storage
from pdfmanager.licensing.license_key import LicenseKeyError, verify_license_key

TRIAL_DURATION_DAYS = 182  # zgodność ze starszymi zapisanymi okresami próbnymi
TRIAL_DURATION_MONTHS = 6
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
    CLOCK_ERROR = "clock_error"


@dataclass(frozen=True)
class LicenseStatus:
    state: LicenseState
    days_remaining: int
    expires_at: datetime
    reason: str = ""

    @property
    def is_blocked(self) -> bool:
        return self.state in (LicenseState.EXPIRED,LicenseState.REMOTE_BLOCKED,LicenseState.CLOCK_ERROR)

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

    @staticmethod
    def _date(value):
        result=datetime.fromisoformat(value)
        if result.tzinfo is None:result=result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)

    def _observed_now(self):
        now=self._date(self._now_fn().isoformat())
        path=self._trial_file.with_name(self._trial_file.name+'.clock')
        records=secure_storage.read_dual(REGISTRY_KEY_PATH,'clock',path)
        seen=[]
        for record in records:
            try:seen.append(self._date(record['seen']))
            except (KeyError,ValueError,TypeError):continue
        previous=max(seen) if seen else now
        rollback=now<previous-timedelta(minutes=5)
        observed=max(now,previous)
        data={'seen':observed.isoformat()}
        secure_storage.write_dual(REGISTRY_KEY_PATH,'clock',path,data)
        if data not in secure_storage.read_dual(REGISTRY_KEY_PATH,'clock',path):raise LicenseKeyError('Nie można zapisać stanu licencji. Sprawdź dostęp do danych aplikacji.')
        return observed,rollback

    def _ensure_trial_started(self,now=None):
        records=secure_storage.read_dual(REGISTRY_KEY_PATH,TRIAL_VALUE_NAME,self._trial_file)
        periods=[]
        for record in records:
            try:
                start=self._date(record['started_at'])
                expiry=self._date(record['expires_at']) if 'expires_at' in record else start+timedelta(days=TRIAL_DURATION_DAYS)
                periods.append((start,expiry))
            except (KeyError,ValueError,TypeError):continue
        if periods:
            started_at,expiry=min(periods,key=lambda value:value[0])
        else:
            started_at=now or self._date(self._now_fn().isoformat())
            if self._trial_file.exists():
                # A damaged existing record must never grant a fresh trial.
                expiry=started_at
            else:
                absolute=started_at.year*12+started_at.month-1+TRIAL_DURATION_MONTHS
                year,month=divmod(absolute,12);month+=1
                expiry=started_at.replace(year=year,month=month,day=min(started_at.day,calendar.monthrange(year,month)[1]))
        data={'started_at':started_at.isoformat(),'expires_at':expiry.isoformat()}
        secure_storage.write_dual(REGISTRY_KEY_PATH,TRIAL_VALUE_NAME,self._trial_file,data)
        if data not in secure_storage.read_dual(REGISTRY_KEY_PATH,TRIAL_VALUE_NAME,self._trial_file):raise LicenseKeyError('Nie można zachować daty pierwszego uruchomienia. Sprawdź dostęp do danych aplikacji.')
        return started_at,expiry

    def _read_active_license_expiry(self) -> datetime | None:
        records = secure_storage.read_dual(REGISTRY_KEY_PATH, LICENSE_VALUE_NAME, self._license_file)
        expiries = []
        for record in records:
            try:
                expiries.append(self._date(record["expires_at"]))
            except (KeyError, ValueError):
                continue
        return max(expiries) if expiries else None

    def activate(self, key_string: str) -> LicenseStatus:
        """Weryfikuje klucz i ustawia nową licencję liczoną od teraz.
        Zgłasza `LicenseKeyError`, jeśli klucz jest nieprawidłowy — stan
        pozostaje wtedy niezmieniony."""
        if not isinstance(key_string,str) or len(key_string)>8192:raise LicenseKeyError('Nieprawidłowy rozmiar kodu licencji.')
        now,rollback=self._observed_now()
        if rollback and not key_string.strip().startswith('PDMR1.'):raise LicenseKeyError('Wykryto cofnięcie zegara. Przywróć datę i użyj nowego kodu administratora.')
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
        if rollback:
            # Only an authenticated, installation-bound owner code can repair
            # the time watermark after a legitimate system-clock correction.
            now=self._date(self._now_fn().isoformat())
            secure_storage.write_dual(REGISTRY_KEY_PATH,'clock',self._trial_file.with_name(self._trial_file.name+'.clock'),{'seen':now.isoformat()})
        expires_at = now + timedelta(days=days)
        secure_storage.write_dual(
            REGISTRY_KEY_PATH, LICENSE_VALUE_NAME, self._license_file, {"expires_at": expires_at.isoformat()}
        )
        used.add(fingerprint)
        secure_storage.write_dual(REGISTRY_KEY_PATH,'used_keys',used_file,{'fingerprints':sorted(used)})
        from pdfmanager.remote.storage import load_config,RemoteState
        if load_config():RemoteState().release()
        return self.get_status()

    def get_status(self) -> LicenseStatus:
        now,rollback = self._observed_now()
        if rollback:return LicenseStatus(LicenseState.CLOCK_ERROR,0,now,'Wykryto cofnięcie zegara. Przywróć prawidłową datę i godzinę systemu Windows.')
        trial_started_at,trial_expiry = self._ensure_trial_started(now)
        from pdfmanager.remote.storage import load_config,RemoteState
        if load_config() and RemoteState().blocked():
            return LicenseStatus(LicenseState.REMOTE_BLOCKED,0,now)

        license_expiry = self._read_active_license_expiry()
        if license_expiry is not None:
            days_remaining = max(0, math.ceil((license_expiry-now).total_seconds()/86400))
            state = LicenseState.LICENSED if license_expiry > now else LicenseState.EXPIRED
            return LicenseStatus(state=state, days_remaining=days_remaining, expires_at=license_expiry)

        used_file=self._license_file.with_name(self._license_file.name+'.used')
        if self._license_file.exists() or any(r.get('fingerprints') for r in secure_storage.read_dual(REGISTRY_KEY_PATH,'used_keys',used_file)):
            return LicenseStatus(LicenseState.EXPIRED,0,now)
        days_remaining = max(0, math.ceil((trial_expiry-now).total_seconds()/86400))
        state = LicenseState.TRIAL if trial_expiry > now else LicenseState.EXPIRED
        return LicenseStatus(state=state, days_remaining=days_remaining, expires_at=trial_expiry)


def get_default_license_manager() -> LicenseManager:
    return LicenseManager()
