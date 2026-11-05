"""0.34.0: merchants' logos (layout 8): from the shop's site or a file, beside the merchant's name,
and as a category's icon."""

from unittest import mock

import pytest

from conftest import keep, wait_logo


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def png(qapp, side=180, colour="#2e7d32"):
    from PySide6.QtGui import QColor, QImage
    from daftarche.logos import to_png
    image = QImage(side, side, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    data = to_png(image) if side <= 128 else _raw_png(image)
    return data


def _raw_png(image):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    out = QByteArray()
    buf = QBuffer(out)
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(out)


@pytest.fixture
def shops(db):
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for name in ("Maple Grocer", "StreamBox", "City Hydro"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, name=name.upper(), merchant=name)
    db.add_category("Subscriptions", "Expense")
    db.conn.commit()
    return db


# ── the database ─────────────────────────────────────────────────────────────
def test_set_find_rename_merge_and_delete(qapp, shops):
    db = shops
    a, b = png(qapp, 64, "#111111"), png(qapp, 64, "#eeeeee")
    db.set_logo("StreamBox", a, "https://streambox.example/apple-touch-icon.png")
    assert db.logo_for("streambox") == a and db.logo_source("StreamBox").startswith("https://")
    subs = db.get_category_by_name("Subscriptions", type_name="Expense")["id"]
    db.set_category_icon(subs, "logo:StreamBox")
    assert db.get_icons()["cat"][subs] == "logo:StreamBox"
    db.rename_merchant("StreamBox", "Stream Box")  # the logo and the category follow
    assert db.logo_for("Stream Box") == a and db.logo_for("StreamBox") is None
    assert db.get_category_by_name("Subscriptions", type_name="Expense")["icon"] == "logo:Stream Box"
    db.set_logo("Maple Grocer", b)
    db.rename_merchant("Stream Box", "Maple Grocer")  # merged into one with a logo: that one stays
    assert db.logo_for("Maple Grocer") == b and list(db.get_logos()) == ["Maple Grocer"]
    db.set_category_icon(subs, "logo:Maple Grocer")
    db.delete_merchant("Maple Grocer")
    assert db.get_logos() == {} and db.get_category_by_name("Subscriptions", type_name="Expense")["icon"] is None


def test_merging_names_that_differ_beyond_ascii(qapp, shops):
    db = shops
    db.conn.execute("UPDATE transactions SET merchant='CAFÉ' WHERE merchant='City Hydro'")
    db.conn.execute("UPDATE transactions SET merchant='Café' WHERE merchant='StreamBox'")
    db.conn.commit()
    a, b = png(qapp, 64, "#111111"), png(qapp, 64, "#eeeeee")
    db.set_logo("Café", a)
    db.set_logo("CAFÉ", b)
    db.rename_merchant("Café", "CAFÉ")  # SQLite's NOCASE sees two names: no error, the target's stays
    assert db.logo_for("CAFÉ") == b and len(db.get_logos()) == 1


def test_a_logo_as_an_icon_is_one(qapp):
    from daftarche.db import clean_icon
    assert clean_icon("logo:  Maple   Grocer ") == "logo:Maple Grocer"
    with pytest.raises(ValueError):
        clean_icon("logo:  ")


def test_an_older_database_gets_the_table_and_a_copy(tmp_path):
    import sqlite3
    from daftarche.db import SCHEMA_VERSION, Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE merchant_logos")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()
    db = Database(path)
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 8
    assert db.get_logos() == {}
    assert (tmp_path / f"old-before-layout-{SCHEMA_VERSION}.db").exists()


def test_the_phone_gets_no_logo(qapp, shops):
    from daftarche.phone import build_snapshot
    db = shops
    db.set_logo("StreamBox", png(qapp, 32))
    subs = db.get_category_by_name("Subscriptions", type_name="Expense")["id"]
    db.set_category_icon(subs, "logo:StreamBox")
    snap = build_snapshot(db)
    cat = next(c for c in snap["categories"] if c["name"] == "Subscriptions")
    assert cat["icon"] is None and "merchant_logos" not in str(snap.keys())


# ── getting one ──────────────────────────────────────────────────────────────
def test_the_site_and_what_is_tried(qapp):
    from daftarche.logos import LogoError, fetch, site_url
    assert site_url("Example.com/ca/") == "https://Example.com" and site_url("http://a.example") == "http://a.example"
    with pytest.raises(LogoError):
        site_url("not a site")
    big, small = png(qapp, 180), png(qapp, 16, "#ff0000")
    asked = []

    def web(pages):
        def get(url):
            asked.append(url)
            if url not in pages:
                raise OSError("404")
            return pages[url], url
        return get
    data, url = fetch("shop.example", get=web({"https://shop.example/apple-touch-icon.png": big}))
    assert url.endswith("/apple-touch-icon.png") and len(data) > 0
    from PySide6.QtGui import QImage
    assert QImage.fromData(data).width() == 128  # made smaller
    page = b'<html><head><link rel="shortcut icon" href="/img/fav.png" sizes="16x16"></head></html>'
    data, url = fetch("shop.example", get=web({"https://shop.example": page, "https://shop.example/img/fav.png": small}))
    assert url == "https://shop.example/img/fav.png"
    data, url = fetch("shop.example", get=web({"https://shop.example/favicon.ico": small}))
    assert url.endswith("/favicon.ico")
    manifest = b'{"icons": [{"src": "/i/192.png", "sizes": "192x192"}, {"src": "/i/48.png", "sizes": "48x48"}]}'
    data, url = fetch("shop.example", get=web({"https://shop.example/site.webmanifest": manifest,
                                               "https://shop.example/i/192.png": big,
                                               "https://shop.example/favicon.ico": small}))
    assert url == "https://shop.example/i/192.png"  # 0.35.2: the web app manifest's icons
    data, url = fetch("shop.example", get=web({"https://shop.example/favicon.ico": small,
                                               "https://www.shop.example/apple-touch-icon.png": big}))
    assert url == "https://www.shop.example/apple-touch-icon.png"  # nothing sharp: with www. too
    with pytest.raises(LogoError):
        fetch("shop.example", get=web({}))
    with pytest.raises(LogoError):
        fetch("shop.example", get=web({"https://shop.example/apple-touch-icon.png": b"not a picture"}))


def test_the_logo_window(qapp, tmp_path):
    from daftarche.logos import LogoDialog
    picture = tmp_path / "mine.png"
    picture.write_bytes(png(qapp, 300))
    fetched = png(qapp, 64)
    d = keep(LogoDialog("Maple Grocer", fetch_logo=lambda site: (fetched, "https://maple.example/favicon.ico")))
    assert d.image is None and d.btn_none.isEnabled() is False
    d.site.setText("maple.example")
    d._get()
    wait_logo(d)
    assert d.image == fetched and d.source.startswith("https://maple.example")
    assert not d.previews[0][0].pixmap().isNull()
    d.use_file(str(picture))
    assert d.source == "mine.png" and d.image
    d._no_logo()
    assert d.image is None
    again = keep(LogoDialog("Maple Grocer", fetched, "https://maple.example/favicon.ico"))
    assert again.site.text() == "maple.example"  # the site it came from


# ── showing it ───────────────────────────────────────────────────────────────
def test_beside_the_merchants_and_in_transactions(qapp, shops):
    from PySide6.QtCore import Qt
    from daftarche.icons import blank_icon
    from daftarche.tabs.manage import ManageDialog
    from daftarche.tabs.transactions import COL_MERCHANT, TransactionsTab
    db = shops
    db.set_logo("Maple Grocer", png(qapp, 64))
    m = keep(ManageDialog(db, lambda: None)).merchants_panel
    rows = {m.table.item(r, m.COL_NAME).text(): m.table.item(r, m.COL_NAME) for r in range(m.table.rowCount())}
    assert not rows["Maple Grocer"].icon().isNull()
    assert rows["City Hydro"].icon().cacheKey() == blank_icon().cacheKey()  # a space: the names in line
    tab = keep(TransactionsTab(db))
    tab._period._select_preset(0, emit=False, persist=False)
    tab.refresh()
    by_name = {tab.model.get_row(i)["merchant"]: i for i in range(tab.model.rowCount())}
    maple = tab.model.data(tab.model.index(by_name["Maple Grocer"], COL_MERCHANT), Qt.DecorationRole)
    hydro = tab.model.data(tab.model.index(by_name["City Hydro"], COL_MERCHANT), Qt.DecorationRole)
    assert not maple.isNull() and hydro is blank_icon()


def test_no_logos_no_space(qapp, shops):
    from PySide6.QtCore import Qt
    from daftarche.tabs.transactions import COL_MERCHANT, TransactionsTab
    tab = keep(TransactionsTab(shops))
    tab._period._select_preset(0, emit=False, persist=False)
    tab.refresh()
    assert tab.model.data(tab.model.index(0, COL_MERCHANT), Qt.DecorationRole) is None


def test_right_click_logo_saves_and_takes_away(qapp, shops):
    from daftarche.tabs.manage import ManageDialog
    db = shops
    m = keep(ManageDialog(db, lambda: None)).merchants_panel
    m.select("StreamBox")
    shown = []
    with mock.patch("daftarche.tabs.manage._exec_menu",
                    lambda menu, where: shown.append([a.text() for a in menu.actions() if a.text()])):
        r = next(i for i in range(m.table.rowCount()) if m.table.item(i, m.COL_NAME).text() == "StreamBox")
        m.table._list_menu(m.table.visualRect(m.table.model().index(r, m.COL_NAME)).center())
    assert "✏️  Edit Merchant…" in shown[0]  # name and logo in one window since 0.35.2
    image = png(qapp, 48)
    with mock.patch("daftarche.tabs.manage.LogoDialog",
                    return_value=mock.Mock(exec=mock.Mock(return_value=True), image=image, source="x.png")):
        m.set_logo()
    assert db.logo_for("StreamBox") == image and db.logo_source("StreamBox") == "x.png"
    with mock.patch("daftarche.tabs.manage.LogoDialog",
                    return_value=mock.Mock(exec=mock.Mock(return_value=True), image=None, source="")):
        m.set_logo()
    assert db.logo_for("StreamBox") is None


def test_a_category_can_use_a_logo(qapp, shops):
    from daftarche.icons import IconPickerDialog, emoji_icon, use_logos
    db = shops
    db.set_logo("StreamBox", png(qapp, 64))
    use_logos(db)
    d = keep(IconPickerDialog("", "Category", name="Subscriptions", logos=db.get_logos()))
    btn = d._logo_buttons["logo:StreamBox"]
    btn.click()
    assert d.icon == "logo:StreamBox" and d.typed.text() == "" and "highlight" in btn.styleSheet()
    assert not d.preview.pixmap().isNull()
    with mock.patch.object(d, "accept"):
        d._accept()
    assert d.icon == "logo:StreamBox"
    assert not emoji_icon("logo:StreamBox").isNull() and emoji_icon("logo:Nobody").isNull()
    plain = keep(IconPickerDialog("", "Category", name="Food"))
    assert plain._logo_buttons == {}  # no logos saved: no row for them


def test_icons_follow_the_font_size(qapp):
    from PySide6.QtWidgets import QTableWidget
    from daftarche.logos import icon_size
    t = keep(QTableWidget())
    small = icon_size(t).width()
    f = t.font()
    f.setPointSize(f.pointSize() * 2)
    t.setFont(f)
    assert icon_size(t).width() > small
