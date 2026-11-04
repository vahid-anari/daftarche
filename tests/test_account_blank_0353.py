"""0.35.3: an income can be made a transfer from outside: the edit window's Account can be empty."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_income_into_a_transfer_from_outside(qapp, db):
    from daftarche.tabs.transactions import TransactionDialog
    db.get_or_create_account("Chequing")
    uc, us = db.get_uncategorized_ids()
    tx = db.add_transaction(2026, "May", 1, "Income", "Chequing", 5000, us, uc, merchant="Wallet")
    db.conn.commit()
    row = next(r for r in db.get_transactions() if r["id"] == tx)
    d = keep(TransactionDialog(db, row))
    assert d.f_account.findText("") == 0 and d.f_account.currentText() == "Chequing"
    d.f_type.setCurrentText("Transfer")
    d.f_account.setCurrentText("")
    d.f_to_account.setCurrentText("Chequing")
    d.f_category.setCurrentText("External Transfer")
    with mock.patch.object(d, "accept"):
        d._save()
    r = db.conn.execute("SELECT account_id, to_account_id, amount FROM transactions WHERE id=?", (tx,)).fetchone()
    assert r["account_id"] is None and r["to_account_id"] == db.get_account_by_name("Chequing")["id"]
    assert db.get_current_total_balance() == 5000  # the balance as before


def test_an_income_still_needs_its_account(qapp, db):
    from daftarche.tabs.transactions import TransactionDialog
    db.get_or_create_account("Chequing")
    uc, us = db.get_uncategorized_ids()
    tx = db.add_transaction(2026, "May", 1, "Income", "Chequing", 50, us, uc)
    db.conn.commit()
    d = keep(TransactionDialog(db, next(r for r in db.get_transactions() if r["id"] == tx)))
    d.f_account.setCurrentText("")
    with mock.patch.object(d, "accept") as accepted, mock.patch("daftarche.tabs.transactions.QMessageBox") as box:
        d._save()
    assert not accepted.called and box.warning.called or box.critical.called
    new = keep(TransactionDialog(db, None))
    assert new.f_account.currentText() == "Chequing"  # a new one: the first account, as before
