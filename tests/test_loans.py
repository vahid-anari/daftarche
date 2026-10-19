"""0.21: Transfer › Loans, the Loans window, Make It a Loan, and tools/move_loans.py."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def old_loans(db):
    """The old way: Income › Personal Loan and Expense › Debt, one sub-category per person."""
    db.add_category("Personal Loan", "Income")
    db.add_category("Debt", "Expense")
    pl = db.get_category_by_name("Personal Loan", type_name="Income")["id"]
    debt = db.get_category_by_name("Debt", type_name="Expense")["id"]
    ids = {}
    for name, cat in (("Sahar", pl), ("Sahar", debt), ("Kevin", debt), ("Fereshteh", pl), ("Fereshteh", debt)):
        db.add_subcategory(name, cat)
    sub = {(c, n): db.get_subcategory_by_name(n, c)["id"] for c in (pl, debt) for n in ("Sahar", "Kevin", "Fereshteh")
           if db.get_subcategory_by_name(n, c)}
    ids["sahar_in"] = db.add_transaction(2020, "May", 1, "Income", "Chequing", 2000, sub[(pl, "Sahar")], pl)
    ids["sahar_out"] = db.add_transaction(2021, "May", 1, "Expense", "Chequing", 2605, sub[(debt, "Sahar")], debt)
    ids["kevin_out"] = db.add_transaction(2021, "June", 1, "Expense", "Chequing", 939.22, sub[(debt, "Kevin")], debt)
    ids["fer_in"] = db.add_transaction(2022, "May", 1, "Income", "Chequing", 6025, sub[(pl, "Fereshteh")], pl)
    ids["fer_out"] = db.add_transaction(2022, "June", 1, "Expense", "Savings", 6020.83, sub[(debt, "Fereshteh")], debt)
    return ids


def _status(db, tx_id):
    return db.conn.execute("SELECT transfer_status FROM transactions WHERE id=?", (tx_id,)).fetchone()[0]


def test_make_loan_keeps_balances_and_direction(db, old_loans):
    before = db.get_latest_account_balances()
    db.make_loan([old_loans["sahar_in"], old_loans["sahar_out"]], "Sahar")
    db.make_loan([old_loans["kevin_out"]], "Kevin")
    assert db.get_latest_account_balances() == before
    rows = {r["id"]: r for r in db.conn.execute("SELECT * FROM transactions")}
    assert rows[old_loans["sahar_in"]]["account_id"] is None and rows[old_loans["sahar_in"]]["to_account_id"]
    assert rows[old_loans["sahar_out"]]["account_id"] and rows[old_loans["sahar_out"]]["to_account_id"] is None
    assert _status(db, old_loans["sahar_in"]) == "loan"
    # never matched with each other or counted as unmatched
    assert db.get_unmatched_transfer_count(2000, "January", 2030, "December") == 0
    db.match_unmatched_transfers()
    assert _status(db, old_loans["sahar_in"]) == "loan"
    sahar = next(e for e in db.get_loans() if e["merchant"] == "Sahar")
    assert (sahar["paid_out"], sahar["received"], sahar["balance"]) == (2605.0, 2000.0, 605.0)


def test_make_loan_refuses_what_it_cannot_keep(db, old_loans):
    with pytest.raises(ValueError):
        db.make_loan([old_loans["kevin_out"]])  # no person
    uc, us = db.get_uncategorized_ids()
    t = db.add_transaction(2022, "May", 1, "Transfer", "Chequing", 5, us, uc)
    with pytest.raises(ValueError):
        db.make_loan([t], "Kevin")
    assert db.get_loans() == []  # nothing changed: all or nothing


def test_a_row_moved_out_of_loans_is_a_transfer_again(db, old_loans):
    db.make_loan([old_loans["kevin_out"]], "Kevin")
    ext = db.get_category_by_name("External Transfer")["id"]
    db.update_transaction(old_loans["kevin_out"], category_id=ext)
    assert _status(db, old_loans["kevin_out"]) == "unmatched"
    db.update_transaction(old_loans["kevin_out"], category_id=db.loans_category()["id"], transfer_status="unmatched")
    assert _status(db, old_loans["kevin_out"]) == "loan"


def test_starting_balance_settle_and_totals(db, old_loans):
    for key, person in (("sahar_in", "Sahar"), ("sahar_out", "Sahar"), ("kevin_out", "Kevin"),
                        ("fer_in", "Fereshteh"), ("fer_out", "Fereshteh")):
        db.make_loan([old_loans[key]], person)
    assert db.get_loan_totals() == (4.17, 1544.22)
    db.set_loan_opening("kevin", -939.22, "lent me money years ago")
    db.set_loan_opening("Sahar", -605)
    assert db.get_loan_totals() == (4.17, 0.0)
    assert db.settle_loan("Fereshteh") == -4.17
    assert db.get_loan_totals() == (0.0, 0.0)
    assert {e["merchant"]: e["balance"] for e in db.get_loans()} == {"Fereshteh": 0.0, "Kevin": 0.0, "Sahar": 0.0}
    db.unsettle_loan("Fereshteh")
    assert db.get_loan_totals() == (4.17, 0.0)


def test_renaming_or_deleting_the_person_carries_the_loan(db, old_loans):
    db.make_loan([old_loans["kevin_out"]], "Kevin")
    db.make_loan([old_loans["sahar_in"]], "Sahar")
    db.set_loan_opening("Kevin", -900)
    db.set_loan_opening("Sahar", -100)
    db.rename_merchant("Kevin", "K. Smith")
    assert {e["merchant"]: e["opening"] for e in db.get_loans()} == {"K. Smith": -900.0, "Sahar": -100.0}
    db.rename_merchant("K. Smith", "sahar")  # a merge: the starting balances add up
    assert [(e["merchant"], e["opening"]) for e in db.get_loans()] == [("Sahar", -1000.0)]
    db.delete_merchant("Sahar")
    assert [e["merchant"] for e in db.get_loans()] == [""]  # the rows stay, with no person


def test_edit_window_keeps_one_account_and_the_direction(qapp, db, old_loans):
    from daftarche.tabs.transactions import LOAN_IN, TransactionDialog
    row = next(r for r in db.get_transactions() if r["id"] == old_loans["fer_in"])
    d = keep(TransactionDialog(db, row=dict(row)))
    d.f_type.setCurrentText("Transfer")
    d.f_category.setCurrentText("Loans")
    assert not d.f_dir.isHidden() and d.f_to_account.isHidden() and d.f_dir.currentText() == LOAN_IN
    d.f_merchant.setCurrentText("Fereshteh")
    with mock.patch.object(d, "accept"):
        d._save()
    r = db.conn.execute("SELECT * FROM transactions WHERE id=?", (old_loans["fer_in"],)).fetchone()
    assert r["account_id"] is None and r["to_account_id"] and r["transfer_status"] == "loan"
    # opened again: the account shows in Account, money in
    row = next(x for x in db.get_transactions() if x["id"] == old_loans["fer_in"])
    d = keep(TransactionDialog(db, row=dict(row)))
    assert d.f_account.currentText() == "Chequing" and d.f_dir.currentText() == LOAN_IN
    d.f_category.setCurrentText("External Transfer")  # out of Loans: the account goes back to To
    assert d.f_to_account.currentText() == "Chequing" and not d.f_account.currentText()


def test_make_it_a_loan_from_transactions(qapp, db, old_loans):
    from daftarche.tabs.transactions import TransactionsTab
    tab = keep(TransactionsTab(db))
    tab._period._select_preset(0, emit=False, persist=False)
    tab.refresh()
    rows = [i for i in range(tab.model.rowCount()) if tab.model.get_row(i)["id"] in
            (old_loans["sahar_in"], old_loans["sahar_out"])]
    with mock.patch("daftarche.tabs.transactions.QInputDialog.getItem", return_value=("sahar ", True)):
        tab.make_loans(rows)
    assert [e["merchant"] for e in db.get_loans()] == ["sahar"]


def test_loans_window(qapp, db, old_loans):
    from daftarche.loans_dialog import LoansDialog
    db.make_loan([old_loans["fer_in"], old_loans["fer_out"]], "Fereshteh")
    shown = []
    dlg = keep(LoansDialog(db, None, shown.append))
    assert "You owe $4.17" in dlg.summary.text()
    dlg.table.selectRow(0)
    assert dlg.table.item(0, dlg.COL_BAL).text() == "You owe $4.17"
    with mock.patch("daftarche.loans_dialog.QMessageBox.question", return_value=mock.ANY) as q:
        from PySide6.QtWidgets import QMessageBox
        q.return_value = QMessageBox.Yes
        dlg.toggle_settled()
    assert dlg.table.item(0, dlg.COL_BAL).text() == "Settled (wrote off $4.17)"
    assert dlg.btn_settle.text().endswith("Undo Settled")
    dlg.open_transactions()
    assert shown == ["Fereshteh"]


def test_a_refund_made_a_loan_in_the_edit_window(qapp, db):
    from daftarche.tabs.transactions import LOAN_IN, TransactionDialog
    uc, us = db.get_uncategorized_ids()
    t = db.add_transaction(2022, "May", 1, "Expense", "Chequing", -50, us, uc, merchant="Ali")
    before = db.get_latest_account_balances()
    d = keep(TransactionDialog(db, row=dict(next(r for r in db.get_transactions() if r["id"] == t))))
    d.f_type.setCurrentText("Transfer")
    d.f_category.setCurrentText("loans")  # typed: still Loans
    assert d.f_dir.currentText() == LOAN_IN and d.f_amount.text() == "50.0"
    with mock.patch.object(d, "accept"):
        d._save()
    assert db.get_latest_account_balances() == before
    assert [(e["merchant"], e["received"]) for e in db.get_loans()] == [("Ali", 50.0)]


def test_older_loans_rows_are_loans_after_the_upgrade(db, tmp_path):
    from daftarche.db import Database
    loans = db.loans_category()["id"]
    sub = db.uncategorized_subcategory(loans)["id"]
    t = db.add_transaction(2022, "May", 1, "Transfer", "Chequing", 10, sub, loans, merchant="Ali")
    db.conn.executescript(f"DROP TRIGGER trg_loan_status_ins; DROP TRIGGER trg_loan_status_upd;"
                          f"UPDATE transactions SET transfer_status='unmatched' WHERE id={t}; PRAGMA user_version = 4;")
    db.conn.commit()
    again = Database(db.path)
    try:
        assert _status(again, t) == "loan"
    finally:
        again.conn.close()


def test_only_a_transfer_is_a_loan(db):
    loans = db.loans_category()["id"]
    sub = db.uncategorized_subcategory(loans)["id"]
    t = db.add_transaction(2022, "May", 1, "Expense", "Chequing", 10, sub, loans, merchant="Ali")
    assert _status(db, t) is None


def test_window_shows_a_persons_loans(qapp, db, old_loans, monkeypatch, tmp_path):
    from daftarche import window as W
    db.make_loan([old_loans["kevin_out"]], "Kevin")
    monkeypatch.setattr(W, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(W, "startup_backup"):
        w = keep(W.MainWindow())
    w.db.conn.close()
    w.db = db
    w._rebuild_tabs()
    w._show_loan("Kevin")
    tab = w.transactions_tab
    assert [tab.model.get_row(i)["id"] for i in range(tab.model.rowCount())] == [old_loans["kevin_out"]]
    assert tab.btn_back.text() == "← Back to Loans"
    tab.go_back()
    assert w._loans_dlg is not None
    w._loans_dlg.close()
    db.make_loan([old_loans["sahar_in"]], "sahar ")  # the same person, written differently
    db.conn.execute("UPDATE transactions SET merchant='sahar ' WHERE id=?", (old_loans["sahar_in"],))
    db.make_loan([old_loans["sahar_out"]], "Sahar")
    db.conn.execute("UPDATE transactions SET merchant=NULL WHERE id=?", (old_loans["kevin_out"],))
    db.conn.commit()
    w._show_loan("Sahar")
    assert sorted(tab.model.get_row(i)["id"] for i in range(tab.model.rowCount())) == sorted(
        [old_loans["sahar_in"], old_loans["sahar_out"]])
    w._show_loan("")  # (no person): only the rows with none
    assert [tab.model.get_row(i)["id"] for i in range(tab.model.rowCount())] == [old_loans["kevin_out"]]
    w._loans_dlg and w._loans_dlg.close()


def test_move_loans_tool(db, old_loans, tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "move_loans", Path(__file__).resolve().parents[1] / "tools" / "move_loans.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    import hashlib
    import sqlite3
    path = str(db.path)
    # Kevin's row has a bank merchant: the sub-category names the person
    db.conn.execute("UPDATE transactions SET merchant='E-TRANSFER' WHERE id=?", (old_loans["kevin_out"],))
    before = db.get_latest_account_balances()
    # an older database (layout 4): a dry run must leave the file exactly as it is
    db.conn.executescript("DROP TRIGGER trg_loan_status_ins; DROP TRIGGER trg_loan_status_upd; DROP TABLE loans;"
                          "PRAGMA user_version = 4;")
    db.conn.commit()
    db.conn.close()
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    args = ["--database", path, "--i-owed", "Kevin=939.22", "--i-owed", "Sahar=605", "--settle", "Fereshteh"]
    assert tool.main(args) == 0
    out = capsys.readouterr().out
    assert "Nothing written yet" in out and "You owe $0.00 · Owed to you $0.00" in out
    assert "merchant 'E-TRANSFER' becomes 'Kevin'" in out
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == digest
    assert tool.main(["--database", path, "--settle", "Kevn"]) == 1  # a typo: nothing done
    assert "No loan for: Kevn" in capsys.readouterr().out
    assert tool.main(args + ["--apply"]) == 0
    backups = sorted((Path(__import__("os").environ["DAFTARCHE_HOME"])).rglob("daftarche-before-loans-*.db"))
    raw = sqlite3.connect(backups[-1])
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 4  # the backup is the file as it was
    raw.close()
    from daftarche.db import Database
    after = Database(path)
    try:
        assert after.get_latest_account_balances() == before
        assert after.get_loan_totals() == (0.0, 0.0)
        assert sorted(e["merchant"] for e in after.get_loans()) == ["Fereshteh", "Kevin", "Sahar"]
        assert after.get_category_by_name("Debt", type_name="Expense") is None
    finally:
        after.conn.close()
