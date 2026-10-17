"""The SQLite layer on a fresh database."""

from daftarche.db import Database, round2


def add(db, month, day, type_name, amount, account="Person-Bank-Checking", fitid=None, to_account=None):
    return db.add_transaction(2026, month, day, type_name, account, amount, None, None,
                              name="test", fitid=fitid, to_account_name=to_account)


def test_default_types_seeded(db):
    names = {row["name"] for row in db.get_types()}
    assert {"Income", "Expense", "Transfer"} <= names


def test_reopen_is_idempotent(tmp_path):
    path = tmp_path / "again.db"
    first = Database(path)
    add(first, "March", 1, "Income", 10)
    first.conn.close()
    second = Database(path)
    assert len(second.get_types()) == 3
    assert second.get_dashboard_summary(2026, "March", 2026, "March")["tx_count"] == 1
    second.conn.close()


def test_dashboard_summary(db):
    add(db, "January", 5, "Income", 1000)
    add(db, "January", 15, "Expense", 42.505)
    add(db, "February", 1, "Expense", 10)
    summary = db.get_dashboard_summary(2026, "January", 2026, "January")
    assert summary == {"income": 1000.0, "expense": 42.51, "net": 957.49, "tx_count": 2}


def test_fitid_duplicate_detection(db):
    add(db, "January", 5, "Income", 1000, fitid="TEST0001")
    assert db.fitid_exists("TEST0001", "Person-Bank-Checking")
    assert not db.fitid_exists("TEST0001", "Person-Bank-Saving")
    assert not db.fitid_exists("TEST9999", "Person-Bank-Checking")
    assert not db.fitid_exists(None, "Person-Bank-Checking")


def test_transfer_fitid_found_on_both_sides(db):
    add(db, "January", 20, "Transfer", 200, fitid="A1|B1",
        account="Person-Bank-Checking", to_account="Person-Bank-Saving")
    assert db.fitid_exists("A1", "Person-Bank-Checking")
    assert db.fitid_exists("B1", "Person-Bank-Saving")


def test_update_and_delete(db):
    tx = add(db, "January", 5, "Expense", 20)
    db.update_transaction(tx, amount=25, month="February")
    assert db.get_dashboard_summary(2026, "February", 2026, "February")["expense"] == 25.0
    db.delete_transaction(tx)
    assert db.get_dashboard_summary(2026, "January", 2026, "December")["tx_count"] == 0


def test_tags_cascade_on_delete(db):
    tx = add(db, "January", 5, "Expense", 20)
    tag = db.add_tag("trip")
    db.set_tags_for_transaction(tx, [tag])
    assert db.get_transaction_count_for_tag(tag) == 1
    db.delete_transaction(tx)
    assert db.get_transaction_count_for_tag(tag) == 0


def test_round2_half_up():
    assert round2(2.675) == 2.68
    assert round2(0.125) == 0.13
