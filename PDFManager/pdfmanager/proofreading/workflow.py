"""Przepływ korekty językowej: PDF -> fragmenty tekstu -> LanguageTool ->
sugestie powiązane z konkretnym fragmentem PDF -> (po zatwierdzeniu przez
użytkownika) zastosowanie przez prawdziwy silnik edycji tekstu (Etap 2).

Nigdy nie modyfikuje dokumentu samodzielnie — zwraca tylko listę sugestii
do przeglądu. Zastosowanie każdej z nich wymaga wyraźnej akcji użytkownika
(patrz `ui/proofreading_dialog.py`) i przechodzi przez `TextEditEngine`,
więc dziedziczy te same ostrzeżenia o zachowaniu układu co zwykła edycja.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pdfmanager.pdf_engine.text_edit import TextEditEngine, TextSpan
from pdfmanager.proofreading.language_tool_client import LanguageToolClient, ProofreadingIssue

_SPAN_SEPARATOR = " "


@dataclass(frozen=True)
class ProofreadingSuggestion:
    page_index: int
    span: TextSpan
    issue: ProofreadingIssue
    suggested_text: str


def _build_flat_text(spans: list[TextSpan]) -> tuple[str, list[tuple[int, int]]]:
    """Zwraca (płaski tekst, lista (start, end) dla każdego fragmentu w `spans`)."""
    parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for span in spans:
        start = cursor
        parts.append(span.text)
        cursor += len(span.text)
        ranges.append((start, cursor))
        parts.append(_SPAN_SEPARATOR)
        cursor += len(_SPAN_SEPARATOR)
    return "".join(parts), ranges


def _find_owning_span(ranges: list[tuple[int, int]], offset: int, length: int) -> int | None:
    """Zwraca indeks fragmentu, który w całości obejmuje zakres błędu, albo None."""
    end = offset + length
    for index, (start, stop) in enumerate(ranges):
        if start <= offset and end <= stop:
            return index
    return None


def check_page(
    client: LanguageToolClient,
    language_code: str,
    engine: TextEditEngine,
    path: Path,
    page_index: int,
) -> list[ProofreadingSuggestion]:
    """Sprawdza jedną stronę PDF i zwraca sugestie powiązane z fragmentami tekstu.

    Błędy, których zakres przecina granicę dwóch fragmentów (rzadki
    przypadek, np. zmiana czcionki w połowie słowa), są pomijane — nie
    można ich bezpiecznie zmapować na edycję jednego fragmentu. Pomijane
    są też błędy bez żadnej konkretnej propozycji zamiany (nic do
    zaakceptowania).
    """
    spans = engine.extract_spans(path, page_index)
    if not spans:
        return []

    flat_text, ranges = _build_flat_text(spans)
    issues = client.check(flat_text, language_code)

    suggestions: list[ProofreadingSuggestion] = []
    for issue in issues:
        if not issue.replacements:
            continue
        span_index = _find_owning_span(ranges, issue.offset, issue.length)
        if span_index is None:
            continue
        span = spans[span_index]
        local_offset = issue.offset - ranges[span_index][0]
        replacement = issue.replacements[0]
        suggested_text = span.text[:local_offset] + replacement + span.text[local_offset + issue.length :]
        if suggested_text == span.text:
            continue
        suggestions.append(
            ProofreadingSuggestion(page_index=page_index, span=span, issue=issue, suggested_text=suggested_text)
        )
    return suggestions


def check_document(
    client: LanguageToolClient,
    language_code: str,
    engine: TextEditEngine,
    path: Path,
    page_count: int,
) -> list[ProofreadingSuggestion]:
    suggestions: list[ProofreadingSuggestion] = []
    for page_index in range(page_count):
        suggestions.extend(check_page(client, language_code, engine, path, page_index))
    return suggestions
