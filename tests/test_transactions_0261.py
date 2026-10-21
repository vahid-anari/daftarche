"""0.26.1: the Merchant filter, whole-row selection, and Manage's buttons drawn whole."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(qapp, db):
    from daftarche.tabs.transactions import TransactionsTab
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Expense", "Card", 40, us, uc, name="WALMART #1", merchant="Walmart")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 9, us, uc, name="TIM HORTONS", merchant="Tim Hortons")
    db.add_transaction(2026, "May", 3, "Expense", "Card", 5, us, uc, name="PURCHASE INTEREST")
    db.save_mapping("Expense", None, name="COSTCO", subcategory_id=us, category_id=uc, merchant="Costco")  # a rule only
    t = keep(TransactionsTab(db))
    t._period._select_preset(0, emit=False, persist=False)  # All
    t.refresh()
    return t


def _names(t):
    return sorted(t.model.get_row(i)["name"] for i in range(t.model.rowCount()))


# ── the Merchant filter ──────────────────────────────────────────────────────
def test_the_merchant_box_lists_merchants_with_transactions(tab):
    from daftarche.tabs.transactions import NO_MERCHANT
    assert tab.f_merchant._items == [NO_MERCHANT, "Tim Hortons", "Walmart"]  # not Costco: a rule only


def test_ticking_merchants_filters(tab):
    from daftarche.tabs.transactions import NO_MERCHANT
    tab.f_merchant.set_selected(["Walmart", "Tim Hortons"])
    tab._on_any_filter_changed()
    assert _names(tab) == ["TIM HORTONS", "WALMART #1"]
    tab.f_merchant.set_selected([NO_MERCHANT])
    tab._on_any_filter_changed()
    assert _names(tab) == ["PURCHASE INTEREST"]
    tab.reset_filters()
    assert tab.f_merchant.get_selected() == [] and len(_names(tab)) == 3


def test_the_merchant_stays_ticked_after_a_refresh(tab):
    tab.f_merchant.set_selected(["Walmart"])
    tab._on_any_filter_changed()
    tab.refresh()
    assert tab.f_merchant.get_selected() == ["Walmart"] and _names(tab) == ["WALMART #1"]


def test_a_jump_ticks_the_merchant_where_you_can_see_it(tab):
    back = mock.Mock()
    tab.show_matching(merchants=["Walmart"], came_from=("Manage", back), text="<b>Walmart</b>")
    assert tab.f_merchant.get_selected() == ["Walmart"] and _names(tab) == ["WALMART #1"]
    assert not tab.nav_bar.isHidden()
    tab.f_merchant.clear_selection()  # widened by hand: an ordinary list again
    tab._on_any_filter_changed()
    assert len(_names(tab)) == 3 and tab.nav_bar.isHidden()


def test_a_jump_to_rows_with_no_merchant(tab):
    from daftarche.tabs.transactions import NO_MERCHANT
    tab.show_matching(merchants=[""], came_from=("Loans", mock.Mock()))
    assert tab.f_merchant.get_selected() == [NO_MERCHANT] and _names(tab) == ["PURCHASE INTEREST"]


# ── whole rows ───────────────────────────────────────────────────────────────
def test_a_click_selects_the_whole_row_and_copy_cell_copies_one_value(tab):
    from PySide6.QtWidgets import QAbstractItemView, QApplication
    from daftarche.tabs.transactions import COL_MERCHANT
    assert tab.table.selectionBehavior() == QAbstractItemView.SelectRows
    tab.table.selectRow(0)
    assert len({i.column() for i in tab.table.selectedIndexes()}) == tab.model.columnCount()
    index = tab.model.index(0, COL_MERCHANT)
    tab._copy_cell(index)
    assert QApplication.clipboard().text() == str(tab.model.data(index) or "")


# ── Manage's small buttons ───────────────────────────────────────────────────
def test_manage_buttons_are_pictures_with_tooltips(qapp, db):
    from PySide6.QtWidgets import QPushButton
    from daftarche.tabs.manage import ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    buttons = [b for b in dlg.cats_panel.findChildren(QPushButton) if b.width() == 50 or b.maximumWidth() == 50]
    assert buttons
    for b in buttons:
        if b.text():
            assert b.text() == "＋"  # a plain sign: text, in the theme's colour
        else:
            assert not b.icon().isNull()  # the emoji as a picture: never cut off
        assert b.toolTip()
    tips = {b.toolTip() for b in buttons}
    assert {"Add Category", "Rename Sub-Category", "Icon…", "Move to Another Category", "Delete Rule",
            "Edit Rule"} <= tips
