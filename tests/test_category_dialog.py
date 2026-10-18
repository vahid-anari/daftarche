"""Edit Category / Sub-Category: typed names, "New", and the rules of the chosen sub-category."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def food(db):
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    db.add_subcategory("Groceries", food)
    db.get_or_create_account("Card")
    return food


def dialog(db, **kw):
    from daftarche.category_dialog import CategoryDialog
    return keep(CategoryDialog(db, "Expense", **kw))


def press_ok(d):
    with mock.patch.object(d, "accept") as accept, mock.patch("daftarche.category_dialog.QMessageBox") as box:
        d._accept()
    return accept.called, box.warning.called


def test_boxes_take_typing(qapp, db, food):
    from PySide6.QtTest import QTest
    d = dialog(db)
    for box in (d.f_category, d.f_subcat):
        assert not box.lineEdit().isReadOnly()
    d.show()
    d.activateWindow()
    for box, text in ((d.f_category, "Pets"), (d.f_subcat, "Vet")):
        box.lineEdit().setFocus()
        QTest.qWait(20)  # the box selects its text on focus: typing replaces it
        QTest.keyClicks(box.lineEdit(), text)
    assert (d.f_category.currentText(), d.f_subcat.currentText()) == ("Pets", "Vet")
    assert not d.new_cat.isHidden() and not d.new_sub.isHidden()
    d.close()


def test_new_names_are_marked_and_added_on_ok(qapp, db, food):
    d = dialog(db)
    d.f_category.setCurrentText("food")  # an existing name in other letters
    d.f_subcat.setCurrentText("groceries")
    assert d.new_cat.isHidden() and d.new_sub.isHidden()
    d.f_subcat.setCurrentText("Snacks")
    assert d.new_cat.isHidden() and not d.new_sub.isHidden()
    assert press_ok(d) == (True, False)
    assert (d.cat_name, d.sub_name) == ("Food", "Snacks") and db.get_subcategory_by_name("Snacks", food)

    d = dialog(db)
    d.f_category.setCurrentText("Pets")
    d.f_subcat.setCurrentText("Vet")
    assert db.get_category_by_name("Pets") is None  # nothing before OK
    assert press_ok(d) == (True, False)
    pets = db.get_category_by_name("Pets", type_name="Expense")
    assert pets["type_name"] == "Expense" and db.get_subcategory_by_name("Vet", pets["id"])


def test_cancel_saves_nothing(qapp, db, food):
    d = dialog(db, default_rule=("COSTCO WHOLESALE", ""))
    d.f_category.setCurrentText("Pets")
    d._add_rule()
    d.reject()
    assert db.get_category_by_name("Pets") is None
    assert db.lookup_mapping("Expense", "Card", "COSTCO WHOLESALE") is None


def test_an_income_category_is_not_an_expense_one(qapp, db, food):
    from daftarche.category_dialog import CategoryDialog
    d = keep(CategoryDialog(db, "Income"))
    d.f_category.setCurrentText("Food")
    assert not d.new_cat.isHidden()
    assert press_ok(d) == (True, False)
    assert db.get_category_by_name("Food", type_name="Income")["type_name"] == "Income"


def test_rules_of_the_chosen_subcategory(qapp, db, food):
    groceries = db.get_subcategory_by_name("Groceries", food)["id"]
    db.save_mapping("Expense", None, name="COSTCO", subcategory_id=groceries, category_id=food)
    db.save_mapping("Expense", "Card", name="FRESHCO", subcategory_id=groceries, category_id=food)
    d = dialog(db, preset_cat="Food", preset_sub="Groceries")
    assert [(e["values"]) for e, *_ in d._rule_rows] == [(None, "COSTCO", ""), ("Card", "FRESHCO", "")]
    assert d.rules_title.text() == "Rules for Food › Groceries"

    entry, account, name, memo = d._rule_rows[0]
    name.setText("COSTCO|GAS")  # edit one
    d._remove_rule(d._rule_rows[1][0])  # remove one
    d.new_name.setText("LOBLAWS")
    d._add_rule()  # add one
    d.f_subcat.setCurrentText(UNCAT := "Uncategorized")  # switching away and back keeps the edits
    d.f_subcat.setCurrentText("Groceries")
    assert [e["values"] for e, *_ in d._rule_rows] == [(None, "COSTCO|GAS", ""), (None, "LOBLAWS", "")]
    assert UNCAT
    assert press_ok(d) == (True, False)
    rules = {(r["account_name"], r["name"]) for r in db.get_rules_for_subcategory(groceries)}
    assert rules == {(None, "COSTCO|GAS"), (None, "LOBLAWS")}


def test_a_rule_needs_a_name_or_memo(qapp, db, food):
    groceries = db.get_subcategory_by_name("Groceries", food)["id"]
    db.save_mapping("Expense", None, name="COSTCO", subcategory_id=groceries, category_id=food)
    d = dialog(db, preset_cat="Food", preset_sub="Groceries")
    d._rule_rows[0][2].setText("")
    assert press_ok(d) == (False, True)
    d.new_name.setText("")
    d.new_memo.setText("")
    d._add_rule()  # a blank new row is ignored
    assert len(d._rule_rows) == 1


def test_new_rule_applies_to_matching_uncategorized(qapp, db, food):
    candidates = [{"key": 1, "account": "Card", "name": "COSTCO WHOLESALE #12", "memo": ""},
                  {"key": 2, "account": "Card", "name": "COSTCO GAS", "memo": ""},
                  {"key": 3, "account": "Card", "name": "NOFRILLS", "memo": ""}]
    d = dialog(db, preset_cat="Food", preset_sub="Groceries", default_rule=("COSTCO WHOLESALE #512", ""),
               candidates=candidates)
    assert d.new_name.text() == "COSTCO WHOLESALE #512" and d.new_account.currentText() == "All"
    assert d.chk_apply.isHidden()
    d.new_name.setText("COSTCO")
    d._add_rule()
    assert not d.chk_apply.isHidden() and "2 matching" in d.chk_apply.text()
    assert press_ok(d) == (True, False)
    assert sorted(d.apply_keys) == [1, 2]


def test_transactions_tab_applies_the_new_rule(qapp, db, food, tmp_path):
    from daftarche.tabs.transactions import TransactionsTab
    uc, us = db.get_uncategorized_ids()
    for name in ("COSTCO #1", "COSTCO #2", "NOFRILLS"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, name=name)
    tab = keep(TransactionsTab(db))
    tab.show_matching()
    row = next(i for i in range(tab.model.rowCount()) if tab.model.get_row(i)["name"] == "COSTCO #1")

    def fill(d):
        d.f_category.setCurrentText("Food")
        d.f_subcat.setCurrentText("Groceries")
        d.new_name.setText("COSTCO")
        d._add_rule()
        d._accept()
        return True

    from daftarche.category_dialog import CategoryDialog
    with mock.patch.object(CategoryDialog, "exec", fill):
        tab._edit_categories([row])
    cats = {r["name"]: (r["category"], r["subcategory"]) for r in db.get_transactions()}
    assert cats == {"COSTCO #1": ("Food", "Groceries"), "COSTCO #2": ("Food", "Groceries"),
                    "NOFRILLS": ("Uncategorized", "Uncategorized")}


def test_switching_names_leaves_no_old_rows_behind(qapp, db, food):
    from PySide6.QtWidgets import QWidget
    d = dialog(db, preset_cat="Food", preset_sub="Groceries")
    for sub in ("Snacks", "Groceries", "Uncategorized", "Groceries"):
        d.f_subcat.setCurrentText(sub)
    shown = [w for w in d._grid_host.findChildren(QWidget) if w.parent() is d._grid_host and not w.isHidden()]
    assert len(shown) == d._grid.count()


QUIT_AFTER_DIALOG = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
app = QApplication([])
from daftarche.window import MainWindow
from daftarche.category_dialog import CategoryDialog
w = MainWindow(); db = w.db
uc, us = db.get_uncategorized_ids()
db.add_transaction(2026, "May", 1, "Expense", "Card", 5, us, uc, name="SHOP")
w.show(); tab = w.transactions_tab; tab.show_matching()
def close():
    d = [x for x in app.topLevelWidgets() if isinstance(x, CategoryDialog) and x.isVisible()][0]
    d.f_subcat.setCurrentText("Bus"); d.reject()
QTimer.singleShot(200, close)
tab._edit_categories([0])
QTimer.singleShot(100, app.quit); app.exec()
"""


def test_quitting_after_the_dialog_does_not_crash(tmp_path):
    import os, subprocess, sys  # noqa: E401
    env = dict(os.environ, DAFTARCHE_HOME=str(tmp_path), QT_QPA_PLATFORM="offscreen")
    for _ in range(3):  # the crash came at Python's shutdown, about 4 runs in 5
        run = subprocess.run([sys.executable, "-c", QUIT_AFTER_DIALOG], env=env, capture_output=True, timeout=60)
        assert run.returncode == 0, run.stderr.decode()[-500:]
