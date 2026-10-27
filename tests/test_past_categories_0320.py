"""0.32.0: the categories a merchant had before, one click away (right-click, the Edit window),
and the question when a rule's category no longer fits its merchant."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_settings():
    from daftarche.past_categories import KEEP_KEY
    from daftarche.style import get_settings
    s = get_settings()
    before = s._data.pop(KEEP_KEY, None)
    with mock.patch.object(s, "save"):
        yield
    s._data.pop(KEEP_KEY, None)
    if before is not None:
        s._data[KEEP_KEY] = before


@pytest.fixture
def amazon(db):
    db.get_or_create_account("Card")
    ids = {}
    for cat, subs in (("Shopping", ("Household", "Electronics")), ("Home", ("Tools",)), ("Leisure", ("Books",))):
        db.add_category(cat, "Expense")
        c = db.get_category_by_name(cat, type_name="Expense")["id"]
        for s in subs:
            db.add_subcategory(s, c)
            ids[s] = (c, db.get_subcategory_by_name(s, c)["id"])
    uc, us = db.get_uncategorized_ids()
    day = iter(range(1, 29))

    def add(sub, n, name="AMAZON"):
        cat, s = ids[sub] if sub else (uc, us)
        return [db.add_transaction(2026, "May", next(day), "Expense", "Card", 10, s, cat, name=name,
                                   merchant="Amazon") for _ in range(n)]
    add("Household", 5)
    add("Electronics", 3)
    add("Tools", 2)
    add("Books", 1)  # the last one bought: books
    new = add(None, 2)  # waiting in To review
    db.save_mapping("Expense", None, name="AMAZON", subcategory_id=ids["Household"][1],
                    category_id=ids["Household"][0], merchant="Amazon")
    db.conn.commit()
    return {"ids": ids, "new": new}


def tab(db):
    from daftarche.tabs.transactions import TransactionsTab
    t = keep(TransactionsTab(db))
    t._period._select_preset(0, emit=False, persist=False)
    t._apply_filters()
    return t


def rows_of(t, ids):
    return [i for i, r in enumerate(t.model._rows) if r["id"] in ids]


# ── the database ─────────────────────────────────────────────────────────────
def test_most_used_first_and_the_last_one_on_top(db, amazon):
    past = db.merchant_categories("amazon ", "Expense")
    assert [(p["subcategory"], p["count"]) for p in past] == [
        ("Books", 1), ("Household", 5), ("Electronics", 3), ("Tools", 2)]  # Books: used last, 4th by count
    assert db.merchant_categories("Amazon", "Income") == [] and db.merchant_categories("", "Expense") == []


def test_the_last_one_among_the_three_most_used_stays_in_place(db, amazon):
    db.add_transaction(2026, "June", 1, "Expense", "Card", 10, amazon["ids"]["Tools"][1], amazon["ids"]["Tools"][0],
                       name="AMAZON", merchant="Amazon")
    assert [p["subcategory"] for p in db.merchant_categories("Amazon", "Expense")] == [
        "Household", "Tools", "Electronics", "Books"]  # Tools: used last, now 3 like Electronics


# ── right-click ──────────────────────────────────────────────────────────────
def test_the_menu_offers_them_and_one_click_sets_it(qapp, db, amazon):
    from PySide6.QtWidgets import QMenu
    t = tab(db)
    picked = rows_of(t, amazon["new"])
    menu = QMenu()
    t._add_past_categories(menu, picked, [t.model.get_row(i) for i in picked])
    sub = menu.actions()[0].menu()
    assert menu.actions()[0].text() == "🏷️  Use a Category of Amazon"
    assert [a.text() for a in sub.actions() if a.text()][:2] == ["Leisure › Books\t1", "Shopping › Household\t5"]
    with mock.patch("daftarche.past_categories.ask_merchant_only", return_value="later") as ask:
        t.use_category(picked, db.merchant_categories("Amazon", "Expense")[2])  # Electronics
    subs = {r["id"]: r["subcategory"] for r in db.get_transactions({})}
    assert [subs[i] for i in amazon["new"]] == ["Electronics", "Electronics"]
    assert ask.call_count == 1  # its rule gives Household: asked once for both rows
    assert db.lookup_mapping("Expense", "Card", "AMAZON")["subcategory_id"] == amazon["ids"]["Household"][1]
    assert sorted(t.model._rows[i]["id"] for i in t._get_selected_row_indices()) == sorted(amazon["new"])


def test_no_menu_for_several_merchants(qapp, db, amazon):
    from PySide6.QtWidgets import QMenu
    t = tab(db)
    db.update_transaction(amazon["new"][1], merchant="Kobo")
    t._apply_filters()
    picked = rows_of(t, amazon["new"])
    menu = QMenu()
    t._add_past_categories(menu, picked, [t.model.get_row(i) for i in picked])
    assert menu.actions() == []


# ── the question about the rule ──────────────────────────────────────────────
@pytest.mark.parametrize("answer", ["merchant", "later", "never"])
def test_the_three_answers(qapp, db, amazon, answer):
    from daftarche.past_categories import KEEP_KEY
    from daftarche.style import get_settings
    t = tab(db)
    tools = next(p for p in db.merchant_categories("Amazon", "Expense") if p["subcategory"] == "Tools")
    with mock.patch("daftarche.past_categories.ask_merchant_only", return_value=answer) as ask:
        t.use_category(rows_of(t, amazon["new"][:1]), tools)
        t.use_category(rows_of(t, amazon["new"][1:]), tools)
    rule = db.lookup_mapping("Expense", "Card", "AMAZON")
    uc, _ = db.get_uncategorized_ids()
    if answer == "merchant":
        assert rule["category_id"] == uc and rule["merchant"] == "Amazon" and ask.call_count == 1  # nothing to ask
    elif answer == "later":
        assert rule["category_id"] == amazon["ids"]["Household"][0] and ask.call_count == 2  # asked again
    else:
        assert rule["id"] in get_settings().get(KEEP_KEY) and ask.call_count == 1


def test_no_question_when_the_rule_gives_that_category(qapp, db, amazon):
    t = tab(db)
    household = next(p for p in db.merchant_categories("Amazon", "Expense") if p["subcategory"] == "Household")
    with mock.patch("daftarche.past_categories.ask_merchant_only") as ask:
        t.use_category(rows_of(t, amazon["new"]), household)
    assert not ask.called


# ── the Edit window ──────────────────────────────────────────────────────────
def test_the_edit_window_shows_them_and_fills_them_in(qapp, db, amazon):
    from daftarche.category_dialog import CategoryDialog
    d = keep(CategoryDialog(db, "Expense", preset_merchant="Amazon"))
    texts = [b.text() for b in d.past_buttons]
    assert texts[0] == "Leisure › Books · 1" and "Shopping › Household · 5" in texts
    d.past_buttons[2].click()  # Electronics
    assert (d.f_category.currentText(), d.f_subcat.currentText()) == ("Shopping", "Electronics")
    d.f_merchant.setCurrentText("Nobody")
    assert d.past_host.isHidden() and d.past_buttons == []
    mixed = keep(CategoryDialog(db, "Expense", preset_merchant=None, merchant_mixed=True))
    assert mixed.past_host.isHidden()


# ── Manage → Merchants: "Used in" ────────────────────────────────────────────
def merchants_panel(db):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import ManageDialog
    from daftarche.tx_list import SHOW_KEY
    get_settings()._data[SHOW_KEY] = True
    return keep(ManageDialog(db, lambda: None)).merchants_panel


def test_used_in_lists_its_categories_and_a_click_narrows_them(qapp, db, amazon):
    m = merchants_panel(db)
    m.select("Amazon")
    names = [m.used.item(r, 0).text() for r in range(m.used.rowCount())]
    counts = [m.used.item(r, m.U_TX).text() for r in range(m.used.rowCount())]
    assert names == ["Shopping › Household", "Shopping › Electronics", "Home › Tools", "Leisure › Books"]
    assert counts == ["5", "3", "2", "1"] and m.used.isColumnHidden(m.U_TYPE)  # one type
    assert len(m.lines.tx.model._rows) == 13 and m.lines.btn_all.isHidden()
    m.used.selectRow(2)
    assert m.lines.title.text() == "Amazon in Home › Tools" and len(m.lines.tx.model._rows) == 2
    assert not m.lines.btn_all.isHidden()
    m.refresh()  # after an edit: still Tools
    assert m.lines.title.text() == "Amazon in Home › Tools"
    m.lines.btn_all.click()
    assert len(m.lines.tx.model._rows) == 13 and m.lines.btn_all.isHidden()


def test_used_in_starts_over_for_another_merchant_and_hides_when_empty(qapp, db, amazon):
    db.add_transaction(2026, "June", 2, "Expense", "Card", 5, *db.get_uncategorized_ids()[::-1], name="X",
                       merchant="Kobo")
    m = merchants_panel(db)
    m.select("Amazon")
    m.used.selectRow(0)
    m.select("Kobo")  # only uncategorized
    assert m.used_host.isHidden() and m.lines.title.text() == "Kobo"
    m.select("Amazon")
    assert not m.used_host.isHidden() and m._selected_used() is None


def test_no_review_button_in_manage(qapp, db, amazon):
    m = merchants_panel(db)
    m.select("Amazon")
    assert m.lines.tx.btn_review.isHidden() and db.get_to_review_count() == 2


def test_the_question_buttons_fit_their_text(qapp):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from daftarche.past_categories import ask_merchant_only
    seen = []

    def look():
        box = next(w for w in QApplication.topLevelWidgets() if isinstance(w, QMessageBox) and w.isVisible())
        seen.extend((b.text(), b.width(), b.fontMetrics().horizontalAdvance(b.text())) for b in box.buttons())
        box.buttons()[0].click()
    QTimer.singleShot(0, look)
    ask_merchant_only(None, "Apollo", "Insurance › Home", 2)
    assert len(seen) == 3 and all(width > text for _, width, text in seen)
