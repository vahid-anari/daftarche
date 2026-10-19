"""0.18: Import in a window, To review in Transactions, the "← Back to …" bar, the Go menu."""

from unittest import mock

import pytest

from conftest import answer_import, keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch, tmp_path):
    from daftarche import window as W
    monkeypatch.setattr(W, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(W, "startup_backup"):
        w = keep(W.MainWindow())
    db = w.db
    uc, us = db.get_uncategorized_ids()
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, name="AMAZON")
    db.add_transaction(2026, "May", 2, "Income", "Card", 20, us, uc, name="ZAHRA")
    db.add_transaction(2026, "May", 3, "Expense", "Card", 30, us, uc, name="SHOP")
    db.add_transaction(2026, "May", 4, "Expense", "Card", 5, db.uncategorized_subcategory(food)["id"], food,
                       name="BAKERY")
    w._refresh_all()
    return w


def names(w):
    tab = w.transactions_tab
    return [tab.model.get_row(i)["name"] for i in range(tab.model.rowCount())]


def test_four_tabs_and_the_go_menu(win):
    assert [win.tabs.tabText(i).strip()[-5:] for i in range(win.tabs.count())] == \
        ["board", "tions", "harts", "ounts"]
    go = next(a.menu() for a in win.menuBar().actions() if a.text() == "Go")
    keys = {a.text(): a.shortcut().toString() for a in go.actions() if a.text()}
    assert keys == {"Dashboard": "Ctrl+1", "Transactions": "Ctrl+2", "Charts": "Ctrl+3", "Accounts": "Ctrl+4",
                    "Back": "Ctrl+["}
    next(a for a in go.actions() if a.text() == "Charts").trigger()
    assert win.tabs.currentWidget() is win.charts_tab
    file_menu = next(a.menu() for a in win.menuBar().actions() if a.text() == "File")
    keys = {a.text(): a.shortcut().toString() for a in file_menu.actions() if a.text()}
    assert keys["Import Statement…"] == "Ctrl+I" and keys["Back Up Database…"] == "Ctrl+S"
    assert keys["Restore Backup…"] == ""  # on purpose


def test_review_stays_in_transactions(win):
    win.show_uncategorized()
    tab = win.transactions_tab
    assert names(win) == ["SHOP", "AMAZON", "ZAHRA"]  # expenses first, newest first
    assert not tab.nav_bar.isHidden() and tab.btn_back.isHidden()  # nowhere to go back to
    assert "Expense 2 · Income 1" in tab.nav_label.text()
    db = win.db
    food = db.get_category_by_name("Food", type_name="Expense")
    tx = next(r for r in db.get_transactions() if r["name"] == "SHOP")
    db.update_transaction(tx["id"], category_id=food["id"], subcategory_id=db.uncategorized_subcategory(food["id"])["id"])
    tab._notify_change()
    assert names(win) == ["AMAZON", "ZAHRA"] and "Expense 1 · Income 1" in tab.nav_label.text()
    tab.f_type.set_selected(["Income"])  # filtering by hand: no longer the jump's list
    tab._on_any_filter_changed()
    assert tab.nav_bar.isHidden()


def test_back_to_where_you_came_from(win):
    tab = win.transactions_tab
    win.tabs.setCurrentWidget(win.dashboard_tab)
    win.dashboard_tab._alert_uncategorized = 3
    win.dashboard_tab._on_alert_clicked()
    assert win.tabs.currentWidget() is tab and tab.btn_back.text() == "← Back to Dashboard"
    tab.go_back()
    assert win.tabs.currentWidget() is win.dashboard_tab and tab.nav_bar.isHidden()
    assert len(names(win)) == 4  # Transactions shows everything again

    win.charts_tab.detail.openRequested.emit({"types": ["Expense"], "categories": ["Food"]})
    assert names(win) == ["BAKERY"] and tab.btn_back.text() == "← Back to Charts"
    tab.go_back()
    assert win.tabs.currentWidget() is win.charts_tab

    with mock.patch.object(win, "show_unmatched_transfers") as reopen:
        win._show_transactions(came_from=("Unmatched Transfers", win.show_unmatched_transfers), types=["Expense"])
        tab.go_back()
    assert reopen.called


def test_import_window_then_the_new_rows(win, tmp_path):
    from daftarche import window as W
    qfx = (tmp_path / "s.qfx")
    qfx.write_text("""OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><CURDEF>CAD<BANKACCTFROM><ACCTID>9</ACCTID><ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260601<TRNAMT>-12.00<FITID>N1<NAME>NEW SHOP</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260602<TRNAMT>-8.00<FITID>N2<NAME>OTHER SHOP</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
""", encoding="cp1252")

    def run(dialog):
        with mock.patch("daftarche.tabs.import_tab.QMessageBox") as box:
            answer_import(box)
            dialog.tab.import_all()
        return 1

    with mock.patch("daftarche.tabs.import_tab.ImportTab._ask_account", return_value="Card"), \
            mock.patch.object(W.ImportDialog, "exec", run):
        win.open_import(str(qfx))
    tab = win.transactions_tab
    assert win.tabs.currentWidget() is tab and sorted(names(win)) == ["NEW SHOP", "OTHER SHOP"]
    assert "Just imported" in tab.nav_label.text() and "2 transactions" in tab.nav_label.text()
    tab.reset_filters()
    assert len(names(win)) == 6


def test_dropping_a_statement_opens_the_import_window(win, tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    event = mock.Mock()
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(tmp_path / "May.QFX"))])
    event.mimeData.return_value = data
    with mock.patch.object(win, "open_import") as opened:
        win.dropEvent(event)
    opened.assert_called_once_with(str(tmp_path / "May.QFX"))
    data.setUrls([QUrl.fromLocalFile(str(tmp_path / "photo.png"))])
    assert win._dropped_statement(event) is None
