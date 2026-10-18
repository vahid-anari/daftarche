"""0.9.0: partly categorized rows, the import warning, View → Uncategorized / Unmatched Transfers."""

from pathlib import Path
from unittest import mock

import pytest
from conftest import answer_import

from daftarche.db import SUB_UNMATCHED, UNCATEGORIZED_SUB

QFX = (Path(__file__).parent / "data" / "sample.qfx").read_text(encoding="cp1252")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def category(db, name, type_name="Expense"):
    db.add_category(name, type_name)
    return db.get_category_by_name(name, type_name=type_name)["id"]


def add(db, type_name, cat_id, sub_id, amount=10, account="A", to_account=None, status=None):
    return db.add_transaction(2026, "May", 5, type_name, account, amount, sub_id, cat_id,
                              to_account_name=to_account, transfer_status=status)


@pytest.fixture
def data(db):
    uncat_cat, uncat_sub = db.get_uncategorized_ids()
    food = category(db, "Food")
    food_uncat = db.uncategorized_subcategory(food)["id"]
    db.add_subcategory("Groceries", food)
    groceries = db.get_subcategory_by_name("Groceries", food)
    add(db, "Expense", uncat_cat, uncat_sub, 30)
    add(db, "Expense", uncat_cat, uncat_sub, 20)
    add(db, "Expense", food, food_uncat, 5)
    add(db, "Expense", food, groceries["id"], 99)                       # categorized: not listed
    add(db, "Income", uncat_cat, uncat_sub, 1000)
    t_cat, t_sub = db.get_transfer_cat_sub(description="INTERNET TRANSFER", matched=False)
    add(db, "Transfer", t_cat, t_sub, 200, account="Checking", status="unmatched")
    add(db, "Transfer", t_cat, t_sub, 50, account=None, to_account="Saving", status="unmatched")
    return db


def test_uncategorized_overview(data):
    rows = {(r["kind"], r["category"]): (r["count"], r["total"]) for r in data.get_uncategorized_overview()}
    assert rows == {("Expense", "Uncategorized"): (2, 50.0), ("Expense", "Food"): (1, 5.0),
                    ("Income", "Uncategorized"): (1, 1000.0)}


def test_unmatched_transfer_overview(data):
    rows = {(r["account"], r["direction"]): (r["count"], r["total"], r["category"])
            for r in data.get_unmatched_transfer_overview()}
    assert rows == {("Checking", "Outgoing"): (1, 200.0, "Internal Transfer"),
                    ("Saving", "Incoming"): (1, 50.0, "Internal Transfer")}


def test_uncategorized_subcategory_is_offered_first(qapp, db):
    from daftarche.tabs.transactions import BulkCatDialog
    food = category(db, "Food")
    db.add_subcategory("Groceries", food)
    dialog = BulkCatDialog(db, "Expense")
    dialog.f_category.setCurrentText("Food")
    dialog._refresh_subcats("Food")
    assert [dialog.f_subcat.itemText(i) for i in range(dialog.f_subcat.count())] == [UNCATEGORIZED_SUB, "Groceries"]
    dialog.f_subcat.setCurrentText(UNCATEGORIZED_SUB)
    with mock.patch.object(dialog, "accept") as accept:
        dialog._accept()
    assert accept.called and db.get_subcategory_by_name(UNCATEGORIZED_SUB, food)


def test_rule_may_set_only_the_category(qapp, db, tmp_path):
    food = category(db, "Food")
    sub = db.uncategorized_subcategory(food)["id"]
    db.save_mapping("Expense", None, name="EXAMPLE GROCERY", subcategory_id=sub, category_id=food)
    db.get_or_create_account("Checking")
    tab = load(db, tmp_path, "Checking")
    row = next(r for r in tab.parsed_rows if r["name"] == "EXAMPLE GROCERY")
    assert (row["category"]["name"], row["subcategory"]["name"]) == ("Food", UNCATEGORIZED_SUB)


def load(db, tmp_path, account):
    from daftarche.tabs.import_tab import ImportTab
    tab = ImportTab(db, lambda: None)
    path = tmp_path / "s.qfx"
    path.write_text(QFX, encoding="cp1252")
    with mock.patch("daftarche.tabs.import_tab.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
         mock.patch.object(tab, "_ask_account", return_value=account):
        tab._browse_ofx()
    return tab


def test_status_bar_counts_and_import_warning(qapp, db, tmp_path):
    db.get_or_create_account("Checking")
    tab = load(db, tmp_path, "Checking")
    status = tab.lbl_status.text()
    assert "⚠️ 2 uncategorized" in status and "1 transfers (1 new, to be matched)" in status
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:  # Go Back
        tab.import_all()
    assert box.return_value.exec.called and db.get_transactions() == []
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        answer_import(box)
        tab.import_all()
    assert len(db.get_transactions()) == 3


def test_overview_line_opens_matching_transactions(qapp, data, monkeypatch, tmp_path):
    from daftarche import window as window_module
    monkeypatch.setattr(window_module, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(window_module, "startup_backup"):
        w = window_module.MainWindow()
    w.db.conn.close()
    w.db = data
    w._rebuild_tabs()
    seen = {}

    def run(dialog_cls, pick, **kw):
        dialog = dialog_cls(data, w._show_transactions, parent=w, **kw)
        item = pick(dialog.tree)
        dialog._open(item)
        seen[dialog_cls.__name__] = sorted((r["category"], r["subcategory"], r["amount"])
                                          for r in w.transactions_tab.model._rows)
        return dialog

    from daftarche.overview import UncategorizedDialog, UnmatchedTransfersDialog
    d = run(UncategorizedDialog, lambda t: t.topLevelItem(0).child(1))  # Expense › Food › Uncategorized
    assert "Expense" in d.summary.text() and w.tabs.currentWidget() is w.transactions_tab
    assert seen["UncategorizedDialog"] == [("Food", UNCATEGORIZED_SUB, 5.0)]
    run(UnmatchedTransfersDialog, lambda t: t.topLevelItem(0))            # Checking
    assert seen["UnmatchedTransfersDialog"] == [("Internal Transfer", SUB_UNMATCHED, 200.0)]


def test_view_menu_and_dashboard_link(qapp, monkeypatch, tmp_path):
    from daftarche import window as window_module
    monkeypatch.setattr(window_module, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(window_module, "startup_backup"):
        w = window_module.MainWindow()
    view = next(a.menu() for a in w.menuBar().actions() if a.text() == "View")
    assert [(a.text(), a.shortcut().toString()) for a in view.actions()] == [
        ("Uncategorized…", "Ctrl+U"), ("Unmatched Transfers…", "Ctrl+Shift+U")]
    with mock.patch.object(w, "show_uncategorized") as unc, mock.patch.object(w, "show_unmatched_transfers") as unm:
        w.dashboard_tab._alert_uncategorized = 3
        w.dashboard_tab._on_alert_clicked()
        w.dashboard_tab._alert_uncategorized = 0
        w.dashboard_tab._on_alert_clicked()
    assert unc.call_count == 1 and unm.call_count == 1
    w.db.conn.close()
