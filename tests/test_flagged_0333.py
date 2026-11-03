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
