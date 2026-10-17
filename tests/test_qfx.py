"""Reading QFX/OFX statements (synthetic file, no real data)."""

from pathlib import Path

from daftarche.tabs.import_tab import parse_ofx, parse_qfx_header

SAMPLE = (Path(__file__).parent / "data" / "sample.qfx").read_text(encoding="cp1252")


def test_header():
    header = parse_qfx_header(SAMPLE)
    assert header["acctid"] == "0000000"
    assert header["accttype"] == "CHECKING"
    assert header["dtstart"] == "20260101"
    assert header["dtend"] == "20260131"
    assert header["balamt"] == 757.50
    assert header["curdef"] == "CAD"


def test_transactions_sorted_by_date():
    rows = parse_ofx(SAMPLE, "Person-Bank-Checking")
    assert [r["fitid"] for r in rows] == ["TEST0001", "TEST0002", "TEST0003"]
    assert [r["date"] for r in rows] == ["2026-01-05", "2026-01-15", "2026-01-20"]


def test_types_amounts_and_direction():
    income, expense, transfer = parse_ofx(SAMPLE, "Person-Bank-Checking")
    assert (income["type"], income["amount"], income["direction"]) == ("Income", 1000.0, "credit")
    assert (expense["type"], expense["amount"], expense["direction"]) == ("Expense", 42.5, "debit")
    assert (transfer["type"], transfer["direction"]) == ("Transfer", "debit")


def test_credit_card_payment_is_a_transfer():
    qfx = SAMPLE.replace("<ACCTTYPE>CHECKING", "<ACCTTYPE>CREDITLINE").replace(
        "EXAMPLE EMPLOYER PAYROLL", "PAYMENT THANK YOU")
    rows = parse_ofx(qfx, "Person-Bank-Credit")
    assert rows[0]["type"] == "Transfer"


def test_crlf_and_empty_input():
    assert len(parse_ofx(SAMPLE.replace("\n", "\r\n"))) == 3
    assert parse_ofx("") == []
