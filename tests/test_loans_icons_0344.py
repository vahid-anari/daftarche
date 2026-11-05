"""0.34.4: under Manage's transactions, loans show what went out and came in and what is owed;
the icon window keeps its emoji (and logos) in rows that scroll, so it stays short."""

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def loans(db):
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for who, amount, kind in (("Ali", 500, "Expense"), ("Ali", 200, "Income"), ("Sara", 100, "Income"),
                              ("Kevin", 50, "Expense")):
        db.make_loan([db.add_transaction(2026, "May", 1, kind, "Card", amount, us, uc, merchant=who)])
    db.set_loan_opening("Kevin", -50)  # owed before the records: paid back now
    db.add_transaction(2026, "May", 2, "Expense", "Card", 9, us, uc, merchant="Shop")
    db.conn.commit()
    return db


def _shown(t, filters):
    t.show(filters)
    return {lbl.text() for lbl in (t.lbl_income, t.lbl_expense, t.lbl_net, t.lbl_transfer) if not lbl.isHidden()}


def test_loans_out_in_and_owed(qapp, loans):
    from daftarche.tx_list import _ManageTransactions
    t = keep(_ManageTransactions(loans, lambda: None))
    t.resize(900, 400)
    every = {"category": ["Loans"]}
    assert _shown(t, every) == {"Out: $550.00", "In: $300.00", "They owe you: $300.00", "You owe: $100.00"}
    assert "starting balance" in t.lbl_net.toolTip()
    assert _shown(t, {"merchant": ["Ali"]}) == {"Out: $500.00", "In: $200.00", "They owe you: $300.00"}
    assert _shown(t, {"merchant": ["Kevin"]}) == {"Out: $50.00", "Settled"}  # with its starting balance
    back = _shown(t, {"merchant": ["Shop"]})  # not loans: the usual Total again
    assert back == {"Total: $9.00"} and t.lbl_net.toolTip().startswith("Spent")
    assert t.lbl_transfer.styleSheet() == ""


def test_the_icon_window_stays_short(qapp, db):
    from daftarche.icons import EMOJI_ROWS, PICKER, IconPickerDialog
    d = keep(IconPickerDialog(PICKER[-1], "Category", name="Food"))
    rows = (len(PICKER) + 7) // 8
    d.show()
    for _ in range(3):
        qapp.processEvents()
    assert rows > EMOJI_ROWS and d.emoji_area.height() < rows * 42  # the rest scrolls
    btn = d._buttons[PICKER[-1]]  # the current one, in the last row: scrolled into sight
    assert d.emoji_area.verticalScrollBar().value() > 0
    assert btn.visibleRegion().boundingRect().height() > 0
    screen = qapp.primaryScreen().availableGeometry().height()
    assert d.maximumHeight() <= screen
