"""0.31.0: "Show transactions" in Manage → Categories: the transactions of what is selected under
the merchants; Manage keeps its size and place."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_settings():
    from daftarche.style import get_settings
    from daftarche.tabs.manage import FILLED_KEY, GEOMETRY_KEY
    from daftarche.tx_list import SHOW_KEY
    keys = (SHOW_KEY, FILLED_KEY, GEOMETRY_KEY, "transactions_columns", "transactions_column_order")
    s = get_settings()
    before = {k: s._data.get(k) for k in keys}
    for k in keys:
        s._data.pop(k, None)
    yield
    for k, v in before.items():
        s._data.pop(k, None)
        if v is not None:
            s._data[k] = v


@pytest.fixture
def food(db):
    db.get_or_create_account("Card")
    db.add_category("Groceries", "Expense")
    cat = db.get_category_by_name("Groceries", type_name="Expense")["id"]
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    for name in ("Bakery", "Market"):
        db.add_subcategory(name, cat)
    bakery = db.get_subcategory_by_name("Bakery", cat)["id"]
    market = db.get_subcategory_by_name("Market", cat)["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", 10, bakery, cat, name="SUNRISE 1", merchant="Sunrise")
    db.add_transaction(2026, "May", 9, "Expense", "Card", 4, bakery, cat, name="SUNRISE REFUND", merchant="Sunrise")
    db.conn.execute("UPDATE transactions SET amount = -4 WHERE name = 'SUNRISE REFUND'")
    db.add_transaction(2026, "May", 5, "Expense", "Card", 30, market, cat, name="FARM STAND")
    split = db.add_transaction(2026, "May", 7, "Expense", "Card", 100, market, cat, name="BIG BOX", merchant="Big Box")
    db.set_splits(split, [(cat, market, 60, None), (home, None, 40, None)])
    db.conn.commit()
    return {"cat": cat, "bakery": bakery, "market": market}


def panel_on(db, shown=True):
    from daftarche.tabs.manage import ManageDialog
    opened = []
    dlg = keep(ManageDialog(db, lambda: None, show_transactions=lambda *a, **k: opened.append((a, k))))
    p = dlg.cats_panel
    p._select_by_name(p.type_table, "Expense")
    p._select_by_name(p.cat_table, "Groceries")
    if shown:
        with mock.patch.object(dlg, "showMaximized"):
            p.chk_lines.setChecked(True)
    return dlg, p, opened


def texts(p, col):
    return [p.lines.table.item(r, col).text() for r in range(p.lines.table.rowCount())]


# ── the database ─────────────────────────────────────────────────────────────
def test_lines_of_a_category_a_sub_category_and_a_merchant(db, food):
    lines = db.get_lines(food["cat"])
    assert [(x["name"], x["amount"]) for x in lines] == [
        ("SUNRISE REFUND", -4), ("BIG BOX", 60), ("FARM STAND", 30), ("SUNRISE 1", 10)]  # newest first
    assert next(x for x in lines if x["name"] == "BIG BOX")["part"]  # its part here, with its own amount
    assert [x["name"] for x in db.get_lines(food["cat"], food["bakery"])] == ["SUNRISE REFUND", "SUNRISE 1"]
    assert [x["name"] for x in db.get_lines(food["cat"], merchant="")] == ["FARM STAND"]
    assert [x["name"] for x in db.get_lines(merchant="Big Box")] == ["BIG BOX", "BIG BOX"]  # both parts


# ── Manage → Categories ──────────────────────────────────────────────────────
def test_off_at_first(qapp, db, food):
    dlg, p, _ = panel_on(db, shown=False)
    assert not p.chk_lines.isChecked() and p.lines.isHidden()


def test_the_transactions_of_the_category(qapp, db, food):
    from daftarche.style import get_settings
    from daftarche.tx_list import SHOW_KEY
    dlg, p, _ = panel_on(db)
    assert get_settings().get(SHOW_KEY) is True and not p.lines.isHidden()
    assert p.lines.title.text() == "Groceries — 4 transactions · $96.00"
    cols = p.lines.columns
    assert texts(p, cols.index("amount")) == ["-$4.00", "✂ $60.00", "$30.00", "$10.00"]
    assert texts(p, cols.index("merchant"))[2] == ""
    p.lines.table.sortItems(cols.index("amount"))  # as numbers, not as text
    assert texts(p, cols.index("amount")) == ["-$4.00", "$10.00", "$30.00", "✂ $60.00"]
    assert "Part of a split transaction" in p.lines.table.item(3, 0).toolTip()


def test_a_merchant_narrows_them_and_show_all_widens_them(qapp, db, food):
    dlg, p, _ = panel_on(db)
    row = next(r for r in range(p.merchant_table.rowCount()) if p.merchant_table.item(r, 0).text() == "Sunrise")
    p.merchant_table.selectRow(row)
    assert p.lines.title.text() == "Sunrise in Groceries — 2 transactions · $6.00"
    assert p.lines.table.isColumnHidden(p.lines.columns.index("merchant"))
    assert not p.lines.btn_all.isHidden()
    p.lines.btn_all.click()
    assert p.lines.title.text().startswith("Groceries — 4") and p.lines.btn_all.isHidden()


def test_a_sub_category_and_the_merchant_kept_on_refresh(qapp, db, food):
    dlg, p, _ = panel_on(db)
    p._select_by_name(p.sub_table, "Bakery")
    assert p.lines.title.text().startswith("Groceries › Bakery — 2")
    assert p.lines.table.isColumnHidden(p.lines.columns.index("subcategory"))
    p.merchant_table.selectRow(0)
    p.refresh()
    assert p.lines.title.text().startswith("Sunrise in Groceries › Bakery — 2")


def test_double_click_opens_that_day_in_transactions(qapp, db, food):
    dlg, p, opened = panel_on(db)
    p.lines._double_clicked(0, 0)
    (text, panel), filters = opened[-1]
    assert panel == "cats" and "Sunrise" in text
    assert filters["from_day"] == filters["to_day"] == "2026-05-09"
    assert filters["categories"] == ["Groceries"] and filters["merchants"] == ["Sunrise"]


def test_the_first_time_manage_fills_the_screen(qapp, db, food):
    dlg, p, _ = panel_on(db, shown=False)
    with mock.patch.object(dlg, "showMaximized") as fill:
        p.chk_lines.setChecked(True)
        p.chk_lines.setChecked(False)
        p.chk_lines.setChecked(True)
    assert fill.call_count == 1


def test_manage_keeps_its_size(qapp, db, food):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import GEOMETRY_KEY, ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    dlg.done(0)
    saved = get_settings().get(GEOMETRY_KEY)
    assert saved == bytes(dlg.saveGeometry().toHex()).decode()
    with mock.patch.object(ManageDialog, "restoreGeometry") as restore:  # the offscreen screen is too small
        keep(ManageDialog(db, lambda: None))
    assert bytes(restore.call_args.args[0].toHex()).decode() == saved


# ── Manage → Merchants ───────────────────────────────────────────────────────
def test_merchants_tab_shows_a_merchants_transactions(qapp, db, food):
    db.add_category("Refunds", "Income")
    ref = db.get_category_by_name("Refunds", type_name="Income")["id"]
    db.add_transaction(2026, "May", 20, "Income", "Card", 3, db.uncategorized_subcategory(ref)["id"], ref,
                       name="SUNRISE GIFT", merchant="Sunrise")
    dlg, p, opened = panel_on(db)
    m = dlg.merchants_panel
    assert m.chk_lines.isChecked() and not m.lines.isHidden()  # one tick for both tabs
    m.chk_lines.setChecked(False)
    assert not p.chk_lines.isChecked() and p.lines.isHidden()
    m.chk_lines.setChecked(True)
    m.select("Sunrise")
    assert m.lines.title.text() == "Sunrise — 3 transactions · $3.00 net spent"  # 10 − 4 − 3
    assert [m.lines.table.item(r, m.lines.columns.index("category")).text()
            for r in range(m.lines.table.rowCount())] == ["Refunds", "Groceries", "Groceries"]
    m.lines._double_clicked(0, 0)
    (text, panel), filters = opened[-1]
    assert panel == "merchants" and filters["types"] == ["Income"] and filters["from_day"] == "2026-05-20"
    m.select("")
    assert m.lines.title.text().startswith("(no merchant) — 1 transaction ")


# ── 0.31.1: the columns of Transactions, and the lists as wide as their text ──
def test_the_columns_are_those_of_transactions(qapp, db, food):
    from daftarche.style import get_settings
    db.add_tag("Party")
    tag_id = db.conn.execute("SELECT id FROM tags WHERE name = 'Party'").fetchone()[0]
    sunrise = db.conn.execute("SELECT id FROM transactions WHERE name = 'SUNRISE 1'").fetchone()[0]
    db.set_tags_for_transaction(sunrise, [tag_id])
    assert next(x for x in db.get_lines(food["cat"]) if x["name"] == "SUNRISE 1")["tags"] == "Party"
    s = get_settings()
    s._data["transactions_columns"] = {"memo": False, "fitid": False}
    s._data["transactions_column_order"] = ["amount", "date", "name", "tags", "merchant", "type", "category",
                                            "subcategory", "account", "memo", "note", "fitid"]
    dlg, p, _ = panel_on(db)
    assert p.lines.columns == ["amount", "date", "name", "tags", "merchant", "subcategory", "account", "note"]
    assert dlg.merchants_panel.lines.columns == ["amount", "date", "name", "tags", "type", "category",
                                                 "subcategory", "account", "note"]  # the merchant left out
    names = [p.lines.table.item(r, 2).text() for r in range(p.lines.table.rowCount())]
    row = names.index("SUNRISE 1")
    assert p.lines.table.item(row, 3).text() == "Party"
    s._data["transactions_columns"] = {"memo": False, "fitid": False, "note": False}  # changed in Transactions
    p.refresh()
    assert "note" not in p.lines.columns


def test_the_merchants_are_only_as_wide_as_their_text(qapp, db, food):
    from PySide6.QtWidgets import QSizePolicy
    dlg, p, _ = panel_on(db)
    assert p.merchant_table.sizePolicy().horizontalPolicy() == QSizePolicy.Maximum
    assert dlg.merchants_panel.rules.sizePolicy().horizontalPolicy() == QSizePolicy.Maximum
