"""Get many merchants' logos at once, look at them, tick the ones you want, Apply.

The CSV has a header with ``merchant`` and ``website`` (one row per merchant; an empty website
is skipped). Each logo is taken from the shop's own site, as Edit Merchant does. Quit Daftarche
first; before Apply writes anything, a copy of the database is saved in the backups folder.

    python tools/pick_logos.py logo-sites.csv
    python tools/pick_logos.py logo-sites.csv --db path/to/daftarche.db

In the window: change a website and press Enter to get it again; a row with a sharp logo found
is ticked when its merchant has none yet (one smaller than 64 px is marked "small" and left for
you to choose). "Also try Google's icons" asks Google's icon service for those still small or
not found (it sends the site's name to Google). Nothing is written before Apply.
"""
import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QSize, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

COL_TICK, COL_NEW, COL_NOW, COL_NAME, COL_SITE, COL_NOTE = range(6)
SHARP = 64  # narrower than this: "small", not ticked by itself
GOOGLE = "https://www.google.com/s2/favicons?domain={host}&sz=128"


def width(png):
    from PySide6.QtGui import QImage
    return QImage.fromData(png).width()


def google_icon(site, get=None):
    """Google's icon of a site, as (PNG, address), or None (its blank globe is 16 px: small)."""
    import urllib.parse

    from daftarche import logos
    host = urllib.parse.urlsplit(logos.site_url(site)).netloc
    url = GOOGLE.format(host=host)
    try:
        data, _final = (get or logos._get)(url)
        return logos.normalise(data), url
    except (OSError, ValueError, logos.LogoError):
        return None


def read_sites(path):
    """[(merchant, website)] from the CSV, in its order, without empty names."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [((r.get("merchant") or "").strip(), (r.get("website") or "").strip())
                for r in csv.DictReader(f) if (r.get("merchant") or "").strip()]


class PickLogos(QDialog):
    def __init__(self, db, rows, fetch=None, workers=8, google=None):
        super().__init__()
        from daftarche.logos import fetch as fetch_logo, icon_size
        self.setWindowTitle("Pick Logos")
        self.db = db
        self._fetch = fetch or fetch_logo
        self._google = google or google_icon
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._pending = {}  # row → future
        self.found = {}  # row → (png, source)
        names = {n.casefold(): n for n in db.get_merchants()}
        layout = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Logo found", "Now", "Merchant", "Website", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        side = max(40, icon_size(self.table).height() * 2)
        self.table.setIconSize(QSize(side, side))
        self.table.verticalHeader().setDefaultSectionSize(side + 8)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_SITE, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        self.names = []
        self.table.blockSignals(True)
        for merchant, site in rows:
            real = names.get(merchant.casefold())
            r = self.table.rowCount()
            self.table.insertRow(r)
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            tick.setCheckState(Qt.Unchecked)
            self.table.setItem(r, COL_TICK, tick)
            for col in (COL_NEW, COL_NOW, COL_NAME, COL_NOTE):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(r, col, item)
            self.table.item(r, COL_NAME).setText(real or merchant)
            self.table.setItem(r, COL_SITE, QTableWidgetItem(site))
            self.names.append(real)
            if real:
                self._show_now(r)
            else:
                tick.setFlags(Qt.NoItemFlags)
                self.table.item(r, COL_NOTE).setText("not in your data")
        self.table.blockSignals(False)
        self.table.itemChanged.connect(self._changed)
        self.use_google = QCheckBox("Also try Google's icons for those small or not found "
                                    "(sends the site's name to Google)")
        self.use_google.toggled.connect(self._google_toggled)
        layout.addWidget(self.use_google)
        row = QHBoxLayout()
        for text, slot in (("Tick All Found", lambda: self._tick_all(True)), ("Untick All", lambda: self._tick_all(False))):
            b = QPushButton(text)
            b.setProperty("class", "secondary")
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply)
        close = QPushButton("Close")
        close.setProperty("class", "secondary")
        close.clicked.connect(self.reject)
        row.addWidget(self.btn_apply)
        row.addWidget(close)
        layout.addLayout(row)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._collect)
        self._timer.start(150)
        for r in range(self.table.rowCount()):
            self._get(r)
        self._update_info()
        self.resize(900, 700)

    def _show_now(self, r):
        from daftarche.logos import logo_icon
        data = self.db.logo_for(self.names[r])
        self.table.item(r, COL_NOW).setIcon(logo_icon(data) if data else logo_icon(None))
        self.table.item(r, COL_NOW).setToolTip("Its logo now" if data else "No logo now")

    def _get(self, r):
        site = self.table.item(r, COL_SITE).text().strip()
        if not self.names[r] or not site:
            if self.names[r]:
                self.table.item(r, COL_NOTE).setText("" if not site else self.table.item(r, COL_NOTE).text())
            return
        self.found.pop(r, None)
        self.table.item(r, COL_NOTE).setText("getting…")
        self._pending[r] = self._pool.submit(self._find, site, self.use_google.isChecked())

    def _find(self, site, google):
        """(PNG, address) from the shop's site; with ``google``, Google's icon when that one is
        larger (the site's was small, or there was none). Runs in a worker thread."""
        from daftarche.logos import LogoError
        try:
            found = self._fetch(site)
        except (LogoError, OSError, ValueError):
            found = None
        if google and (found is None or width(found[0]) < SHARP):
            other = self._google(site)
            if other is not None and (found is None or width(other[0]) > width(found[0])):
                found = other
        if found is None:
            raise LogoError(f"No logo found for {site}")
        return found

    def _google_toggled(self, on):
        if on:  # again, for those small or not found
            for r in range(self.table.rowCount()):
                if r not in self.found or width(self.found[r][0]) < SHARP:
                    self._get(r)

    def _collect(self):
        from daftarche.logos import LogoError, logo_icon
        done = [r for r, f in self._pending.items() if f.done()]
        if not done:
            return
        self.table.blockSignals(True)
        for r in done:
            future = self._pending.pop(r)
            try:
                data, source = future.result()
            except (LogoError, OSError, ValueError) as exc:
                self.table.item(r, COL_NEW).setIcon(logo_icon(None))
                self.table.item(r, COL_NOTE).setText("none found")
                self.table.item(r, COL_NOTE).setToolTip(str(exc))
                self.table.item(r, COL_TICK).setCheckState(Qt.Unchecked)
                continue
            self.found[r] = (data, source)
            side = width(data)
            small = side < SHARP
            self.table.item(r, COL_NEW).setIcon(logo_icon(data))
            self.table.item(r, COL_NOTE).setText(f"{side} px" + (" · small" if small else "")
                                                 + (" · Google" if "google.com" in source else ""))
            self.table.item(r, COL_NEW).setToolTip(source)
            # sharp and none yet: ticked; small, or one already: you choose
            on = not small and not self.db.logo_for(self.names[r])
            self.table.item(r, COL_TICK).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_info()

    def _changed(self, item):
        if item.column() == COL_SITE:
            self._get(item.row())
        self._update_info()

    def _tick_all(self, on):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if r in self.found or not on:
                if self.table.item(r, COL_TICK).flags() & Qt.ItemIsUserCheckable:
                    self.table.item(r, COL_TICK).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_info()

    def ticked(self):
        return [r for r in range(self.table.rowCount())
                if self.table.item(r, COL_TICK).checkState() == Qt.Checked and r in self.found]

    def _update_info(self):
        waiting = len(self._pending)
        self.info.setText(f"{len(self.found)} logos found" + (f", {waiting} still being got" if waiting else "")
                          + f" · {len(self.ticked())} ticked. Quit Daftarche before Apply; a copy of your "
                          "data is saved first. Change a website and press Enter to get it again.")
        self.btn_apply.setEnabled(bool(self.ticked()))

    def apply(self):
        from daftarche.backup import copy_db
        from daftarche.paths import BACKUP_DIR
        rows = self.ticked()
        if not rows:
            return
        if QMessageBox.question(self, "Apply", f"Give {len(rows)} merchant(s) the logo ticked?\n\n"
                                "Quit Daftarche first, if it is open.",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        safety = BACKUP_DIR / f"daftarche-before-logos-{datetime.now():%Y-%m-%d-%H%M%S}.db"
        copy_db(self.db.conn, safety)
        with self.db.transaction():
            for r in rows:
                data, source = self.found[r]
                self.db.set_logo(self.names[r], data, source)
        for r in rows:
            self._show_now(r)
            self.table.item(r, COL_TICK).setCheckState(Qt.Unchecked)
        QMessageBox.information(self, "Apply", f"{len(rows)} logo(s) saved. Your data from before is in\n"
                                f"{safety.name} (backups folder).")

    def done(self, result):
        self._timer.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
        super().done(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", help="merchant,website rows")
    parser.add_argument("--db", help="a database file (default: your data folder)")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    from daftarche.db import Database
    from daftarche.paths import DB_PATH
    from daftarche.style import build_stylesheet
    app.setStyleSheet(build_stylesheet())
    db = Database(Path(args.db) if args.db else DB_PATH)
    dlg = PickLogos(db, read_sites(args.csv))
    dlg.exec()
    db.conn.close()


if __name__ == "__main__":
    main()
