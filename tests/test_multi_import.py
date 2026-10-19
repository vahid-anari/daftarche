"""0.18: several statements in one import: accounts, wrong files, overlaps, balances, transfers."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def qfx(acctid, rows, balance=None, kind="CHECKING"):
    body = "".join(f"<STMTTRN><TRNTYPE>{t}<DTPOSTED>{d}<TRNAMT>{a}<FITID>{f}<NAME>{n}<MEMO>{m}</STMTTRN>\n"
                   for t, d, a, f, n, m in rows)
    bal = f"<LEDGERBAL><BALAMT>{balance}<DTASOF>20260630</LEDGERBAL>" if balance is not None else ""
    return (f"OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>CAD<BANKACCTFROM><BANKID>010"
            f"<ACCTID>{acctid}<ACCTTYPE>{kind}</BANKACCTFROM><BANKTRANLIST><DTSTART>20260601<DTEND>20260630\n"
            f"{body}</BANKTRANLIST>{bal}</STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>\n")


@pytest.fixture
def files(db, tmp_path):
    db.get_or_create_account("Vahid-CIBC-Chequing")
    db.get_or_create_account("Vahid-CIBC-Saving")
    db.save_account_id("111", "Vahid-CIBC-Chequing")
    db.save_account_id("222", "Vahid-CIBC-Saving")
    out = {}
    out["chequing"] = tmp_path / "chequing.qfx"
    out["chequing"].write_text(qfx("111", [
        ("DEBIT", "20260605", "-40.00", "C1", "GROCER", ""),
        ("XFER", "20260610", "-100.00", "C2", "INTERNET TRANSFER", "INTERNET TRANSFER 000"),
    ]), encoding="cp1252")
    out["overlap"] = tmp_path / "chequing-again.qfx"  # the same account again, one row overlapping
    out["overlap"].write_text(qfx("111", [
        ("DEBIT", "20260605", "-40.00", "C1", "GROCER", ""),
        ("DEBIT", "20260620", "-15.00", "C3", "BAKERY", ""),
    ]), encoding="cp1252")
    out["saving"] = tmp_path / "saving.qfx"
    out["saving"].write_text(qfx("222", [
        ("XFER", "20260610", "100.00", "S1", "INTERNET TRANSFER", "INTERNET TRANSFER 000"),
    ]), encoding="cp1252")
    out["visa"] = tmp_path / "visa.qfx"  # an account never seen
    out["visa"].write_text(qfx("4500999988884521", [
        ("DEBIT", "20260612", "-30.00", "V1", "SHOP", ""),
    ], balance="-530.00", kind="CREDITLINE"), encoding="cp1252")
    out["junk"] = tmp_path / "notes.qfx"
    out["junk"].write_text("just some notes", encoding="utf-8")
    return out


def tab_for(db):
    from daftarche.tabs.import_tab import ImportTab
    return keep(ImportTab(db, lambda: None))


def test_files_are_listed_with_their_state(qapp, db, files):
    tab = tab_for(db)
    with mock.patch.object(tab, "_ask_account", return_value=None):  # Cancel: choose it later
        tab.load_files([str(files[k]) for k in ("chequing", "overlap", "saving", "visa", "junk")])
    labels = [tab.file_list.item(i).text() for i in range(tab.file_list.count())]
    assert labels[0].startswith("✓  chequing.qfx") and "2 new" in labels[0]
    assert "1 new" in labels[1]  # GROCER is already in the first file
    assert labels[3].startswith("⚠  visa.qfx") and "…4521" in labels[3]
    assert labels[4].startswith("✗  notes.qfx") and "not a bank statement" in labels[4]
    assert not tab.file_list.isHidden()
    tab.file_list.setCurrentRow(3)
    assert tab.current.name == "visa.qfx" and not tab.btn_choose_account.isHidden()
    assert [st.name for st in tab._ready()] == ["chequing.qfx", "chequing-again.qfx", "saving.qfx"]


def test_import_all_files_matches_transfers_and_offers_a_starting_balance(qapp, db, files):
    tab = tab_for(db)

    def new_account(*_a, **_k):  # typed a new name in the window
        db.get_or_create_account("Vahid-CIBC-Visa")
        tab._made_account = True
        return "Vahid-CIBC-Visa"

    with mock.patch.object(tab, "_ask_account", side_effect=new_account):
        tab.load_files([str(files[k]) for k in ("chequing", "overlap", "saving", "visa", "junk")])
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        box.return_value.clickedButton.return_value = box.return_value.addButton.return_value  # Import, Add
        tab.import_all()
    txs = db.get_transactions()
    assert sorted(r["name"] for r in txs if r["type"] != "Transfer") == ["BAKERY", "GROCER", "SHOP"]
    transfers = [r for r in txs if r["type"] == "Transfer"]
    pair = [r for r in transfers if r["name"] != "Starting balance"]
    assert len(pair) == 1 and pair[0]["transfer_status"] == "matched"  # the two sides became one
    start = next(r for r in transfers if r["name"] == "Starting balance")
    assert (start["account"], start["amount"], start["date"]) == ("Vahid-CIBC-Visa", 500.0, "2026-06-11")
    visa = db.get_account_by_name("Vahid-CIBC-Visa")["id"]
    assert db.get_latest_account_balances()[visa] == -530.0  # now as the bank says
    assert db.get_account_by_acctid("4500999988884521")["name"] == "Vahid-CIBC-Visa"  # known next time
    assert len(tab.imported_ids) == 5  # 5 rows, the transfer pair counted once, + the starting balance
    assert all(db.conn.execute("SELECT 1 FROM transactions WHERE id=?", (i,)).fetchone() for i in tab.imported_ids)


def test_account_window_suggests_a_name_in_your_style(qapp, db):
    db.get_or_create_account("Vahid-CIBC-Chequing")
    db.get_or_create_account("Vahid-TD-Saving")
    tab = tab_for(db)
    assert tab._suggest_account_name("CREDITLINE", "010") == "Vahid-CIBC-Credit"
    assert tab._suggest_account_name("CHECKING", "004") == "Vahid-TD-Chequing"


def test_two_files_of_one_new_account(qapp, db, tmp_path):
    """Asked once; the starting balance goes before the earliest row of either file."""
    may, june = tmp_path / "may.qfx", tmp_path / "june.qfx"
    may.write_text(qfx("777", [("DEBIT", "20260510", "-10.00", "M1", "SHOP", "")]), encoding="cp1252")
    june.write_text(qfx("777", [("DEBIT", "20260610", "-20.00", "J1", "SHOP", "")], balance="70.00"),
                    encoding="cp1252")
    tab = tab_for(db)
    asked = []

    def new_account(*_a, **_k):
        asked.append(1)
        tab._made_account = True
        return "Vahid-CIBC-Chequing"

    with mock.patch.object(tab, "_ask_account", side_effect=new_account):
        tab.load_files([str(june), str(may)])
    assert len(asked) == 1 and [st.account for st in tab.statements] == ["Vahid-CIBC-Chequing"] * 2
    assert db.get_account_by_name("Vahid-CIBC-Chequing") is None  # nothing saved before the import
    with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
        box.return_value.clickedButton.return_value = box.return_value.addButton.return_value
        tab.import_all()
    start = next(r for r in db.get_transactions() if r["name"] == "Starting balance")
    assert (start["amount"], start["date"]) == (100.0, "2026-05-09")  # before May's row
    acc = db.get_account_by_name("Vahid-CIBC-Chequing")["id"]
    assert db.get_latest_account_balances()[acc] == 70.0
    assert db.get_account_by_acctid("777")["name"] == "Vahid-CIBC-Chequing"


def test_choosing_later_marks_the_overlap_and_cancel_saves_nothing(qapp, db, tmp_path):
    a, b = tmp_path / "a.qfx", tmp_path / "b.qfx"
    a.write_text(qfx("888", [("DEBIT", "20260601", "-5.00", "X1", "SHOP", "")]), encoding="cp1252")
    b.write_text(qfx("888", [("DEBIT", "20260601", "-5.00", "X1", "SHOP", ""),
                             ("DEBIT", "20260602", "-6.00", "X2", "CAFE", "")]), encoding="cp1252")
    db.get_or_create_account("Acc")
    tab = tab_for(db)
    with mock.patch.object(tab, "_ask_account", return_value=None):  # Cancel
        tab.load_files([str(a), str(b)])
    assert [st.account for st in tab.statements] == [None, None]
    tab.file_list.setCurrentRow(0)
    with mock.patch.object(tab, "_ask_account", return_value="Acc"):
        tab._choose_account()  # both files have that account number
    assert [st.account for st in tab.statements] == ["Acc", "Acc"]
    assert "1 new" in tab.file_list.item(1).text()  # X1 is in the first file
    tab._clear()  # closed without importing
    assert db.get_account_by_acctid("888") is None
