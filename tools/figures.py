"""The pictures and the animation of the Daftarche docs (``docs/figures``).

    python tools/figures.py                     # everything, in the dark theme
    python tools/figures.py charts              # only this one
    FIGURES_THEME=light python tools/figures.py dashboard --out-dir /tmp/check
    python tools/figures.py --list

Each item starts the app in a fresh process on a new demo database (the invented year of
``tools/make_demo_db.py``) in a temporary data folder, so your own data and settings never
show. The pictures use Daftarche's own theme, dark unless FIGURES_THEME says otherwise
(``--dark`` is not needed). How it works: sciwidgets.devtools; on macOS the pictures have the
window's title bar and shadow (``pip install -e ".[dev]"``, Screen Recording permission for
the terminal). The phone pictures are taken on the phone and are not made here.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

from sciwidgets.devtools import Gif, Player, Shot, main

TOOLS = Path(__file__).resolve().parent
THEME = os.environ.get("FIGURES_THEME", "dark")
"""Daftarche's theme in the pictures: "dark" (the default theme) or "light"."""
SIZE = (1536, 886)
"""Window size of the pictures."""


# ------------------------------------------------------------------- starting the app
def daftarche() -> int:
    """Start the app on a new demo database, without the splash and the update check."""
    folder = Path(tempfile.mkdtemp(prefix="daftarche-figures-"))
    os.environ["DAFTARCHE_HOME"] = str(folder)  # before daftarche is imported: its data folder
    (folder / "config.json").write_text(json.dumps({"theme": THEME, "splash_seconds": 0}))
    sys.path.insert(0, str(TOOLS))
    from make_demo_db import make_demo
    make_demo(folder)

    import sciwidgets.style
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from sciwidgets.app.update_ui import AppUpdates

    from daftarche.app_info import APP, APP_NAME
    from daftarche.window import MainWindow

    AppUpdates.check = lambda self, *args, **kwargs: None
    # devtools sets Qt's light or dark scheme as it starts; Daftarche's own theme decides here
    # (the window keeps the real function, imported above)
    sciwidgets.style.set_color_scheme = lambda app, scheme: None
    app = QApplication([])
    app.setApplicationName("daftarche")
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")
    if APP.icon.exists():
        app.setWindowIcon(QIcon(str(APP.icon)))
    window = MainWindow()
    window.show()
    return app.exec()


# ------------------------------------------------------------------- helpers
def _tab(p: Player, name: str, seconds: float = 0.5) -> Iterator[float]:
    """Glide to a tab and open it."""
    tabs = p.win.tabs
    bar = tabs.tabBar()
    index = next(i for i in range(tabs.count()) if name in tabs.tabText(i))
    rect = bar.tabRect(index)
    yield from p.move(p.at(bar, rect.center().x() / bar.width(), rect.center().y() / bar.height()), seconds)
    tabs.setCurrentIndex(index)
    yield 0.6


def _hover(p: Player, to, seconds: float = 0.6) -> Iterator[float]:
    """Glide the mouse to a point, moving the pointer over the widgets on the way (hover effects)."""
    from PySide6.QtCore import QEvent, Qt
    for wait in p.move(to, seconds):
        p._send(QEvent.MouseMove, Qt.NoButton, Qt.NoButton)
        yield wait


def _stacked_bars(p: Player) -> Iterator[float]:
    """Charts: monthly expenses as stacked bars, without Home (the rent would dwarf the rest)."""
    charts = p.win.charts_tab
    charts.f_chart_type.setCurrentText("Stacked Bars")
    yield 0.6
    charts._cat_cbs["Home"][0].setChecked(False)
    yield 0.8


def _bar_point(p: Player, category: str, months_back: int = 2):
    """The middle of a category's part of a stacked bar, ``months_back`` months before the last."""
    from PySide6.QtCore import QPoint, QPointF
    overlay = p.win.charts_tab._stack_overlay_widget
    rects = [(rect, pi) for rect, pi, cat, _val, _base in overlay._bar_rects() if cat == category]
    last = max(pi for _rect, pi in rects)
    rect = next(rect for rect, pi in rects if pi == last - months_back)
    return QPointF(p.win.mapFromGlobal(overlay.mapToGlobal(QPoint(round(rect.center().x()),
                                                                 round(rect.center().y())))))


# ------------------------------------------------------------------- picture states
def dashboard(p: Player) -> Iterator[float]:
    """The Dashboard as it opens."""
    yield 0.8


def transactions(p: Player) -> Iterator[float]:
    """The Transactions tab: filters, the table and the totals."""
    p.win.tabs.setCurrentWidget(p.win.transactions_tab)
    yield 0.8


def charts(p: Player) -> Iterator[float]:
    """Charts: stacked bars by category, the mouse over Groceries two months back."""
    p.win.tabs.setCurrentWidget(p.win.charts_tab)
    yield 0.6
    yield from _stacked_bars(p)
    yield from _hover(p, _bar_point(p, "Groceries"))
    yield 0.8


def accounts(p: Player) -> Iterator[float]:
    """The Accounts tab: the balance of each account by month."""
    p.win.tabs.setCurrentWidget(p.win.accounts_tab)
    yield 0.8


# ------------------------------------------------------------------- animation
def tour(p: Player) -> Iterator[float]:
    """The four tabs, Groceries in the charts, then View → Appearance → Light and back to Dark."""
    yield 1.0
    yield from _tab(p, "Transactions")
    yield 1.0
    yield from _tab(p, "Charts")
    yield from _stacked_bars(p)
    yield from _hover(p, _bar_point(p, "Groceries", 4), 0.8)
    yield 0.9
    yield from _hover(p, _bar_point(p, "Groceries", 2), 0.8)
    yield 1.0
    yield from _tab(p, "Accounts")
    yield 1.0
    yield from _tab(p, "Dashboard")
    yield 0.6
    yield from p.open_menu("View")
    yield from p.choose("Appearance")
    yield from p.choose("Light" if THEME == "dark" else "Dark")
    yield 1.6
    yield from p.open_menu("View")
    yield from p.choose("Appearance")
    yield from p.choose("Dark" if THEME == "dark" else "Light")
    yield 1.0


SHOTS = {
    "dashboard": Shot(daftarche, dashboard, size=SIZE),
    "transactions": Shot(daftarche, transactions, size=SIZE),
    "charts": Shot(daftarche, charts, size=SIZE),
    "accounts": Shot(daftarche, accounts, size=SIZE),
}

GIFS = {
    "tour": Gif(daftarche, tour, width=900, size=SIZE),
}

if __name__ == "__main__":
    raise SystemExit(main(SHOTS, GIFS))
