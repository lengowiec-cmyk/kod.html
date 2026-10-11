import json
import urllib.error

import pytest

from pdfmanager.proofreading.language_tool_client import LanguageToolClient, LanguageToolError


def _fake_response(matches):
    body = json.dumps({"matches": matches})

    def fake_post(url, params, timeout):
        assert "text" in params and "language" in params
        return body

    return fake_post


def test_check_parses_matches_into_issues():
    matches = [
        {
            "offset": 5,
            "length": 4,
            "message": "Wykryto prawdopodobny błąd pisowni",
            "shortMessage": "Błędna pisownia",
            "replacements": [{"value": "błąd"}, {"value": "blat"}],
            "rule": {"id": "PL_SPELLING", "category": {"id": "TYPOS"}},
        }
    ]
    client = LanguageToolClient(http_post=_fake_response(matches))
    issues = client.check("Zrobiłem bląd w tekście.", "pl-PL")

    assert len(issues) == 1
    issue = issues[0]
    assert issue.offset == 5
    assert issue.length == 4
    assert issue.replacements == ("błąd", "blat")
    assert issue.rule_id == "PL_SPELLING"
    assert issue.category == "TYPOS"


def test_check_returns_empty_list_for_blank_text():
    calls = []

    def fake_post(url, params, timeout):
        calls.append(params)
        return json.dumps({"matches": []})

    client = LanguageToolClient(http_post=fake_post)
    assert client.check("   ", "pl-PL") == []
    assert calls == []  # nie wysyłamy żądania dla pustego tekstu


def test_check_skips_replacements_without_value():
    matches = [
        {
            "offset": 0,
            "length": 3,
            "message": "msg",
            "shortMessage": "",
            "replacements": [],
            "rule": {"id": "X", "category": {"id": "Y"}},
        }
    ]
    client = LanguageToolClient(http_post=_fake_response(matches))
    issues = client.check("abc", "en-US")
    assert issues[0].replacements == ()
    assert issues[0].short_message == "msg"  # pada na message gdy shortMessage puste


def test_rate_limit_error_raises_language_tool_error():
    def fake_post(url, params, timeout):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    client = LanguageToolClient(http_post=fake_post)
    with pytest.raises(LanguageToolError, match="limitu zapytań"):
        client.check("tekst", "pl-PL")


def test_connection_error_raises_language_tool_error():
    def fake_post(url, params, timeout):
        raise urllib.error.URLError("brak połączenia")

    client = LanguageToolClient(http_post=fake_post)
    with pytest.raises(LanguageToolError, match="Nie udało się połączyć"):
        client.check("tekst", "pl-PL")


def test_malformed_json_raises_language_tool_error():
    client = LanguageToolClient(http_post=lambda url, params, timeout: "to nie jest json")
    with pytest.raises(LanguageToolError, match="nieprawidłową odpowiedź"):
        client.check("tekst", "pl-PL")
