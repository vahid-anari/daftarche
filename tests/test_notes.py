"""The Note column, and the tools that export shop purchases and write notes back."""

import csv
import importlib.util
import sqlite3
from pathlib import Path

import pytest

from conftest import keep

TOOLS = Path(__file__).resolve().parents[1] / "tools"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def tool(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def shop(db):
    uc, us = db.get_uncategorized_ids()
    db.add_category("Electronics", "Expense")
    cat = db.get_category_by_name("Electronics", type_name="Expense")["id"]
    db.add_subcategory("Cables", cat)
    ids = [db.add_transaction(2026, "May", d, "Expense", "Card", amount, us, uc, name=name)
           for d, amount, name in ((3, 84.2, "AMAZON.CA*AB12C"), (5, 12.0, "NOFRILLS"),
                                   (9, 19.99, "ALIEXPRESS.COM"), (11, 7.5, "AMZN Mktp CA"))]
    return ids


def test_note_is_saved_searched_and_exported(qapp, db, shop, tmp_path):
    from daftarche.tabs.transactions import COL_NOTE, TransactionsTab
    tab = keep(TransactionsTab(db))
    tab.show_matching()
    row = next(i for i in range(tab.model.rowCount()) if tab.model.get_row(i)["name"] == "NOFRILLS")
    assert tab.model.setData(tab.model.index(row, COL_NOTE), "  milk and bread ")
    assert {r["name"]: r["note"] for r in db.get_transactions()}["NOFRILLS"] == "milk and bread"
    assert tab.model.data(tab.model.index(row, COL_NOTE)) == "milk and bread"
    found = db.get_transactions({"search": "bread", "search_fields": {"name": True}})
    assert [r["name"] for r in found] == ["NOFRILLS"]  # notes are searched unless turned off
    db.export_to_xlsx(tmp_path / "x.xlsx")
    import pandas as pd
    assert "milk and bread" in pd.read_excel(tmp_path / "x.xlsx")["Note"].tolist()


def test_old_database_gets_the_note_column(tmp_path):
    from daftarche.db import SCHEMA_VERSION, Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)  # make it look like layout 1, before notes
    conn.execute("DROP VIEW tx_lines")
    conn.execute("ALTER TABLE transactions DROP COLUMN note")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    db = Database(path)
    assert "note" in [r[1] for r in db.conn.execute("PRAGMA table_info(transactions)")]
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 7
    db.conn.close()


def test_sort_dialog_names_the_right_columns(qapp):
    from daftarche.tabs.transactions import COL_NAME, COL_NOTE, COL_TAGS, SortDialog
    dialog = keep(SortDialog([{"col": COL_TAGS, "desc": False}, {"col": COL_NOTE, "desc": True}]))
    assert [w._col_combo.currentText() for w in dialog._rows_widgets] == ["Tags", "Note"]
    dialog._rows_widgets[0]._col_combo.setCurrentText("Name")
    dialog._save_and_accept()
    assert [c["col"] for c in dialog.get_config()] == [COL_NAME, COL_NOTE]


def test_export_has_only_the_shops(db, shop, tmp_path):
    out = tmp_path / "shops.csv"
    tool("export_shop_charges").main([str(db.path), "-o", str(out)])
    rows = list(csv.DictReader(out.open()))
    assert [r["name"] for r in rows] == ["AMAZON.CA*AB12C", "ALIEXPRESS.COM", "AMZN Mktp CA"]
    assert list(rows[0]) == ["id", "date", "account", "type", "amount", "name", "memo", "category",
                             "subcategory", "note"]


def test_import_notes_shows_first_then_writes(db, shop, tmp_path, monkeypatch):
    importer = tool("import_notes")
    from daftarche import paths
    monkeypatch.setattr(paths, "BACKUP_DIR", tmp_path / "backups")
    notes = tmp_path / "notes.csv"
    with notes.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "note", "category", "subcategory"])
        w.writerow([shop[0], "USB-C cable", "Electronics", "Cables"])
        w.writerow([shop[2], "phone case", "Gadgets", "Cases"])  # unknown category: note only
        w.writerow([99999, "nothing", "", ""])
    path = str(db.path)
    db.conn.close()

    importer.main([str(notes), "--database", path])  # dry run
    from daftarche.db import Database
    check = Database(path)
    assert all(r["note"] is None for r in check.get_transactions())
    check.conn.close()

    importer.main([str(notes), "--database", path, "--apply"])
    check = Database(path)
    got = {r["id"]: (r["note"], r["category"], r["subcategory"]) for r in check.get_transactions()}
    assert got[shop[0]] == ("USB-C cable", "Electronics", "Cables")
    assert got[shop[2]] == ("phone case", "Uncategorized", "Uncategorized")
    assert list((tmp_path / "backups").glob("daftarche-before-notes-*.db"))
    check.conn.close()


def test_list_categories_tool(db, shop, capsys):
    tool("list_categories").main([str(db.path), "--totals"])
    out = capsys.readouterr().out
    assert "EXPENSE" in out and "  Electronics  (0 tx" in out and "      Cables  (0 tx, $0.00)" in out
    assert "Uncategorized" in out and "$123.69" in out  # the shop rows are uncategorized
