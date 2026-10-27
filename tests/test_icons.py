"""0.22: an icon (emoji) per category, and optionally per sub-category."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def cats(db):
    db.add_category("Car", "Expense")
    car = db.get_category_by_name("Car", type_name="Expense")["id"]
    db.add_subcategory("Gas", car)
    db.add_subcategory("Insurance", car)
    db.add_category("Groceries", "Expense")
    groc = db.get_category_by_name("Groceries", type_name="Expense")["id"]
    db.add_subcategory("Produce", groc)
    return {"car": car, "groc": groc, "gas": db.get_subcategory_by_name("Gas", car)["id"],
            "ins": db.get_subcategory_by_name("Insurance", car)["id"],
            "produce": db.get_subcategory_by_name("Produce", groc)["id"]}


def test_a_sub_category_shows_its_own_icon_or_its_categorys(db, cats):
    db.set_category_icon(cats["car"], "🚗")
    db.set_subcategory_icon(cats["gas"], "⛽")
    icons = db.get_icons()
    assert icons["cat"] == {cats["car"]: "🚗"}
    assert icons["sub"][cats["gas"]] == "⛽" and icons["sub"][cats["ins"]] == "🚗"
    assert cats["produce"] not in icons["sub"]
    assert db.category_icon("Car", "Expense") == "🚗" and db.category_icon("Car", "Income") == ""
    db.set_subcategory_icon(cats["gas"], "")  # No Icon: the category's again
    assert db.get_icons()["sub"][cats["gas"]] == "🚗"


def test_an_older_database_gets_the_icon_columns(tmp_path):
    import sqlite3
    from daftarche.db import Database, SCHEMA_VERSION
    path = tmp_path / "old.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE categories DROP COLUMN icon")
    conn.execute("ALTER TABLE subcategories DROP COLUMN icon")
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()
    db = Database(path)
    try:
        for table in ("categories", "subcategories"):
            assert "icon" in [r[1] for r in db.conn.execute(f"PRAGMA table_info({table})")]
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 7
    finally:
        db.conn.close()


@pytest.mark.parametrize("name, icon", [
    ("Groceries", "🛒"), ("Dining Out", "🍽️"), ("Coffee & Snacks", "☕"), ("Pets", "🐾"),
    ("Gas", "⛽"), ("Car Rental", "🚗"), ("Carbon Rebate", "🔁"), ("Credit Card", "💳"),
    ("Bank Fees", "🏦"), ("Fees", ""), ("Public Transit", "🚇"), ("Miscellaneous", ""), ("Toktam", ""),
    ("Amazon Prime", "📺"), ("Home Improvement", "🔧"), ("Delivery", "🥡"), ("Training", ""),
    ("Presentation", ""), ("Utilities", "🧾"), ("Electricity", "💡"), ("Trains & Buses", "🚇"),
])
def test_suggested_icons(name, icon):
    from daftarche.icons import suggest_icon
    assert suggest_icon(name) == icon


def test_an_icon_is_one_emoji(db, cats):
    from daftarche.db import clean_icon
    assert clean_icon(" 🍽️ ") == "🍽️" and clean_icon("🇨🇦") == "🇨🇦" and clean_icon("") == ""
    for junk in ("Food", "🍕🍔", "1", "hello world"):
        with pytest.raises(ValueError):
            clean_icon(junk)
    with pytest.raises(ValueError):
        db.set_category_icon(cats["car"], "car")
    assert db.get_icons()["cat"] == {}


def test_merging_keeps_an_icon(db, cats):
    db.add_category("Auto", "Expense")
    auto = db.get_category_by_name("Auto", type_name="Expense")["id"]
    db.add_subcategory("Gas", auto)
    db.set_category_icon(auto, "🚙")
    db.set_subcategory_icon(db.get_subcategory_by_name("Gas", auto)["id"], "⛽")
    db.rename_category(auto, "Car")  # merged into Car, which has no icon yet
    icons = db.get_icons()
    assert icons["cat"] == {cats["car"]: "🚙"} and icons["sub_own"] == {cats["gas"]: "⛽"}


def test_icon_picker(qapp):
    from daftarche.icons import IconPickerDialog
    d = keep(IconPickerDialog("🚗", "Icon for Car"))
    with mock.patch("daftarche.icons.QMessageBox.warning") as warn:
        d._choose("Food")
    assert warn.called and d.icon == "🚗"
    d.typed.setText(" 🚙 ")
    with mock.patch.object(d, "accept"):
        d._choose(d.typed.text())
    assert d.icon == "🚙"


def test_transactions_table_shows_the_icons(qapp, db, cats):
    from PySide6.QtCore import Qt
    from daftarche.tabs.transactions import COL_CAT, COL_SUBCAT, TransactionsTab
    db.set_category_icon(cats["car"], "🚗")
    db.set_subcategory_icon(cats["gas"], "⛽")
    db.add_transaction(2026, "May", 1, "Expense", "Card", 40, cats["gas"], cats["car"], name="SHELL")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 9, db.uncategorized_subcategory(cats["groc"])["id"],
                       cats["groc"], name="LOBLAWS")
    tab = keep(TransactionsTab(db))
    tab._period._select_preset(0, emit=False, persist=False)
    tab.refresh()
    rows = {tab.model.get_row(i)["name"]: i for i in range(tab.model.rowCount())}
    shell = rows["SHELL"]
    assert not tab.model.data(tab.model.index(shell, COL_CAT), Qt.DecorationRole).isNull()
    assert not tab.model.data(tab.model.index(shell, COL_SUBCAT), Qt.DecorationRole).isNull()
    assert tab.model.data(tab.model.index(shell, COL_CAT), Qt.DisplayRole) == "Car"  # the name stays
    assert tab.model.data(tab.model.index(rows["LOBLAWS"], COL_CAT), Qt.DecorationRole) is None


def test_manage_sets_an_icon(qapp, db, cats):
    from daftarche.tabs.manage import ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    panel = dlg.cats_panel
    expense = next(r for r in range(panel.type_table.rowCount()) if panel.type_table.item(r, 0).text() == "Expense")
    panel.type_table.selectRow(expense)
    car = next(r for r in range(panel.cat_table.rowCount()) if panel.cat_table.item(r, 0).text() == "Car")
    panel.cat_table.selectRow(car)
    picked = mock.Mock(exec=mock.Mock(return_value=True), icon="🚗")
    with mock.patch("daftarche.tabs.manage.IconPickerDialog", return_value=picked):
        panel._set_cat_icon()
    assert db.get_icons()["cat"] == {cats["car"]: "🚗"}
    car = next(r for r in range(panel.cat_table.rowCount()) if panel.cat_table.item(r, 0).text() == "Car")
    assert not panel.cat_table.item(car, 0).icon().isNull()


def test_icon_picker_offers_the_suggestion(qapp):
    from daftarche.icons import IconPickerDialog
    d = keep(IconPickerDialog("", "Icon for Groceries", suggested="🛒"))
    assert d.typed.text() == "🛒"
    d._choose(d.typed.text())
    assert d.icon == "🛒"
    kept = keep(IconPickerDialog("🥕", "Icon for Groceries", suggested="🛒"))
    assert kept.typed.text() == "🥕"  # its own icon: nothing offered
