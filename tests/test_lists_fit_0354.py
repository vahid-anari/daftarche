"""0.35.4: Manage › Categories' lists are never cut (a longer name chosen after another type, a
list long enough for its scroll bar), a long list scrolls in a short window, and the columns of
the transactions under them have a few pixels to spare."""

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def settle(app):
    for _ in range(6):
        app.processEvents()


def test_lists_fit_their_text_and_scroll(qapp, db):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import ManageDialog
    from daftarche.tx_list import SHOW_KEY
    db.get_or_create_account("Card")
    db.add_category("Bank", "Income")
    for i in range(25):
        db.add_category(f"A rather long expense category {i}", "Expense")
    db.conn.commit()
    get_settings()._data[SHOW_KEY] = True
    m = keep(ManageDialog(db, lambda: None))
    m.resize(900, 560)
    m.show()
    p = m.cats_panel
    m.tabs.setCurrentWidget(p.parentWidget() if m.tabs.indexOf(p) < 0 else p)
    settle(qapp)
    types = {p.type_table.item(r, 0).text(): r for r in range(p.type_table.rowCount())}
    p.type_table.selectRow(types["Income"])
    settle(qapp)
    p.type_table.selectRow(types["Expense"])  # longer names than the Income ones, and many
    settle(qapp)
    for table in (p.type_table, p.cat_table, p.sub_table):
        columns = sum(table.columnWidth(c) for c in range(table.columnCount()))
        assert table.viewport().width() >= columns, table.objectName()
        assert table.geometry().right() < table.parentWidget().width() + 1  # not cut by its column
    t = p.cat_table
    assert t.verticalScrollBar().maximum() > 0  # a long list in a short window: it scrolls
    assert t.height() < t.verticalHeader().length()


def test_columns_below_have_room_to_spare(qapp, db):
    from daftarche.tabs.transactions import COL_DATE
    from daftarche.tx_list import SLACK, TransactionList
    db.get_or_create_account("Wallet")
    cat, sub = db.get_transfer_cat_sub(description="x", matched=True)
    db.add_transaction(2023, "August", 21, "Transfer", None, 5000, sub, cat, to_account_name="Wallet")
    db.conn.commit()
    lines = keep(TransactionList(db, lambda: None))
    lines.show_transactions("Wallet", {"type": ["Transfer"]})
    t = lines.tx.table
    need = t.sizeHintForIndex(t.model().index(0, COL_DATE)).width()
    assert t.columnWidth(COL_DATE) >= need + SLACK
