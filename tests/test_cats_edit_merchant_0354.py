"""0.35.4: right-click a merchant in Manage › Categories › Edit Merchant… (name and logo, as in the
Merchants tab); it stays selected under its new name. The no-merchant line has no such item."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_edit_merchant_from_categories(qapp, db):
    from daftarche.tabs.manage import ManageDialog
    db.get_or_create_account("Card")
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    sub = db.uncategorized_subcategory(food)["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", 10, sub, food, merchant="Second cup")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 5, sub, food)
    db.conn.commit()
    m = keep(ManageDialog(db, lambda: None))
    p = m.cats_panel
    types = {p.type_table.item(r, 0).text(): r for r in range(p.type_table.rowCount())}
    p.type_table.selectRow(types["Expense"])
    cats = {p.cat_table.item(r, 0).text(): r for r in range(p.cat_table.rowCount())}
    p.cat_table.selectRow(cats["Food"])
    names = [p.merchant_table.item(r, 0).text() for r in range(p.merchant_table.rowCount())]
    p.merchant_table.selectRow(names.index("Second cup"))
    menu = p._merchant_menu()
    assert menu[0][0] == "✏️  Edit Merchant…"
    dlg = mock.Mock(exec=mock.Mock(return_value=True), image=None, logo_changed=False, source="", person=False)
    dlg.name = "Second Cup"
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=dlg) as window:
        menu[0][1]()
    assert window.call_args.args[0] == "Second cup" and window.call_args.args[3] is p  # over Categories
    assert "Second Cup" in db.get_merchants() and "Second cup" not in db.get_merchants()
    chosen = p._selected_data(p.merchant_table)
    assert chosen and chosen["merchant"] == "Second Cup"
    names = [p.merchant_table.item(r, 0).text() for r in range(p.merchant_table.rowCount())]
    p.merchant_table.selectRow(names.index("(no merchant)"))
    assert all(item is None or "Edit Merchant" not in item[0] for item in p._merchant_menu())
