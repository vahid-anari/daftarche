"""
style.py — Centralized style system for Daftarche.

All colors, fonts, and QSS are generated from a Settings object.
Settings are persisted to config.json and can be reloaded at runtime.

Public API
----------
get_settings() -> Settings
build_stylesheet(s=None) -> str
color(key) -> str
FS_*  font-size offset constants
ACCOUNT_COLORS  list of 10 distinct account colors
"""

import json
import os

from daftarche.paths import CONFIG_PATH

DARK_COLORS: dict = {
    "accent": "#7c6af7",
    "bg_base": "#1e1c18",
    "bg_surface": "#2a2720",
    "bg_raised": "#38342e",
    "text": "#e8e0d0",
    "text_dim": "#9a9080",
    "border": "#4a4338",
    "income": "#2ecc71",
    "expense": "#e74c3c",
    "transfer": "#f39c12",
    "danger": "#c0392b",
}
LIGHT_COLORS: dict = {
    "accent": "#6b57e8",
    "bg_base": "#f5f3ee",
    "bg_surface": "#ffffff",
    "bg_raised": "#e9e5dc",
    "text": "#2a2620",
    "text_dim": "#7a7064",
    "border": "#d4ccbe",
    "income": "#1f9d55",
    "expense": "#d33a2c",
    "transfer": "#c97a06",
    "danger": "#c0392b",
}
THEMES = {"dark": DARK_COLORS, "light": LIGHT_COLORS}
THEME_NAMES = {"dark": "Dark", "light": "Light", "system": "Same as System"}
COLOR_KEYS = tuple(DARK_COLORS)

DEFAULTS: dict = {
    "font_family": "Helvetica Neue",
    "font_size": 14,
    "splash_seconds": 3.5,   # how long the splash stays at least; 0 = no splash
    "theme": "dark",         # dark, light, or system (follows the system's appearance)
    **DARK_COLORS,           # the colours as they were before themes (old settings files)
}


_platform_theme = None  # the system's own scheme, last seen while the app followed it


def system_theme() -> str:
    """"light" or "dark", as the Mac (or the system) shows windows now; "dark" when unknown.

    While the app is set to Dark or Light, Qt reports that choice instead of the Mac's
    (sciwidgets.style.set_color_scheme), so the Mac's scheme as last seen is given then.
    """
    global _platform_theme
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from sciwidgets.style import color_scheme
        if QGuiApplication.instance() is None:
            return "dark"
        if color_scheme() != "system" and _platform_theme is not None:
            return _platform_theme
        theme = "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"
        if color_scheme() == "system":
            _platform_theme = theme
        return theme
    except (ImportError, AttributeError):
        return "dark"

TAB20_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
    "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5",
]

# Font-size offset constants
FS_SUMMARY = 2
FS_TOTAL_BALANCE = +4
FS_ACCOUNT_CARD = +3
FS_SUMMARY_CARD = +3
FS_LABEL = 0
FS_DIALOG = +1
FS_SETTINGS = -1

# Account color palette
ACCOUNT_COLORS: list[str] = [
    "#7c6af7", "#2ecc71", "#e74c3c", "#f39c12", "#3498db",
    "#e91e8c", "#00bcd4", "#ff5722", "#8bc34a", "#9c27b0",
]


# Color helpers
def _lighten(hex_color: str, amount: int = 40) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{min(255, r + amount):02x}{min(255, g + amount):02x}{min(255, b + amount):02x}"


def _shade(hex_color: str, amount: int) -> str:
    """Lighter for a dark colour, darker for a light one: a hover that shows on either theme."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if 0.299 * r + 0.587 * g + 0.114 * b < 140:
        return _lighten(hex_color, amount)
    return f"#{max(0, r - amount):02x}{max(0, g - amount):02x}{max(0, b - amount):02x}"


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# Settings
class Settings:
    """Persistent key/value store for theme settings."""

    def __init__(self) -> None:
        self._data: dict = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    self._data.update(json.load(f))
            except (OSError, ValueError):
                # keep the damaged file for a look instead of silently overwriting it
                os.replace(CONFIG_PATH, f"{CONFIG_PATH}.broken")
        # before themes, colours were kept at the top: they were changes to the dark theme
        old = {k: self._data[k] for k in COLOR_KEYS if k in self._data and self._data[k] != DARK_COLORS[k]}
        if old and "colors_dark" not in self._data:
            self._data["colors_dark"] = old
        for k in COLOR_KEYS:
            self._data.pop(k, None)

    # ── themes ───────────────────────────────────────────────────────────────
    def theme(self) -> str:
        """The chosen theme: "dark", "light" or "system"."""
        t = self._data.get("theme", "dark")
        return t if t in THEME_NAMES else "dark"

    def active_theme(self) -> str:
        """The theme on screen now: "dark" or "light" ("system" follows the Mac)."""
        t = self.theme()
        return system_theme() if t == "system" else t

    def theme_colors(self, theme: str) -> dict:
        """A theme's colours, with your changes to it."""
        return {**THEMES[theme], **self._data.get(f"colors_{theme}", {})}

    def set_theme_colors(self, theme: str, colors: dict) -> None:
        """Keep only what differs from the theme's own colours (so a later default change shows)."""
        changed = {k: v for k, v in colors.items() if k in COLOR_KEYS and v != THEMES[theme][k]}
        if changed:
            self._data[f"colors_{theme}"] = changed
        else:
            self._data.pop(f"colors_{theme}", None)
        self.save()

    def save(self) -> None:
        """Write to a temporary file and swap it in: a crash mid-write never leaves half a file."""
        tmp = f"{CONFIG_PATH}.tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, CONFIG_PATH)

    def get(self, key: str):
        if key in COLOR_KEYS:
            return self.theme_colors(self.active_theme())[key]
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        if key in COLOR_KEYS:  # a change to the theme on screen
            theme = self.active_theme()
            self.set_theme_colors(theme, {**self.theme_colors(theme), key: value})
            return
        self._data[key] = value
        self.save()

    def reset(self) -> None:
        self._data = {k: v for k, v in DEFAULTS.items() if k not in COLOR_KEYS}
        self.save()


# Module-level singleton
_settings = Settings()


def get_settings() -> Settings:
    return _settings


def color(key: str) -> str:
    return _settings.get(key)


# Style vars
def _style_vars(s: Settings) -> dict:
    ac = s.get("accent")
    danger = s.get("danger")
    raised = s.get("bg_raised")
    surf = s.get("bg_surface")
    return {
        "ac": ac,
        "bg": s.get("bg_base"),
        "surf": surf,
        "raised": raised,
        "txt": s.get("text"),
        "dim": s.get("text_dim"),
        "bdr": s.get("border"),
        "inc": s.get("income"),
        "exp": s.get("expense"),
        "trf": s.get("transfer"),
        "danger": danger,
        "ff": s.get("font_family"),
        "fs": s.get("font_size"),
        "ac_hover": _lighten(ac, 35),
        "danger_hover": _lighten(danger, 35),
        "raised_hover": _shade(raised, 20),
        "surf_hover": _shade(surf, 15),
        "ac_sel": _rgba(ac, 0.28),
        "ac_selA": _rgba(ac, 0.45),
        "ac_item": _rgba(ac, 0.35),
    }


# Style section builders — organized by widget type
def _style_base(v) -> str:
    bg, txt, ff, fs = v["bg"], v["txt"], v["ff"], v["fs"]
    return f"""
QMainWindow, QDialog {{ background: {bg}; }}
QWidget              {{ background: {bg}; color: {txt}; font-family: '{ff}'; font-size: {fs}pt; }}
"""


def _style_labels(v) -> str:
    txt, dim, inc, exp, trf, fs = (
        v["txt"], v["dim"], v["inc"], v["exp"], v["trf"], v["fs"]
    )
    return f"""
QLabel {{ font-size: {fs}pt; color: {txt}; background: transparent; }}

/* Named — only override what differs */
QLabel#total_balance_label {{ font-size: {fs + 3}pt; }}
QLabel#total_balance_value {{ font-size: {fs + 3}pt; font-weight: bold; }}
QLabel#total_balance_value[balanceState="positive"] {{ color: {inc}; }}
QLabel#total_balance_value[balanceState="negative"] {{ color: {exp}; }}

QLabel#summary_income,
QLabel#summary_expense,
QLabel#summary_net,
QLabel#summary_transfer {{ font-weight: bold; font-size: {fs + 2}pt; }}
QLabel#summary_income   {{ color: {inc}; }}
QLabel#summary_expense  {{ color: {exp}; }}
QLabel#summary_transfer {{ color: {trf}; }}

/* Class — only override what differs */
QLabel[class="settings-title"]   {{ font-size: {fs + 1}pt; font-weight: bold; }}
QLabel[class="settings-section"] {{ font-weight: bold; }}
QLabel[class="dim-label"]        {{ color: {dim}; }}
QLabel[class="filter-label"],
QLabel[class="range-label"]      {{ font-weight: bold; }}
"""


def _style_buttons(v) -> str:
    ac, raised, dim, bdr, danger, fs = (
        v["ac"], v["raised"], v["dim"], v["bdr"], v["danger"], v["fs"]
    )
    txt = v["txt"]
    ac_hover = v["ac_hover"]
    danger_hover = v["danger_hover"]
    raised_hover = v["raised_hover"]
    bg = v["bg"]
    return f"""
QPushButton {{
    background: {ac};
    color: #ffffff;
    border: none;
    padding: 8px 18px;
    border-radius: 6px;
    font-weight: bold;
}}
QPushButton:hover   {{ background: {ac_hover}; }}
QPushButton:pressed {{ background: {ac}; }}
QPushButton:disabled {{ background: {raised}; color: {dim}; }}

/* secondary */
QPushButton[class="secondary"] {{
    background: {raised};
    color: {dim};
    border: 1px solid {bdr};
    font-weight: normal;
}}
QPushButton[class="secondary"]:hover    {{ background: {raised_hover}; color: {txt}; }}
QPushButton[class="secondary"]:pressed  {{ background: {raised}; }}
QPushButton[class="secondary"]:disabled {{ color: {bdr}; }}

/* danger */
QPushButton[class="danger"] {{ background: {danger}; border: none; }}
QPushButton[class="danger"]:hover   {{ background: {danger_hover}; }}
QPushButton[class="danger"]:pressed {{ background: {danger}; }}

/* period preset */
QPushButton[class="period-preset-btn"] {{
    background: {raised};
    color: {dim};
    border: 1px solid {bdr};
    border-radius: 6px;
    padding: 5px 12px;
    font-weight: normal;
    font-size: {fs}pt;
}}
QPushButton[class="period-preset-btn"]:hover         {{ background: {raised_hover}; color: {txt}; border-color: {dim}; }}
QPushButton[class="period-preset-btn"]:checked       {{ background: {ac}; color: #ffffff; border-color: {ac};}}
QPushButton[class="period-preset-btn"]:checked:hover {{ background: {ac_hover}; border-color: {ac_hover}; }}

/* nav (◀ ▶ OK in pickers) */
QPushButton[class="nav-btn"] {{
    background: {raised};
    color: {txt};
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    min-width: 0;
    font-size: {fs}pt;
}}
QPushButton[class="nav-btn"]:hover {{ background: {raised_hover}; border: 1px solid {dim}; }}

/* picker grid (day/month/year cells) */
QPushButton[class="picker-btn"] {{
    background: {raised};
    color: {txt};
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    min-width: 0;
    font-size: {fs}pt;
}}
QPushButton[class="picker-btn"]:hover    {{ background: {raised_hover}; }}
QPushButton[class="picker-btn"]:disabled {{ background: {bg}; color: {bdr}; }}

QPushButton[class="picker-btn"][state="selected"] {{ background: {ac}; color: #ffffff; font-weight: bold; }}
QPushButton[class="picker-btn"][state="today"]    {{ color: {ac}; border: 1px solid {ac}; font-weight: bold; }}
QPushButton[class="picker-btn"][state="overflow"] {{ background: transparent; color: {dim}; border: none; }}
QPushButton[class="picker-btn"][state="overflow"]:hover {{ background: {raised}; color: {txt}; }}
QPushButton[class="picker-ghost"] {{ background: transparent; border: none; padding: 0; min-width: 0; }}

/* spin (▲▼ in StepSpinBox) */
QPushButton[class="spin-btn"] {{
    background: {raised};
    color: {txt};
    border: 1px solid {bdr};
    border-radius: 3px;
    padding: 0;
    font-size: {fs - 2}pt;
}}
QPushButton[class="spin-btn"]:hover    {{ background: {raised_hover}; border-color: {dim}; }}
QPushButton[class="spin-btn"]:disabled {{ color: {dim}; }}

/* DialogButtonBox */
QDialogButtonBox QPushButton {{ min-width: 80px; padding: 7px 16px; }}
"""


def _style_toolbuttons(v) -> str:
    raised, txt, ac, bdr, fs = v["raised"], v["txt"], v["ac"], v["bdr"], v["fs"]
    return f"""
/* ── QToolButton ──────────────────────────────────── */

QToolButton[class="picker-combo"],
QToolButton[class="check-combo"] {{
    background: {raised};
    color: {txt};
    border: 1px solid {bdr};
    border-radius: 6px;
    padding: 0 10px;
    text-align: left;
    font-size: {fs + 2}pt;
}}
QToolButton[class="picker-combo"]:hover,
QToolButton[class="check-combo"]:hover {{ border-color: {ac}; }}
"""


def _style_inputs(v) -> str:
    surf, bdr, txt, dim, ac, raised, ac_item = (
        v["surf"], v["bdr"], v["txt"], v["dim"], v["ac"], v["raised"], v["ac_item"]
    )
    return f"""
/* ── QLineEdit / QTextEdit ────────────────────────── */

QLineEdit, QTextEdit {{
    background: {surf};
    border: 1px solid {bdr};
    color: {txt};
    padding: 6px 10px;
    border-radius: 6px;
}}
QLineEdit:hover,    QTextEdit:hover    {{ border-color: {dim}; }}
QLineEdit:focus,    QTextEdit:focus    {{ border-color: {ac}; }}
QLineEdit:disabled, QTextEdit:disabled {{ color: {dim}; border-color: {bdr}; }}

/* ── QCheckBox ────────────────────────────────────── */

QCheckBox {{ color: {txt}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    background: {surf};
    border: 1px solid {bdr};
    border-radius: 3px;
}}
QCheckBox::indicator:hover   {{ border-color: {dim}; }}
QCheckBox::indicator:checked {{ background: {ac}; border-color: {ac}; }}

/* ── QComboBox ────────────────────────────────────── */

QComboBox,
QComboBox[class="single-combo"] {{
    background: {surf};
    border: 1px solid {bdr};
    color: {txt};
    padding: 6px 32px 6px 10px;
    border-radius: 6px;
}}
QComboBox:hover,
QComboBox[class="single-combo"]:hover {{ border-color: {dim}; }}
QComboBox:focus,
QComboBox[class="single-combo"]:focus {{ border-color: {ac}; }}
QComboBox::drop-down {{
    border-left: 1px solid {bdr};
    width: 26px;
    subcontrol-origin: padding;
    subcontrol-position: right center;
}}
QComboBox::down-arrow {{ width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: {raised};
    color: {txt};
    border: 1px solid {bdr};
    selection-background-color: {ac_item};
    selection-color: {txt};
    outline: none;
}}
QComboBox QAbstractItemView::item {{ padding: 6px 10px; min-height: 28px; }}
QComboBox QAbstractItemView::item:hover {{ background: {ac_item}; }}
"""


def _style_frames(v) -> str:
    bg, surf, bdr, dim, fs = v["bg"], v["surf"], v["bdr"], v["dim"], v["fs"]
    return f"""
/* cards — shared base */
QFrame[class="stat-card"],
QFrame[class="summary-card"] {{
    background: {surf};
    border: 1px solid {bdr};
    border-radius: 8px;
    min-height: 72px;
}}
QFrame[class="stat-card"] QLabel[class="stat-label"],
QFrame[class="summary-card"] QLabel[class="summary-label"] {{
    color: {dim};
    font-size: {fs + 1}pt;
    font-weight: bold;
}}
QFrame[class="stat-card"] QLabel[class="stat-value"],
QFrame[class="summary-card"] QLabel[class="summary-value"] {{
    font-size: {fs + 3}pt;
    font-weight: bold;
}}

/* named frames */
QFrame#summary_bar        {{ background: {surf}; border-top: 1px solid {bdr}; border-radius: 0; }}
QFrame#total_balance_card {{ background: {surf}; border: 1px solid {dim}; border-radius: 8px; }}
QFrame#cat_panel          {{ background: {surf}; border: 1px solid {bdr}; border-radius: 8px; }}

/* picker popup */
QFrame[class="picker-popup"] {{
    background: {bg};
    border: 1px solid {bdr};
    border-radius: 8px;
}}

/* dividers */
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{ color: {bdr}; }}

/* ── QGroupBox ────────────────────────────────────── */

QGroupBox {{
    border: 1px solid {bdr};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    color: {dim};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
"""


def _style_tables(v) -> str:
    surf, raised, bdr, txt, dim, ac_sel, ac_selA = (
        v["surf"], v["raised"], v["bdr"], v["txt"],
        v["dim"], v["ac_sel"], v["ac_selA"]
    )
    return f"""
/* ── QTableView / QTableWidget ───────────────────── */

QTableView, QTableWidget {{
    background: {surf};
    alternate-background-color: {raised};
    gridline-color: {bdr};
    border: 1px solid {bdr};
    color: {txt};
    selection-background-color: {ac_sel};
}}
QTableView QHeaderView::section,
QTableWidget QHeaderView::section {{
    background: {raised};
    color: {dim};
    padding: 6px 10px;
    border: none;
    border-right: 1px solid {bdr};
    border-bottom: 1px solid {bdr};
    font-weight: bold;
}}
QTableView QHeaderView::section:vertical,
QTableWidget QHeaderView::section:vertical {{ color: {txt}; padding: 0 8px; }}
QTableView QHeaderView::section:last,
QTableWidget QHeaderView::section:last {{ border-right: none; }}
QTableView::item,
QTableWidget::item {{ padding: 0 8px; }}
QTableView::item:selected,
QTableWidget::item:selected {{ background: {ac_sel}; color: {txt}; }}
QTableView::item:selected:active,
QTableWidget::item:selected:active {{ background: {ac_selA}; color: {txt}; }}
"""


def _style_lists(v) -> str:
    surf, bdr, txt, ac = v["surf"], v["bdr"], v["txt"], v["ac"]
    return f"""
/* ── QListWidget (inside picker-popup) ───────────── */

QFrame[class="picker-popup"] QListWidget {{
    border: none;
    background: transparent;
    outline: none;
}}
QFrame[class="picker-popup"] QListWidget::item {{ padding: 4px 6px; border-radius: 3px; color: {txt}; }}
QFrame[class="picker-popup"] QListWidget::item:hover {{ background: {surf}; }}
QFrame[class="picker-popup"] QListWidget::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {bdr};
    border-radius: 3px;
    background: {surf};
}}
QFrame[class="picker-popup"] QListWidget::indicator:checked {{ background: {ac}; border-color: {ac}; image: none; }}
"""


def _style_tabs(v) -> str:
    surf, raised, txt, dim, ac = v["surf"], v["raised"], v["txt"], v["dim"], v["ac"]
    return f"""
/* ── QTabWidget / QTabBar ─────────────────────────── */

QTabWidget::pane {{ border: none; background: {surf}; }}
QTabBar::tab {{
    background: {raised};
    color: {dim};
    padding: 10px 22px;
    border: none;
    margin-right: 2px;
}}
QTabBar::tab:selected        {{ background: {surf}; color: {txt}; border-bottom: 2px solid {ac}; }}
QTabBar::tab:hover:!selected {{ background: {surf}; color: {txt}; }}
"""


def _style_chrome(v) -> str:
    surf, raised, bdr, txt, ac, ac_item = (
        v["surf"], v["raised"], v["bdr"], v["txt"], v["ac"], v["ac_item"]
    )
    return f"""
/* ── QScrollBar ───────────────────────────────────── */

QScrollBar:vertical   {{ background: {surf}; width: 8px;  border-radius: 4px; margin: 0; }}
QScrollBar:horizontal {{ background: {surf}; height: 8px; border-radius: 4px; margin: 0; }}
QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{ background: {bdr}; border-radius: 4px; min-height: 20px; min-width: 20px; }}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{ background: {ac}; }}
QScrollBar::add-line:vertical,  QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ height: 0; width: 0; }}

/* ── QScrollArea ──────────────────────────────────── */

QScrollArea                     {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ── QSplitter ────────────────────────────────────── */

QSplitter::handle {{ background: {bdr}; }}

/* ── QToolTip ─────────────────────────────────────── */

QToolTip {{
    background: {raised};
    color: {txt};
    border: 1px solid {bdr};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ── QMenu ────────────────────────────────────────── */

QMenu {{ background: {surf}; border: 1px solid {bdr}; color: {txt}; padding: 4px; }}
QMenu::item      {{ padding: 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ac_item}; }}
QMenu::separator {{ background: {bdr}; height: 1px; margin: 4px 0; }}

/* ── QMenuBar ─────────────────────────────────────── */

QMenuBar {{ background: {surf}; color: {txt}; border-bottom: 1px solid {bdr}; padding: 2px 4px; }}
QMenuBar::item          {{ background: transparent; padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {ac_item}; }}
"""


def _style_dialogs(v) -> str:
    bg, surf, bdr, txt = v["bg"], v["surf"], v["bdr"], v["txt"]
    return f"""
/* ── QMessageBox ──────────────────────────────────── */

QMessageBox        {{ background: {bg}; }}
QMessageBox QLabel {{ color: {txt}; }}

/* ── QInputDialog ─────────────────────────────────── */

QInputDialog        {{ background: {bg}; }}
QInputDialog QLabel {{ color: {txt}; }}
QInputDialog QLineEdit {{
    background: {surf};
    border: 1px solid {bdr};
    color: {txt};
    padding: 6px 10px;
    border-radius: 6px;
}}

/* ── QDialogButtonBox ─────────────────────────────── */

QDialogButtonBox QPushButton {{ min-width: 80px; padding: 7px 16px; }}
"""


# Public builder
def popup_list_stylesheet(s: Settings | None = None) -> str:
    """A free-standing list popup (e.g. a combo's completer) in the theme's combo-list colours."""
    v = _style_vars(s or get_settings())
    return f"""
QAbstractItemView {{
    background: {v['raised']};
    color: {v['txt']};
    border: 1px solid {v['bdr']};
    selection-background-color: {v['ac_item']};
    selection-color: {v['txt']};
    outline: none;
}}
QAbstractItemView::item {{ padding: 6px 10px; min-height: 28px; }}
QAbstractItemView::item:hover {{ background: {v['ac_item']}; }}
"""


def build_stylesheet(s: Settings | None = None) -> str:
    """Build and return the full application QSS string."""
    if s is None:
        s = _settings
    v = _style_vars(s)
    return "".join([
        _style_base(v),
        _style_labels(v),
        _style_buttons(v),
        _style_toolbuttons(v),
        _style_inputs(v),
        _style_frames(v),
        _style_tables(v),
        _style_lists(v),
        _style_tabs(v),
        _style_chrome(v),
        _style_dialogs(v),
    ])
