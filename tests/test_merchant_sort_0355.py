"""0.35.5: Manage › Categories' merchants sorted A to Z at first; a click on a heading sorts by it
(again: the other way), kept for next time, the no-merchant line always last. Edit Merchant's
wrapped note keeps its height, so the preview is never under the buttons."""

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def names(p):
    return [p.merchant_table.item(r, 0).text() for r in range(p.merchant_table.rowCount())]


def test_sort_by_a_heading(qapp, db):
    from daftarche.style import get_settings
    from daftarche.tabs.manage import ManageDialog, CatsRulesPanel
    get_settings()._data.pop(CatsRulesPanel.MERCHANT_SORT_KEY, None)
    db.get_or_create_account("Card")
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    sub = db.uncategorized_subcategory(food)["id"]
    for merchant, times, amount in (("zebra Shop", 3, 10), ("Apple", 1, 50), ("mango", 2, 5), (None, 1, 1)):
        for _ in range(times):
            db.add_transaction(2026, "May", 1, "Expense", "Card", amount, sub, food, merchant=merchant)
    db.conn.commit()
    p = keep(ManageDialog(db, lambda: None)).cats_panel
    types = {p.type_table.item(r, 0).text(): r for r in range(p.type_table.rowCount())}
    p.type_table.selectRow(types["Expense"])
    cats = {p.cat_table.item(r, 0).text(): r for r in range(p.cat_table.rowCount())}
    p.cat_table.selectRow(cats["Food"])
    assert names(p) == ["Apple", "mango", "zebra Shop", "(no merchant)"]  # A to Z, any letter case
    p.merchant_table.horizontalHeader().sectionClicked.emit(p.M_TX)
    assert names(p) == ["zebra Shop", "mango", "Apple", "(no merchant)"]  # most first
    p.merchant_table.horizontalHeader().sectionClicked.emit(p.M_TX)
    assert names(p) == ["Apple", "mango", "zebra Shop", "(no merchant)"]  # again: fewest first
    p.merchant_table.horizontalHeader().sectionClicked.emit(p.M_TOTAL)
    assert names(p)[:3] == ["Apple", "zebra Shop", "mango"]  # 50, 30, 10
    again = keep(ManageDialog(db, lambda: None)).cats_panel
    assert again._merchant_sort() == (p.M_TOTAL, True)  # kept
    p.merchant_table.horizontalHeader().sectionClicked.emit(p.M_NAME)
    assert names(p) == ["Apple", "mango", "zebra Shop", "(no merchant)"]


def test_edit_merchant_preview_not_under_the_buttons(qapp):
    """The note wraps on to a second line; a logo got after the window opened made it taller, and
    by less than it needed: the big preview went under the buttons."""
    from PySide6.QtGui import QColor, QImage

    from daftarche.logos import LogoDialog, to_png
    from daftarche.style import build_stylesheet, get_settings
    image = QImage(128, 128, QImage.Format_ARGB32)
    image.fill(QColor("#123456"))
    qapp.setStyleSheet(build_stylesheet(get_settings()))
    try:
        d = keep(LogoDialog("Ontario", edit_name=True, fetch_logo=lambda site: (to_png(image), "https://x")))
        d.show()
        for _ in range(5):
            qapp.processEvents()
        d.site.setText("ontario.ca")
        d._get()
        for _ in range(5):
            qapp.processEvents()
        assert d.previews[0][0].geometry().bottom() < d.btn_none.geometry().top()
    finally:
        qapp.setStyleSheet("")
