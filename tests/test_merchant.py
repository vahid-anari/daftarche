"""0.17: the merchant, money back as negative amounts, merchant-only rules, To review, remapping."""

import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

from conftest import answer_import, keep

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

QFX = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>CAD<BANKACCTFROM><ACCTID>1</ACCTID><ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260501<TRNAMT>-80.00<FITID>A1<NAME>AMAZON.CA ORDER</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260503<TRNAMT>30.00<FITID>A2<NAME>AMAZON.CA REFUND</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260504<TRNAMT>-45.50<FITID>A3<NAME>NETFLIX.COM</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260505<TRNAMT>3000.00<FITID>A4<NAME>PAYROLL WESTERN</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def rules(db):
    """Amazon: merchant only. Netflix: Bills › Streaming. Western: Salary (an income)."""
    db.get_or_create_account("Checking")
    uc, us = db.get_uncategorized_ids()
    db.save_mapping("Expense", None, name="AMAZON", subcategory_id=us, category_id=uc, merchant="Amazon")
    db.add_category("Bills", "Expense")
    bills = db.get_category_by_name("Bills", type_name="Expense")["id"]
    db.add_subcategory("Streaming", bills)
    streaming = db.get_subcategory_by_name("Streaming", bills)["id"]
    db.save_mapping("Expense", None, name="NETFLIX.COM", subcategory_id=streaming, category_id=bills, merchant="Netflix")
    db.add_category("Salary", "Income")
    salary = db.get_category_by_name("Salary", type_name="Income")["id"]
    db.save_mapping("Income", None, name="WESTERN", subcategory_id=db.uncategorized_subcategory(salary)["id"],
                    category_id=salary, merchant="Western")
    return db


def load(db, tmp_path):
    from daftarche.tabs.import_tab import ImportTab
    tab = keep(ImportTab(db, lambda: None))
    path = tmp_path / "s.qfx"
    path.write_text(QFX, encoding="cp1252")
    with mock.patch("daftarche.tabs.import_tab.QFileDialog.getOpenFileNames", return_value=([str(path)], "")), \
         mock.patch.object(tab, "_ask_account", return_value="Checking"):
        tab._browse_ofx()
    return tab


def test_old_database_gets_the_merchant_columns(tmp_path):
    from daftarche.db import SCHEMA_VERSION, Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)  # as layout 2 left it
    conn.execute("DROP VIEW tx_lines")
    conn.execute("DROP INDEX idx_tx_merchant")
    conn.execute("ALTER TABLE transactions DROP COLUMN merchant")
    conn.execute("ALTER TABLE import_mappings DROP COLUMN merchant")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    db = Database(path)
    for table in ("transactions", "import_mappings"):
        assert "merchant" in [r[1] for r in db.conn.execute(f"PRAGMA table_info({table})")]
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 5
    db.conn.close()


def test_a_credit_only_an_expense_rule_knows_is_money_back(rules):
    from daftarche.tabs.import_tab import find_rule
    rule, type_name, back = find_rule(rules, "Income", "Checking", "AMAZON.CA REFUND", "")
    assert (rule["merchant"], type_name, back) == ("Amazon", "Expense", True)
    rule, type_name, back = find_rule(rules, "Income", "Checking", "PAYROLL WESTERN", "")
    assert (rule["merchant"], type_name, back) == ("Western", "Income", False)  # its own type wins
    assert find_rule(rules, "Income", "Checking", "SOMEONE", "") == (None, "Income", False)


def test_import_sets_merchant_category_and_negative_refund(qapp, rules, tmp_path):
    tab = load(rules, tmp_path)
    got = {r["name"]: (r["type"], r["amount"], r["merchant"], r["category"]["name"]) for r in tab.parsed_rows}
    assert got == {
        "AMAZON.CA ORDER": ("Expense", 80.0, "Amazon", "Uncategorized"),  # merchant only: To review
        "AMAZON.CA REFUND": ("Expense", -30.0, "Amazon", "Uncategorized"),
        "NETFLIX.COM": ("Expense", 45.5, "Netflix", "Bills"),
        "PAYROLL WESTERN": ("Income", 3000.0, "Western", "Salary"),
    }
    from daftarche.tabs.import_tab import COL_AMT, COL_MERCHANT
    refund = next(i for i, r in enumerate(tab.parsed_rows) if r["name"] == "AMAZON.CA REFUND")
    assert tab.model.index(refund, COL_AMT).data() == "-$30.00"
    assert tab.model.index(refund, COL_MERCHANT).data() == "Amazon"
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        answer_import(box)
        tab.import_all()
    stored = {r["name"]: (r["amount"], r["merchant"]) for r in rules.get_transactions()}
    assert stored["AMAZON.CA REFUND"] == (-30.0, "Amazon")
    assert rules.get_to_review_count() == 2
    summary = rules.get_dashboard_summary(2026, "May", 2026, "May")
    assert summary["expense"] == 80 - 30 + 45.5  # money back is taken off the expenses
    balances = rules.get_latest_account_balances()
    assert balances[rules.get_account_by_name("Checking")["id"]] == 3000 - 80 + 30 - 45.5


def test_money_and_colours():
    from daftarche.widgets import amount_color_key, money
    assert (money(1234.5), money(-30), money(None)) == ("$1,234.50", "-$30.00", "")
    assert amount_color_key("Expense", 10) == "expense" and amount_color_key("Expense", -10) == "income"
    assert amount_color_key("Income", -5) == "expense" and amount_color_key("Transfer", 5) == "transfer"


def test_merchant_suggestions(db):
    db.add_category("Household", "Expense")
    db.add_category("Personal Care", "Expense")
    h = db.get_category_by_name("Household", type_name="Expense")["id"]
    p = db.get_category_by_name("Personal Care", type_name="Expense")["id"]
    for cat in (h, h, p):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, db.uncategorized_subcategory(cat)["id"], cat,
                           merchant="Amazon")
    assert db.get_merchants() == ["Amazon"]
    assert db.get_categories_for_merchant("amazon", "Expense") == ["Household", "Personal Care"]
    assert db.get_categories_for_merchant("", "Expense") == []


def test_category_window_merchant_only_rule_and_flip(qapp, db):
    from daftarche.category_dialog import CategoryDialog
    db.get_or_create_account("Card")
    db.add_category("Clothing", "Expense")
    d = keep(CategoryDialog(db, "Income", can_flip=True, default_rule=("AMAZON", "")))
    d.f_merchant.setCurrentText("Amazon")
    assert not d.new_merchant.isHidden() and d.new_rule_merchant.text() == "Amazon"
    d.f_type.setCurrentText("Expense")  # a refund: money back of an expense
    assert d.flipped and "Clothing" in [d.f_category.itemText(i) for i in range(d.f_category.count())]
    d.f_category.setCurrentText("")  # no category: the rule only sets the merchant
    assert "only set the merchant" in d.rules_title.text()
    d._add_rule()
    with mock.patch.object(d, "accept"), mock.patch("daftarche.category_dialog.QMessageBox") as box:
        d._accept()
    assert not box.warning.called
    rule = db.lookup_mapping("Expense", "Card", "AMAZON.CA")
    assert rule["merchant"] == "Amazon" and rule["category_id"] == db.get_uncategorized_ids()[0]
    assert (d.row_type, d.merchant, d.merchant_changed, d.cat_name) == ("Expense", "Amazon", True, "Uncategorized")


def test_transactions_tab_shows_minus_dash_and_to_review(qapp, db):
    from daftarche.tabs.transactions import COL_AMOUNT, COL_MERCHANT, COL_SUBCAT, TransactionsTab
    db.add_category("Clothing", "Expense")
    clothing = db.get_category_by_name("Clothing", type_name="Expense")["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", -40, db.uncategorized_subcategory(clothing)["id"],
                       clothing, name="REFUND", merchant="Gap")
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 2, "Expense", "Card", 25, us, uc, name="AMAZON", merchant="Amazon")
    tab = keep(TransactionsTab(db))
    tab.show_matching()
    i = next(i for i in range(tab.model.rowCount()) if tab.model.get_row(i)["name"] == "REFUND")
    assert tab.model.index(i, COL_AMOUNT).data() == "-$40.00"
    assert tab.model.index(i, COL_SUBCAT).data() == "—" and tab.model.index(i, COL_MERCHANT).data() == "Gap"
    assert tab.btn_review.text() == "📝 Review (1)" and not tab.btn_review.isHidden()
    tab.show_to_review()
    assert [tab.model.get_row(r)["name"] for r in range(tab.model.rowCount())] == ["AMAZON"]


def test_flipping_in_the_transactions_tab_makes_the_amount_negative(qapp, db):
    from daftarche.category_dialog import CategoryDialog
    from daftarche.tabs.transactions import TransactionsTab
    db.add_category("Clothing", "Expense")
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Income", "Card", 40, us, uc, name="GAP REFUND")
    tab = keep(TransactionsTab(db))
    tab.show_matching()

    def fill(d):
        d.f_type.setCurrentText("Expense")
        d.f_merchant.setCurrentText("Gap")
        d.f_category.setCurrentText("Clothing")
        d._accept()
        return True

    with mock.patch.object(CategoryDialog, "exec", fill):
        tab._edit_categories([0])
    (row,) = db.get_transactions()
    assert (row["type"], row["amount"], row["merchant"], row["category"]) == ("Expense", -40, "Gap", "Clothing")


def test_remap_moves_merchants_refunds_and_rules(db, tmp_path):
    import remap_categories as R
    # the old way: the sub-category is the shop, refunds are income
    db.add_category("Shopping", "Expense")
    shop = db.get_category_by_name("Shopping", type_name="Expense")["id"]
    db.add_subcategory("Amazon", shop)
    amazon = db.get_subcategory_by_name("Amazon", shop)["id"]
    db.add_category("Refund", "Income")
    refund = db.get_category_by_name("Refund", type_name="Income")["id"]
    db.add_subcategory("Amazon", refund)
    r_amazon = db.get_subcategory_by_name("Amazon", refund)["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", 80, amazon, shop, name="AMAZON")
    db.add_transaction(2026, "May", 3, "Income", "Card", 30, r_amazon, refund, name="AMAZON")
    db.save_mapping("Expense", None, name="AMAZON", subcategory_id=amazon, category_id=shop)
    db.save_mapping("Income", None, name="AMAZON", subcategory_id=r_amazon, category_id=refund)

    rows = R.current_rows(db)
    assert {(r["type"], r["category"], r["subcategory"], r["merchant"]) for r in rows} == {
        ("Expense", "Shopping", "Amazon", "Amazon"), ("Income", "Refund", "Amazon", "Amazon")}
    for r in rows:  # what Vahid would write in the CSV
        r["new_type"], r["new_category"], r["new_subcategory"] = "Expense", "Shopping", "General"
        r["rules_set"] = "merchant"
    path = tmp_path / "mapping.csv"
    R.write_csv(rows, path)
    moves, problems = R.plan(db, R.read_csv(path))
    assert not problems and len(moves) == 2 and any(m["flip"] for m in moves)
    before = db.get_dashboard_summary(2026, "May", 2026, "May")
    assert (before["income"], before["expense"]) == (30, 80)  # inflated both ways

    emptied = R.apply(db, moves)
    txs = {(r["type"], r["amount"], r["merchant"], r["category"], r["subcategory"]) for r in db.get_transactions()}
    assert txs == {("Expense", 80, "Amazon", "Shopping", "General"), ("Expense", -30, "Amazon", "Shopping", "General")}
    after = db.get_dashboard_summary(2026, "May", 2026, "May")
    assert (after["income"], after["expense"], after["net"]) == (0, 50, before["net"])  # same net, true totals
    rules = db.conn.execute("SELECT ty.name AS type, m.merchant, m.category_id FROM import_mappings m "
                            "JOIN types ty ON ty.id = m.type_id").fetchall()
    assert [(r["type"], r["merchant"], r["category_id"]) for r in rules] == [("Expense", "Amazon", db.get_uncategorized_ids()[0])]
    assert "Income › Refund" in emptied and db.get_category_by_name("Refund", type_name="Income") is None


def test_remap_reports_bad_lines(db):
    import remap_categories as R
    rows = [{"type": "Expense", "category": "Nope", "subcategory": "X"},
            {"type": "", "category": "", "subcategory": ""}]
    moves, problems = R.plan(db, rows)
    assert moves == [] and len(problems) == 2


def test_remap_moves_each_line_only_once(db):
    """A line moving into another line's sub-category: the second line must not move (or flip)
    the first line's rows again."""
    import remap_categories as R
    db.add_category("Shopping", "Expense")
    shop = db.get_category_by_name("Shopping", type_name="Expense")["id"]
    db.add_subcategory("Amazon", shop)
    amazon = db.get_subcategory_by_name("Amazon", shop)["id"]
    db.add_category("Refund", "Income")
    refund = db.get_category_by_name("Refund", type_name="Income")["id"]
    db.add_subcategory("Amazon", refund)
    r_amazon = db.get_subcategory_by_name("Amazon", refund)["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", 80, amazon, shop, name="AMAZON")
    db.add_transaction(2026, "May", 3, "Income", "Card", 30, r_amazon, refund, name="AMAZON REFUND")
    rows = [  # refunds into Shopping › Amazon, which itself moves to Income › Reimbursed (a swap)
        {"type": "Income", "category": "Refund", "subcategory": "Amazon", "merchant": "Amazon",
         "new_type": "Expense", "new_category": "Shopping", "new_subcategory": "Amazon"},
        {"type": "Expense", "category": "Shopping", "subcategory": "Amazon", "merchant": "Amazon",
         "new_type": "Income", "new_category": "Reimbursed", "new_subcategory": "Work"},
    ]
    moves, problems = R.plan(db, rows)
    assert not problems
    R.apply(db, moves)
    got = {r["name"]: (r["type"], r["amount"], r["category"], r["subcategory"]) for r in db.get_transactions()}
    assert got == {"AMAZON REFUND": ("Expense", -30, "Shopping", "Amazon"),
                   "AMAZON": ("Income", -80, "Reimbursed", "Work")}


def test_remap_rules_to_uncategorized_need_a_merchant(db):
    import remap_categories as R
    db.add_category("Gifts", "Expense")
    g = db.get_category_by_name("Gifts", type_name="Expense")["id"]
    db.add_subcategory("Mom", g)
    mom = db.get_subcategory_by_name("Mom", g)["id"]
    db.save_mapping("Expense", None, name="MOM", subcategory_id=mom, category_id=g)
    _, problems = R.plan(db, [{"type": "Expense", "category": "Gifts", "subcategory": "Mom", "merchant": "",
                               "new_type": "Expense", "new_category": "", "new_subcategory": ""}])
    assert problems and "merchant" in problems[0]


def test_import_preview_refuses_mixed_types_and_keeps_manual_edits(qapp, rules, tmp_path):
    from daftarche.category_dialog import CategoryDialog
    tab = load(rules, tmp_path)
    rows = tab.parsed_rows
    pay = next(i for i, r in enumerate(rows) if r["name"] == "PAYROLL WESTERN")
    order = next(i for i, r in enumerate(rows) if r["name"] == "AMAZON.CA ORDER")
    with mock.patch.object(tab, "_get_selected_row_indices", return_value=[pay, order]), \
            mock.patch("daftarche.tabs.import_tab.QMessageBox") as box, \
            mock.patch.object(CategoryDialog, "exec") as run:
        tab._bulk_edit_cat()
    assert box.warning.called and not run.called and rows[pay]["amount"] == 3000

    def flip(d):  # this payroll is really money back of an expense
        d.f_type.setCurrentText("Expense")
        d._accept()
        return True

    with mock.patch.object(CategoryDialog, "exec", flip):
        tab._edit_categories([pay], "Income")
    assert (rows[pay]["type"], rows[pay]["amount"]) == ("Expense", -3000)
    with mock.patch("daftarche.tabs.import_tab.QMessageBox"):
        tab._reapply_mappings()  # the Western income rule must not flip it back
    assert (rows[pay]["type"], rows[pay]["amount"]) == ("Expense", -3000)
