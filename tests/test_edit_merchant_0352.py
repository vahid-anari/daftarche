"""0.35.2: Edit Merchant: a merchant's name and logo in one window (double-click, ✏️, right-click)."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def png(colour):
    from PySide6.QtGui import QColor, QImage
    from daftarche.logos import to_png
    image = QImage(32, 32, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    return to_png(image)


@pytest.fixture
def shops(db):
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for name in ("StreamBox", "Maple Grocer"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, name=name.upper(), merchant=name)
    db.conn.commit()
    return db


def panel(db):
    from daftarche.tabs.manage import ManageDialog
    return keep(ManageDialog(db, lambda: None)).merchants_panel


def answer(name, image=None, changed=False, source="", ok=True):
    dlg = mock.Mock(exec=mock.Mock(return_value=ok), image=image, logo_changed=changed, source=source)
    dlg.name = name  # Mock(name=…) names the mock itself
    return dlg


def test_the_window_has_the_name_and_the_logo(qapp):
    from daftarche.logos import LogoDialog
    d = keep(LogoDialog("StreamBox", edit_name=True, fetch_logo=lambda site: (png("#111111"), "https://s.example/x.png")))
    assert d.windowTitle() == "Edit Merchant" and d.name_field.text() == "StreamBox" and not d.logo_changed
    d.name_field.setText("  Stream   Box ")
    d.site.setText("s.example")
    d._get()
    with mock.patch.object(d, "accept"):
        d._accept()
    assert d.name == "Stream Box" and d.logo_changed and d.image
    d.name_field.setText("   ")
    with mock.patch.object(d, "accept") as accepted, mock.patch("daftarche.logos.QMessageBox.warning"):
        d._accept()
    assert not accepted.called  # no name: not closed


def test_rename_and_logo_together(qapp, shops):
    p = panel(shops)
    p.select("StreamBox")
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=answer("Stream Box", png("#222222"), True, "f.png")):
        p.edit()
    assert "Stream Box" in shops.get_merchants() and shops.logo_for("Stream Box") and shops.logo_source("Stream Box") == "f.png"
    p.select("Stream Box")
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=answer("Stream Box")):
        p.edit()  # nothing changed
    assert shops.logo_for("Stream Box")


def test_merge_keeps_the_logo_chosen_and_cancel_changes_nothing(qapp, shops):
    p = panel(shops)
    shops.set_logo("Maple Grocer", png("#333333"))
    mine = png("#444444")
    p.select("StreamBox")
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=answer("maple grocer", mine, True)), \
            mock.patch("daftarche.tabs.manage._confirm_merge", return_value=False):
        p.edit()  # merge declined: nothing at all
    assert "StreamBox" in shops.get_merchants() and shops.logo_for("StreamBox") is None
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=answer("maple grocer", mine, True)), \
            mock.patch("daftarche.tabs.manage._confirm_merge", return_value=True):
        p.edit()
    assert "StreamBox" not in shops.get_merchants() and shops.logo_for("Maple Grocer") == mine


def test_double_click_on_the_name_opens_it(qapp, shops):
    p = panel(shops)
    p.select("StreamBox")
    r = next(i for i in range(p.table.rowCount()) if p.table.item(i, p.COL_NAME).text() == "StreamBox")
    with mock.patch.object(p, "edit") as edit:
        p.table.cellDoubleClicked.emit(r, p.COL_NAME)
    assert edit.called
