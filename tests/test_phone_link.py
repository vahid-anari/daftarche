"""0.28.0: the phone connection through Google Drive — sealing, the pairing link, sign-in, the Drive."""

import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from daftarche import phone_link as L
from daftarche.seal import SealError, is_sealed, key_from_text, key_to_text, new_key, open_sealed, seal

ROOT = Path(__file__).resolve().parents[1]


def _direct(url):
    """The browser coming back to 127.0.0.1 (never through a proxy)."""
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5).read()


# ── sealing ──────────────────────────────────────────────────────────────────
def test_sealed_data_opens_with_its_key_only():
    key, data = new_key(), json.dumps({"x": list(range(5000))}).encode()
    blob = seal(data, key)
    assert is_sealed(blob) and data not in blob and len(blob) < len(data)  # compressed, scrambled
    assert open_sealed(blob, key) == data
    assert seal(data, key) != blob  # a new nonce each time
    with pytest.raises(SealError):
        open_sealed(blob, new_key())
    changed = bytearray(blob)
    changed[40] ^= 1
    with pytest.raises(SealError):
        open_sealed(bytes(changed), key)
    with pytest.raises(SealError):
        open_sealed(b"<html>not found</html>", key)
    assert open_sealed(seal(b"", key), key) == b""


def test_keys_as_text():
    key = new_key()
    text = key_to_text(key)
    assert len(text) == 43 and key_from_text(f"  {text} ") == key
    with pytest.raises(SealError):
        key_from_text("abc")


def test_the_phone_has_the_same_seal():
    assert (ROOT / "src/daftarche/seal.py").read_text() == \
        (ROOT / "mobile/src/daftarche_phone/seal.py").read_text()


# ── the pairing link ─────────────────────────────────────────────────────────
def test_pairing_link_round_trip():
    link = L.pairing_link("1AbC-xyz_9", "k" * 43, "Vahid's Pixel")
    assert link.startswith("https://vahid-anari.github.io/pair/#v=1&")  # the key after "#": never sent
    assert L.parse_pairing_link("daftarche://pair?" + link.split("#", 1)[1])["file"] == "1AbC-xyz_9"
    assert L.parse_pairing_link(f"\n {link} ") == {"file": "1AbC-xyz_9", "key": "k" * 43, "name": "Vahid's Pixel"}
    assert L.parse_pairing_link("https://example.com/?f=1&k=2") is None
    assert L.parse_pairing_link("daftarche://pair?v=1&f=1") is None


# ── talking to Google, with a fake Google ────────────────────────────────────
class FakeGoogle:
    def __init__(self):
        self.calls, self.files, self.permissions = [], {}, {}
        self.refresh_ok = True

    def __call__(self, req):
        url, method = req.full_url, req.get_method()
        self.calls.append((method, url))
        if url == L.TOKEN_URL:
            form = dict(urllib.parse.parse_qsl(req.data.decode()))
            if form["grant_type"] == "authorization_code":
                claims = base64.urlsafe_b64encode(json.dumps({"email": "vahid@example.com"}).encode()).decode()
                return self._ok({"refresh_token": "R1", "access_token": "A1", "expires_in": 3600,
                                 "scope": "openid https://www.googleapis.com/auth/drive.file email",
                                 "id_token": f"x.{claims.rstrip('=')}.y"})
            if not self.refresh_ok:
                return self._err(400, {"error": "invalid_grant"})
            return self._ok({"access_token": "A2", "expires_in": 3600})
        assert req.headers["Authorization"].startswith("Bearer ")
        if url.startswith(L.UPLOAD_URL + "?uploadType=multipart"):
            fid = f"F{len(self.files) + 1}"
            self.files[fid] = req.data
            return self._ok({"id": fid})
        if "/permissions" in url:
            fid = url.split("/files/")[1].split("/")[0]
            self.permissions[fid] = json.loads(req.data)
            return self._ok({"id": "p"})
        fid = url.split("/files/")[1].split("?")[0]
        if fid not in self.files:
            return self._err(404, {"error": {"message": "File not found"}})
        if method == "PATCH":
            self.files[fid] = req.data
            return self._ok({"id": fid})
        if method == "DELETE":
            del self.files[fid]
            return self._ok(None, 204)
        raise AssertionError((method, url))

    @staticmethod
    def _ok(data, status=200):
        class R:
            def __init__(self):
                self.status = status

            def read(self):
                return json.dumps(data).encode() if data is not None else b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R()

    @staticmethod
    def _err(code, data):
        import io
        raise urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(json.dumps(data).encode()))


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setenv("DAFTARCHE_GOOGLE_CLIENT", "cid.apps.googleusercontent.com:sec")
    return FakeGoogle()


def test_sign_in_through_the_browser(google):
    def browser(url):  # the person agrees; Google sends the browser back to Daftarche
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert q["scope"] == L.SCOPES and q["code_challenge_method"] == "S256" and q["access_type"] == "offline"
        back = f"{q['redirect_uri']}/?" + urllib.parse.urlencode({"code": "C", "state": q["state"]})
        threading.Thread(target=lambda: _direct(back), daemon=True).start()

    assert L.sign_in(browser, timeout_s=10, opener=google) == {"refresh_token": "R1", "email": "vahid@example.com"}


def test_sign_in_refused_or_without_a_client(google, monkeypatch):
    def refuse(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        back = f"{q['redirect_uri']}/?" + urllib.parse.urlencode({"error": "access_denied", "state": q["state"]})
        threading.Thread(target=lambda: _direct(back), daemon=True).start()

    with pytest.raises(L.LinkError, match="cancelled"):
        L.sign_in(refuse, timeout_s=10, opener=google)
    monkeypatch.delenv("DAFTARCHE_GOOGLE_CLIENT")
    monkeypatch.setattr(L, "CLIENT_ID", "")
    with pytest.raises(L.LinkError, match="no Google client"):
        L.sign_in(lambda url: None, opener=google)


def test_a_phone_file_is_made_shared_updated_and_deleted(google):
    drive = L.Drive("R1", opener=google)
    fid = drive.create("Daftarche phone - Pixel", b"sealed bytes")
    assert google.files[fid].count(b"sealed bytes") == 1
    assert google.permissions[fid] == {"role": "reader", "type": "anyone"}
    drive.update(fid, b"newer")
    assert google.files[fid] == b"newer"
    drive.delete(fid)
    drive.delete(fid)  # already gone: fine
    assert fid not in google.files
    with pytest.raises(L.FileGone):
        drive.update(fid, b"x")
    assert sum(1 for m, u in google.calls if u == L.TOKEN_URL) == 1  # one access token, kept


def test_a_revoked_sign_in_says_sign_in_again(google):
    google.refresh_ok = False
    with pytest.raises(L.SignedOut):
        L.Drive("R1", opener=google).update("F1", b"x")


def test_offline_is_a_plain_message():
    def offline(req):
        raise urllib.error.URLError("nodename nor servname provided")
    with pytest.raises(L.LinkError, match="Could not reach Google"):
        L._request("GET", "https://x", opener=offline)


def test_download_url():
    assert L.download_url("F1") == "https://drive.usercontent.google.com/download?id=F1&export=download&confirm=t"


def test_a_stray_or_idle_visit_does_not_stop_the_sign_in(google):
    import socket

    def browser(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        port = int(q["redirect_uri"].rsplit(":", 1)[1])

        def visit():
            idle = socket.create_connection(("127.0.0.1", port))  # a preconnect that never asks
            try:
                _direct(f"{q['redirect_uri']}/favicon.ico")
            except urllib.error.HTTPError:
                pass
            try:
                _direct(f"{q['redirect_uri']}/?" + urllib.parse.urlencode({"error": "x", "state": "wrong"}))
            except urllib.error.HTTPError:
                pass
            _direct(f"{q['redirect_uri']}/?" + urllib.parse.urlencode({"code": "C", "state": q["state"]}))
            idle.close()
        threading.Thread(target=visit, daemon=True).start()

    assert L.sign_in(browser, timeout_s=30, opener=google)["refresh_token"] == "R1"
