"""0.26: the phone snapshot (docs/phone-snapshot.md): what it holds. 0.28: sent to the phones' files on
Google Drive, sealed, a minute after a change (with a fake Drive)."""

import json
from datetime import datetime, timezone

import pytest

from conftest import keep
from daftarche.phone import VERSION, build_snapshot


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def book(db):
    """Two months: pay, a split shop with a tag, a transfer to savings, money lent to Sahar."""
    db.add_category("Groceries", "Expense")
    db.add_category("Home", "Expense")
    db.add_category("Salary", "Income")
    groc = db.get_category_by_name("Groceries", type_name="Expense")["id"]
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    sal = db.get_category_by_name("Salary", type_name="Income")["id"]
    db.add_subcategory("Food", groc)
    db.add_subcategory("Cleaning", home)
    db.add_subcategory("Pay", sal)
    food = db.get_subcategory_by_name("Food", groc)["id"]
    clean = db.get_subcategory_by_name("Cleaning", home)["id"]
    pay = db.get_subcategory_by_name("Pay", sal)["id"]
    db.set_category_icon(groc, "🛒")
    ids = {"pay": db.add_transaction(2026, "September", 1, "Income", "Chequing", 3000, pay, sal, name="ACME PAY",
                                     fitid="BANK-ID-1"),
           "shop": db.add_transaction(2026, "October", 3, "Expense", "Chequing", 100, food, groc,
                                      name="MAPLE #12", merchant="Maple Grocer", note="weekly shop")}
    db.set_splits(ids["shop"], [(groc, food, 70, None), (home, clean, 30, "soap")])
    db.add_tag("Trip")
    tag = next(t["id"] for t in db.get_tags() if t["name"] == "Trip")
    db.set_tags_for_transaction(ids["shop"], [tag])
    cat, sub = db.get_transfer_cat_sub("TO SAVINGS", matched=True, from_account="Chequing", to_account="Savings")
    ids["save"] = db.add_transaction(2026, "October", 5, "Transfer", "Chequing", 500, sub, cat, name="TO SAVINGS",
                                     to_account_name="Savings")
    ids["lent"] = db.add_transaction(2026, "October", 6, "Expense", "Chequing", 200, food, groc, merchant="Sahar")
    db.make_loan([ids["lent"]], "Sahar")
    db.save_account_id("12345-678", "Chequing")
    ids["tag"] = tag
    return ids


def test_the_snapshot_holds_what_the_phone_shows(db, book):
    snap = build_snapshot(db, "0.26.0", now=datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc))
    assert (snap["format"], snap["version"], snap["app_version"]) == ("daftarche-phone", VERSION, "0.26.0")
    assert snap["created"] == "2026-10-20T08:00:00+00:00"

    accounts = {a["name"]: a for a in snap["accounts"]}
    assert accounts["Chequing"]["balance"] == 2200 and accounts["Savings"]["balance"] == 500
    latest = db.get_latest_account_balances()
    assert {a["id"]: a["balance"] for a in snap["accounts"]} == latest  # the desktop's own numbers
    assert snap["balances"]["months"] == ["2026-09", "2026-10"]
    assert snap["balances"]["by_account"][str(accounts["Chequing"]["id"])] == [3000, 2200]

    tx = {t["id"]: t for t in snap["transactions"]}
    assert [t["date"] for t in snap["transactions"]] == sorted((t["date"] for t in snap["transactions"]), reverse=True)
    shop = tx[book["shop"]]
    assert (shop["type"], shop["amount"], shop["merchant"], shop["note"]) == ("Expense", 100, "Maple Grocer",
                                                                              "weekly shop")
    assert [(p["amount"], p["note"]) for p in shop["parts"]] == [(70, None), (30, "soap")]
    assert shop["tags"] == [book["tag"]] and snap["tags"] == [{"id": book["tag"], "name": "Trip"}]
    assert tx[book["save"]]["type"] == "Transfer" and tx[book["save"]]["transfer"] == "matched"
    assert tx[book["save"]]["to_account"] == accounts["Savings"]["id"]
    assert tx[book["lent"]]["transfer"] == "loan" and tx[book["pay"]]["transfer"] is None

    groceries = next(c for c in snap["categories"] if c["name"] == "Groceries")
    assert groceries["type"] == "Expense" and groceries["icon"] == "🛒"
    assert groceries["subcategories"] == [{"id": shop["parts"][0]["subcategory"], "name": "Food", "icon": "🛒"}]

    assert [(e["person"], e["balance"]) for e in snap["loans"]] == [("Sahar", 200)]


def test_nothing_private_that_the_phone_does_not_need(db, book):
    text = json.dumps(build_snapshot(db))
    assert "BANK-ID-1" not in text and "12345-678" not in text  # bank ids, account numbers
    assert "fitid" not in text and "memorandum" not in text


def test_an_empty_book(db):
    snap = build_snapshot(db)
    assert snap["transactions"] == [] and snap["loans"] == [] and snap["balances"]["months"] == []


class FakeDrive:
    files, fail = {}, None

    def __init__(self, token):
        assert token == "R"

    def create(self, name, data):
        fid = f"F{len(self.files) + 1}"
        self.files[fid] = data
        return fid

    def update(self, file_id, data):
        if FakeDrive.fail:
            raise FakeDrive.fail
        if file_id not in self.files:
            from daftarche.phone_link import FileGone
            raise FileGone("gone")
        self.files[file_id] = data

    def delete(self, file_id):
        self.files.pop(file_id, None)


@pytest.fixture
def sender(qapp, db, book, tmp_path):
    from daftarche.phone_sync import PhoneSender, PhoneStore
    FakeDrive.files, FakeDrive.fail = {}, None
    store = PhoneStore(tmp_path / "phone-link.json")
    s = PhoneSender(lambda: db, "0.28.0", store=store, drive_factory=FakeDrive)
    s.timer.stop()
    s.signed_in({"refresh_token": "R", "email": "v@example.com"})
    return s


def _wait(sender):
    from PySide6.QtWidgets import QApplication
    import time
    end = time.monotonic() + 5
    while sender.busy and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    assert not sender.busy


def _opened(sender, phone):
    from daftarche.seal import key_from_text, open_sealed
    return json.loads(open_sealed(FakeDrive.files[phone["file"]], key_from_text(phone["key"])))


def test_connecting_a_phone_puts_its_sealed_copy_on_the_drive(sender, tmp_path):
    import os
    from daftarche.phone_link import parse_pairing_link
    phone, link = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    paired = parse_pairing_link(link)
    assert (paired["file"], paired["key"], paired["name"]) == (phone["file"], phone["key"], "Pixel")
    assert b"Groceries" not in FakeDrive.files[phone["file"]]  # Google sees only scrambled bytes
    assert _opened(sender, phone)["app_version"] == "0.28.0"
    assert oct(os.stat(tmp_path / "phone-link.json").st_mode & 0o777) == "0o600"  # it holds the keys


def test_changes_go_a_minute_after_the_last_one(sender, db):
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    sender.tick(now=1000.0)
    assert not sender.pending()
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "June", 9, "Expense", "Card", 7, us, uc, name="LATE SHOP")
    sender.tick(now=1000.0)
    assert sender.pending() and not sender.busy  # noted, not sent yet
    sender.tick(now=1030.0)
    assert not sender.busy
    sender.tick(now=1061.0)
    _wait(sender)
    assert not sender.pending() and "LATE SHOP" in [t["name"] for t in _opened(sender, phone)["transactions"]]
    assert sender.store.phones[0]["sent"] and not sender.store.phones[0]["error"]


def test_offline_tries_again_later_and_says_so(sender, db):
    from daftarche.phone_link import LinkError
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    FakeDrive.fail = LinkError("Could not reach Google: offline")
    sender.send_now()
    _wait(sender)
    assert sender.pending() and "offline" in sender.store.phones[0]["error"] and "offline" in sender.last_error
    FakeDrive.fail = None
    sender.send_now()
    _wait(sender)
    assert not sender.pending() and sender.store.phones[0]["error"] is None


def test_a_revoked_sign_in_signs_out(sender):
    from daftarche.phone_link import SignedOut
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    FakeDrive.fail = SignedOut("Google no longer accepts Daftarche's sign-in")
    sender.send_now()
    _wait(sender)
    assert sender.store.google is None and "sign-in" in sender.last_error and not sender.active()


def test_disconnect_deletes_the_file(sender):
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    assert sender.disconnect_phone(phone["id"]) is None
    assert phone["file"] not in FakeDrive.files and sender.store.phones == []


def test_never_a_database_opened_to_look_at(qapp, db, book, tmp_path):
    from daftarche.phone_sync import PhoneSender, PhoneStore
    store = PhoneStore(tmp_path / "p.json")
    store.data = {"google": {"refresh_token": "R"}, "phones": [{"id": "1", "name": "P", "file": "F", "key": "k"}]}
    s = PhoneSender(lambda: None, store=store, drive_factory=FakeDrive)
    s.timer.stop()
    assert not s.active()
    s.send_now()
    assert not s.busy


def test_settings_shows_the_phones(sender, qapp):
    from daftarche.phone_window import PhoneSection, ago
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    section = keep(PhoneSection(sender))
    texts = [w.text() for w in section.findChildren(__import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)]
    assert any("Pixel" in t for t in texts) and any("v@example.com" in t for t in texts)
    assert section.btn_account.text() == "Sign Out" and not section.btn_send.isHidden()
    from datetime import datetime
    now = datetime(2026, 10, 21, 12, 0)
    assert ago("2026-10-21T11:55:00", now) == "5 minutes ago" and ago("2026-10-20T09:05:00", now) == \
        "yesterday at 09:05" and ago(None) == "never"


def test_the_qr_code_draws(qapp):
    from daftarche.phone_window import qr_pixmap
    pix = qr_pixmap("daftarche://pair?v=1&f=F&k=K&n=P")
    assert not pix.isNull() and pix.width() == pix.height()


# ── from the review ──────────────────────────────────────────────────────────
def test_quitting_waits_for_a_send_and_sends_what_came_after(sender, db):
    import threading
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    gate = threading.Event()
    real_update = FakeDrive.update

    def slow(self, file_id, data):
        gate.wait(5)
        real_update(self, file_id, data)
    FakeDrive.update = slow
    try:
        sender.send_now()
        assert sender.busy
        uc, us = db.get_uncategorized_ids()
        db.add_transaction(2026, "June", 9, "Expense", "Card", 7, us, uc, name="WHILE SENDING")
        gate.set()
        sender.finish()  # Daftarche closing
    finally:
        FakeDrive.update = real_update
    assert not sender.busy and not sender.pending()
    assert "WHILE SENDING" in [t["name"] for t in _opened(sender, phone)["transactions"]]
    assert sender.store.data["dirty"] is False


def test_unsent_changes_are_remembered_across_a_quit(sender, db, tmp_path):
    from daftarche.phone_sync import PhoneSender, PhoneStore
    from daftarche.phone_link import LinkError
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    sender.store.phones[0]["error"] = None
    sender.store.save()
    FakeDrive.fail = LinkError("offline")
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "June", 9, "Expense", "Card", 7, us, uc, name="OFFLINE")
    sender.finish()
    again = PhoneSender(lambda: db, store=PhoneStore(tmp_path / "phone-link.json"), drive_factory=FakeDrive)
    again.timer.stop()
    assert again.pending()  # the next start knows there is something to send


def test_a_restored_backup_is_sent(sender, db):
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    sender.database_switched(changed=True)
    _wait(sender)
    assert not sender.pending() and sender.store.phones[0]["sent"]
    sender.database_switched(changed=False)  # Open Database… / Back to My Database: nothing new
    sender.tick(now=10**9)
    assert not sender.busy


def test_disconnect_while_signed_out_says_so(sender):
    phone, _ = sender.connect_phone("Pixel")
    sender.add_phone(phone)
    sender.sign_out()
    assert "signed out" in sender.disconnect_phone(phone["id"])
    assert phone["file"] in FakeDrive.files  # still there: to delete by hand, as said


def test_connect_is_off_while_viewing_another_database(qapp, tmp_path):
    from daftarche.phone_sync import PhoneSender, PhoneStore
    from daftarche.phone_window import PhoneSection
    store = PhoneStore(tmp_path / "p.json")
    store.data["google"] = {"refresh_token": "R", "email": "v@example.com"}
    s = PhoneSender(lambda: None, store=store, drive_factory=FakeDrive)
    s.timer.stop()
    section = keep(PhoneSection(s))
    assert not section.btn_connect.isEnabled()


# ── 0.28.1: Settings in tabs ─────────────────────────────────────────────────
def test_settings_in_tabs_opens_on_the_last_one(sender, qapp):
    from PySide6.QtWidgets import QWidget
    from daftarche.style import get_settings
    from daftarche.window import SettingsDialog
    parent = keep(QWidget())
    parent.phone_sender = sender
    settings = get_settings()
    settings.set("settings_tab", 2)
    d = keep(SettingsDialog(settings, parent))
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == ["Appearance", "Backups", "Phone"]
    assert d.tabs.currentIndex() == 2 and d.btn_reset.isHidden()  # Reset is about Appearance only
    d.tabs.setCurrentIndex(0)
    assert not d.btn_reset.isHidden() and settings.get("settings_tab") == 0
    size = d.size()
    d.tabs.setCurrentIndex(1)
    assert d.size() == size  # the same size on every tab
