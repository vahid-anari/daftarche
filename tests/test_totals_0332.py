"""0.33.2: one Total under the transactions in Manage (Categories, Merchants, Tags), coloured by
what it means, as the Total columns are; the list of merchants as wide as its contents."""

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shop(db):
    db.get_or_create_account("Card")
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    db.add_subcategory("Tools", home)
    tools = db.get_subcategory_by_name("Tools", home)["id"]
    db.add_category("Pay", "Income")
    pay = db.get_category_by_name("Pay", type_name="Income")["id"]
    salary = db.uncategorized_subcategory(pay)["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", 50, tools, home, name="HDW", merchant="Hardware")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 80, tools, home, name="HDW BACK", merchant="Hardware")
    db.conn.execute("UPDATE transactions SET amount = -80 WHERE name = 'HDW BACK'")  # money back, more than spent
    db.add_transaction(2026, "May", 3, "Expense", "Card", 20, tools, home, name="SHOP", merchant="Shop")
    db.add_transaction(2026, "May", 4, "Income", "Card", 900, salary, pay, name="PAY", merchant="Employer")
    db.conn.commit()
    return db


def manage(db):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import ManageDialog
    from daftarche.tx_list import SHOW_KEY
    get_settings()._data[SHOW_KEY] = True
    return keep(ManageDialog(db, lambda: None))


def colour(brush_or_label):
    from daftarche.style import get_settings
    s = get_settings()
    return {s.get("expense").lower(): "red", s.get("income").lower(): "green"}.get(
        brush_or_label.color().name().lower(), "other")


def test_one_total_coloured_by_what_it_means(qapp, shop):
    m = manage(shop).merchants_panel
    for name, text, kind in (("Hardware", "Total: -$30.00", "green"), ("Shop", "Total: $20.00", "red"),
                             ("Employer", "Total: -$900.00", "green")):
        m.select(name)
        tx = m.lines.tx
        assert tx.lbl_net.text() == text and tx.lbl_income.isHidden() and tx.lbl_expense.isHidden()
        assert shop_colour({"green": "income", "red": "expense"}[kind]) in tx.lbl_net.styleSheet()


def shop_colour(key):
    from daftarche.style import get_settings
    return get_settings().get(key)


def test_the_total_columns_take_the_same_colours(qapp, shop):
    m = manage(shop).merchants_panel
    rows = {m.table.item(r, m.COL_NAME).text(): r for r in range(m.table.rowCount())}
    assert colour(m.table.item(rows["Shop"], m.COL_TOTAL).foreground()) == "red"
    assert colour(m.table.item(rows["Hardware"], m.COL_TOTAL).foreground()) == "green"
    assert colour(m.table.item(rows["Employer"], m.COL_TOTAL).foreground()) == "green"
    assert colour(m.totals.item(0, m.COL_TOTAL).foreground()) == "green"  # -$910 in all
    m.select("Employer")
    assert colour(m.used.item(0, m.U_TOTAL).foreground()) == "green"  # income: money in


def test_accounts_keep_the_four_sums(qapp, shop):
    dlg = manage(shop)
    a = dlg.accounts_panel
    a.refresh()
    a.table.selectRow(0)
    tx = a.lines.tx
    assert tx.lbl_net.text().startswith("Net:") and not tx.lbl_income.isHidden() and not tx.lbl_expense.isHidden()


def test_the_merchants_list_is_as_wide_as_its_contents(qapp, shop):
    dlg = manage(shop)
    m = dlg.merchants_panel
    dlg.tabs.setCurrentWidget(m)
    dlg.resize(1300, 800)
    dlg.show()
    qapp.processEvents()
    narrow = (m._left.width(), m.table.columnWidth(m.COL_NAME))
    dlg.resize(1900, 800)
    qapp.processEvents()
    assert (m._left.width(), m.table.columnWidth(m.COL_NAME)) == narrow  # the window does not stretch it
    shop.add_transaction(2026, "May", 5, "Expense", "Card", 1, None, None, name="X",
                         merchant="A merchant with a really very long name that goes on and on")
    m.refresh()
    assert m.table.columnWidth(m.COL_NAME) == m.NAME_MAX  # at most
    long_row = next(r for r in range(m.table.rowCount()) if m.table.item(r, m.COL_NAME).text().startswith("A merchant"))
    assert m.table.item(long_row, m.COL_NAME).toolTip().endswith("on and on")
    m.find.setText("shop")
    assert m.table.columnWidth(m.COL_NAME) == m.NAME_MAX  # looking for one does not change it
    dlg.hide()
