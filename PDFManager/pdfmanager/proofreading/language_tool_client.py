"""Klient usługi LanguageTool (sprawdzanie pisowni/grammatyki/interpunkcji).

Domyślnie korzysta z publicznego, darmowego API LanguageTool
(https://api.languagetool.org) — co oznacza, że treść dokumentu jest
wysyłana do zewnętrznej usługi. Warstwa UI (patrz `ui/proofreading_dialog.py`)
MUSI poinformować użytkownika i uzyskać jego zgodę przed każdym wywołaniem —
ten moduł sam niczego nie wysyła bez wyraźnego polecenia wywołującego.

Dla pracy z dokumentami poufnymi aplikacja pozwala skonfigurować adres
własnego, samodzielnie hostowanego serwera LanguageTool (patrz
`base_url`) — wtedy żadne dane nie opuszczają sieci użytkownika.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

PUBLIC_API_URL = "https://api.languagetool.org"
DEFAULT_TIMEOUT = 20.0

# Mapowanie języka interfejsu/dokumentu (pl/en/uk) na kod języka LanguageTool.
LANGUAGE_CODES = {
    "pl": "pl-PL",
    "en": "en-US",
    "uk": "uk-UA",
}


@dataclass(frozen=True)
class ProofreadingIssue:
    offset: int
    length: int
    message: str
    short_message: str
    replacements: tuple[str, ...]
    rule_id: str
    category: str


class LanguageToolError(Exception):
    """Błąd komunikacji z usługą LanguageTool (sieć, limit zapytań, odpowiedź)."""


class LanguageToolClient:
    def __init__(self, base_url: str = PUBLIC_API_URL, timeout: float = DEFAULT_TIMEOUT, http_post=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http_post = http_post or _default_http_post

    def check(self, text: str, language: str) -> list[ProofreadingIssue]:
        if not text.strip():
            return []
        try:
            raw = self._http_post(f"{self.base_url}/v2/check", {"text": text, "language": language}, self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise LanguageToolError(
                    "Usługa LanguageTool odrzuciła żądanie z powodu przekroczenia limitu zapytań "
                    "(publiczne API jest ograniczone). Spróbuj później albo skonfiguruj własny serwer."
                ) from exc
            raise LanguageToolError(f"Usługa LanguageTool zwróciła błąd HTTP {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise LanguageToolError(f"Nie udało się połączyć z usługą LanguageTool ({self.base_url}): {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:
            raise LanguageToolError(f"Przekroczono czas połączenia z usługą LanguageTool: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LanguageToolError("Usługa LanguageTool zwróciła nieprawidłową odpowiedź.") from exc

        issues = []
        for match in data.get("matches", []):
            replacements = tuple(r["value"] for r in match.get("replacements", []) if r.get("value"))
            issues.append(
                ProofreadingIssue(
                    offset=match["offset"],
                    length=match["length"],
                    message=match.get("message", ""),
                    short_message=match.get("shortMessage", "") or match.get("message", ""),
                    replacements=replacements,
                    rule_id=match.get("rule", {}).get("id", ""),
                    category=match.get("rule", {}).get("category", {}).get("id", ""),
                )
            )
        return issues


def _default_http_post(url: str, params: dict, timeout: float) -> str:
    data = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")
