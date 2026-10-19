"""0.20.1: Manage → Merchants, the "(merchant only)" rules, typing a new tag."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shops(db):
    db.add_category("Groceries", "Expense")
    groc = db.get_category_by_name("Groceries", type_name="Expense")["id"]
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Expense", "Card", 40, us, uc, name="WALMART #1", merchant="Walmart")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 10, us, uc, name="WAL-MART", merchant="walmart.ca")
    db.add_transaction(2026, "May", 3, "Expense", "Card", 25, db.uncategorized_subcategory(groc)["id"], groc,
                       name="WALMART #2", merchant="Walmart")
    db.save_mapping("Expense", None, name="WALMART", subcategory_id=us, category_id=uc, merchant="Walmart")
    return groc


def test_overview_rename_merge_and_delete(db, shops):
    rows = {m["merchant"]: m for m in db.get_merchant_overview()}
    assert (rows["Walmart"]["count"], rows["Walmart"]["rules"], rows["Walmart"]["total"]) == (2, 1, 65.0)
    assert rows["Walmart"]["rule_targets"] == {"(merchant only)"}
    assert db.rename_merchant("walmart.ca", "WALMART") == "Walmart"  # merged into the one there
    assert {m["merchant"]: m["count"] for m in db.get_merchant_overview()} == {"Walmart": 3}
    db.delete_merchant("Walmart")
    assert db.get_merchant_overview() == [] and len(db.get_transactions()) == 3


def test_set_category_for_rules_and_uncategorized_only(db, shops):
    uc, us = db.get_uncategorized_ids()
    db.add_category("Household", "Expense")
    home = db.get_category_by_name("Household", type_name="Expense")["id"]
    split = db.add_transaction(2026, "May", 4, "Expense", "Card", 20, us, uc, name="WALMART #3", merchant="Walmart")
    db.set_splits(split, [(home, None, 10, None), (shops, None, 10, None)])
    sub = db.uncategorized_subcategory(shops)["id"]
    assert db.set_merchant_category("Walmart", "Expense", shops, sub) == (1, 1)  # the rule, WALMART #1
    cats = {r["name"]: r["category"] for r in db.get_transactions()}
    assert cats["WALMART #1"] == "Groceries" and cats["WAL-MART"] == "Uncategorized"  # another merchant
    assert len(db.get_splits(split)) == 2  # split left alone
    assert db.lookup_mapping("Expense", "Card", "WALMART")["category_id"] == shops


def test_merchants_tab_and_merchant_only_line(qapp, db, shops):
    from daftarche.tabs.manage import ManageDialog
    shown = []
    dlg = keep(ManageDialog(db, lambda: None, show_merchant=shown.append))
    panel = dlg.merchants_panel
    names = [panel.table.item(r, 0).text() for r in range(panel.table.rowCount())]
    assert names == ["Walmart", "walmart.ca"]
    assert panel.table.item(0, panel.COL_CAT).text() == "(merchant only)"
    panel.table.selectRow(0)
    panel.open_transactions()
    assert shown == ["Walmart"]
    cats = dlg.cats_panel
    expense_row = next(r for r in range(cats.type_table.rowCount()) if cats.type_table.item(r, 0).text() == "Expense")
    cats.type_table.selectRow(expense_row)
    assert cats.cat_table.item(0, 0).text() == "(merchant only)" and cats.cat_table.item(0, 2).text() == "1"
    cats.cat_table.selectRow(0)
    cats.sub_table.selectRow(0)
    assert [cats.map_table.item(r, 3).text() for r in range(cats.map_table.rowCount())] == ["Walmart"]
    with mock.patch("daftarche.tabs.manage.QMessageBox") as box:
        cats._delete_cat()  # not a category to delete
    assert box.information.called and db.get_category_by_name("Uncategorized")


def test_window_shows_a_merchant_and_goes_back_to_manage(qapp, db, shops, monkeypatch, tmp_path):
    from daftarche import window as W
    monkeypatch.setattr(W, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(W, "startup_backup"):
        w = keep(W.MainWindow())
    w.db.conn.close()
    w.db = db
    w._rebuild_tabs()
    w._show_merchant("Walmart")
    tab = w.transactions_tab
    assert sorted(tab.model.get_row(i)["name"] for i in range(tab.model.rowCount())) == ["WALMART #1", "WALMART #2"]
    assert tab.btn_back.text() == "← Back to Manage"
    tab.go_back()
    assert w._manage_dlg is not None and w._manage_dlg.tabs.currentWidget() is w._manage_dlg.merchants_panel
    w._manage_dlg.close()


def test_typing_a_new_tag(qapp, db):
    from daftarche.tag_picker import TagsDialog
    db.add_tag("Trip")
    d = keep(TagsDialog(db, ["Trip"]))
    d.tags.find.setText("trip to montreal")
    assert not d.tags.add_btn.isHidden()
    d.tags._enter()
    assert set(d.get_selected()) == {"Trip", "trip to montreal"}
    assert [t["name"] for t in db.get_tags()] == ["Trip"]  # not before Save
    with mock.patch.object(d, "accept"):
        d._save()
    assert sorted(t["name"] for t in db.get_tags()) == ["Trip", "trip to montreal"]
    assert len(d.get_selected_ids()) == 2


def test_typing_a_new_tag_in_the_edit_window(qapp, db, shops):
    from daftarche.tabs.transactions import TransactionDialog
    row = db.get_transactions()[0]
    d = keep(TransactionDialog(db, row=dict(row)))
    d.f_tags._search.setText("Groceries run")
    d.f_tags._add_typed()
    assert d.f_tags.get_selected() == ["Groceries run"]
    with mock.patch.object(d, "accept"):
        d._save()
    assert [t["name"] for t in db.get_tags_for_transaction(row["id"])] == ["Groceries run"]


def test_set_category_keeps_to_its_type(qapp, db):
    """An Expense rule's category is not offered (or saved) for the merchant's Income rows."""
    from daftarche.tabs.manage import MerchantCategoryDialog
    db.add_category("Groceries", "Expense")
    db.add_category("Refunds", "Income")
    groc = db.get_category_by_name("Groceries", type_name="Expense")["id"]
    uc, us = db.get_uncategorized_ids()
    db.save_mapping("Expense", None, name="AMZN", subcategory_id=db.uncategorized_subcategory(groc)["id"],
                    category_id=groc, merchant="Amazon")
    for i in range(2):
        db.add_transaction(2026, "May", 1 + i, "Income", "Card", 20, us, uc, name=f"AMZN REF{i}", merchant="Amazon")
    m = next(x for x in db.get_merchant_overview() if x["merchant"] == "Amazon")
    dlg = keep(MerchantCategoryDialog(db, m))
    assert dlg.f_type.currentText() == "Income" and dlg.f_cat.currentText() == "Uncategorized"
    with pytest.raises(ValueError):
        db.set_merchant_category("Amazon", "Income", groc, db.uncategorized_subcategory(groc)["id"])
    assert {r["category"] for r in db.get_transactions()} == {"Uncategorized"}


def test_uncategorized_never_wipes_categories(qapp, db, shops):
    from daftarche.tabs.manage import MerchantCategoryDialog
    uc, us = db.get_uncategorized_ids()
    db.set_merchant_category("Walmart", "Expense", uc, us, all_transactions=True)
    assert {r["name"]: r["category"] for r in db.get_transactions()}["WALMART #2"] == "Groceries"
    m = next(x for x in db.get_merchant_overview() if x["merchant"] == "Walmart")
    dlg = keep(MerchantCategoryDialog(db, m))
    dlg.f_cat.setCurrentText("Uncategorized")
    assert not dlg.chk_all.isEnabled() and not dlg.chk_all.isChecked()
    dlg.f_cat.setCurrentText("Groceries")
    assert dlg.chk_all.isEnabled() and dlg.chk_uncat.isChecked()


def test_net_spent_and_delete_drops_merchant_only_rules(db, shops):
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 9, "Income", "Card", 15, us, uc, name="WALMART REFUND", merchant="Walmart")
    db.add_transaction(2026, "May", 9, "Transfer", "Card", 500, us, uc, name="WALMART XFER", merchant="Walmart")
    rows = {m["merchant"]: m for m in db.get_merchant_overview()}
    assert rows["Walmart"]["total"] == 50.0  # 40 + 25 spent, 15 back, the transfer left out
    sub = db.uncategorized_subcategory(shops)["id"]
    db.save_mapping("Expense", None, name="WMT", subcategory_id=sub, category_id=shops, merchant="Walmart")
    assert db.delete_merchant("Walmart") == 1  # the merchant-only rule
    left = db.conn.execute("SELECT name, merchant FROM import_mappings").fetchall()
    assert [(r["name"], r["merchant"]) for r in left] == [("WMT", None)]
