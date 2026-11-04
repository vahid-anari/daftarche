"""0.35.1: Manage › Categories shows what has no category ("(no category)", last in each type's
categories) and a category's "Uncategorized" as "(no sub-category)", only when something is in it."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def mixed(db):
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    db.add_subcategory("Groceries", food)
    groc = db.get_subcategory_by_name("Groceries", food)["id"]
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    db.uncategorized_subcategory(home)  # an empty "Uncategorized": not shown
    db.add_transaction(2026, "May", 1, "Expense", "Card", 30, us, uc, merchant="Shop")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 20, us, uc)
    db.add_transaction(2026, "May", 3, "Income", "Card", 500, us, uc, merchant="Boss")
    db.add_transaction(2026, "May", 4, "Expense", "Card", 9, db.uncategorized_subcategory(food)["id"], food,
                       merchant="Market")
    db.add_transaction(2026, "May", 5, "Expense", "Card", 5, groc, food, merchant="Market")
    db.conn.commit()
    return db


def panel(db):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import ManageDialog
    from daftarche.tx_list import SHOW_KEY
    get_settings()._data[SHOW_KEY] = True
    p = keep(ManageDialog(db, lambda: None)).cats_panel
    expense = next(r for r in range(p.type_table.rowCount()) if p.type_table.item(r, 0).text() == "Expense")
    p.type_table.selectRow(expense)
    return p


def rows(table, *cols):
    return {table.item(r, 0).text(): [table.item(r, c).text() for c in cols] for r in range(table.rowCount())}


def test_no_category_last_with_its_numbers(qapp, mixed):
    from daftarche.tabs.manage import NO_CATEGORY
    p = panel(mixed)
    names = [p.cat_table.item(r, 0).text() for r in range(p.cat_table.rowCount())]
    assert names[-1] == NO_CATEGORY and "Uncategorized" not in names
    assert rows(p.cat_table, 1, 3)[NO_CATEGORY] == ["2", "$50.00"]  # the expenses only, not the income
    p.cat_table.selectRow(names.index(NO_CATEGORY))
    merchants = [p.merchant_table.item(r, 0).text() for r in range(p.merchant_table.rowCount())]
    assert merchants == ["Shop", "(no merchant)"] and p.sub_table.rowCount() == 0
    assert p.lines.tx.model.rowCount() == 2 and "(no category)" in p.lines.title.text()


def test_no_sub_category_only_when_used(qapp, mixed):
    from daftarche.tabs.manage import NO_SUB
    p = panel(mixed)
    cats = [p.cat_table.item(r, 0).text() for r in range(p.cat_table.rowCount())]
    p.cat_table.selectRow(cats.index("Food"))
    subs = [p.sub_table.item(r, 0).text() for r in range(p.sub_table.rowCount())]
    assert subs == ["Groceries", NO_SUB]
    p.cat_table.selectRow(cats.index("Home"))
    assert p.sub_table.rowCount() == 0  # its "Uncategorized" is empty: not shown


def test_they_are_not_renamed_or_deleted(qapp, mixed):
    from daftarche.tabs.manage import NO_CATEGORY
    p = panel(mixed)
    cats = [p.cat_table.item(r, 0).text() for r in range(p.cat_table.rowCount())]
    p.cat_table.selectRow(cats.index(NO_CATEGORY))
    with mock.patch("daftarche.tabs.manage.QMessageBox.information") as told, \
            mock.patch("daftarche.tabs.manage.IconPickerDialog") as picker, \
            mock.patch("daftarche.tabs.manage.QMessageBox.question") as asked:
        p._rename_cat()
        p._delete_cat()
        p._add_sub()
    assert told.call_count == 3 and not picker.called and not asked.called
    p.cat_table.selectRow(cats.index("Food"))
    p.sub_table.selectRow(p.sub_table.rowCount() - 1)
    with mock.patch("daftarche.tabs.manage.QMessageBox.information") as told, \
            mock.patch("daftarche.tabs.manage.QMessageBox.question") as asked:
        p._delete_sub()
        p._rename_sub()
    assert told.call_count == 2 and not asked.called
