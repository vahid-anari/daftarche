"""tools/pick_logos.py: many merchants' logos at once, ticked, then Apply (with a copy first)."""

import importlib.util
import time
from pathlib import Path
from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location(
        "pick_logos", Path(__file__).resolve().parents[1] / "tools" / "pick_logos.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png(colour, side=128):
    from PySide6.QtGui import QColor, QImage
    from daftarche.logos import to_png
    image = QImage(side, side, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    return to_png(image)


def test_pick_and_apply(qapp, tool, db, tmp_path, monkeypatch):
    from daftarche import paths
    from daftarche.logos import LogoError
    monkeypatch.setattr(paths, "BACKUP_DIR", tmp_path)
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for name in ("IKEA", "Costco", "Ali"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, merchant=name)
    db.set_logo("Costco", png("#999999"))
    db.conn.commit()
    csv_file = tmp_path / "sites.csv"
    csv_file.write_text("merchant,website\nikea,ikea.com\nCostco,costco.ca\nAli,\nNobody,nobody.example\n"
                        "Missing,missing.example\n", encoding="utf-8")
    rows = tool.read_sites(csv_file)
    assert rows[0] == ("ikea", "ikea.com") and len(rows) == 5
    new = {"ikea.com": png("#0058a3"), "costco.ca": png("#e31837")}

    def fetch(site):
        if site not in new:
            raise LogoError("none")
        return new[site], f"https://{site}/apple-touch-icon.png"
    d = keep(tool.PickLogos(db, rows, fetch=fetch, workers=2))
    for _ in range(50):
        d._collect()
        if not d._pending:
            break
        time.sleep(0.02)
    t = d.table
    assert t.item(0, tool.COL_NAME).text() == "IKEA"  # the spelling in your data
    assert t.item(0, tool.COL_TICK).checkState() == tool.Qt.Checked  # no logo yet: ticked
    assert t.item(1, tool.COL_TICK).checkState() == tool.Qt.Unchecked  # has one: you choose
    assert t.item(3, tool.COL_NOTE).text() == "not in your data"
    assert d.ticked() == [0]
    with mock.patch.object(tool.QMessageBox, "question", return_value=tool.QMessageBox.Yes), \
            mock.patch.object(tool.QMessageBox, "information"):
        d.apply()
    assert db.logo_for("IKEA") == new["ikea.com"] and db.logo_for("Costco") == png("#999999")
    assert db.logo_source("IKEA") == "https://ikea.com/apple-touch-icon.png"
    assert list(tmp_path.glob("daftarche-before-logos-*.db"))
    t.item(2, tool.COL_SITE).setText("costco.ca")  # Ali: a website typed: got
    for _ in range(50):
        d._collect()
        if not d._pending:
            break
        time.sleep(0.02)
    assert 2 in d.found


def test_small_ones_are_not_ticked_and_google_is_asked_only_when_ticked(qapp, tool, db):
    from daftarche.logos import LogoError
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for name in ("Tiny", "Gone"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, merchant=name)
    db.conn.commit()
    asked = []

    def fetch(site):
        if site == "tiny.example":
            return png("#123456", 16), "https://tiny.example/favicon.ico"
        raise LogoError("none")

    def google(site):
        asked.append(site)
        return png("#654321", 128), "https://www.google.com/s2/favicons?domain=" + site

    def settle(d):
        for _ in range(100):
            d._collect()
            if not d._pending:
                return
            time.sleep(0.02)
    d = keep(tool.PickLogos(db, [("Tiny", "tiny.example"), ("Gone", "gone.example")], fetch=fetch, google=google))
    settle(d)
    assert d.table.item(0, tool.COL_NOTE).text() == "16 px · small"
    assert d.table.item(0, tool.COL_TICK).checkState() == tool.Qt.Unchecked and asked == []
    d.use_google.setChecked(True)
    settle(d)
    assert sorted(asked) == ["gone.example", "tiny.example"]
    assert d.table.item(0, tool.COL_NOTE).text() == "128 px · Google" and d.ticked() == [0, 1]
