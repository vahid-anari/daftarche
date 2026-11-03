"""0.35.0: Manage's sums wrap, list buttons stay at the list, Categories' transactions under all
the lists with Total columns, a split transaction's share in the category shown, Balance Check."""

import pytest
from PySide6.QtCore import Qt

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def money_db(db):
    db.get_or_create_account("Chequing")
    db.get_or_create_account("Card")
    db.get_or_create_account("Savings")
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    db.add_subcategory("Groceries", food)
    groc = db.get_subcategory_by_name("Groceries", food)["id"]
    db.add_category("Paid for Others", "Expense")
    others = db.get_category_by_name("Paid for Others", type_name="Expense")["id"]
    db.add_subcategory("Zahra", others)
    zahra = db.get_subcategory_by_name("Zahra", others)["id"]
    db.add_category("Pay", "Income")
    pay = db.get_category_by_name("Pay", type_name="Income")["id"]
    salary = db.uncategorized_subcategory(pay)["id"]
    ext = db.get_category_by_name("External Transfer", type_name="Transfer")
    ext_sub = db.uncategorized_subcategory(ext["id"])["id"]
    ids = {}
    ids["start"] = db.add_transaction(2026, "January", 1, "Transfer", None, 1000, ext_sub, ext["id"],
                                      to_account_name="Chequing")  # the starting money, from outside
    ids["pay"] = db.add_transaction(2026, "January", 5, "Income", "Chequing", 2000, salary, pay, merchant="Employer")
    ids["shop"] = db.add_transaction(2026, "January", 6, "Expense", "Card", 100, groc, food, merchant="Shop")
    db.set_splits(ids["shop"], [(food, groc, 60, None), (others, zahra, 40, None)])
    ids["move"] = db.add_transaction(2026, "January", 7, "Transfer", "Chequing", 300, ext_sub, ext["id"],
                                     to_account_name="Savings")
    db.make_loan([db.add_transaction(2026, "January", 8, "Expense", "Chequing", 50, groc, food, merchant="Ali")])
    ids["nodate"] = db.add_transaction(2026, "January", 9, "Expense", None, 5, groc, food, merchant="Cash")
    db.conn.commit()
    return db, ids


# ── 1. the sums go on to a second line ─────────────────────────────────────────
def test_the_sums_wrap_so_the_line_can_go_further(qapp, money_db):
    from daftarche.tx_list import _ManageTransactions
    db, _ = money_db
    t = keep(_ManageTransactions(db, lambda: None, total=False))
    t.show({"account": ["Chequing"]})
    wide = t.sums.sizeHint().width()
    assert t.minimumSizeHint().width() < wide  # narrower than the sums in one line
    flow = t.sums.layout()
    assert flow.heightForWidth(wide) < flow.heightForWidth(wide // 3)  # narrow: more lines


# ── 2. the buttons stay at the list's corner ───────────────────────────────────
def test_the_title_line_is_as_wide_as_the_list(qapp, money_db):
    from daftarche.tabs.manage import ManageDialog
    db, _ = money_db
    dlg = keep(ManageDialog(db, lambda: None))
    dlg.resize(1400, 700)
    dlg.show()
    for panel in (dlg.accounts_panel, dlg.tags_panel):
        panel.set_show_lines(False)
        qapp.processEvents()
        box = panel.table.parentWidget()
        assert box.width() <= panel.table.width() + 2 and box.width() < 1000


# ── 3. Categories: the transactions under the lists; Total columns ────────────
def test_categories_transactions_below_and_totals(qapp, money_db):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import ManageDialog
    from daftarche.tx_list import SHOW_KEY
    db, _ = money_db
    get_settings()._data[SHOW_KEY] = True
    p = keep(ManageDialog(db, lambda: None)).cats_panel
    assert p.split.orientation() == Qt.Vertical and p.split.widget(1) is p.lines
    headers = lambda table: [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    assert headers(p.type_table)[-1] == headers(p.cat_table)[-1] == headers(p.sub_table)[-1] == "Total"
    types = {p.type_table.item(r, 0).text(): p.type_table.item(r, 3).text() for r in range(p.type_table.rowCount())}
    assert types["Expense"] == "$105.00" and types["Income"] == "$2,000.00" and types["Transfer"] == "—"
    expense = next(r for r in range(p.type_table.rowCount()) if p.type_table.item(r, 0).text() == "Expense")
    p.type_table.selectRow(expense)
    cats = {p.cat_table.item(r, 0).text(): r for r in range(p.cat_table.rowCount())}
    assert p.cat_table.item(cats["Food"], 3).text() == "$65.00"  # its part of the split one, and the $5
    assert p.cat_table.item(cats["Paid for Others"], 3).text() == "$40.00"
    p.cat_table.selectRow(cats["Paid for Others"])
    subs = {p.sub_table.item(r, 0).text(): p.sub_table.item(r, 4).text() for r in range(p.sub_table.rowCount())}
    assert subs["Zahra"] == "$40.00"


# ── 4. a split transaction's share ─────────────────────────────────────────────
def test_a_split_share_in_the_category_shown(qapp, money_db):
    from daftarche.tabs.transactions import COL_AMOUNT, COL_CAT, COL_SUBCAT, cell_text
    from daftarche.tx_list import _ManageTransactions
    db, ids = money_db
    t = keep(_ManageTransactions(db, lambda: None))
    t.show({"category": ["Paid for Others"], "subcategory": ["Zahra"]})
    m = t.model
    r = next(i for i in range(m.rowCount()) if m.get_row(i)["id"] == ids["shop"])
    cell = lambda c: m.data(m.index(r, c), Qt.DisplayRole)
    assert cell(COL_AMOUNT) == "$40.00 of $100.00"
    assert cell(COL_CAT) == "Paid for Others" and cell(COL_SUBCAT) == "Zahra"
    assert "$40.00 of its $100.00" in m.data(m.index(r, COL_AMOUNT), Qt.ToolTipRole)
    assert t.lbl_net.text() == "Total: $40.00"
    t.table.selectRow(r)
    assert "40.00" in t.lbl_selected_sum.text() and "100.00" not in t.lbl_selected_sum.text()
    for c in range(m.columnCount()):
        assert cell(c) == cell_text(m.get_row(r), c)
    t.show({"merchant": ["Shop"]})  # not narrowed by category: the whole of it, "Split (2)"
    r = 0
    assert cell(COL_AMOUNT) == "$100.00" and cell(COL_CAT) == "Split (2)"


# ── 5. Balance Check ───────────────────────────────────────────────────────────
def test_balance_check_adds_up(qapp, money_db):
    from daftarche.balance_check import BalanceCheckDialog, lines
    db, _ = money_db
    b = db.balance_breakdown()
    assert b["spent"] == 100 + 5 - 2000  # expenses − income of all of them: the Merchants' Total
    assert b["no_account"] == -5.0 and b["between"] == 300.0
    assert b["transfers"]["External Transfer"] == {"in": 1000.0, "out": 0.0}
    assert b["transfers"]["Loans"] == {"in": 0.0, "out": 50.0}
    assert b["computed"] == b["balance"] == 1000 + 2000 - 100 - 50
    assert b["accounts"][db.get_account_by_name("Savings")["id"]]["balance"] == 300.0
    steps = [what for what, _a, _w in lines(b)]
    assert "Transfer › Loans: out" in steps and "Moved between your accounts" in steps
    d = keep(BalanceCheckDialog(db))
    assert "agree" in d.verdict.text()


def test_merchants_total_is_the_first_line(qapp, money_db):
    """The first step of Balance Check is the line under Manage › Merchants (with nothing searched)."""
    from daftarche.tabs.manage import ManageDialog
    from daftarche.widgets import money
    db, _ = money_db
    mp = keep(ManageDialog(db, lambda: None)).merchants_panel
    b = db.balance_breakdown()
    assert mp.totals.item(0, mp.COL_TOTAL).text() == money(b["spent"]) == money(b["merchants_total"])
