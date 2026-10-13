"""
Motyw wizualny aplikacji — ciemny panel diagnostyczny w stylu narzędzi
sieciowych/administracyjnych. Jeden plik ze wszystkimi tokenami koloru,
typografii i arkuszem stylów Qt, żeby zmiana wyglądu nie wymagała
przeszukiwania main.py.

Paleta:
    tło główne     #0f1419   głęboki grafit-navy
    tło karty      #171d26
    obramowanie    #2a3441
    tekst główny   #e6edf3
    tekst wyciszony#8b98a5
    akcent (teal)  #3dd6c4   sieć / transmisja danych
    akcent hover   #2bc4b2
    sukces         #4ade80
    błąd           #f87171
    uwaga          #fbbf24
"""

BG_MAIN = "#0f1419"
BG_CARD = "#171d26"
BG_CARD_ALT = "#1c2330"
BORDER = "#2a3441"
BORDER_LIGHT = "#3a4554"
TEXT_MAIN = "#e6edf3"
TEXT_MUTED = "#8b98a5"
ACCENT = "#3dd6c4"
ACCENT_HOVER = "#2bc4b2"
ACCENT_DIM = "#1f4d47"
SUCCESS = "#4ade80"
DANGER = "#f87171"
WARNING = "#fbbf24"

FONT_DISPLAY = "Segoe UI Semibold"
FONT_BODY = "Segoe UI"
FONT_MONO = "Consolas"


STYLESHEET = f"""
QMainWindow {{
    background-color: {BG_MAIN};
}}

QWidget {{
    color: {TEXT_MAIN};
    font-family: "{FONT_BODY}";
    font-size: 13px;
}}

/* ── Karty (QGroupBox jako sekcja) ── */
QGroupBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 14px 14px 14px;
    font-weight: 600;
    font-size: 12px;
    color: {TEXT_MUTED};
    letter-spacing: 0.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: 2px;
    padding: 0 6px;
    background-color: {BG_MAIN};
    color: {ACCENT};
}}

/* ── Pola tekstowe ── */
QLineEdit {{
    background-color: {BG_CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 9px 11px;
    color: {TEXT_MAIN};
    font-family: "{FONT_MONO}";
    font-size: 13px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── Przyciski ── */
QPushButton {{
    background-color: {BG_CARD_ALT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 7px;
    padding: 9px 16px;
    color: {TEXT_MAIN};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #232b3a;
    border: 1px solid {ACCENT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DIM};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_CARD};
}}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: #06231f;
    border: none;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.5px;
}}
QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:disabled {{
    background-color: #2a3d3a;
    color: #5a6b68;
}}

/* ── Radio buttons ── */
QRadioButton {{
    spacing: 8px;
    padding: 4px 0;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 9px;
    border: 2px solid {BORDER_LIGHT};
    background: {BG_CARD_ALT};
}}
QRadioButton::indicator:checked {{
    border: 2px solid {ACCENT};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                                 fx:0.5, fy:0.5,
                                 stop:0 {ACCENT}, stop:0.5 {ACCENT}, stop:0.6 {BG_CARD_ALT});
}}

/* ── Checkboxy ── */
QCheckBox {{
    spacing: 8px;
    padding: 4px 0;
    color: {TEXT_MAIN};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 2px solid {BORDER_LIGHT};
    background: {BG_CARD_ALT};
}}
QCheckBox::indicator:checked {{
    border: 2px solid {ACCENT};
    background: {ACCENT};
}}

/* ── Log / konsola ── */
QTextEdit#logConsole {{
    background-color: #0a0e13;
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px;
    color: #b8c4cf;
    font-family: "{FONT_MONO}";
    font-size: 12px;
}}

/* ── Pasek postępu ── */
QProgressBar {{
    border: none;
    border-radius: 4px;
    background-color: {BG_CARD_ALT};
    height: 6px;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}

/* ── Scrollbar ── */
QScrollBar:vertical {{
    background: {BG_CARD};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Tooltips ── */
QToolTip {{
    background-color: {BG_CARD_ALT};
    color: {TEXT_MAIN};
    border: 1px solid {ACCENT};
    padding: 4px 8px;
    border-radius: 4px;
}}
"""


def status_dot_html(color: str) -> str:
    """Zwraca inline-HTML kropkę statusu w danym kolorze (do użycia w QLabel z richtext)."""
    return (
        f'<span style="color:{color}; font-size:16px;">●</span>'
    )
