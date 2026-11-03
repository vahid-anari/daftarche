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


def test_a_sub_category_shows_only_its_own_icon(db, cats):
    db.set_category_icon(cats["car"], "🚗")
    db.set_subcategory_icon(cats["gas"], "⛽")
    icons = db.get_icons()
    assert icons["cat"] == {cats["car"]: "🚗"}
    assert icons["sub"] == {cats["gas"]: "⛽"}  # 0.33.5: Insurance shows none (its category's is beside it)
    assert db.category_icon("Car", "Expense") == "🚗" and db.category_icon("Car", "Income") == ""
    db.set_subcategory_icon(cats["gas"], "")  # No Icon
    assert db.get_icons()["sub"] == {}


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
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 8
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
    assert d.typed.text() == "🚗" and not d.preview.pixmap().isNull()  # the current icon, large
    d.typed.setText("Food")
    with mock.patch("daftarche.icons.QMessageBox.warning") as warn, mock.patch.object(d, "accept") as ok:
        d._accept()
    assert warn.called and not ok.called
    d.typed.setText(" 🚙 ")
    with mock.patch.object(d, "accept") as ok:
        d._accept()
    assert ok.called and d.icon == "🚙"


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
    from daftarche.icons import blank_icon
    groceries = tab.model.data(tab.model.index(rows["LOBLAWS"], COL_CAT), Qt.DecorationRole)
    assert groceries is blank_icon()  # no icon: a space, so the names stay in line


def test_manage_sets_an_icon(qapp, db, cats):
    from daftarche.tabs.manage import ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    panel = dlg.cats_panel
    expense = next(r for r in range(panel.type_table.rowCount()) if panel.type_table.item(r, 0).text() == "Expense")
    panel.type_table.selectRow(expense)
    car = next(r for r in range(panel.cat_table.rowCount()) if panel.cat_table.item(r, 0).text() == "Car")
    panel.cat_table.selectRow(car)
    picked = mock.Mock(exec=mock.Mock(return_value=True), icon="🚗", name="Car")
    picked.name = "Car"
    with mock.patch("daftarche.tabs.manage.IconPickerDialog", return_value=picked):
        panel._rename_cat()  # ✏️: name and icon in one window
    assert db.get_icons()["cat"] == {cats["car"]: "🚗"}
    car = next(r for r in range(panel.cat_table.rowCount()) if panel.cat_table.item(r, 0).text() == "Car")
    assert not panel.cat_table.item(car, 0).icon().isNull()


def test_icon_picker_offers_the_suggestion(qapp):
    from daftarche.icons import IconPickerDialog, suggest_icon
    d = keep(IconPickerDialog("", "New category", name="", suggest=suggest_icon))
    assert d.tip.isHidden()
    d.name_field.setText("Groceries")  # the offer follows the name typed
    assert not d.tip.isHidden() and "🛒" in d.tip.text() and d.icon == ""  # offered, not chosen
    d.use_tip.click()
    assert d.icon == "🛒" and d.typed.text() == "🛒" and d.tip.isHidden()
    kept = keep(IconPickerDialog("🥕", "Category", name="Groceries", suggest=suggest_icon))
    assert kept.typed.text() == "🥕" and kept.tip.isHidden()  # its own icon: nothing offered


def test_the_grid_draws_pictures_and_marks_the_choice(qapp):
    from daftarche.icons import PICKER, IconPickerDialog
    d = keep(IconPickerDialog("☕", "Category", name="Coffee"))
    btn = d._buttons["☕"]
    assert btn.text() == "" and not btn.icon().isNull()  # a picture: as text it was cut off
    assert "highlight" in btn.styleSheet() and d._buttons[PICKER[0]].styleSheet() == ""
    d._buttons["🍕"].click()  # a click chooses; OK keeps it
    assert d.icon == "🍕" and d.typed.text() == "🍕" and "highlight" in d._buttons["🍕"].styleSheet()
    with mock.patch.object(d, "accept"):
        d._accept()
    assert (d.name, d.icon) == ("Coffee", "🍕")


def test_a_name_is_needed_and_the_loans_name_is_kept(qapp):
    from daftarche.icons import IconPickerDialog
    d = keep(IconPickerDialog("", "New category", name="  "))
    with mock.patch("daftarche.icons.QMessageBox.warning") as warn, mock.patch.object(d, "accept") as ok:
        d._accept()
    assert warn.called and not ok.called
    loans = keep(IconPickerDialog("", "Category", name="Loans", name_locked=True))
    assert loans.name_field.isReadOnly()


def test_add_category_with_its_icon_and_edit_with_merge(qapp, db, cats):
    from daftarche.tabs.manage import ManageDialog
    panel = keep(ManageDialog(db, lambda: None)).cats_panel
    expense = next(r for r in range(panel.type_table.rowCount()) if panel.type_table.item(r, 0).text() == "Expense")
    panel.type_table.selectRow(expense)
    new = mock.Mock(exec=mock.Mock(return_value=True), icon="🎁")
    new.name = "Gifts"
    with mock.patch("daftarche.tabs.manage.IconPickerDialog", return_value=new):
        panel._add_cat()
    gifts = db.get_category_by_name("Gifts", type_name="Expense")
    assert gifts and gifts["icon"] == "🎁"
    car = next(r for r in range(panel.cat_table.rowCount()) if panel.cat_table.item(r, 0).text() == "Car")
    panel.cat_table.selectRow(car)
    into = mock.Mock(exec=mock.Mock(return_value=True), icon="🚘")
    into.name = "Gifts"
    with mock.patch("daftarche.tabs.manage.IconPickerDialog", return_value=into), \
            mock.patch("daftarche.tabs.manage._confirm_merge", return_value=True):
        panel._rename_cat()  # renamed to an existing name: merged, and the icon goes to the one kept
    assert db.get_category_by_name("Car", type_name="Expense") is None
    assert db.get_category_by_name("Gifts", type_name="Expense")["icon"] == "🚘"


def test_right_click_menus_in_manage(qapp, db, cats):
    from PySide6.QtCore import QPoint
    from daftarche.tabs.manage import ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    shown = []
    with mock.patch("daftarche.tabs.manage._exec_menu",
                    lambda menu, where: shown.append([a.text() for a in menu.actions() if a.text()])):
        dlg.cats_panel.cat_table._list_menu(QPoint(5, 400))  # below the rows: only Add
        dlg.tags_panel.table._list_menu(QPoint(5, 400))
        db.get_or_create_account("Card")
        dlg.accounts_panel.refresh()
        table = dlg.accounts_panel.table
        assert table.rowCount()
        table._list_menu(table.visualRect(table.model().index(0, 0)).center())  # on a row
    assert shown[0] == ["＋  Add Category…"] and shown[1] == ["＋  Add Tag…"]
    assert shown[2] == ["＋  Add Account…", "✏️  Edit Account…", "🗑️  Delete Account"]
    assert dlg.accounts_panel.table.selectionModel().selectedRows()  # the row was selected first


def test_looking_for_any_emoji_by_name(qapp):
    from daftarche.icons import IconPickerDialog, search_emoji
    assert {"🚗", "🚕", "🏎"} <= set(search_emoji("car")) and "💰" in search_emoji("money")
    assert search_emoji("racing car")[0] == "🏎" and search_emoji("") == [] and search_emoji("zzqq") == []
    d = keep(IconPickerDialog("", "Category", name="Birthdays"))
    assert d.found.isHidden()
    d.search.setText("cake")
    assert not d.found.isHidden() and d.found.count() > 1
    item = next(d.found.item(i) for i in range(d.found.count()) if d.found.item(i).data(0x0100) == "🎂")
    assert not item.icon().isNull()  # drawn as a picture, as the grid
    d.found.itemClicked.emit(item)
    assert d.icon == "🎂" and d.typed.text() == "🎂"
    d.search.setText("zzqq")
    assert d.found.isHidden() and not d.nothing.isHidden()
