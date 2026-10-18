"""Transactions columns: saved by name, movable, in the Columns window, copied as shown."""

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(monkeypatch):
    from daftarche import style
    s = style.get_settings()
    monkeypatch.setattr(s, "_data", {**style.DEFAULTS})
    monkeypatch.setattr(s, "save", lambda *a, **k: None, raising=False)
    return s


def test_old_settings_by_position_become_names():
    from daftarche.tabs.transactions import COLUMN_KEYS, DEFAULT_ORDER, column_settings
    visible, order = column_settings({"9": False, "6": False}, None)  # 0.14: FITID and Tags hidden
    assert visible["fitid"] is False and visible["tags"] is False and visible["note"] is True
    assert order == COLUMN_KEYS  # an existing table keeps its order
    visible, order = column_settings(None, None)
    assert all(visible.values()) and order == DEFAULT_ORDER and order.index("note") == order.index("memo") + 1
    _, order = column_settings({"fitid": False}, ["note", "date", "bogus"])
    assert order[:2] == ["note", "date"] and sorted(order) == sorted(COLUMN_KEYS)


def test_moving_a_header_is_saved_and_copied_as_shown(qapp, db, settings):
    from PySide6.QtWidgets import QApplication
    from daftarche.tabs.transactions import COL_AMOUNT, COL_DATE, COL_FITID, COL_NOTE, TransactionsTab
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Expense", "Card", 12.5, us, uc, name="SHOP")
    tab = keep(TransactionsTab(db))
    tab.show_matching()
    header = tab.table.horizontalHeader()
    header.moveSection(header.visualIndex(COL_AMOUNT), 0)  # drag Amount to the front
    assert settings.get("transactions_column_order")[:2] == ["amount", "date"]
    for key in ("type", "account", "category", "subcategory", "tags", "name", "memo", "fitid"):
        tab._visible_columns[key] = False
    tab._apply_column_visibility()
    tab.table.selectRow(0)
    tab._copy_selected()
    assert QApplication.clipboard().text().splitlines()[0] == "Amount\tDate\tNote"

    again = keep(TransactionsTab(db))  # next start: same order
    assert again._visual_columns()[:2] == [COL_AMOUNT, COL_DATE]
    assert again._visual_columns()[-2:] == [COL_NOTE, COL_FITID]  # a fresh start: Note after Memorandum


def test_columns_window_moves_and_resets(qapp, settings):
    from daftarche.tabs.transactions import COLUMN_KEYS, DEFAULT_ORDER, ColumnVisibilityDialog
    visible = {k: k != "fitid" for k in COLUMN_KEYS}
    dialog = keep(ColumnVisibilityDialog(visible, list(COLUMN_KEYS)))
    dialog.list.setCurrentRow(COLUMN_KEYS.index("note"))
    dialog._move(-1)  # Note above FITID: right after Memorandum
    shown, order = dialog.result()
    assert order.index("note") == order.index("memo") + 1 and shown["fitid"] is False
    dialog._reset()
    shown, order = dialog.result()
    assert order == DEFAULT_ORDER and all(shown.values())
