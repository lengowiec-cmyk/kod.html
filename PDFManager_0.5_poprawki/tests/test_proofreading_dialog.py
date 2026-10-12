from pathlib import Path
from unittest.mock import patch

import pymupdf
from PySide6.QtCore import Qt

from pdfmanager.pdf_engine.text_edit import PyMuPDFTextEditBackend
from pdfmanager.proofreading.workflow import ProofreadingSuggestion
from pdfmanager.proofreading.language_tool_client import ProofreadingIssue
from pdfmanager.ui.proofreading_dialog import ProofreadingDialog


def _make_pdf(path: Path, text: str = "Zrobilem bląd w tekscie") -> Path:
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), text, fontname="helv", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def _real_suggestion(path: Path) -> ProofreadingSuggestion:
    engine = PyMuPDFTextEditBackend()
    span = engine.extract_spans(path, 0)[0]
    issue = ProofreadingIssue(
        offset=9, length=4, message="Błąd pisowni", short_message="Błąd pisowni",
        replacements=("błąd",), rule_id="R", category="C",
    )
    return ProofreadingSuggestion(page_index=0, span=span, issue=issue, suggested_text="Zrobilem błąd w tekscie")


def test_check_without_consent_shows_warning_and_does_not_call_service(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf")
    dialog = ProofreadingDialog(path, page_count=1)

    with patch("pdfmanager.ui.proofreading_dialog.check_document") as mock_check, \
         patch("pdfmanager.ui.proofreading_dialog.QMessageBox.warning") as mock_warning:
        dialog._run_check()
        mock_check.assert_not_called()
        mock_warning.assert_called_once()


def test_check_with_consent_populates_results(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf")
    dialog = ProofreadingDialog(path, page_count=1)
    dialog._consent_checkbox.setChecked(True)

    suggestion = _real_suggestion(path)
    with patch("pdfmanager.ui.proofreading_dialog.check_document", return_value=[suggestion]):
        dialog._run_check()

    assert dialog._stack.currentWidget() is dialog._results_page
    assert dialog._results_list.count() == 1
    item = dialog._results_list.item(0)
    assert item.checkState() == Qt.CheckState.Checked
    assert item.data(Qt.ItemDataRole.UserRole) is suggestion


def test_no_suggestions_shows_placeholder_message(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf")
    dialog = ProofreadingDialog(path, page_count=1)
    dialog._consent_checkbox.setChecked(True)

    with patch("pdfmanager.ui.proofreading_dialog.check_document", return_value=[]):
        dialog._run_check()

    assert dialog._results_list.count() == 1
    assert dialog._results_list.item(0).flags() == Qt.ItemFlag.NoItemFlags


def test_apply_selected_writes_correction_to_file(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf")
    dialog = ProofreadingDialog(path, page_count=1)
    dialog._consent_checkbox.setChecked(True)

    suggestion = _real_suggestion(path)
    with patch("pdfmanager.ui.proofreading_dialog.check_document", return_value=[suggestion]):
        dialog._run_check()

    with patch("pdfmanager.ui.proofreading_dialog.QMessageBox.information") as mock_info, \
         patch("pdfmanager.ui.proofreading_dialog.QMessageBox.warning"):
        # "helv" nie jest osadzoną czcionką -> apply_edit zgłosi ostrzeżenie
        # o foncie zastępczym; to nie jest przedmiotem tego testu.
        dialog._apply_selected()
        mock_info.assert_called_once()

    final_text = pymupdf.open(str(path))[0].get_text()
    assert "Zrobilem błąd w tekscie" in final_text


def test_unchecked_suggestion_is_not_applied(qapp, tmp_path):
    path = _make_pdf(tmp_path / "doc.pdf")
    original_text = pymupdf.open(str(path))[0].get_text()
    dialog = ProofreadingDialog(path, page_count=1)
    dialog._consent_checkbox.setChecked(True)

    suggestion = _real_suggestion(path)
    with patch("pdfmanager.ui.proofreading_dialog.check_document", return_value=[suggestion]):
        dialog._run_check()

    dialog._results_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    with patch("pdfmanager.ui.proofreading_dialog.QMessageBox.information"), \
         patch("pdfmanager.ui.proofreading_dialog.QMessageBox.warning"):
        dialog._apply_selected()

    final_text = pymupdf.open(str(path))[0].get_text()
    assert final_text == original_text  # oryginał bez zmian (sugestia odznaczona)
