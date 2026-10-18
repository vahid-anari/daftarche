"""Batch D (0.8.0): safe settings, schema version, cached balances, export, charts and refresh."""

import json
import sqlite3
from unittest import mock

import pytest

from daftarche import backup
from daftarche.db import SCHEMA_VERSION, Database, NewerDatabaseError


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def add(db, year, month, type_name="Expense", account="A", amount=10, to_account=None, fitid=None):
    cat_id, sub_id = db.get_uncategorized_ids()
    return db.add_transaction(year, month, 5, type_name, account, amount, sub_id, cat_id,
                              to_account_name=to_account, fitid=fitid)


# ── settings ─────────────────────────────────────────────────────────────────

def test_settings_are_written_whole(tmp_path, monkeypatch):
    from daftarche import style
    path = tmp_path / "config.json"
    monkeypatch.setattr(style, "CONFIG_PATH", str(path))
    settings = style.Settings()
    settings.set("font_size", 17)
    assert json.loads(path.read_text())["font_size"] == 17
    assert not (tmp_path / "config.json.tmp").exists()


def test_damaged_settings_file_is_kept_aside(tmp_path, monkeypatch):
    from daftarche import style
    path = tmp_path / "config.json"
    path.write_text('{"font_size": 1')
    monkeypatch.setattr(style, "CONFIG_PATH", str(path))
    assert style.Settings().get("font_size") == style.DEFAULTS["font_size"]
    assert (tmp_path / "config.json.broken").read_text() == '{"font_size": 1'


# ── schema version ───────────────────────────────────────────────────────────

def test_database_records_its_layout_version(tmp_path):
    db = Database(tmp_path / "d.db")
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    db.conn.close()


def test_newer_database_is_refused(tmp_path):
    path = tmp_path / "newer.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(NewerDatabaseError, match="newer version"):
        Database(path)
    with pytest.raises(ValueError, match="newer version"):
        backup.check_backup(path)


# ── balances, duplicates ─────────────────────────────────────────────────────

def test_monthly_balances_fill_empty_months_and_follow_changes(db):
    add(db, 2026, "January", "Income", amount=100)
    add(db, 2026, "March", amount=30)
    snapshots, accounts = db.get_account_monthly_balance()
    a = next(i for i, n in accounts.items() if n == "A")
    assert [snapshots[(2026, m)][a] for m in ("January", "February", "March")] == [100, 100, 70]
    add(db, 2026, "March", amount=20)
    assert db.get_account_monthly_balance()[0][(2026, "March")][a] == 50


def test_balances_of_a_transfer(db):
    add(db, 2026, "May", "Income", amount=100)
    add(db, 2026, "May", "Transfer", account="A", to_account="B", amount=40)
    assert db.get_latest_account_balances() == {
        db.get_account_by_name("A")["id"]: 60.0, db.get_account_by_name("B")["id"]: 40.0}


def test_fitid_lookup_with_combined_fitids(db):
    add(db, 2026, "May", "Transfer", account="A", to_account="B", fitid="F1|F22")
    assert db.fitid_exists("F1", "A") and db.fitid_exists("F22", "B")
    assert not db.fitid_exists("F2", "A") and not db.fitid_exists("F", "B")


# ── export ───────────────────────────────────────────────────────────────────

def test_export_keeps_order_and_adds_tags(db, tmp_path):
    pd = pytest.importorskip("pandas")
    first, second = add(db, 2026, "May", fitid="X1"), add(db, 2026, "June")
    db.add_tag("trip")
    db.set_tags_for_transaction(first, [db.get_tags()[0]["id"]])
    rows = sorted(db.get_transactions(), key=lambda r: r["id"])
    db.export_to_xlsx(tmp_path / "e.xlsx", rows=rows)
    frame = pd.read_excel(tmp_path / "e.xlsx").fillna("")
    assert list(frame["Date"]) == ["2026-05-05", "2026-06-05"]
    assert list(frame["Tags"]) == ["trip", ""] and list(frame["FITID"]) == ["X1", ""]
    assert second


# ── charts and refresh ───────────────────────────────────────────────────────

def test_replaced_charts_are_deleted(qapp):
    from PySide6.QtCore import QCoreApplication, QEvent
    from daftarche.chart_utils import HoverChartView, make_chart
    view = HoverChartView()
    gone = []
    first = make_chart("one")
    first.destroyed.connect(lambda: gone.append("one"))
    view.setChart(first)
    view.setChart(make_chart("two"))
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert gone == ["one"]


def test_months_between():
    from daftarche.tabs.charts import _months_between
    assert _months_between((2025, "November"), (2026, "February")) == [
        (2025, "November"), (2025, "December"), (2026, "January"), (2026, "February")]


def test_only_the_visible_tab_refreshes(qapp, monkeypatch, tmp_path):
    from daftarche import window as window_module
    monkeypatch.setattr(window_module, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(window_module, "startup_backup"):
        w = window_module.MainWindow()
    calls = []
    for tab in (w.dashboard_tab, w.transactions_tab, w.charts_tab, w.accounts_tab):
        tab.refresh = (lambda name: (lambda: calls.append(name)))(type(tab).__name__)
    w._refresh_all()
    assert calls == ["DashboardTab"]
    w.tabs.setCurrentWidget(w.charts_tab)
    w.tabs.setCurrentWidget(w.dashboard_tab)
    assert calls == ["DashboardTab", "ChartsTab"]
    w.db.conn.close()


def test_failed_auto_backup_is_shown(qapp, monkeypatch, tmp_path):
    from daftarche import window as window_module
    monkeypatch.setattr(window_module, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(window_module, "startup_backup", side_effect=OSError("disk full")):
        w = window_module.MainWindow()
    assert "disk full" in w.statusBar().currentMessage()
    w.db.conn.close()


def test_popups_belong_to_their_widget(qapp):
    """Parentless popups were left for Python's shutdown to delete, in no particular order;
    on Python 3.15 that crashed the app as it quit."""
    from daftarche.widgets import CheckComboBox, DatePicker
    combo, picker = CheckComboBox(), DatePicker()
    assert combo._popup.parent() is combo and picker._popup.parent() is picker
    assert combo._popup.isWindow() and picker._popup.isWindow()  # still separate popup windows
