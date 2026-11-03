"""0.34.1: the transactions in Manage size their columns from every row, so a long text far down
the list is not cut with "…" (Qt's ResizeToContents looked at the first rows only, for speed)."""

import pytest
from PySide6.QtCore import Qt

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def many(db):
    db.get_or_create_account("Card")
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    db.add_subcategory("Tools", home)
    tools = db.get_subcategory_by_name("Tools", home)["id"]
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    plain = db.uncategorized_subcategory(food)["id"]
    for i in range(300):
        db.add_transaction(2026, "May", 1 + i % 28, "Expense", "Card", 10 + i, tools, home,
                           name="SHOP", memorandum="SHORT", merchant="Shop")
    long_memo = "E-TRANSFER 105357600152;A VERY LONG NAME OF SOMEONE;Internet Banking"
    tx = db.add_transaction(2020, "January", 1, "Expense", "Card", 30, plain, food,  # the oldest: last
                            name="LAST", memorandum=long_memo, merchant="A Merchant With A Long Name")
    db.conn.commit()
    return db, tx, long_memo


def test_a_long_text_far_down_is_not_cut(qapp, many):
    from daftarche.tabs.transactions import COL_MEMO, COL_MERCHANT, COL_SUBCAT
    from daftarche.tx_list import _ManageTransactions
    db, _tx, long_memo = many
    t = keep(_ManageTransactions(db, lambda: None))
    t._visible_columns = {**t._visible_columns, "memo": True, "merchant": True}
    t.show({"type": []})
    model, table = t.model, t.table
    last = model.rowCount() - 1
    assert model.data(model.index(last, COL_MEMO), Qt.DisplayRole) == long_memo  # far below the first rows
    for col in (COL_MEMO, COL_MERCHANT):
        need = max(table.sizeHintForIndex(model.index(r, col)).width() for r in range(model.rowCount()))
        assert table.columnWidth(col) >= need
    assert model.data(model.index(last, COL_SUBCAT), Qt.DisplayRole) == "—"  # no sub-category


def test_the_text_measured_is_the_text_shown(qapp, many):
    from daftarche.tabs.transactions import cell_text
    from daftarche.tx_list import _ManageTransactions
    db, tx, _memo = many
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    db.set_splits(tx, [(home, None, 10, None), (food, None, 20, None)])
    db.conn.commit()
    t = keep(_ManageTransactions(db, lambda: None))
    t.show({"type": []})
    m = t.model
    for r in range(m.rowCount()):
        for c in range(m.columnCount()):
            assert m.data(m.index(r, c), Qt.DisplayRole) == cell_text(m.get_row(r), c)
