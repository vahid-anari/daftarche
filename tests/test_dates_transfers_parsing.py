"""Batch C (0.7.0): date picker and ranges, transfer matching, QFX parsing, typed category names."""

from pathlib import Path
from unittest import mock

import pytest
from conftest import answer_import

QFX = (Path(__file__).parent / "data" / "sample.qfx").read_text(encoding="cp1252")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ── date picker and ranges ───────────────────────────────────────────────────

def test_browsing_months_does_not_change_the_date(qapp):
    from daftarche.widgets import DatePicker
    picker, seen = DatePicker(), []
    picker.dateChanged.connect(lambda *a: seen.append(a))
    picker.set_date(2026, "January", 31)
    picker._show()
    picker._next_month()
    picker._popup.hide()
    assert (picker.get_year(), picker.get_month(), picker.get_day()) == (2026, "January", 31) and seen == []
    picker._show()
    picker._next_month()
    picker._pick_day(28)
    assert seen == [(2026, "February", 28)]


def test_grey_day_of_next_month_is_picked_and_announced(qapp):
    from daftarche.widgets import DatePicker
    picker, seen = DatePicker(), []
    picker.dateChanged.connect(lambda *a: seen.append(a))
    picker.set_date(2026, "February", 10)
    picker._show()
    picker._pick_overflow(2026, 3, 2)
    assert picker.get_month() == "March" and seen == [(2026, "March", 2)]


def test_month_picker_changes_only_on_ok(qapp):
    from daftarche.widgets import DatePicker
    picker = DatePicker(mode="month")
    picker.set_date(2026, "May")
    picker._show()
    picker._prev_month()
    picker._popup.hide()
    assert picker.get_month() == "May"
    picker._show()
    picker._prev_month()
    picker._confirm_month()
    assert picker.get_month() == "April"


def test_range_to_before_from_moves_from(qapp):
    from daftarche.widgets import DateRangeWidget
    seen = []
    rng = DateRangeWidget(mode="month", config_key="test_range")
    rng.rangeChanged.connect(lambda *a: seen.append(a))
    rng.from_p.set_date(2026, "June")
    rng.to_p.set_date(2026, "March")
    rng._on_to_changed(2026, "March", 1)
    assert rng.get_range()[:2] == (2026, "March") and seen[-1][:2] == (2026, "March")


# ── transfer matching ────────────────────────────────────────────────────────

def transfer(db, day, amount, account=None, to_account=None, name=None, memo=None):
    cat_id, sub_id = db.get_transfer_cat_sub(description=memo or "", matched=False)
    return db.add_transaction(2026, "January", day, "Transfer", account, amount, sub_id, cat_id,
                              name=name, memorandum=memo, to_account_name=to_account,
                              transfer_status="unmatched")


def rows(db):
    return {r["id"]: r for r in db.get_transactions()}


def test_closest_dates_are_paired(db):
    early = transfer(db, 1, 100, account="Person-CIBC-Checking")
    same_day = transfer(db, 9, 100, account="Person-CIBC-Checking")
    incoming = transfer(db, 9, 100, to_account="Other-TD-Saving")
    assert db.match_unmatched_transfers() == 1
    r = rows(db)
    assert r[same_day]["to_account"] == "Other-TD-Saving" and r[early]["to_account"] is None
    assert incoming not in r


def test_matching_keeps_incoming_tags_and_text(db):
    out = transfer(db, 5, 50, account="Person-CIBC-Checking")
    incoming = transfer(db, 5, 50, to_account="Person-CIBC-Saving", name="FROM CHEQUING", memo="memo text")
    db.add_tag("rent")
    tag = db.get_tags()[0]["id"]
    db.set_tags_for_transaction(incoming, [tag])
    db.match_unmatched_transfers()
    row = rows(db)[out]
    assert (row["name"], row["memorandum"]) == ("FROM CHEQUING", "memo text")
    assert [t["id"] for t in db.get_tags_for_transaction(out)] == [tag]


def test_internet_transfer_stays_internal(db):
    out = transfer(db, 5, 50, account="Alice-Bank1-Checking", memo="INTERNET TRANSFER 000123")
    transfer(db, 5, 50, to_account="Bob-Bank2-Saving")
    db.match_unmatched_transfers()
    assert rows(db)[out]["category"] == "Internal Transfer"


# ── QFX parsing ──────────────────────────────────────────────────────────────

def test_cp1252_statement_is_decoded_as_cp1252():
    from daftarche.tabs.import_tab import decode_statement, parse_ofx
    raw = QFX.replace("EXAMPLE GROCERY", "TIM’S – CAFÉ").encode("cp1252")
    rows_ = parse_ofx(decode_statement(raw))
    assert "TIM’S – CAFÉ" in [r["name"] for r in rows_]
    assert decode_statement("ENCODING:UTF-8\n<OFX>é".encode("utf-8")).endswith("é")


def credit_card_statement():
    return (QFX.replace("<BANKACCTFROM>", "<CCACCTFROM>").replace("</BANKACCTFROM>", "</CCACCTFROM>")
               .replace("<ACCTTYPE>CHECKING\n", "").replace("STMTRS>", "CCSTMTRS>")
               .replace("EXAMPLE EMPLOYER PAYROLL", "PAYMENT THANK YOU"))


def test_credit_card_payment_is_a_transfer_whatever_the_account_name():
    from daftarche.tabs.import_tab import parse_ofx
    rows_ = parse_ofx(credit_card_statement(), "Person-Bank-Visa")
    assert {r["name"]: r["type"] for r in rows_}["PAYMENT THANK YOU"] == "Transfer"


def test_paymentus_is_not_a_payment():
    from daftarche.tabs.import_tab import parse_ofx
    rows_ = parse_ofx(credit_card_statement().replace("PAYMENT THANK YOU", "PAYMENTUS CITY"), "Visa")
    assert {r["name"]: r["type"] for r in rows_}["PAYMENTUS CITY"] == "Income"


def test_unreadable_rows_are_reported():
    from daftarche.tabs.import_tab import parse_ofx
    skipped = []
    bad = QFX.replace("20260105", "20260230").replace("<TRNAMT>-42.50", "<TRNAMT>-1.00 CAD")
    assert len(parse_ofx(bad, skipped=skipped)) == 1
    assert sorted(why.split()[0] for why, _ in skipped) == ["amount", "impossible"]


def test_import_keeps_the_previewed_transfer_category(qapp, db, tmp_path):
    from daftarche.tabs.import_tab import ImportTab
    db.get_or_create_account("Person-Bank-Visa")
    tab = ImportTab(db, lambda: None)
    path = tmp_path / "visa.qfx"
    path.write_text(credit_card_statement(), encoding="cp1252")
    with mock.patch("daftarche.tabs.import_tab.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
         mock.patch.object(tab, "_ask_account", return_value="Person-Bank-Visa"):
        tab._browse_ofx()
    preview = {r["name"]: r["category"]["name"] for r in tab.parsed_rows if r["is_transfer"]}
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        answer_import(box)
        tab.import_all()
    stored = {r["name"]: r["category"] for r in db.get_transactions() if r["type"] == "Transfer"}
    assert stored == preview and stored["PAYMENT THANK YOU"] == "Internal Transfer"


# ── typed category names ─────────────────────────────────────────────────────

def test_bulk_edit_refuses_unknown_names(qapp, db):
    from daftarche.tabs.transactions import BulkCatDialog
    db.add_category("Food", "Expense")
    db.add_subcategory("Groceries", db.get_category_by_name("Food", type_name="Expense")["id"])
    dialog = BulkCatDialog(db, "Expense")
    for cat_text, sub_text, ok in [("Costco", "x", False), ("Food", "Costco", False), ("Food", "Groceries", True)]:
        dialog.f_category.setCurrentText(cat_text)
        dialog.f_subcat.setCurrentText(sub_text)
        with mock.patch("daftarche.tabs.transactions.QMessageBox.warning") as warning, \
             mock.patch.object(dialog, "accept") as accept:
            dialog._accept()
        assert accept.called is ok and warning.called is not ok
