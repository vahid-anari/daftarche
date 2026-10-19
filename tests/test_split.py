"""0.20: split transactions: parts in their own categories, totals, filters, the Split window."""

import datetime
from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def cat(db, name, sub=None):
    db.add_category(name, "Expense")
    c = db.get_category_by_name(name, type_name="Expense")["id"]
    if sub:
        db.add_subcategory(sub, c)
        return c, db.get_subcategory_by_name(sub, c)["id"]
    return c, db.uncategorized_subcategory(c)["id"]


@pytest.fixture
def amazon(db):
    """An $80 Amazon order: $50 Household › Cleaning (dish soap), $30 Personal Care › Hair (shampoo)."""
    home = cat(db, "Household", "Cleaning")
    care = cat(db, "Personal Care", "Hair")
    uc, us = db.get_uncategorized_ids()
    tx = db.add_transaction(2026, "May", 12, "Expense", "Visa", 80, us, uc, name="AMAZON.CA", merchant="Amazon")
    db.set_splits(tx, [(home[0], home[1], 50, "dish soap"), (care[0], care[1], 30, "shampoo")])
    return tx


def test_parts_must_add_up(db, amazon):
    home = db.get_category_by_name("Household", type_name="Expense")["id"]
    with pytest.raises(ValueError):
        db.set_splits(amazon, [(home, None, 50, None), (home, None, 20, None)])
    assert [p["amount"] for p in db.get_splits(amazon)] == [50, 30]  # unchanged


def test_totals_count_each_part_in_its_category(db, amazon):
    totals = db.get_period_totals_by_group(2026, "May", 2026, "May", "Expense")
    assert totals == {"Household": 50.0, "Personal Care": 30.0}
    assert db.get_dashboard_summary(2026, "May", 2026, "May")["expense"] == 80
    assert db.get_to_review_count() == 0  # every part has a category
    lines = db.get_transaction_lines("Expense", "2026-05-01", "2026-05-31", category="Personal Care")
    assert [(r["amount"], r["note"]) for r in lines] == [(30, "shampoo")]


def test_filters_find_a_split_row_by_its_parts(db, amazon):
    assert [r["id"] for r in db.get_transactions({"category": ["Personal Care"]})] == [amazon]
    assert [r["id"] for r in db.get_transactions({"subcategory": ["Cleaning"]})] == [amazon]
    assert db.get_transactions({"category": ["Uncategorized"]}) == []
    (row,) = db.get_transactions()
    assert [(p["category"], p["amount"]) for p in row["parts"]] == [("Household", 50), ("Personal Care", 30)]
    options = db.get_filter_options({})
    assert {"Household", "Personal Care"} <= set(options["category"])


def test_category_changes_carry_the_parts(db, amazon):
    care = db.get_category_by_name("Personal Care", type_name="Expense")["id"]
    db.rename_category(care, "Household")  # merge into Household
    assert db.get_period_totals_by_group(2026, "May", 2026, "May", "Expense") == {"Household": 80.0}
    home = db.get_category_by_name("Household", type_name="Expense")["id"]
    db.delete_category(home)
    assert db.get_to_review_count() == 1  # its parts went to Uncategorized, with the category


def test_export_writes_a_line_per_part(db, amazon, tmp_path):
    import pandas as pd
    path = tmp_path / "x.xlsx"
    db.export_to_xlsx(path)
    df = pd.read_excel(path)
    assert list(df["Amount"]) == [50, 30] and list(df["Split"]) == ["1 of 2", "2 of 2"]
    assert list(df["Note"]) == ["dish soap", "shampoo"]


def test_split_window(qapp, db):
    from daftarche.split_dialog import SplitDialog
    cat(db, "Household", "Cleaning")
    cat(db, "Personal Care", "Hair")
    d = keep(SplitDialog(db, "Expense", 80, category="Household", subcategory="Cleaning"))
    first, second = d._rows
    assert first[2].text() == "80.00" and not d.ok.isEnabled()  # the second part has no amount yet
    second[0].setCurrentText("Personal Care")
    second[2].setText("30")
    second[2].textEdited.emit("30")
    assert first[2].text() == "50.00" and d.left.text() == "Left: $0.00" and d.ok.isEnabled()
    first[2].setText("40")
    first[2].textEdited.emit("40")  # typed: the first no longer follows
    assert d.left.text() == "Left: $10.00" and not d.ok.isEnabled()
    first[2].setText("50")
    first[2].textEdited.emit("50")
    with mock.patch.object(d, "accept"):
        d._accept()
    home = db.get_category_by_name("Household", type_name="Expense")["id"]
    assert [(p[0] == home, p[2]) for p in d.result_parts] == [(True, 50.0), (False, 30.0)]


def test_transactions_tab_shows_and_joins_splits(qapp, db, amazon):
    from daftarche.category_dialog import CategoryDialog
    from daftarche.tabs.transactions import COL_CAT, COL_SUBCAT, TransactionsTab
    tab = keep(TransactionsTab(db))
    tab.show_matching()
    assert tab.model.index(0, COL_CAT).data() == "Split (2)" and tab.model.index(0, COL_SUBCAT).data() == "—"
    tip = tab.model.index(0, COL_CAT).data(3)  # Qt.ToolTipRole
    assert "$50.00   Household › Cleaning  ·  dish soap" in tip

    def fill(d):
        d.f_category.setCurrentText("Household")
        d._accept()
        return True

    with mock.patch.object(CategoryDialog, "exec", fill), \
            mock.patch("daftarche.tabs.transactions.QMessageBox.question", return_value=mock.ANY) as ask:
        from daftarche.tabs import transactions as T
        ask.return_value = T.QMessageBox.Yes
        tab._edit_categories([0])
    assert db.get_splits(amazon) == [] and db.get_transactions()[0]["category"] == "Household"


def test_details_panel_lists_the_part(qapp, db, amazon):
    from daftarche.tabs.charts import ChartsTab
    db.conn.execute("UPDATE transactions SET date = ?", (datetime.date.today().isoformat(),))
    db.conn.commit()
    tab = keep(ChartsTab(db))
    tab._period._select_preset(3)
    tab.f_cat_selector.set_items(["Personal Care"], include_all=True, selected="Personal Care")
    tab._on_category_pick_changed()
    tab._detail("Hair")
    t = tab.detail.table
    assert [(t.item(0, 1).text(), t.item(0, 2).text())] == [("Amazon: shampoo", "$30.00")]


def test_both_filters_must_match_one_part(db):
    food = cat(db, "Food", "Groceries")
    home = cat(db, "Home", "Other")
    db.add_subcategory("Other", food[0])
    uc, us = db.get_uncategorized_ids()
    tx = db.add_transaction(2026, "May", 1, "Expense", "Card", 100, us, uc, name="COSTCO")
    db.set_splits(tx, [(food[0], food[1], 60, None), (home[0], home[1], 40, None)])
    assert db.get_transactions({"category": ["Food"], "subcategory": ["Other"]}) == []
    (row,) = db.get_transactions({"category": ["Food"]})
    assert row["shown_amount"] == 60 and row["amount"] == 100  # the summary counts the part


def test_counts_search_and_guards(db, amazon):
    home = db.get_category_by_name("Household", type_name="Expense")["id"]
    uc, us = db.get_uncategorized_ids()
    tx = db.add_transaction(2026, "May", 2, "Expense", "Visa", 20, us, uc, name="X")
    db.set_splits(tx, [(uc, us, 10, None), (uc, us, 10, None)])
    assert db.get_uncategorized_count(2026, "May", 2026, "May") == 1  # one transaction, two parts
    assert [r["id"] for r in db.get_transactions({"search": "shampoo"})] == [amazon]  # a part's note
    with pytest.raises(ValueError):
        db.update_transaction(amazon, amount=90)  # the parts would no longer add up
    with pytest.raises(ValueError):
        db.update_transaction(amazon, type_name="Income")
    db.add_category("Salary", "Income")
    salary = db.get_category_by_name("Salary", type_name="Income")["id"]
    with pytest.raises(ValueError):
        db.set_splits(amazon, [(salary, None, 40, None), (home, None, 40, None)])  # another type's category
    with pytest.raises(ValueError):
        db.set_splits(amazon, [(home, None, 80, None)])  # one part is no split
    assert len(db.get_splits(amazon)) == 2


def test_split_window_after_removing_the_first_part(qapp, db):
    from daftarche.split_dialog import SplitDialog
    cat(db, "Household", "Cleaning")
    d = keep(SplitDialog(db, "Expense", 100, category="Household"))
    d._remove_row(d._rows[0])
    d._add_row()
    first, second = d._rows
    first[2].setText("30")
    first[2].textEdited.emit("30")  # now the first part: typed, so kept
    second[2].setText("70")
    second[2].textEdited.emit("70")
    assert (first[2].text(), second[2].text()) == ("30", "70") and d.ok.isEnabled()


def test_edit_window_refuses_a_new_type_for_old_parts(qapp, db, amazon):
    from daftarche.tabs.transactions import TransactionDialog
    (row,) = db.get_transactions()
    d = keep(TransactionDialog(db, row=dict(row)))
    d.f_type.setCurrentText("Income")
    with mock.patch("daftarche.tabs.transactions.QMessageBox") as box:
        d._save()
    assert box.warning.called and db.get_transactions()[0]["type"] == "Expense"
