"""Phone 0.3.0: connected to the Mac by its QR code, the data fetched from its Google Drive."""

import asyncio
import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from daftarche_phone import link
from daftarche_phone.seal import key_to_text, new_key, seal

KEY = key_to_text(new_key())


def test_the_pairing_link_pasted_or_as_a_route():
    full = f"daftarche://pair?v=1&f=1AbC_x-9&k={KEY}&n=Vahid%27s+Pixel"
    want = {"file": "1AbC_x-9", "key": KEY, "name": "Vahid's Pixel"}
    assert link.parse_pairing(f"  {full}\n") == want
    assert link.parse_pairing(f"/?v=1&f=1AbC_x-9&k={KEY}&n=Vahid%27s+Pixel") == want  # the app's route
    assert link.parse_pairing("https://evil.example/?f=1&k=" + KEY) is None
    assert link.parse_pairing("daftarche://pair?v=1&f=1&k=short") is None
    assert link.parse_pairing("/") is None and link.parse_pairing("") is None
    page = f"https://vahid-anari.github.io/pair/#v=1&f=1AbC_x-9&k={KEY}&n=Vahid%27s+Pixel"
    assert link.parse_pairing(page) == want  # the QR code's web link, copied on the Mac and pasted
    assert link.parse_pairing(f"https://evil.example/pair/#v=1&f=1&k={KEY}") is None


def _answer(status=200, body=b""):
    def opener(req):
        if status != 200:
            raise urllib.error.HTTPError(req.full_url, status, "x", {}, io.BytesIO(body))

        class R:
            def read(self):
                return body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()
    return opener


def test_fetching():
    blob = seal(b"{}", link.key_from_text(KEY))
    assert link.fetch("F", opener=_answer(body=blob)) == blob
    with pytest.raises(link.Disconnected):
        link.fetch("F", opener=_answer(404))
    with pytest.raises(link.FetchError):
        link.fetch("F", opener=_answer(body=b"<html>Google Drive - Virus scan warning</html>"))

    def offline(req):
        raise urllib.error.URLError("no network")
    with pytest.raises(link.FetchError, match="No connection"):
        link.fetch("F", opener=offline)


# ── the app ──────────────────────────────────────────────────────────────────
def test_the_app_opens_the_copy_it_keeps(app):
    phone, page, view = app
    assert phone.snap is not None and phone.pairing["name"] == "Test phone"


def test_disconnected_on_the_mac(app, monkeypatch):
    from daftarche_phone.app import DISCONNECTED, NOT_PAIRED

    def gone(file_id):
        raise link.Disconnected("gone")
    monkeypatch.setattr(link, "fetch", gone)
    phone, page, view = app
    asyncio.run(phone._fetch())
    assert phone.snap is None and phone.pairing is None and phone.problem == NOT_PAIRED
    assert link.load_cache() is None  # the copy is removed from the phone
    texts = [c.value for c in _texts(phone._welcome())]
    assert DISCONNECTED in texts


def test_offline_keeps_showing_the_copy(app, monkeypatch):
    def offline(file_id):
        raise link.FetchError("No connection")
    monkeypatch.setattr(link, "fetch", offline)
    phone, page, view = app
    before = phone.snap
    asyncio.run(phone._fetch(manual=True))
    assert phone.snap is before and "No connection" in page.dialogs[-1].content.value


def test_connecting_by_the_link(app, monkeypatch):
    from daftarche.db import Database  # a fresh book on "another Mac"
    from daftarche.phone import build_snapshot
    phone, page, view = app
    key = new_key()
    db = Database(":memory:")
    blob = seal(json.dumps(build_snapshot(db, "9.9.9")).encode(), key)
    monkeypatch.setattr(link, "fetch", lambda file_id: blob if file_id == "NEW" else None)
    saved = {}

    async def remember(k, v):
        saved[k] = v
    phone.prefs = SimpleNamespace(set=remember)
    asyncio.run(phone._forget())  # a phone not connected yet: the link connects it at once
    asyncio.run(phone._route_changed(SimpleNamespace(route=f"/?v=1&f=NEW&k={key_to_text(key)}&n=Tablet")))
    assert phone.pairing == {"file": "NEW", "key": key_to_text(key), "name": "Tablet"}
    assert phone.snap.app_version == "9.9.9" and json.loads(saved["pairing"])["f"] == "NEW"


def test_pasting_a_wrong_link_says_so(app):
    phone, page, view = app
    asyncio.run(phone._forget())
    phone._welcome()
    phone._paste_field.value = "hello"
    asyncio.run(phone._paste())
    assert "not Daftarche's link" in page.dialogs[-1].content.value and phone.pairing is None


def _texts(control):
    import flet as ft
    stack = [control]
    while stack:
        c = stack.pop()
        if isinstance(c, ft.Text):
            yield c
        for name in ("content", "controls"):
            inner = getattr(c, name, None)
            stack.extend(inner if isinstance(inner, list) else [inner] if inner is not None else [])


# ── from the review ──────────────────────────────────────────────────────────
def test_only_daftarches_own_link_form():
    assert link.parse_pairing(f"daftarche://pair?f=1&k={KEY}") is None  # no version
    assert link.parse_pairing(f"notes ?v=1&f=1&k={KEY}") is None
    assert link.parse_pairing(f"daftarche://other?v=1&f=1&k={KEY}") is None


def test_a_late_disconnected_answer_does_not_undo_a_new_connection(app, monkeypatch):
    phone, page, view = app
    key = new_key()
    from daftarche.db import Database
    from daftarche.phone import build_snapshot
    new_blob = seal(json.dumps(build_snapshot(Database(":memory:"), "9.9.9")).encode(), key)

    async def run():
        release = asyncio.Event()

        def fetch(file_id):  # the old file: gone, but only answers after the new pairing
            if file_id == "NEW":
                return new_blob
            import time
            while not release.is_set():
                time.sleep(0.01)
            raise link.Disconnected("gone")
        monkeypatch.setattr(link, "fetch", fetch)
        old = asyncio.create_task(phone._fetch())
        await asyncio.sleep(0.05)
        phone.prefs = SimpleNamespace(set=_noop)
        await phone._pair({"file": "NEW", "key": key_to_text(key), "name": "Tablet"})
        release.set()
        await old
    asyncio.run(run())
    assert phone.pairing["file"] == "NEW" and phone.snap.app_version == "9.9.9"


def test_another_link_asks_before_replacing(app):
    phone, page, view = app
    before = phone.pairing
    asyncio.run(phone._offer({"file": "OTHER", "key": KEY, "name": "Someone"}))
    assert phone.pairing is before and type(page.dialogs[-1]).__name__ == "AlertDialog"


async def _noop(*a, **k):
    return None
