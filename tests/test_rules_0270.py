"""0.27.0: rules live under their merchant, the Categories tab lists merchants, Transfer rules
set the person and the category (Loans)."""

from unittest import mock

import pytest

from conftest import keep
from test_multi_import import qfx, tab_for


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shop(db):
    db.get_or_create_account("Card")
    db.add_category("Shopping", "Expense")
    cat = db.get_category_by_name("Shopping", type_name="Expense")["id"]
    db.add_subcategory("Books", cat)
    db.add_subcategory("Electronics", cat)
    books = db.get_subcategory_by_name("Books", cat)["id"]
    elec = db.get_subcategory_by_name("Electronics", cat)["id"]
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Expense", "Card", 30, books, cat, name="AMZN DIGITAL", merchant="Amazon")
    db.add_transaction(2026, "May", 2, "Expense", "Card", 200, elec, cat, name="AMZN MKTP CA", merchant="Amazon")
    db.add_transaction(2026, "May", 3, "Expense", "Card", 12, books, cat, name="INDIGO 123", merchant="Indigo")
    db.add_transaction(2026, "May", 4, "Expense", "Card", 8, books, cat, name="USED BOOK SALE")
    db.save_mapping("Expense", None, name="AMZN DIGITAL", subcategory_id=books, category_id=cat, merchant="Amazon")
    db.save_mapping("Expense", None, name="AMZN MKTP", subcategory_id=us, category_id=uc, merchant="Amazon")
    db.save_mapping("Expense", None, name="KOBO", subcategory_id=books, category_id=cat, merchant="Kobo")
    db.save_mapping("Expense", "Card", name="PURCHASE INTEREST", subcategory_id=us, category_id=uc)  # no merchant
    return {"cat": cat, "books": books, "elec": elec}


# ── the database ─────────────────────────────────────────────────────────────
def test_rules_of_a_merchant_and_of_none(db, shop):
    from daftarche.tabs.manage import YOU_CHOOSE, rule_sets, rule_text
    amazon = db.get_rules("Amazon")
    assert [(r["name"], rule_sets(r)) for r in amazon] == [("AMZN DIGITAL", "Shopping › Books"),
                                                           ("AMZN MKTP", YOU_CHOOSE)]
    assert [r["name"] for r in db.get_rules(no_merchant=True)] == ["PURCHASE INTEREST"]
    assert rule_text({"name": "AMAZON", "memorandum": "REFUND"}) == "AMAZON  /  memo: REFUND"
    assert db.get_no_merchant_counts() == (1, 1)


def test_rules_get_a_merchant_in_its_spelling(db, shop):
    rule = db.get_rules(no_merchant=True)[0]["id"]
    assert db.set_rules_merchant([rule], "  amazon ") == "Amazon"  # the name already used
    assert db.get_no_merchant_counts() == (1, 0) and len(db.get_rules("Amazon")) == 3
    with pytest.raises(ValueError):
        db.set_rules_merchant([rule], " ")


def test_merchants_in_a_sub_category_and_in_a_category(db, shop):
    sub = {m["merchant"]: (m["count"], m["total"], m["rules"]) for m in db.get_merchants_in(shop["cat"], shop["books"])}
    assert sub == {"Amazon": (1, 30.0, 1), "Indigo": (1, 12.0, 0), "Kobo": (0, 0.0, 1), "": (1, 8.0, 0)}
    whole = db.get_merchants_in(shop["cat"])
    assert whole[0]["merchant"] == "Amazon" and (whole[0]["count"], whole[0]["total"]) == (2, 230.0)
    assert whole[-1]["merchant"] == ""  # no merchant: last


def test_split_parts_count_in_their_own_sub_category(db, shop):
    amazon = next(t for t in db.get_transactions() if t["name"] == "AMZN MKTP CA")["id"]
    db.set_splits(amazon, [(shop["cat"], shop["books"], 50, None), (shop["cat"], shop["elec"], 150, None)])
    books = {m["merchant"]: (m["count"], m["total"]) for m in db.get_merchants_in(shop["cat"], shop["books"])}
    assert books["Amazon"] == (2, 80.0)


# ── the rule window ──────────────────────────────────────────────────────────
def test_rule_window_counts_what_it_matches(qapp, db, shop):
    from daftarche.tabs.manage import RuleEditDialog
    d = keep(RuleEditDialog(db, merchant="Amazon"))
    assert d.f_merchant.currentText() == "Amazon" and d.f_type.currentText() == "Expense"
    d.f_name.setText("amzn")
    assert d.matches.text().startswith("Matches 2 of your transactions")
    d.f_name.setText("amzn|digital")
    assert d.matches.text() == "Matches 1 of your transactions, e.g. AMZN DIGITAL."
    d.f_name.setText("walmart")
    assert d.matches.text() == "Matches none of your transactions yet."


def test_rule_window_values(qapp, db, shop):
    from daftarche.tabs.manage import YOU_CHOOSE, RuleEditDialog
    uc, us = db.get_uncategorized_ids()
    d = keep(RuleEditDialog(db, merchant="amazon"))
    d.f_name.setText("AMAZON PRIME")
    assert d.f_cat.currentText() == YOU_CHOOSE and not d.f_sub.isEnabled()
    v = d.values()
    assert (v["merchant"], v["category_id"], v["subcategory_id"]) == ("Amazon", uc, us)  # its spelling
    d.f_cat.setCurrentText("Shopping")
    d.f_sub.setCurrentText("Books")
    assert (d.values()["category_id"], d.values()["subcategory_id"]) == (shop["cat"], shop["books"])
    edit = keep(RuleEditDialog(db, existing=db.get_rules("Kobo")[0]))
    assert (edit.f_merchant.currentText(), edit.f_cat.currentText(), edit.f_sub.currentText(),
            edit.f_name.text()) == ("Kobo", "Shopping", "Books", "KOBO")


def test_rule_window_needs_a_merchant_and_words(qapp, db, shop):
    from daftarche.tabs.manage import RuleEditDialog
    d = keep(RuleEditDialog(db))
    d.f_name.setText("SHOP")
    with mock.patch("daftarche.tabs.manage.QMessageBox") as box, mock.patch.object(d, "accept") as ok:
        d._validate()
        assert box.warning.called and not ok.called
        d.f_merchant.setCurrentText("Shop")
        d.f_name.setText("")
        d._validate()
        assert not ok.called
        d.f_name.setText("KOBO")  # the text of Kobo's rule: replace it?
        box.question.return_value = box.No
        d._validate()
        assert box.question.called and not ok.called


def test_transfer_rules_offer_external_transfer_and_loans(qapp, db):
    from daftarche.db import CAT_EXTERNAL_TRANSFER, SUB_UNMATCHED
    from daftarche.tabs.manage import RuleEditDialog
    d = keep(RuleEditDialog(db, merchant="Ali"))
    d.f_type.setCurrentText("Transfer")
    cats = [d.f_cat.itemText(i) for i in range(d.f_cat.count())]
    assert cats[0] == CAT_EXTERNAL_TRANSFER and "Loans" in cats and "Internal Transfer" not in cats
    d.f_name.setText("ALI")
    v = d.values()
    ext = db.get_category_by_name(CAT_EXTERNAL_TRANSFER)
    assert v["category_id"] == ext["id"]
    assert v["subcategory_id"] == db.get_subcategory_by_name(SUB_UNMATCHED, ext["id"])["id"]
    d.f_cat.setCurrentText("Loans")
    assert d.values()["category_id"] == db.loans_category()["id"] and d.f_sub.isEnabled()


# ── importing: a Transfer rule sets the person and its category ──────────────
def test_an_etransfer_rule_to_loans_sets_the_person_and_loans(qapp, db, tmp_path):
    db.get_or_create_account("Vahid-CIBC-Chequing")
    db.save_account_id("111", "Vahid-CIBC-Chequing")
    loans = db.loans_category()["id"]
    db.save_mapping("Transfer", None, name="ALI", subcategory_id=db.uncategorized_subcategory(loans)["id"],
                    category_id=loans, merchant="Ali")
    db.save_mapping("Transfer", None, name="SARA", subcategory_id=None, category_id=None, merchant="Sara")
    sara_rule = db.get_rule_id("Transfer", None, "SARA")
    ext = db.get_category_by_name("External Transfer")["id"]
    db.conn.execute("UPDATE import_mappings SET category_id=?, subcategory_id=(SELECT id FROM subcategories "
                    "WHERE category_id=? LIMIT 1) WHERE id=?", (ext, ext, sara_rule))
    f = tmp_path / "c.qfx"
    f.write_text(qfx("111", [("DEBIT", "20260605", "-500.00", "E1", "E-TRANSFER ALI", "E-TRANSFER 123"),
                             ("DEBIT", "20260606", "-20.00", "E2", "E-TRANSFER SARA", "E-TRANSFER 456")]),
                 encoding="cp1252")
    tab = tab_for(db)
    tab.load_files([str(f)])
    rows = {r["name"]: r for r in tab.parsed_rows}
    assert rows["E-TRANSFER ALI"]["category"]["name"] == "Loans" and rows["E-TRANSFER ALI"]["merchant"] == "Ali"
    assert rows["E-TRANSFER SARA"]["category"]["name"] == "External Transfer"
    assert rows["E-TRANSFER SARA"]["merchant"] == "Sara"  # was left out before
    with mock.patch("daftarche.tabs.import_tab.QMessageBox"):
        tab.import_all()
    ali = next(t for t in db.get_transactions() if t["name"] == "E-TRANSFER ALI")
    assert (ali["category"], ali["merchant"], ali["transfer_status"]) == ("Loans", "Ali", "loan")
    assert [e["merchant"] for e in db.get_loans()] == ["Ali"]


# ── Manage ───────────────────────────────────────────────────────────────────
def _expense(panel, name="Shopping"):
    t = panel.type_table
    t.selectRow(next(r for r in range(t.rowCount()) if t.item(r, 0).text() == "Expense"))
    c = panel.cat_table
    c.selectRow(next(r for r in range(c.rowCount()) if c.item(r, 0).text() == name))


def test_categories_tab_lists_the_merchants(qapp, db, shop):
    from daftarche.tabs.manage import NO_MERCHANT, ManageDialog
    shown = []
    dlg = keep(ManageDialog(db, lambda: None, show_transactions=lambda text, panel, **f: shown.append((panel, f))))
    panel = dlg.cats_panel
    _expense(panel)
    names = lambda: [panel.merchant_table.item(r, 0).text() for r in range(panel.merchant_table.rowCount())]  # noqa
    assert panel._selected_data(panel.sub_table) is None  # the whole category first
    assert names() == ["Amazon", "Indigo", "Kobo", NO_MERCHANT]
    assert panel.merchant_title.text().startswith("Merchants in Shopping")
    books = next(r for r in range(panel.sub_table.rowCount()) if panel.sub_table.item(r, 0).text() == "Books")
    panel.sub_table.selectRow(books)
    assert names() == ["Amazon", "Indigo", "Kobo", NO_MERCHANT] and panel.merchant_title.text() == \
        "Merchants in Books"
    panel._merchant_double_clicked(0, panel.M_TX)  # its transactions in the main window
    assert shown == [("cats", {"types": ["Expense"], "categories": ["Shopping"], "subcategories": ["Books"],
                               "merchants": ["Amazon"]})]
    panel._merchant_double_clicked(2, panel.M_NAME)  # the merchant: its rules
    assert dlg.tabs.currentWidget() is dlg.merchants_panel
    assert dlg.merchants_panel._selected()["merchant"] == "Kobo"
    assert dlg.merchants_panel.rules.rowCount() == 1


def test_merchants_tab_no_merchant_line_and_set_merchant(qapp, db, shop):
    from PySide6.QtCore import Qt
    from daftarche.tabs.manage import NO_MERCHANT, ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    panel = dlg.merchants_panel
    for order in (Qt.AscendingOrder, Qt.DescendingOrder):
        panel.table.sortByColumn(panel.COL_TX, order)
        assert panel.table.item(panel.table.rowCount() - 1, 0).text() == NO_MERCHANT  # always last
    panel.select("")
    assert not panel.btn_set_merchant.isHidden() and panel.rules.rowCount() == 1
    panel.rules.selectRow(0)
    with mock.patch("daftarche.tabs.manage.QInputDialog.getItem", return_value=("CIBC", True)):
        panel.set_rules_merchant()
    assert [r["name"] for r in db.get_rules("CIBC")] == ["PURCHASE INTEREST"]
    assert db.get_no_merchant_counts() == (1, 0)


def test_merchants_tab_adds_and_edits_rules(qapp, db, shop):
    from daftarche.tabs.manage import ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    panel = dlg.merchants_panel
    panel.select("Amazon")

    def fill(d):
        d.f_name.setText("AMAZON PRIME")
        d.f_cat.setCurrentText("Shopping")
        return True

    with mock.patch("daftarche.tabs.manage.RuleEditDialog.exec", fill):
        panel.add_rule()
    assert sorted(r["name"] for r in db.get_rules("Amazon")) == ["AMAZON PRIME", "AMZN DIGITAL", "AMZN MKTP"]
    row = next(r for r in range(panel.rules.rowCount()) if panel.rules.item(r, 0).text() == "AMZN MKTP")
    panel.rules.selectRow(row)

    def move(d):
        d.f_merchant.setCurrentText("Amazon Marketplace")
        return True

    with mock.patch("daftarche.tabs.manage.RuleEditDialog.exec", move):
        panel.edit_rule()
    assert [r["name"] for r in db.get_rules("Amazon Marketplace")] == ["AMZN MKTP"]
    assert panel._selected()["merchant"] == "Amazon Marketplace"


# ── from the review ──────────────────────────────────────────────────────────
def test_editing_keeps_a_category_the_list_does_not_offer(qapp, db):
    from daftarche.db import CAT_INTERNAL_TRANSFER, SUB_MATCHED
    from daftarche.tabs.manage import RuleEditDialog
    internal = db.get_category_by_name(CAT_INTERNAL_TRANSFER)["id"]
    matched = db.get_subcategory_by_name(SUB_MATCHED, internal)["id"]
    db.save_mapping("Transfer", None, name="VISA PAYMENT", subcategory_id=matched, category_id=internal,
                    merchant="CIBC")
    d = keep(RuleEditDialog(db, existing=db.get_rules("CIBC")[0]))
    v = d.values()
    assert (v["category_id"], v["subcategory_id"]) == (internal, matched)  # OK unchanged changes nothing


def test_the_exact_merchant_spelling_is_kept(qapp, db):
    from daftarche.tabs.manage import RuleEditDialog
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Expense", "Card", 5, us, uc, name="X", merchant="Amazon")
    db.save_mapping("Expense", None, name="AMZ", subcategory_id=us, category_id=uc, merchant="amazon")
    d = keep(RuleEditDialog(db, existing=db.get_rules("amazon")[0]))
    assert d.values()["merchant"] == "amazon"
    assert db.get_merchants() == ["Amazon", "amazon"]  # a steady order


def test_rule_text_in_another_letter_case_is_the_same_rule(db):
    uc, us = db.get_uncategorized_ids()
    db.save_mapping("Expense", None, name="KOBO", subcategory_id=us, category_id=uc, merchant="Kobo")
    assert db.get_rule_id("Expense", None, "kobo ") == db.get_rule_id("Expense", None, "KOBO")
    db.save_mapping("Expense", None, name="kobo", subcategory_id=us, category_id=uc, merchant="Kobo2")
    assert [(r["name"], r["merchant"]) for r in db.get_rules("Kobo2")] == [("KOBO", "Kobo2")]
    assert db.get_rules("Kobo") == []


def test_a_rule_with_no_type_must_get_one(qapp, db):
    from daftarche.tabs.manage import RuleEditDialog
    uc, us = db.get_uncategorized_ids()
    db.save_mapping(None, None, name="OLD", subcategory_id=us, category_id=uc, merchant="Old")
    d = keep(RuleEditDialog(db, existing=db.get_rules("Old")[0]))
    assert d.f_type.currentText() == ""
    with mock.patch("daftarche.tabs.manage.QMessageBox") as box, mock.patch.object(d, "accept") as ok:
        d._validate()
    assert box.warning.called and not ok.called


def test_values_write_nothing_before_ok(qapp, db, shop):
    from daftarche.tabs.manage import RuleEditDialog, save_rule
    db.add_category("Pets", "Expense")
    before = db.conn.execute("SELECT COUNT(*) FROM subcategories").fetchone()[0]
    d = keep(RuleEditDialog(db, merchant="Pet Shop"))
    d.f_name.setText("PET SHOP")
    d.f_cat.setCurrentText("Pets")
    v = d.values()
    assert v["subcategory_id"] is None
    assert db.conn.execute("SELECT COUNT(*) FROM subcategories").fetchone()[0] == before
    save_rule(db, v)
    assert db.get_rules("Pet Shop")[0]["subcategory"] == "Uncategorized"


def test_reapply_moves_an_etransfer_to_loans(qapp, db, tmp_path):
    db.get_or_create_account("Vahid-CIBC-Chequing")
    db.save_account_id("111", "Vahid-CIBC-Chequing")
    f = tmp_path / "c.qfx"
    f.write_text(qfx("111", [("DEBIT", "20260605", "-500.00", "E1", "E-TRANSFER ALI", "E-TRANSFER 123")]),
                 encoding="cp1252")
    tab = tab_for(db)
    tab.load_files([str(f)])
    assert tab.parsed_rows[0]["type"] == "Expense"
    loans = db.loans_category()["id"]
    db.save_mapping("Transfer", None, name="ALI", subcategory_id=db.uncategorized_subcategory(loans)["id"],
                    category_id=loans, merchant="Ali")
    with mock.patch("daftarche.tabs.import_tab.QMessageBox"):
        tab._reapply_mappings()
    row = tab.parsed_rows[0]
    assert (row["type"], row["category"]["name"], row["merchant"], row["amount"]) == ("Transfer", "Loans", "Ali", 500.0)
