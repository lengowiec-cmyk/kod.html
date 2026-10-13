"""
Zarządzanie wykluczeniami Windows Defender.

WAŻNE — zasady działania tego modułu:
- Wszystkie funkcje wymagają uprawnień administratora (tak samo jak
  reszta konfiguracji systemu w tej aplikacji).
- Wykonywane są WYŁĄCZNIE oficjalnym, udokumentowanym mechanizmem
  PowerShell (Add-MpPreference / Get-MpPreference) — dokładnie tym
  samym, którego używają narzędzia administracyjne IT do zarządzania
  Defenderem w środowiskach firmowych. Nic nie jest wyłączane ani
  ukrywane — dodawany jest tylko konkretny plik/folder do listy
  wykluczeń skanowania w czasie rzeczywistym.
- Funkcja NIGDY nie jest wywoływana automatycznie/w tle bez wiedzy
  użytkownika — w GUI odpowiada jej jawny checkbox z opisem, co dokładnie
  zostanie zmienione, zaznaczany świadomie przez osobę obsługującą program.
- Nic tu nie wyłącza Defendera, nie ukrywa działania programu przed
  systemem antywirusowym w sposób inny niż standardowe wykluczenie ścieżki,
  i nie ingeruje w żadne inne aplikacje ani pliki poza wskazanymi.
"""

import sys

from .system_utils import run_powershell


def get_current_executable_path() -> str:
    """
    Ścieżka do aktualnie uruchomionego pliku wykonywalnego.
    - Po spakowaniu przez PyInstaller (sys.frozen=True): zwraca ścieżkę do
      samego pliku .exe — to jest poprawny cel dla -ExclusionProcess.
    - Uruchomione jako skrypt .py: zwraca None, bo wykluczenie procesu
      python.exe byłoby zbyt szerokie (wykluczyłoby WSZYSTKIE skrypty
      Pythona uruchamiane w systemie, nie tylko ten program) — w tym
      trybie krok wykluczenia procesu jest pomijany.
    """
    if getattr(sys, "frozen", False):
        return sys.executable
    return None


def is_defender_active(logger=None) -> bool:
    """Sprawdza, czy usługa Windows Defender w ogóle działa na tym komputerze
    (może być wyłączona/zastąpiona innym antywirusem — wtedy wykluczenie nie ma sensu)."""
    out = run_powershell(
        "(Get-Service -Name WinDefend -ErrorAction SilentlyContinue).Status",
        timeout=15
    )
    active = "running" in out.lower()
    if logger:
        logger.info(
            f"Windows Defender: {'aktywny' if active else 'nieaktywny lub zastąpiony innym AV'}"
        )
    return active


def add_defender_exclusion(path: str, logger, is_folder: bool = False) -> bool:
    """
    Dodaje pojedynczą ścieżkę (plik lub folder) do wykluczeń skanowania
    Windows Defender przez oficjalne polecenie Add-MpPreference.
    Idempotentne — wielokrotne wywołanie z tą samą ścieżką nie tworzy duplikatów.
    """
    param = "-ExclusionPath" if is_folder or path.endswith("\\") else "-ExclusionPath"
    logger.info(f"Dodaję wykluczenie Defendera dla: {path}")
    out = run_powershell(
        f"Add-MpPreference {param} '{path}'",
        timeout=30
    )
    success = "[BŁĄD]" not in out and "[UWAGA]" not in out
    if success:
        logger.info(f"  ✔ Wykluczenie dodane: {path}")
    else:
        logger.warning(f"  Nie udało się dodać wykluczenia dla {path}: {out}")
    return success


def add_defender_exclusion_process(process_path: str, logger) -> bool:
    """
    Dodaje wykluczenie procesu (-ExclusionProcess) — zgodnie z dokumentacją
    Microsoftu, ten parametr wyklucza ze skanowania pliki OTWIERANE przez
    wskazany proces, a nie sam plik wykonywalny procesu. Dlatego dla realnej
    ochrony pliku EXE przed powtórnym skanowaniem przy starcie używamy
    OBU mechanizmów: ExclusionProcess (pliki otwierane w trakcie działania)
    oraz ExclusionPath (sam plik EXE jako taki).
    """
    logger.info(f"Dodaję wykluczenie procesu Defendera dla: {process_path}")
    out = run_powershell(
        f"Add-MpPreference -ExclusionProcess '{process_path}'",
        timeout=30
    )
    success = "[BŁĄD]" not in out and "[UWAGA]" not in out

    # Dodatkowo: wyklucz sam plik EXE przez ExclusionPath — to jest właściwy
    # mechanizm ochrony pliku przed skanowaniem przy każdym uruchomieniu.
    out2 = run_powershell(
        f"Add-MpPreference -ExclusionPath '{process_path}'",
        timeout=30
    )
    success = success and ("[BŁĄD]" not in out2 and "[UWAGA]" not in out2)

    if success:
        logger.info(f"  ✔ Wykluczenie procesu i pliku dodane: {process_path}")
    else:
        logger.warning(f"  Nie udało się dodać pełnego wykluczenia procesu: {out} {out2}")
    return success


def list_current_exclusions(logger=None) -> list[str]:
    """Zwraca aktualną listę wykluczonych ścieżek (do wglądu/weryfikacji)."""
    out = run_powershell("(Get-MpPreference).ExclusionPath -join ';'", timeout=15)
    if "[BŁĄD]" in out or "[UWAGA]" in out:
        return []
    paths = [p.strip() for p in out.split(";") if p.strip()]
    if logger:
        logger.info(f"Obecne wykluczenia Defendera: {len(paths)} pozycji")
    return paths


def configure_defender_trust(scan_folder: str, logger,
                              include_executable: bool = True) -> dict:
    """
    Główna funkcja wysokiego poziomu — wywoływana WYŁĄCZNIE po jawnym
    zaznaczeniu opcji przez użytkownika w GUI. Dodaje do wykluczeń:
    - folder skanów (żeby zapisywane tam pliki nie były opóźniane
      skanowaniem w czasie rzeczywistym przy każdym zapisie skanu),
    - plik wykonywalny programu (żeby sam konfigurator nie był
      poddawany powtórnej analizie przy każdym uruchomieniu).

    Zwraca słownik z wynikami każdego kroku — do pokazania w raporcie.
    """
    logger.section("Konfiguracja wykluczeń Windows Defender (na żądanie użytkownika)")

    if not is_defender_active(logger):
        logger.info(
            "Windows Defender nie jest aktywną usługą ochrony na tym komputerze — "
            "pomijam konfigurację wykluczeń (prawdopodobnie używany jest inny antywirus)."
        )
        return {"defender_active": False, "folder_excluded": False, "exe_excluded": False}

    folder_ok = add_defender_exclusion(scan_folder, logger, is_folder=True)

    exe_ok = False
    if include_executable:
        exe_path = get_current_executable_path()
        if exe_path:
            exe_ok = add_defender_exclusion_process(exe_path, logger)
        else:
            logger.info(
                "Uruchomiono jako skrypt .py (nie .exe) — pomijam wykluczenie "
                "procesu, żeby nie wykluczyć całego interpretera Pythona z ochrony."
            )

    return {
        "defender_active": True,
        "folder_excluded": folder_ok,
        "exe_excluded": exe_ok,
    }
