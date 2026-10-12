"""Warstwa UI automatycznego importu skanów — dotąd bez testów (patrz audyt 0.5).

Test koordynacji (`poll`) podmienia `process_scans` na kontrolowaną atrapę:
chcemy sprawdzić logikę ScanAutomation (StableFiles + `failed_stamps` chroniące
przed ponownym importem znanego błędnego pliku), a nie samo `process_scans`
(ma już osobne, szczegółowe testy w test_productivity.py).

Worker uruchomiony przez `poll()` jest prawdziwym QThread, więc test musi
poczekać na jego sygnał `finished` przez realną pętlę zdarzeń (`QTest.qWait`,
nie `time.sleep`) i wywołać `automation.stop()` przed zamknięciem okna —
tak samo jak robi to `MainWindow.closeEvent` w produkcji. Zamknięcie okna
z wciąż "żywym" (niezatrzymanym i nieprzetworzonym) workerem jako dzieckiem
Qt prowadzi do segfaultu przy sprzątaniu obiektów.
"""
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow
from PySide6.QtTest import QTest
import pdfmanager.ui.scan_automation as scan_automation_module
from pdfmanager.dms.preferences import Preferences
from pdfmanager.ui.scan_automation import ScanAutomation


def _wait_for_worker(automation, timeout_ms=5000, step_ms=25):
    waited = 0
    while automation.worker is not None and waited < timeout_ms:
        QTest.qWait(step_ms)
        waited += step_ms
    assert automation.worker is None, 'Worker nie zakończył się w oczekiwanym czasie.'


def _isolated_automation(tmp_path, window):
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat)
    automation = ScanAutomation(window)
    automation.prefs = Preferences(settings)
    return automation


def test_vendor_reuses_saved_path_without_reprompting(qapp, tmp_path):
    window = QMainWindow()
    automation = _isolated_automation(tmp_path, window)
    executable = tmp_path / 'scanner.exe'
    executable.write_text('nie jest to prawdziwy plik wykonywalny')
    automation.prefs.put('scanner_application', str(executable))
    with patch.object(scan_automation_module, 'QFileDialog') as dialog, \
         patch.object(scan_automation_module, 'QMessageBox') as message_box:
        automation.vendor()
        dialog.getOpenFileName.assert_not_called()
        # plik nie jest uruchamialny na tej maszynie -> ostrzeżenie, nie cisza/awaria
        message_box.warning.assert_called_once()
    window.close()


def test_vendor_prompts_and_saves_path_when_none_configured(qapp, tmp_path):
    window = QMainWindow()
    automation = _isolated_automation(tmp_path, window)
    executable = tmp_path / 'chosen.exe'
    executable.write_text('x')
    with patch.object(scan_automation_module, 'QFileDialog') as dialog, \
         patch.object(scan_automation_module, 'QMessageBox'):
        dialog.getOpenFileName.return_value = (str(executable), '')
        automation.vendor()
        dialog.getOpenFileName.assert_called_once()
    assert automation.prefs.get('scanner_application', '') == str(executable)
    window.close()


def test_poll_skips_known_failed_file_until_it_changes(qapp, tmp_path, monkeypatch):
    window = QMainWindow()
    automation = _isolated_automation(tmp_path, window)
    input_dir = tmp_path / 'in'; input_dir.mkdir()
    output_dir = tmp_path / 'out'; output_dir.mkdir()
    automation.config = {
        'input': str(input_dir), 'output': str(output_dir),
        'pattern': '{source}_{counter}', 'ocr': False, 'language': 'pol',
    }

    broken = input_dir / 'broken.png'
    broken.write_bytes(b'placeholder')

    calls = []
    def failing(paths, destination, *, pattern, ocr, language, ledger=None):
        calls.append(list(paths))
        return [(p, 'error', 'symulowany błąd dekodowania') for p in paths]
    monkeypatch.setattr(scan_automation_module, 'process_scans', failing)

    # StableFiles wymaga kilku identycznych odczytów rozmiaru/mtime z rzędu,
    # zanim uzna plik za "stabilny" i gotowy do importu.
    for _ in range(10):
        automation.poll()
        if automation.worker is not None:
            break
    _wait_for_worker(automation)
    assert broken in automation.failed_stamps
    assert len(calls) == 1

    # Plik niezmieniony i znany jako błędny -> kolejne przebiegi nie ponawiają importu.
    for _ in range(5):
        automation.poll()
        _wait_for_worker(automation)
    assert len(calls) == 1

    # Dopiero nowy plik (inna zawartość) odblokowuje import.
    ok = input_dir / 'ok.png'
    ok.write_bytes(b'inna-zawartosc')

    def succeeding(paths, destination, *, pattern, ocr, language, ledger=None):
        calls.append(list(paths))
        return [(p, 'ok', Path(destination) / 'wynik.pdf') for p in paths]
    monkeypatch.setattr(scan_automation_module, 'process_scans', succeeding)

    for _ in range(10):
        automation.poll()
        if automation.worker is not None:
            break
    _wait_for_worker(automation)
    assert len(calls) == 2
    assert calls[-1] == [ok]
    automation.stop()
    window.close()
