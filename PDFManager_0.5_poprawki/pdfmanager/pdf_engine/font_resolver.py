"""Wybór czcionki używanej do wstawienia nowego tekstu po edycji.

Priorytet: użyć oryginalnej, osadzonej w PDF czcionki (idealne dopasowanie
wizualne), a dopiero gdy ona nie istnieje lub nie zawiera glifów wymaganych
przez nowy tekst (częsty przypadek dla polskich znaków diakrytycznych i
cyrylicy ukraińskiej w nieosadzonych czcionkach bazowych) — użyć dołączonej
czcionki zastępczej DejaVu Sans, która pokrywa łacinę rozszerzoną i
cyrylicę (patrz pdfmanager/resources/fonts/LICENSE_DEJAVU.txt).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

FALLBACK_FONTS_DIR = Path(__file__).resolve().parent.parent / "resources" / "fonts"

FALLBACK_VARIANTS: dict[tuple[bool, bool], Path] = {
    (False, False): FALLBACK_FONTS_DIR / "DejaVuSans.ttf",
    (True, False): FALLBACK_FONTS_DIR / "DejaVuSans-Bold.ttf",
    (False, True): FALLBACK_FONTS_DIR / "DejaVuSans-Oblique.ttf",
    (True, True): FALLBACK_FONTS_DIR / "DejaVuSans-BoldOblique.ttf",
}


@dataclass(frozen=True)
class ResolvedFont:
    fontname: str
    fontfile: Path | None
    fontbuffer: bytes | None
    is_fallback: bool


def _font_covers_text(font_bytes: bytes, text: str) -> bool:
    try:
        tt_font = TTFont(BytesIO(font_bytes), fontNumber=0, lazy=True)
        cmap = tt_font.getBestCmap()
    except (TTLibError, Exception):
        return False
    if not cmap:
        return False
    return all(ord(ch) in cmap for ch in text if not ch.isspace())


_SUBSET_PREFIX_RE = re.compile(r"^[A-Za-z]{6}\+")


def _normalize_font_name(name: str) -> str:
    """Usuwa prefiks subsetu (np. 'ABCDEF+') i znaki niealfanumeryczne.

    Nazwa czcionki w span["font"] (get_text("dict")) i basefont zwracany
    przez page.get_fonts() bywają zapisane w różny sposób dla tej samej
    czcionki (np. "DejaVuSans" vs "DejaVu Sans Book") — porównujemy je więc
    jako znormalizowane podciągi, nie jako dokładne dopasowanie.
    """
    name = _SUBSET_PREFIX_RE.sub("", name)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _extract_embedded_font(page, span_font_name: str) -> bytes | None:
    doc = page.parent
    target = _normalize_font_name(span_font_name)
    if not target:
        return None
    for font_info in page.get_fonts(full=True):
        xref, basefont = font_info[0], font_info[3]
        candidate = _normalize_font_name(basefont)
        if candidate and (target in candidate or candidate in target):
            extracted = doc.extract_font(xref)
            content = extracted[3] if len(extracted) >= 4 else None
            if content:
                return content
    return None


def resolve_font(page, span_font_name: str, text: str, bold: bool, italic: bool) -> ResolvedFont:
    """Zwraca czcionkę gwarantującą pokrycie wszystkich znaków `text`."""
    if span_font_name.startswith('system:'):
        path=system_font_file(span_font_name[7:],bold,italic)
        if path and _font_covers_text(path.read_bytes(),text):return ResolvedFont('system_'+uuid.uuid4().hex[:10],path,None,False)
        span_font_name=''
    embedded = _extract_embedded_font(page, span_font_name)
    if embedded and _font_covers_text(embedded, text):
        unique_name = f"orig_{uuid.uuid4().hex[:10]}"
        return ResolvedFont(fontname=unique_name, fontfile=None, fontbuffer=embedded, is_fallback=False)

    fallback_path = FALLBACK_VARIANTS[(bold, italic)]
    fallback_name = f"fallback_{uuid.uuid4().hex[:10]}"
    return ResolvedFont(fontname=fallback_name, fontfile=fallback_path, fontbuffer=None, is_fallback=True)

# Installed fonts are resolved inside the PDF worker, never by parsing TTFs in Qt.
def system_font_file(family,bold=False,italic=False):
    import os,subprocess
    from functools import lru_cache
    return _system_font_file(family,bold,italic)

from functools import lru_cache
@lru_cache(maxsize=128)
def _system_font_file(family,bold,italic):
    import os,subprocess
    target=_normalize_font_name(family)
    candidates=[]
    if os.name=='nt':
        import winreg
        folders=[Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts',Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft/Windows/Fonts']
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
                    for i in range(min(winreg.QueryInfoKey(key)[1],5000)):
                        name,value,_=winreg.EnumValue(key,i)
                        if not isinstance(value,str) or target not in _normalize_font_name(name):continue
                        for folder in folders:
                            path=Path(value) if Path(value).is_absolute() else folder/value
                            if path.is_file():candidates.append(path)
            except OSError:continue
    else:
        style=('Bold' if bold else 'Regular')+(' Italic' if italic else '')
        try:
            result=subprocess.run(['fc-match','-f','%{file}',family+':weight='+('bold' if bold else 'regular')+':slant='+('italic' if italic else 'roman')],capture_output=True,text=True,timeout=5,check=True)
            candidates=[Path(result.stdout)]
        except (OSError,subprocess.SubprocessError):pass
    best=None;best_score=-1
    for path in dict.fromkeys(candidates):
        try:
            if path.suffix.lower() not in ('.ttf','.otf','.ttc') or path.stat().st_size>32*1024*1024:continue
            with TTFont(path,fontNumber=0,lazy=True) as font:
                names={_normalize_font_name(n.toUnicode()) for n in font['name'].names if n.nameID in (1,16)}
                if target not in names:continue
                flags=font['head'].macStyle
                score=int(bool(flags&1)==bold)+int(bool(flags&2)==italic)
                # Restricted-license embedding cannot be overridden by this editor.
                if 'OS/2' in font and font['OS/2'].fsType&2:continue
                if score>best_score:best=path;best_score=score
        except (OSError,TTLibError,KeyError,ValueError):continue
    return best if best_score==2 else None
