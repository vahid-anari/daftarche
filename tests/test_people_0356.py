"""0.35.6: a merchant can be a person (Edit Merchant: "A person, not a shop"): 👤 beside it where
a logo would be, Merchants can show only people; it follows a rename or a merge (layout 9). Get
Logo works in the background: the window stays alive, and pressing it again cancels."""

import sqlite3
import threading
from unittest import mock

import pytest

from conftest import keep, wait_logo


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def two(db):
    db.get_or_create_account("Card")
    uc, us = db.get_uncategorized_ids()
    for name in ("Ali", "Ali M", "IKEA"):
        db.add_transaction(2026, "May", 1, "Expense", "Card", 10, us, uc, merchant=name)
    db.conn.commit()
    return db


def test_people_in_the_database(two):
    db = two
    db.set_person("ali")
    assert db.is_person("Ali") and db.get_people() == {"ali"}
    db.rename_merchant("Ali", "Ali Mohammadi")
    assert db.is_person("Ali Mohammadi") and not db.is_person("Ali")
    db.rename_merchant("Ali M", "ali mohammadi")  # merged into a person
    assert db.get_people() == {"ali mohammadi"}
    db.delete_merchant("Ali Mohammadi")
    assert db.get_people() == set()
    db.set_person("IKEA")
    db.set_person("IKEA", False)
    assert not db.is_person("IKEA")


def test_an_older_database_gets_the_table(tmp_path):
    from daftarche.db import SCHEMA_VERSION, Database
    path = tmp_path / "old.db"
    Database(path).conn.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE merchant_people")
    conn.execute("PRAGMA user_version = 8")
    conn.commit()
    conn.close()
    db = Database(path)
    assert SCHEMA_VERSION >= 9 and db.get_people() == set()
    db.set_person("Zahra")
    assert db.is_person("zahra")


def test_edit_merchant_person_and_the_icon(qapp, two):
    from daftarche.icons import PERSON, emoji_icon
    from daftarche.tabs.manage import ManageDialog
    db = two
    p = keep(ManageDialog(db, lambda: None)).merchants_panel
    dlg = mock.Mock(exec=mock.Mock(return_value=True), image=None, logo_changed=False, source="", person=True)
    dlg.name = "Ali"
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=dlg) as window:
        p.edit_named("Ali", p)
    assert window.call_args.kwargs["person"] is False and db.is_person("Ali")
    p.refresh()
    rows = {p.table.item(r, p.COL_NAME).text(): r for r in range(p.table.rowCount())}
    icon = p.table.item(rows["Ali"], p.COL_NAME).icon()
    assert icon.cacheKey() == emoji_icon(PERSON).cacheKey()
    p.btn_only_people.click()
    shown = [p.table.item(r, p.COL_NAME).text() for r in range(p.table.rowCount()) if not p.table.isRowHidden(r)]
    assert shown == ["Ali"]


def test_get_logo_in_the_background_and_cancel(qapp):
    from daftarche.logos import LogoDialog
    gate = threading.Event()

    def slow(site):
        gate.wait(5)
        return b"not used", "https://slow.example"
    d = keep(LogoDialog("Slow", fetch_logo=slow, edit_name=True, person=True))
    assert d.chk_person.isChecked()
    d.site.setText("slow.example")
    d._get()
    assert d.busy() and d.btn_get.text() == "Cancel"  # the window answers meanwhile
    d._get()  # Cancel
    assert not d.busy() and d.btn_get.text() == "Get Logo"
    gate.set()
    assert d.image is None  # what came after Cancel is not used


def test_a_site_that_does_not_answer_ends_in_time():
    import time

    from daftarche.logos import LogoError, fetch_within
    tried = []

    def hang(url, timeout):
        tried.append(timeout)
        time.sleep(min(timeout, 0.3))
        raise TimeoutError("no answer")
    start = time.monotonic()
    with pytest.raises(LogoError):
        fetch_within("nobody.example", seconds=1, get=hang)
    assert time.monotonic() - start < 2 and all(t <= 1 for t in tried)


def test_a_failed_get_says_so(qapp):
    from daftarche.logos import LogoDialog, LogoError

    def none(site):
        raise LogoError("No logo found at https://x.example")
    d = keep(LogoDialog("X", fetch_logo=none))
    d.site.setText("x.example")
    with mock.patch("daftarche.logos.QMessageBox.warning") as warned:
        d._get()
        wait_logo(d)
    assert warned.called and d.image is None


def test_merge_and_rename_keep_what_was_chosen(qapp, two):
    """Merged into a person with the box left alone: it stays a person; renamed with the box
    unticked: no longer one (inside one transaction, the list of people is read afresh)."""
    from daftarche.tabs.manage import ManageDialog
    db = two
    db.set_person("Ali")
    db.conn.commit()
    p = keep(ManageDialog(db, lambda: None)).merchants_panel

    def window(name, person):
        dlg = mock.Mock(exec=mock.Mock(return_value=True), image=None, logo_changed=False, source="", person=person)
        dlg.name = name
        return dlg
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=window("ali", False)), \
            mock.patch("daftarche.tabs.manage._confirm_merge", return_value=True):
        p.edit_named("Ali M", p)  # a shop merged into the person Ali, its box (unticked) untouched
    assert db.is_person("Ali") and "Ali M" not in db.get_merchants()
    with mock.patch("daftarche.tabs.manage.LogoDialog", return_value=window("Alireza", False)):
        p.edit_named("Ali", p)  # renamed, and unticked
    assert not db.is_person("Alireza") and db.get_people() == set()


def test_accented_letter_case(two):
    db = two
    db.set_person("Café")
    assert db.is_person("CAFÉ")
    db.set_person("CAFÉ", False)
    assert db.get_people() == set()
