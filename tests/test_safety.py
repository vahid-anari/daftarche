"""Batch A (0.5.0): writes are all-or-nothing, restore is checked, edits and imports never touch the wrong rows."""

import sqlite3
from unittest import mock

import pytest
from conftest import answer_import

from daftarche import backup
from daftarche.db import Database


def add(db, type_name="Expense", account="Person-Bank-Checking", to_account=None, amount=10, fitid=None):
    cat_id, sub_id = db.get_uncategorized_ids()
    return db.add_transaction(2026, "January", 5, type_name, account, amount, sub_id, cat_id,
                              name="test", fitid=fitid, to_account_name=to_account)


def rows(db):
    return {r["id"]: r for r in db.get_transactions()}


# ── transactions ─────────────────────────────────────────────────────────────

def test_failed_method_leaves_nothing_behind(db):
    """A merge whose last step fails used to leave the first steps pending, and the next
    unrelated save committed them (transactions moved, old account still there)."""
    add(db, account="A")
    add(db, account="B")
    db.conn.execute("CREATE TRIGGER keep BEFORE DELETE ON accounts BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(sqlite3.DatabaseError, match="blocked"):
        db.rename_account("A", "B")
    db.add_tag("later")
    accounts = {r["account"] for r in db.get_transactions()}
    assert accounts == {"A", "B"}


def test_transaction_rolls_back_everything(db):
    with pytest.raises(RuntimeError):
        with db.transaction():
            add(db)
            db.set_tags_for_transaction(add(db), [])
            raise RuntimeError("boom")
    assert rows(db) == {}


def test_nested_atomic_methods_commit_once_at_the_end(db):
    with db.transaction():
        add(db)
        db.add_tag("x")
        assert db.conn.in_transaction
    assert not db.conn.in_transaction
    assert len(rows(db)) == 1


def test_update_with_empty_account_creates_no_account(db):
    tx = add(db, type_name="Transfer", account=None, to_account="B")
    db.update_transaction(tx, account_name=None, to_account_name="B", name="edited")
    assert "" not in {a["name"] for a in db.get_accounts()}
    assert rows(db)[tx]["account"] is None


# ── restore ──────────────────────────────────────────────────────────────────

@pytest.fixture
def backups(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    return tmp_path / "backups"


def test_restore_rejects_a_file_that_is_not_a_database(db, tmp_path, backups):
    add(db)
    bad = tmp_path / "notes.db"
    bad.write_text("hello")
    with pytest.raises(ValueError, match="not a database"):
        backup.restore_backup(db.conn, bad)
    assert len(rows(db)) == 1
    assert not backups.exists()


def test_restore_rejects_a_foreign_database(db, tmp_path, backups):
    other = tmp_path / "other.db"
    sqlite3.connect(other).execute("CREATE TABLE x (y)").connection.commit()
    with pytest.raises(ValueError, match="not a Daftarche database"):
        backup.restore_backup(db.conn, other)


def test_restore_keeps_a_copy_of_the_replaced_data(db, tmp_path, backups):
    saved = tmp_path / "saved.db"
    add(db, amount=1)
    backup.copy_db(db.conn, saved)
    add(db, amount=2)
    safety = backup.restore_backup(db.conn, saved)
    assert [r["amount"] for r in db.get_transactions()] == [1.0]
    before = Database(safety)
    assert sorted(r["amount"] for r in before.get_transactions()) == [1.0, 2.0]
    before.conn.close()


# ── edit dialog ──────────────────────────────────────────────────────────────

@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def edit_memo_and_save(qapp, db, tx_id):
    from daftarche.tabs.transactions import TransactionDialog
    dialog = TransactionDialog(db, rows(db)[tx_id])
    dialog.f_memo.setText("edited")
    with mock.patch("daftarche.tabs.transactions.QMessageBox.warning") as warning:
        dialog._save()
    assert not warning.called, warning.call_args
    return rows(db)[tx_id]


def test_edit_keeps_uncategorized(qapp, db):
    db.add_category("Auto", "Expense")
    db.add_subcategory("Gas", db.get_category_by_name("Auto")["id"])
    row = edit_memo_and_save(qapp, db, add(db))
    assert (row["category"], row["subcategory"], row["memorandum"]) == ("Uncategorized", "Uncategorized", "edited")


def test_edit_keeps_a_closed_account(qapp, db):
    add(db, account="Open")
    tx = add(db, account="Closed")
    db.update_account(db.get_account_by_name("Closed")["id"], active=0)
    assert edit_memo_and_save(qapp, db, tx)["account"] == "Closed"


def test_edit_keeps_an_incoming_transfer_unmatched(qapp, db):
    add(db, account="Other")
    tx = add(db, type_name="Transfer", account=None, to_account="Savings")
    db.update_transaction(tx, transfer_status="unmatched")
    row = edit_memo_and_save(qapp, db, tx)
    assert (row["account"], row["to_account"], row["transfer_status"]) == (None, "Savings", "unmatched")


# ── import ───────────────────────────────────────────────────────────────────

QFX = (__import__("pathlib").Path(__file__).parent / "data" / "sample.qfx").read_text(encoding="cp1252")


def import_tab(db, tmp_path, content, account):
    from daftarche.tabs.import_tab import ImportTab
    tab = ImportTab(db, lambda: None)
    path = tmp_path / "statement.qfx"
    path.write_text(content, encoding="cp1252")
    with mock.patch("daftarche.tabs.import_tab.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
         mock.patch.object(tab, "_ask_account", return_value=account):
        tab._browse_ofx()
    return tab


def test_empty_second_file_does_not_import_the_first_one(qapp, db, tmp_path):
    db.get_or_create_account("Checking")
    db.get_or_create_account("Savings")
    tab = import_tab(db, tmp_path, QFX, "Checking")
    assert len(tab.parsed_rows) == 3
    empty = QFX.split("<STMTTRN>")[0] + "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
    path = tmp_path / "empty.qfx"
    path.write_text(empty.replace("<ACCTID>0000000", "<ACCTID>999"), encoding="cp1252")
    with mock.patch("daftarche.tabs.import_tab.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
         mock.patch.object(tab, "_ask_account", return_value="Savings"):
        tab._browse_ofx()
    assert tab.parsed_rows == []
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        answer_import(box)
        tab.import_all()
    assert rows(db) == {}


def test_failed_import_imports_nothing(qapp, db, tmp_path):
    db.get_or_create_account("Checking")
    tab = import_tab(db, tmp_path, QFX, "Checking")
    real_add = db.add_transaction
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise sqlite3.OperationalError("disk I/O error")
        return real_add(*args, **kwargs)

    with mock.patch.object(db, "add_transaction", side_effect=flaky), \
         mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        answer_import(box)
        tab.import_all()
    assert box.critical.called
    assert rows(db) == {}
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        answer_import(box)
        tab.import_all()
    assert len(rows(db)) == 3


def test_impossible_dates_are_not_parsed():
    from daftarche.tabs.import_tab import parse_ofx
    assert len(parse_ofx(QFX.replace("20260105", "20260230"))) == 2
