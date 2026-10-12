from pathlib import Path

import pymupdf
import pytest

from pdfmanager.pdf_engine.text_edit import PyMuPDFTextEditBackend
from pdfmanager.proofreading.language_tool_client import ProofreadingIssue
from pdfmanager.proofreading.workflow import check_document, check_page


class _FakeClient:
    def __init__(self, issues: list[ProofreadingIssue]) -> None:
        self._issues = issues
        self.calls: list[tuple[str, str]] = []

    def check(self, text: str, language: str) -> list[ProofreadingIssue]:
        self.calls.append((text, language))
        return self._issues


@pytest.fixture
def engine() -> PyMuPDFTextEditBackend:
    return PyMuPDFTextEditBackend()


def _issue(offset: int, length: int, replacement: str) -> ProofreadingIssue:
    return ProofreadingIssue(
        offset=offset,
        length=length,
        message="msg",
        short_message="msg",
        replacements=(replacement,),
        rule_id="RULE",
        category="CAT",
    )


def test_single_span_suggestion_maps_correctly(tmp_path, engine):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Zrobilem bląd w tekscie", fontname="helv", fontsize=12)
    path = tmp_path / "doc.pdf"
    doc.save(str(path))
    doc.close()

    # "Zrobilem bląd..." -> "bląd" zaczyna się po "Zrobilem " (9 znaków)
    client = _FakeClient([_issue(9, 4, "błąd")])
    suggestions = check_page(client, "pl-PL", engine, path, 0)

    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.page_index == 0
    assert suggestion.suggested_text == "Zrobilem błąd w tekscie"
    assert client.calls[0][1] == "pl-PL"


def test_issue_in_second_span_maps_to_correct_span(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "First line", fontname="helv", fontsize=12)
    page.insert_text((72, 120), "Secnd line", fontname="helv", fontsize=12)
    path = tmp_path / "doc.pdf"
    doc.save(str(path))
    doc.close()

    spans = engine.extract_spans(path, 0)
    assert [s.text for s in spans] == ["First line", "Secnd line"]

    # "First line " (11 znaków z separatorem) + "Secnd" zaczyna się na offsecie 11
    second_span_start = len("First line") + 1
    client = _FakeClient([_issue(second_span_start, 5, "Second")])
    suggestions = check_page(client, "en-US", engine, path, 0)

    assert len(suggestions) == 1
    assert suggestions[0].span.text == "Secnd line"
    assert suggestions[0].suggested_text == "Second line"


def test_issue_crossing_span_boundary_is_skipped(tmp_path, engine):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "First line", fontname="helv", fontsize=12)
    page.insert_text((72, 120), "Second line", fontname="helv", fontsize=12)
    path = tmp_path / "doc.pdf"
    doc.save(str(path))
    doc.close()

    # Zakres obejmujący koniec pierwszego fragmentu i separator -> poza granicami fragmentu.
    client = _FakeClient([_issue(len("First line") - 2, 6, "XYZ")])
    suggestions = check_page(client, "en-US", engine, path, 0)
    assert suggestions == []


def test_issue_without_replacements_is_skipped(tmp_path, engine):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Some text here", fontname="helv", fontsize=12)
    path = tmp_path / "doc.pdf"
    doc.save(str(path))
    doc.close()

    issue_no_replacement = ProofreadingIssue(
        offset=0, length=4, message="m", short_message="m", replacements=(), rule_id="R", category="C"
    )
    client = _FakeClient([issue_no_replacement])
    assert check_page(client, "en-US", engine, path, 0) == []


def test_empty_page_returns_no_suggestions_without_calling_client(tmp_path, engine):
    doc = pymupdf.open()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50))
    pix.set_rect(pix.irect, (0, 0, 0))
    page = doc.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 200, 200), pixmap=pix)
    path = tmp_path / "scanned.pdf"
    doc.save(str(path))
    doc.close()

    client = _FakeClient([_issue(0, 1, "x")])
    assert check_page(client, "en-US", engine, path, 0) == []
    assert client.calls == []


def test_check_document_aggregates_pages_with_correct_index(tmp_path, engine):
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 72), "Bład na stronie jeden", fontname="helv", fontsize=12)
    doc.new_page(width=595, height=842).insert_text((72, 72), "Bład na stronie dwa", fontname="helv", fontsize=12)
    path = tmp_path / "doc.pdf"
    doc.save(str(path))
    doc.close()

    client = _FakeClient([_issue(0, 5, "Błąd")])
    suggestions = check_document(client, "pl-PL", engine, path, page_count=2)

    assert [s.page_index for s in suggestions] == [0, 1]
    assert len(client.calls) == 2
