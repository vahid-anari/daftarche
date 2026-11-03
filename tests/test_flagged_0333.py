"""0.33.3: 🚩 merchants to look at again while tidying up (kept in the settings, not the data)."""

from unittest import mock

import pytest
from PySide6.QtCore import Qt

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_settings():
    from daftarche.style import get_settings
    from daftarche.tabs.manage import MerchantsPanel
    s = get_settings()
    before = s._data.pop(MerchantsPanel.FLAG_KEY, None)
    with mock.patch.object(s, "save"):
        yield
    s._data.pop(MerchantsPanel.FLAG_KEY, None)
    if before is not None:
        s._data[MerchantsPanel.FLAG_KEY] = before


@pytest.fixture
def shops(db):
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for name in ("Amazon", "Bakery", "Cafe"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, name=name.upper(), merchant=name)
    db.add_transaction(2026, "May", 2, "Expense", "Card", 5, us, uc, name="NONE")
    db.conn.commit()
    return db


def panel(db):
    from daftarche.tabs.manage import ManageDialog
    return keep(ManageDialog(db, lambda: None)).merchants_panel


def row_of(m, name):
    return next(r for r in range(m.table.rowCount()) if m.table.item(r, m.COL_NAME).text() == name)


def shown(m):
    return [m.table.item(r, m.COL_NAME).text() for r in range(m.table.rowCount()) if not m.table.isRowHidden(r)]


def test_tick_untick_and_only_those(qapp, shops):
    from daftarche.style import get_settings
    m = panel(shops)
    assert not m.table.item(row_of(m, "(no merchant)"), m.COL_FLAG).flags() & Qt.ItemIsUserCheckable
    m.table.item(row_of(m, "Cafe"), m.COL_FLAG).setCheckState(Qt.Checked)
    m.table.item(row_of(m, "Amazon"), m.COL_FLAG).setCheckState(Qt.Checked)
    assert get_settings().get(m.FLAG_KEY) == ["Amazon", "Cafe"] and m.totals.item(0, m.COL_FLAG).text() == "2"
    m.btn_only_flagged.setChecked(True)
    m._only_flagged_changed()
    assert shown(m) == ["Amazon", "Cafe"]
    m.find.setText("caf")
    assert shown(m) == ["Cafe"]
    m.find.clear()
    m.table.item(row_of(m, "Amazon"), m.COL_FLAG).setCheckState(Qt.Unchecked)  # done with it
    assert shown(m) == ["Cafe"] and get_settings().get(m.FLAG_KEY) == ["Cafe"]
    m.btn_only_flagged.setChecked(False)
    m._only_flagged_changed()
    assert len(shown(m)) == 4


def test_kept_after_a_refresh_and_sorted_first(qapp, shops):
    m = panel(shops)
    m.table.item(row_of(m, "Cafe"), m.COL_FLAG).setCheckState(Qt.Checked)
    m.refresh()
    assert m.table.item(row_of(m, "Cafe"), m.COL_FLAG).checkState() == Qt.Checked
    m.table.sortByColumn(m.COL_FLAG, Qt.AscendingOrder)
    assert m.table.item(0, m.COL_NAME).text() == "Cafe"
    assert m.table.item(m.table.rowCount() - 1, m.COL_NAME).text() == "(no merchant)"  # always last


def test_rename_keeps_the_tick_and_delete_drops_it(qapp, shops):
    from daftarche.style import get_settings
    m = panel(shops)
    m.table.item(row_of(m, "Cafe"), m.COL_FLAG).setCheckState(Qt.Checked)
    m.table.item(row_of(m, "Bakery"), m.COL_FLAG).setCheckState(Qt.Checked)
    m.select("Cafe")
    with mock.patch("daftarche.tabs.manage.QInputDialog.getText", return_value=("Coffee House", True)):
        m.rename()
    m.refresh()
    assert get_settings().get(m.FLAG_KEY) == ["Bakery", "Coffee House"]
    assert m.table.item(row_of(m, "Coffee House"), m.COL_FLAG).checkState() == Qt.Checked
    m.select("Bakery")
    with mock.patch("daftarche.tabs.manage.QMessageBox.question", return_value=mock.ANY) as ask:
        from PySide6.QtWidgets import QMessageBox
        ask.return_value = QMessageBox.Yes
        m.delete()
    assert get_settings().get(m.FLAG_KEY) == ["Coffee House"]


def test_right_click_ticks_it(qapp, shops):
    m = panel(shops)
    m.select("Amazon")
    m._toggle_flag()
    assert m.table.item(row_of(m, "Amazon"), m.COL_FLAG).checkState() == Qt.Checked and m._is_flagged()
    m._toggle_flag()
    assert not m._is_flagged()


# ── a rule's transactions ────────────────────────────────────────────────────
@pytest.fixture
def ruled(db):
    db.get_or_create_account("Card")
    db.get_or_create_account("Bank")
    uc, us = db.get_uncategorized_ids()
    add = lambda name, merchant, account="Card": db.add_transaction(  # noqa: E731
        2026, "May", 1, "Expense", account, 10, us, uc, name=name, merchant=merchant)
    ids = {"mkt": add("AMAZON MKTP 1", "Amazon"), "prime": add("AMAZON PRIME", "Amazon"),
           "audible": add("AMAZON AUDIBLE", "Audible"), "bank": add("AMAZON MKTP 2", "Amazon", "Bank"),
           "other": add("BAKERY", "Bakery")}
    db.add_category("Shopping", "Expense")
    shopping = db.get_category_by_name("Shopping", type_name="Expense")["id"]
    db.update_transaction(ids["prime"], category_id=shopping,
                          subcategory_id=db.uncategorized_subcategory(shopping)["id"])  # for Used in
    for name, accounts in (("AMAZON", None), ("AMAZON PRIME", None), ("AMAZON", ["Bank"])):
        db.save_mapping("Expense", accounts, name=name, subcategory_id=us, category_id=uc, merchant="Amazon")
    db.conn.commit()
    rules = {(r["name"], tuple(r["accounts"])): r["id"] for r in db.get_rules("Amazon")}
    return db, ids, rules


def test_a_rules_transactions_are_those_it_wins_now(ruled):
    db, ids, rules = ruled
    general = rules[("AMAZON", ())]
    assert sorted(db.rule_transaction_ids([general])) == sorted([ids["mkt"], ids["audible"]])  # Audible too
    assert db.rule_transaction_ids([rules[("AMAZON PRIME", ())]]) == [ids["prime"]]  # more text: it wins
    assert db.rule_transaction_ids([rules[("AMAZON", ("Bank",))]]) == [ids["bank"]]  # fewer accounts: it wins
    assert db.rule_transaction_ids([]) == []


def test_selecting_a_rule_shows_its_transactions_and_the_merchant_again_all(qapp, ruled):
    from daftarche.style import get_settings
    from daftarche.tx_list import SHOW_KEY
    db, ids, rules = ruled
    get_settings()._data[SHOW_KEY] = True
    m = panel(db)
    m.select("Amazon")
    names = lambda: sorted(r["name"] for r in m.lines.tx.model._rows)  # noqa: E731
    assert len(names()) == 3
    row = next(r for r in range(m.rules.rowCount())
               if m.rules.item(r, 0).data(Qt.UserRole)["id"] == rules[("AMAZON", ())])
    m.rules.selectRow(row)
    assert names() == ["AMAZON AUDIBLE", "AMAZON MKTP 1"] and m.lines.title.text().startswith("Amazon · rule")
    assert not m.lines.btn_all.isHidden()
    m.refresh()  # after an edit: still that rule
    assert names() == ["AMAZON AUDIBLE", "AMAZON MKTP 1"]
    assert m.used.rowCount()
    m.used.selectRow(0)  # one filter at a time
    assert not m.rules.selectionModel().hasSelection()
    m.rules.selectRow(row)
    assert not m.used.selectionModel().hasSelection()
    m.table.cellClicked.emit(row_of(m, "Amazon"), m.COL_NAME)  # the merchant again: all of its
    assert len(names()) == 3 and not m.rules.selectionModel().hasSelection() and m.lines.btn_all.isHidden()
    m.rules.selectRow(row)
    m.lines.btn_all.click()
    assert len(names()) == 3


def test_each_rule_counts_its_transactions_and_the_line_compares(qapp, ruled):
    db, ids, rules = ruled
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 3, "Expense", "Card", 5, us, uc, name="GIFT CARD", merchant="Amazon")  # by hand
    db.conn.commit()
    counts, line = db.merchant_rule_counts("Amazon")
    assert counts == {rules[("AMAZON", ())]: 2, rules[("AMAZON PRIME", ())]: 1, rules[("AMAZON", ("Bank",))]: 1}
    assert line == {"total": 4, "from_rules": 3, "none": 1, "other_rule": 0, "elsewhere": 1}  # Audible
    m = panel(db)
    m.select("Amazon")
    assert sorted(m.rules.item(r, m.R_TX).text() for r in range(m.rules.rowCount())) == ["1", "1", "2"]
    assert m.rules_count.text() == ("3 of its 4 transactions come from these rules · 1 from no rule (set by hand)"
                                    " · 1 more have another merchant now")
