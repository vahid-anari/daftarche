"""0.36.0: a split transaction's parts have tags of their own (layout 10): one refund for two
trips, each part its trip's tag. A tag filter shows such a transaction with the share of the
parts that have it; the Note column shows the parts' notes too; Manage › Tags counts them."""

import sqlite3

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def refund(db):
    db.get_or_create_account("Card")
    db.add_category("Education", "Expense")
    edu = db.get_category_by_name("Education", type_name="Expense")["id"]
    db.add_subcategory("Reimbursements", edu)
    back = db.get_subcategory_by_name("Reimbursements", edu)["id"]
    db.add_tag("Toktam")
    tx = db.add_transaction(2026, "October", 21, "Expense", "Card", -1690.10, back, edu, merchant="McMaster",
                            note="CREDIT MEMO")
    db.set_tags_for_transaction(tx, [db.get_tags()[0]["id"]])
    db.set_splits(tx, [(edu, back, -1650.10, "CASCA", ["CASCA 2026"]), (edu, back, -40.00, "WISE", ["WISE 2026"])])
    db.conn.commit()
    return db, tx


def test_parts_keep_their_tags(refund):
    db, tx = refund
    parts = db.get_splits(tx)
    assert [p["tags"] for p in parts] == [["CASCA 2026"], ["WISE 2026"]]
    assert {t["name"] for t in db.get_tags()} == {"Toktam", "CASCA 2026", "WISE 2026"}  # made by the split


def test_a_tag_filter_shows_the_share(refund):
    db, tx = refund
    (row,) = db.get_transactions({"tags": ["WISE 2026"]})
    assert row["shown_amount"] == -40.00 and [p["note"] for p in row["shown_parts"]] == ["WISE"]
    assert row["tags"] == "Toktam, WISE 2026"
    (whole,) = db.get_transactions({"tags": ["Toktam"]})  # the transaction's own tag: all of it
    assert whole["shown_amount"] == -1690.10 and len(whole["shown_parts"]) == 2
    assert whole["tags"] == "CASCA 2026, Toktam, WISE 2026"
    assert db.get_transactions({"tags": ["CASCA 2026"], "category": ["Education"]})[0]["shown_amount"] == -1650.10
    assert db.get_transactions({"search": "WISE 20", "search_fields": {"tags": True}})


def test_counts_lines_export_and_a_tag_deleted(refund, tmp_path):
    import pandas as pd
    db, tx = refund
    ids = {t["name"]: t["id"] for t in db.get_tags()}
    assert db.get_transaction_count_for_tag(ids["CASCA 2026"]) == 1
    lines = db.get_lines(tag_id=ids["WISE 2026"])
    assert [(line["amount"], line["tags"]) for line in lines] == [(-40.0, "Toktam, WISE 2026")]
    path = tmp_path / "out.xlsx"
    db.export_to_xlsx(path)
    sheet = pd.read_excel(path)
    assert list(sheet["Tags"]) == ["CASCA 2026, Toktam", "Toktam, WISE 2026"]
    db.delete_tag(ids["CASCA 2026"])
    assert db.get_splits(tx)[0]["tags"] == []


def test_an_older_database_gets_the_table(tmp_path):
    from daftarche.db import SCHEMA_VERSION, Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE split_tags")
    conn.execute("PRAGMA user_version = 9")
    conn.commit()
    conn.close()
    db = Database(path)
    assert SCHEMA_VERSION == 10 and db.conn.execute("SELECT COUNT(*) FROM split_tags").fetchone()[0] == 0


def test_note_column_and_the_split_window(qapp, refund):
    from daftarche.split_dialog import SplitDialog
    from daftarche.tabs.transactions import COL_NOTE, cell_text
    db, tx = refund
    whole = next(r for r in db.get_transactions() if r["id"] == tx)
    assert cell_text(whole, COL_NOTE) == "CREDIT MEMO · CASCA · WISE"
    share = db.get_transactions({"tags": ["WISE 2026"]})[0]
    assert cell_text(share, COL_NOTE) == "CREDIT MEMO · WISE"  # only the parts shown
    d = keep(SplitDialog(db, "Expense", whole["amount"], parts=whole["parts"]))
    assert d._rows[1][4].get_selected() == ["WISE 2026"]
    d._rows[1][4].set_selected(["WISE 2026", "Toktam"])
    d._accept()
    assert sorted(d.result_parts[1][4]) == ["Toktam", "WISE 2026"]


def test_check_list_shows_its_rows(qapp):
    from daftarche.widgets import CheckComboBox
    box = keep(CheckComboBox("All"))
    box.populate(["Bank", "Earnings", "Sales", "Tax & Benefits"])
    box.show()
    qapp.processEvents()
    height = box._list_height()
    assert height >= 4 * box._list.sizeHintForRow(0)  # all four, not three and a scroll
    box.populate([f"Item {i}" for i in range(40)])
    row = max(box._list.sizeHintForRow(0), box.fontMetrics().height() + 8)
    assert row * CheckComboBox.ROWS_SHOWN <= box._list_height() <= row * (CheckComboBox.ROWS_SHOWN + 1)


def test_tags_in_any_letter_case_are_one_and_joining_keeps_them(refund):
    db, tx = refund
    edu = db.get_category_by_name("Education", type_name="Expense")["id"]
    back = db.get_subcategory_by_name("Reimbursements", edu)["id"]
    db.set_splits(tx, [(edu, back, -1650.10, "", ["casca 2026"]), (edu, back, -40.00, "", ["Rome"]),
                       ])
    db.set_splits(tx, [(edu, back, -1650.10, "", ["Rome"]), (edu, back, -40.00, "", ["rome"])])
    names = sorted(t["name"] for t in db.get_tags())
    assert names == ["CASCA 2026", "Rome", "Toktam", "WISE 2026"]  # no "casca 2026", no "rome"
    db.set_splits(tx, [])  # joined again: the parts' tags are the transaction's
    own = {t["name"] for t in db.get_tags_for_transaction(tx)}
    assert own == {"Toktam", "Rome"}


def test_the_phone_keeps_a_parts_tags_with_the_part(refund):
    from daftarche.phone import build_snapshot
    db, tx = refund
    snap = build_snapshot(db)
    t = next(x for x in snap["transactions"] if x["id"] == tx)
    names = {g["id"]: g["name"] for g in snap["tags"]}
    assert [names[i] for i in t["tags"]] == ["Toktam"]  # the phone adds up the whole: only its own
    assert [[names[i] for i in p["tags"]] for p in t["parts"]] == [["CASCA 2026"], ["WISE 2026"]]
