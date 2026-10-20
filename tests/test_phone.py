"""0.26: the phone snapshot (docs/phone-snapshot.md): what it holds, how it is written, and when."""

import json
from datetime import datetime, timezone

import pytest

from conftest import keep
from daftarche.phone import SNAPSHOT_NAME, VERSION, build_snapshot, write_snapshot


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def book(db):
    """Two months: pay, a split shop with a tag, a transfer to savings, money lent to Sahar."""
    db.add_category("Groceries", "Expense")
    db.add_category("Home", "Expense")
    db.add_category("Salary", "Income")
    groc = db.get_category_by_name("Groceries", type_name="Expense")["id"]
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    sal = db.get_category_by_name("Salary", type_name="Income")["id"]
    db.add_subcategory("Food", groc)
    db.add_subcategory("Cleaning", home)
    db.add_subcategory("Pay", sal)
    food = db.get_subcategory_by_name("Food", groc)["id"]
    clean = db.get_subcategory_by_name("Cleaning", home)["id"]
    pay = db.get_subcategory_by_name("Pay", sal)["id"]
    db.set_category_icon(groc, "🛒")
    ids = {"pay": db.add_transaction(2026, "September", 1, "Income", "Chequing", 3000, pay, sal, name="ACME PAY",
                                     fitid="BANK-ID-1"),
           "shop": db.add_transaction(2026, "October", 3, "Expense", "Chequing", 100, food, groc,
                                      name="MAPLE #12", merchant="Maple Grocer", note="weekly shop")}
    db.set_splits(ids["shop"], [(groc, food, 70, None), (home, clean, 30, "soap")])
    db.add_tag("Trip")
    tag = next(t["id"] for t in db.get_tags() if t["name"] == "Trip")
    db.set_tags_for_transaction(ids["shop"], [tag])
    cat, sub = db.get_transfer_cat_sub("TO SAVINGS", matched=True, from_account="Chequing", to_account="Savings")
    ids["save"] = db.add_transaction(2026, "October", 5, "Transfer", "Chequing", 500, sub, cat, name="TO SAVINGS",
                                     to_account_name="Savings")
    ids["lent"] = db.add_transaction(2026, "October", 6, "Expense", "Chequing", 200, food, groc, merchant="Sahar")
    db.make_loan([ids["lent"]], "Sahar")
    db.save_account_id("12345-678", "Chequing")
    ids["tag"] = tag
    return ids


def test_the_snapshot_holds_what_the_phone_shows(db, book):
    snap = build_snapshot(db, "0.26.0", now=datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc))
    assert (snap["format"], snap["version"], snap["app_version"]) == ("daftarche-phone", VERSION, "0.26.0")
    assert snap["created"] == "2026-10-20T08:00:00+00:00"

    accounts = {a["name"]: a for a in snap["accounts"]}
    assert accounts["Chequing"]["balance"] == 2200 and accounts["Savings"]["balance"] == 500
    latest = db.get_latest_account_balances()
    assert {a["id"]: a["balance"] for a in snap["accounts"]} == latest  # the desktop's own numbers
    assert snap["balances"]["months"] == ["2026-09", "2026-10"]
    assert snap["balances"]["by_account"][str(accounts["Chequing"]["id"])] == [3000, 2200]

    tx = {t["id"]: t for t in snap["transactions"]}
    assert [t["date"] for t in snap["transactions"]] == sorted((t["date"] for t in snap["transactions"]), reverse=True)
    shop = tx[book["shop"]]
    assert (shop["type"], shop["amount"], shop["merchant"], shop["note"]) == ("Expense", 100, "Maple Grocer",
                                                                              "weekly shop")
    assert [(p["amount"], p["note"]) for p in shop["parts"]] == [(70, None), (30, "soap")]
    assert shop["tags"] == [book["tag"]] and snap["tags"] == [{"id": book["tag"], "name": "Trip"}]
    assert tx[book["save"]]["type"] == "Transfer" and tx[book["save"]]["transfer"] == "matched"
    assert tx[book["save"]]["to_account"] == accounts["Savings"]["id"]
    assert tx[book["lent"]]["transfer"] == "loan" and tx[book["pay"]]["transfer"] is None

    groceries = next(c for c in snap["categories"] if c["name"] == "Groceries")
    assert groceries["type"] == "Expense" and groceries["icon"] == "🛒"
    assert groceries["subcategories"] == [{"id": shop["parts"][0]["subcategory"], "name": "Food", "icon": "🛒"}]

    assert [(e["person"], e["balance"]) for e in snap["loans"]] == [("Sahar", 200)]


def test_nothing_private_that_the_phone_does_not_need(db, book):
    text = json.dumps(build_snapshot(db))
    assert "BANK-ID-1" not in text and "12345-678" not in text  # bank ids, account numbers
    assert "fitid" not in text and "memorandum" not in text


def test_written_whole_or_not_at_all(db, book, tmp_path):
    phone = tmp_path / "phone"
    phone.mkdir()
    path = write_snapshot(db, phone, "0.26.0")
    assert path == phone / SNAPSHOT_NAME
    assert [p.name for p in phone.iterdir()] == [SNAPSHOT_NAME]  # no temporary file left
    assert json.loads(path.read_text(encoding="utf-8"))["app_version"] == "0.26.0"
    with pytest.raises(FileNotFoundError):
        write_snapshot(db, tmp_path / "gone")


def test_an_empty_book(db):
    snap = build_snapshot(db)
    assert snap["transactions"] == [] and snap["loans"] == [] and snap["balances"]["months"] == []


def test_the_window_writes_it_into_the_phone_folder(qapp, tmp_path, monkeypatch):
    from daftarche import window as W
    from daftarche.db import Database
    mine = tmp_path / "mine.db"
    db = Database(mine)
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "June", 1, "Expense", "Card", 5, us, uc, name="MY SHOP")
    db.conn.close()
    monkeypatch.setattr(W, "DB_PATH", mine)
    phone = tmp_path / "phone"
    phone.mkdir()
    win = keep(W.MainWindow())
    monkeypatch.setitem(win.settings._data, "phone_dir", "")
    assert win.write_phone_snapshot() is None  # no folder chosen: nothing, and no question
    monkeypatch.setitem(win.settings._data, "phone_dir", str(phone))
    assert win.write_phone_snapshot() == phone / SNAPSHOT_NAME
    names = [t["name"] for t in json.loads((phone / SNAPSHOT_NAME).read_text())["transactions"]]
    assert names == ["MY SHOP"]

    (phone / SNAPSHOT_NAME).unlink()
    win.viewing = mine  # Open Database…: not your own data, never sent to the phone
    assert win.write_phone_snapshot() is None and not (phone / SNAPSHOT_NAME).exists()
    win.viewing = None

    monkeypatch.setitem(win.settings._data, "phone_dir", str(tmp_path / "unplugged"))
    assert win.write_phone_snapshot() is None  # a missing folder: said in the status bar only
    assert "not written" in win.statusBar().currentMessage()
    monkeypatch.setitem(win.settings._data, "phone_dir", "")
