"""0.34.2: Set Merchant… gives selected transactions one merchant and changes nothing else."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def rows(db):
    db.get_or_create_account("Card")
    db.get_or_create_account("Savings")
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    db.add_subcategory("Groceries", food)
    groc = db.get_subcategory_by_name("Groceries", food)["id"]
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    tools = db.uncategorized_subcategory(home)["id"]
    a = db.add_transaction(2026, "May", 1, "Expense", "Card", 30, groc, food, name="A", merchant="Old Shop")
    b = db.add_transaction(2026, "May", 2, "Expense", "Card", 20, tools, home, name="B")
    c = db.add_transaction(2026, "May", 3, "Expense", "Card", 50, groc, food, name="C", merchant="Other")
    db.set_splits(c, [(food, groc, 20, None), (home, tools, 30, None)])
    xfer = db.get_category_by_name("Internal Transfer", type_name="Transfer")
    d = db.add_transaction(2026, "May", 4, "Transfer", "Card", 100, db.uncategorized_subcategory(xfer["id"])["id"]
                           if xfer else None, xfer["id"] if xfer else None, name="D", to_account_name="Savings")
    db.conn.commit()
    return db, (a, b, c, d)


def tab(db):
    from daftarche.tabs.transactions import TransactionsTab
    t = keep(TransactionsTab(db))
    t._period._select_preset(0, emit=False, persist=False)
    t.refresh()
    return t


def state(db, tx_id):
    r = db.conn.execute("SELECT merchant, category_id, subcategory_id, type_id, amount FROM transactions WHERE id=?",
                        (tx_id,)).fetchone()
    return dict(r), db.get_splits(tx_id)


def test_one_merchant_for_several_and_nothing_else(qapp, rows):
    db, ids = rows
    t = tab(db)
    before = {i: state(db, i) for i in ids}
    every = list(range(t.model.rowCount()))
    with mock.patch("daftarche.tabs.transactions.MerchantDialog") as dialog:
        dialog.return_value.exec.return_value = True
        dialog.return_value.merchant = "Corner Store"
        t.set_merchant(every)
        shown = dialog.call_args.args[1]
    assert sorted(n or "" for n in shown) == sorted(["Old Shop", "", "Other", ""])
    for i in ids:
        (old, old_parts), (new, new_parts) = before[i], state(db, i)
        assert new["merchant"] == "Corner Store"
        assert {k: v for k, v in new.items() if k != "merchant"} == {k: v for k, v in old.items() if k != "merchant"}
        assert new_parts == old_parts  # a split one keeps its parts
    assert len(t.table.selectionModel().selectedRows()) == len(ids)  # still selected


def test_empty_takes_it_off(qapp, rows):
    db, (a, *_rest) = rows
    t = tab(db)
    r = next(i for i in range(t.model.rowCount()) if t.model.get_row(i)["id"] == a)
    with mock.patch("daftarche.tabs.transactions.MerchantDialog") as dialog:
        dialog.return_value.exec.return_value = True
        dialog.return_value.merchant = None
        t.set_merchant([r])
    assert state(db, a)[0]["merchant"] is None


def test_the_window(qapp, rows):
    from daftarche.category_dialog import MerchantDialog
    db, _ids = rows
    d = keep(MerchantDialog(db, ["Old Shop", "Old Shop"]))
    assert d.f_merchant.currentText() == "Old Shop" and d.new_merchant.isHidden()
    d.f_merchant.setCurrentText("old shop")
    with mock.patch.object(d, "accept"):
        d._accept()
    assert d.merchant == "Old Shop"  # the existing spelling
    mixed = keep(MerchantDialog(db, ["Old Shop", "", "Other"]))
    assert mixed.f_merchant.currentText() == "" and "2 have one" in mixed.note.text()
    mixed.f_merchant.setCurrentText("Brand New")
    assert not mixed.new_merchant.isHidden() and mixed.note.isHidden()


def test_in_the_right_click_menu(qapp, rows):
    db, _ids = rows
    t = tab(db)
    t.table.selectAll()
    seen = []
    with mock.patch("daftarche.tabs.transactions._exec_menu",
                    lambda menu, where: seen.extend(x.text() for x in menu.actions())):
        rect = t.table.visualRect(t.model.index(0, 0))
        t._context_menu(rect.center())
    assert "🏪  Set Merchant (4)…" in seen
