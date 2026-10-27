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
            dlg.chk_lines.setChecked(True)
    return dlg, p, opened


def shown(lines):
    """The bank names of the transactions a Manage list shows, as listed."""
    return [r["name"] for r in lines.tx.model._rows]


def hidden(lines, key):
    from daftarche.tabs.transactions import COLUMN_KEYS
    return lines.table.isColumnHidden(COLUMN_KEYS.index(key))


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
    assert not dlg.chk_lines.isChecked() and p.lines.isHidden()
    assert dlg.tabs.cornerWidget() is dlg.chk_lines.parentWidget()  # beside the tabs, once for all



def test_the_transactions_of_the_category(qapp, db, food):
    from daftarche.style import get_settings
    from daftarche.tabs.transactions import TransactionsTab
    from daftarche.tx_list import SHOW_KEY
    dlg, p, _ = panel_on(db)
    assert get_settings().get(SHOW_KEY) is True and not p.lines.isHidden()
    assert isinstance(p.lines.tx, TransactionsTab)  # the Transactions table itself
    assert p.lines.title.text() == "Groceries"
    assert sorted(shown(p.lines)) == ["BIG BOX", "FARM STAND", "SUNRISE 1", "SUNRISE REFUND"]  # Big Box by its part
    assert hidden(p.lines, "type") and hidden(p.lines, "category") and not hidden(p.lines, "merchant")
    assert p.lines.tx.lbl_rows_info.text().startswith("Rows: 4")


def test_a_merchant_narrows_them_and_show_all_widens_them(qapp, db, food):
    dlg, p, _ = panel_on(db)
    row = next(r for r in range(p.merchant_table.rowCount()) if p.merchant_table.item(r, 0).text() == "Sunrise")
    p.merchant_table.selectRow(row)
    assert p.lines.title.text() == "Sunrise in Groceries"
    assert sorted(shown(p.lines)) == ["SUNRISE 1", "SUNRISE REFUND"] and hidden(p.lines, "merchant")
    assert not p.lines.btn_all.isHidden()
    p.lines.btn_all.click()
    assert len(shown(p.lines)) == 4 and p.lines.btn_all.isHidden() and not hidden(p.lines, "merchant")


def test_a_sub_category_and_the_merchant_kept_on_refresh(qapp, db, food):
    dlg, p, _ = panel_on(db)
    p._select_by_name(p.sub_table, "Bakery")
    assert p.lines.title.text() == "Groceries › Bakery" and len(shown(p.lines)) == 2
    assert hidden(p.lines, "subcategory")
    p.merchant_table.selectRow(0)
    p.refresh()
    assert p.lines.title.text() == "Sunrise in Groceries › Bakery"


def test_rows_edited_there_as_in_transactions(qapp, db, food):
    """Several rows selected, Edit Merchant / Category: saved, and Manage shows it at once."""
    from types import SimpleNamespace
    from PySide6.QtCore import QItemSelectionModel
    changes = []
    dlg, p, _ = panel_on(db)
    dlg.on_change_cb = lambda: changes.append(1)
    p._select_by_name(p.sub_table, "Bakery")
    tx = p.lines.tx
    rows = [i for i, r in enumerate(tx.model._rows)]
    for i in rows:
        tx.table.selectionModel().select(tx.model.index(i, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    answer = SimpleNamespace(exec=lambda: True, cat_name="Groceries", sub_name="Market", row_type="Expense",
                             merchant_changed=True, merchant="Sunrise Bakery", flipped=False,
                             apply_keys=[], apply_merchants={})
    with mock.patch.object(type(tx), "_category_dialog", lambda self, kind, rows: answer):
        tx._bulk_edit_cat()
    subs = {r["name"]: (r["subcategory"], r["merchant"]) for r in db.get_transactions({})}
    assert subs["SUNRISE 1"] == ("Market", "Sunrise Bakery") and subs["SUNRISE REFUND"] == ("Market", "Sunrise Bakery")
    assert changes  # the main window is told too
    counts = {p.sub_table.item(r, 0).text(): p.sub_table.item(r, 1).text() for r in range(p.sub_table.rowCount())}
    assert counts["Bakery"] == "0" and counts["Market"] == "4"  # the lists followed


def test_the_first_time_manage_fills_the_screen(qapp, db, food):
    dlg, p, _ = panel_on(db, shown=False)
    with mock.patch.object(dlg, "showMaximized") as fill:
        dlg.chk_lines.setChecked(True)
        dlg.chk_lines.setChecked(False)
        dlg.chk_lines.setChecked(True)
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
    dlg, p, _ = panel_on(db)
    m = dlg.merchants_panel
    assert not m.lines.isHidden()  # one tick for every tab
    dlg.chk_lines.setChecked(False)
    assert p.lines.isHidden() and m.lines.isHidden()
    dlg.chk_lines.setChecked(True)
    m.select("Sunrise")
    assert m.lines.title.text() == "Sunrise" and hidden(m.lines, "merchant")
    assert sorted(shown(m.lines)) == ["SUNRISE 1", "SUNRISE GIFT", "SUNRISE REFUND"]
    m.select("")
    assert shown(m.lines) == ["FARM STAND"]


# ── 0.31.1: the columns of Transactions, and the lists as wide as their text ──
def test_the_columns_are_those_of_transactions(qapp, db, food):
    from daftarche.style import get_settings
    s = get_settings()
    s._data["transactions_columns"] = {"memo": False, "fitid": False}
    dlg, p, _ = panel_on(db)
    assert hidden(p.lines, "memo") and hidden(p.lines, "fitid") and not hidden(p.lines, "name")


def test_the_merchants_are_only_as_wide_as_their_text(qapp, db, food):
    from PySide6.QtWidgets import QSizePolicy
    dlg, p, _ = panel_on(db)
    assert p.merchant_table.sizePolicy().horizontalPolicy() == QSizePolicy.Maximum
    assert dlg.merchants_panel.rules.sizePolicy().horizontalPolicy() == QSizePolicy.Maximum


def test_the_line_between_the_lists_lights_up_and_has_room(qapp, db, food):
    from PySide6.QtCore import Qt
    from daftarche.style import build_stylesheet
    dlg, p, _ = panel_on(db)
    for panel in (p, dlg.merchants_panel):
        handle = panel.split.handle(1)
        assert handle.testAttribute(Qt.WA_Hover)
        assert panel.split.widget(0).layout().contentsMargins().bottom() == 10
    assert "QSplitter::handle:hover" in build_stylesheet()


def test_sub_categories_count_their_merchants_and_rules(qapp, db, food):
    db.save_mapping("Expense", None, name="SUNRISE", subcategory_id=food["bakery"], category_id=food["cat"],
                    merchant="Sunrise")
    assert db.get_merchant_count_for_subcategory(food["bakery"]) == 1
    assert db.get_merchant_count_for_subcategory(food["market"]) == 1  # Big Box's part; FARM STAND has none
    dlg, p, _ = panel_on(db, shown=False)
    rows = {p.sub_table.item(r, 0).text(): [p.sub_table.item(r, c).text() for c in (1, 2, 3)]
            for r in range(p.sub_table.rowCount())}
    assert rows["Bakery"] == ["2", "1", "1"] and rows["Market"] == ["2", "1", "0"]
    assert p.sub_table.horizontalHeaderItem(3).toolTip() == "Rules that send money here"


# ── one way of writing numbers; the totals line; Accounts and Tags ──────────────
def test_headers_and_quiet_zeros(qapp, db, food):
    dlg, p, _ = panel_on(db, shown=False)
    headers = lambda table: [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    assert headers(p.sub_table) == ["Name", "Tx", "M", "R"]
    assert headers(p.merchant_table) == ["Merchant", "Tx", "R", "Total"]
    assert headers(dlg.merchants_panel.table) == ["Merchant", "Tx", "R", "Total"]
    assert headers(dlg.accounts_panel.table)[-1] == "Tx" and headers(dlg.tags_panel.table) == ["Tag", "Tx"]
    rows = {p.merchant_table.item(r, 0).text(): r for r in range(p.merchant_table.rowCount())}
    none = rows["(no merchant)"]
    assert p.merchant_table.item(none, p.M_RULES).text() == "0"  # a number, not —
    mp = dlg.merchants_panel
    mrows = {mp.table.item(r, 0).text(): r for r in range(mp.table.rowCount())}
    assert mp.table.item(mrows["(no merchant)"], mp.COL_TOTAL).text() == "$30.00"
    zero = mp.table.item(mrows["Sunrise"], mp.COL_RULES)
    assert zero.text() == "0" and zero.foreground().color().name() != mp.table.item(mrows["Sunrise"], 0).foreground().color().name()


def test_the_merchants_totals_line(qapp, db, food):
    dlg, p, _ = panel_on(db, shown=False)
    mp = dlg.merchants_panel
    line = [mp.totals.item(0, c).text() for c in range(4)]
    assert line == ["2 merchants", "4", "0", "$136.00"]  # Sunrise, Big Box (all of it), the one with none
    mp.find.setText("sun")
    assert [mp.totals.item(0, c).text() for c in range(4)] == ["1 merchant", "2", "0", "$6.00"]


def test_accounts_and_tags_show_their_transactions_beside_them(qapp, db, food):
    from PySide6.QtCore import Qt
    db.add_tag("Party")
    tag_id = db.conn.execute("SELECT id FROM tags WHERE name = 'Party'").fetchone()[0]
    sunrise = db.conn.execute("SELECT id FROM transactions WHERE name = 'SUNRISE 1'").fetchone()[0]
    db.set_tags_for_transaction(sunrise, [tag_id])
    dlg, p, _ = panel_on(db)
    a = dlg.accounts_panel
    assert a.split.orientation() == Qt.Horizontal and not a.lines.isHidden()
    a.table.selectRow(0)
    assert a.lines.title.text() == "Card" and len(shown(a.lines)) == 4  # Big Box once, with its parts
    tg = dlg.tags_panel
    tg.table.selectRow(0)
    assert tg.lines.title.text() == "Party" and shown(tg.lines) == ["SUNRISE 1"]


def test_manage_follows_changes_made_in_the_window(qapp, db, food):
    dlg, p, _ = panel_on(db, shown=False)
    db.add_tag("Later")
    dlg.outside_change()
    assert [dlg.tags_panel.table.item(r, 0).text() for r in range(dlg.tags_panel.table.rowCount())] == ["Later"]
