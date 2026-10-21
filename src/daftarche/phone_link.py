"""The phone connection, without Qt: Google sign-in, the phones' files on Google Drive, the
pairing link the QR code carries.

How it fits together (docs/phone-snapshot.md):

* The Mac signs in to Google once, asking only for ``drive.file``: Daftarche can see and change
  the files it made itself, nothing else in the Drive.
* Each phone has its own file there, ``Daftarche phone - <name>``, holding the snapshot sealed
  with that phone's own key (seal.py), and shared as "anyone with the link" so the phone can
  download it without signing in. Google holds only scrambled bytes.
* The QR code carries the pairing link ``daftarche://pair?v=1&f=<file id>&k=<key>&n=<name>``:
  the key goes from the Mac's screen to the phone's camera, never through Google.
* Disconnect deletes that phone's file: the phone then finds it gone and says so.

Only the standard library is used (urllib, http.server).
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

# The Google Cloud client of Daftarche ("Desktop app"). For an installed app these are not
# secrets: they ship inside it, and Google lets them sign in only with the person's consent
# and only to the files Daftarche itself made. $DAFTARCHE_GOOGLE_CLIENT (id:secret) overrides.
CLIENT_ID = "546519598762-kgdljm6r25f31299m0i018ii9u3h9b3t.apps.googleusercontent.com"
CLIENT_SECRET = "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"

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
FILES_URL = "https://www.googleapis.com/drive/v3/files"
SCOPES = "openid email https://www.googleapis.com/auth/drive.file"
TIMEOUT_S = 30

PAIR_SCHEME = "daftarche"
PAIR_HOST = "pair"
LINK_VERSION = "1"
PAIR_PAGE = "https://vahid-anari.github.io/pair/"
"""The QR code's link: any phone camera opens a web link. That page (docs/site/pair/) hands the
part after "#" on to the app as daftarche://pair?…; browsers never send that part to a server,
so the key does not reach GitHub either."""


class LinkError(Exception):
    """Something went wrong talking to Google (shown to the person as it is)."""


class SignedOut(LinkError):
    """Google no longer accepts the sign-in (revoked, or expired): sign in again."""


class FileGone(LinkError):
    """That phone's file is no longer on the Drive."""


def client():
    """(id, secret) of the Google client, or (None, None) when Daftarche has none."""
    override = os.environ.get("DAFTARCHE_GOOGLE_CLIENT", "")
    if ":" in override:
        cid, secret = override.split(":", 1)
        return cid, secret
    return (CLIENT_ID, CLIENT_SECRET) if CLIENT_ID else (None, None)


# ── the pairing link ─────────────────────────────────────────────────────────
def pairing_link(file_id, key_text, name):
    """The link in the QR code: the pairing page, with the pairing after "#"."""
    query = urllib.parse.urlencode({"v": LINK_VERSION, "f": file_id, "k": key_text, "n": name})
    return f"{PAIR_PAGE}#{query}"


def parse_pairing_link(text):
    """{file, key, name} from a pairing link, the page's or the app's own
    (daftarche://pair?…); None if it is not one."""
    text = (text or "").strip()
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return None
    if text.startswith(PAIR_PAGE + "#"):
        query = parts.fragment
    elif parts.scheme == PAIR_SCHEME and parts.netloc == PAIR_HOST:
        query = parts.query
    else:
        return None
    q = dict(urllib.parse.parse_qsl(query))
    if q.get("v") != LINK_VERSION:
        return None
    if not q.get("f") or not q.get("k"):
        return None
    return {"file": q["f"], "key": q["k"], "name": q.get("n", "")}


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _request(method, url, data=None, headers=None, opener=None):
    """(status, body bytes). Raises LinkError when offline, with Google's own message otherwise."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    urlopen = opener or (lambda r: urllib.request.urlopen(r, timeout=TIMEOUT_S, context=_context()))
    try:
        with urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return exc.code, body
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise LinkError(f"Could not reach Google: {reason}") from exc


def _message(body):
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return (body or b"")[:200].decode("utf-8", "replace")
    err = data.get("error")
    if isinstance(err, dict):
        return err.get("message") or json.dumps(err)
    return data.get("error_description") or err or ""


# ── signing in ───────────────────────────────────────────────────────────────
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class _CatchCode(http.server.BaseHTTPRequestHandler):
    timeout = 5  # an idle connection (a browser's preconnect) never holds up the sign-in

    def do_GET(self):  # noqa: N802 (http.server's name)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        if query.get("state") != self.server.state or ("code" not in query and "error" not in query):
            self.send_response(404)  # not Google's answer to this sign-in (a favicon, a stray visit)
            self.end_headers()
            return
        self.server.result = query
        ok = "code" in query
        page = ("<h2>Daftarche is connected to your Google Drive.</h2><p>You can close this tab.</p>" if ok else
                "<h2>Daftarche was not connected.</h2><p>You can close this tab and try again.</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body style='font-family:sans-serif;margin:3em'>{page}</body></html>".encode())

    def log_message(self, *args):  # quiet
        pass


def sign_in(open_browser, timeout_s=300, opener=None, cancelled=lambda: False):
    """Google's sign-in in the browser (``open_browser(url)``), answered on this Mac at
    127.0.0.1. Returns {refresh_token, email}. Blocks until done: call it off the main thread."""
    cid, secret = client()
    if not cid:
        raise LinkError("This copy of Daftarche has no Google client set up.")
    server = http.server.HTTPServer(("127.0.0.1", 0), _CatchCode)
    server.result = None
    server.timeout = 0.5
    redirect = f"http://127.0.0.1:{server.server_address[1]}"
    verifier = _b64(secrets.token_bytes(48))
    state = secrets.token_urlsafe(16)
    server.state = state
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        "state": state, "access_type": "offline", "prompt": "consent"})
    try:
        open_browser(url)
        end = time.monotonic() + timeout_s
        while server.result is None:
            if cancelled() or time.monotonic() > end:
                raise LinkError("Signing in was not finished.")
            server.handle_request()
    finally:
        server.server_close()
    result = server.result
    if "code" not in result:
        raise LinkError("Google sign-in was cancelled." if result.get("error") == "access_denied"
                        else f"Google said: {result.get('error')}")
    status, body = _request("POST", TOKEN_URL, urllib.parse.urlencode({
        "code": result["code"], "client_id": cid, "client_secret": secret, "redirect_uri": redirect,
        "grant_type": "authorization_code", "code_verifier": verifier}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"}, opener)
    if status != 200:
        raise LinkError(f"Google did not accept the sign-in: {_message(body)}")
    tokens = json.loads(body)
    if not tokens.get("refresh_token"):
        raise LinkError("Google gave no lasting sign-in: try again.")
    if "drive.file" not in tokens.get("scope", "drive.file"):
        raise LinkError("Daftarche needs the Google Drive permission: tick it when signing in.")
    return {"refresh_token": tokens["refresh_token"], "email": _email(tokens.get("id_token"))}


def _email(id_token):
    """The account's address from the sign-in's ID token (shown, never trusted for anything)."""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("email", "")
    except (AttributeError, IndexError, ValueError):
        return ""


def sign_out(refresh_token, opener=None):
    """Tell Google to forget the sign-in (quietly: it is forgotten here anyway)."""
    try:
        _request("POST", REVOKE_URL, urllib.parse.urlencode({"token": refresh_token}).encode(),
                 {"Content-Type": "application/x-www-form-urlencoded"}, opener)
    except LinkError:
        pass


# ── the Drive ────────────────────────────────────────────────────────────────
class Drive:
    """The phones' files on the signed-in Google Drive."""

    def __init__(self, refresh_token, opener=None):
        self.refresh_token = refresh_token
        self.opener = opener
        self._access, self._until = None, 0.0

    def _token(self):
        if self._access and time.monotonic() < self._until:
            return self._access
        cid, secret = client()
        status, body = _request("POST", TOKEN_URL, urllib.parse.urlencode({
            "client_id": cid, "client_secret": secret, "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"}).encode(), {"Content-Type": "application/x-www-form-urlencoded"},
            self.opener)
        if status in (400, 401) and b"invalid_grant" in body:
            raise SignedOut("Google no longer accepts Daftarche's sign-in: sign in again in Settings.")
        if status != 200:
            raise LinkError(f"Google: {_message(body)}")
        data = json.loads(body)
        self._access = data["access_token"]
        self._until = time.monotonic() + max(int(data.get("expires_in", 3600)) - 120, 60)
        return self._access

    def _call(self, method, url, data=None, headers=None, ok=(200,)):
        for attempt in (1, 2):
            status, body = _request(method, url, data, {"Authorization": f"Bearer {self._token()}",
                                                        **(headers or {})}, self.opener)
            if status == 401 and attempt == 1:  # the access token ran out early: once more
                self._access = None
                continue
            break
        if status == 404:
            raise FileGone("That phone's file is no longer on the Drive.")
        if status not in ok:
            raise LinkError(f"Google Drive: {_message(body) or status}")
        return json.loads(body) if body else {}

    def create(self, name, data):
        """A new file for a phone, readable by anyone with its link; its id."""
        boundary = "daftarche" + secrets.token_hex(8)
        meta = json.dumps({"name": name, "mimeType": "application/octet-stream",
                           "appProperties": {"daftarche": "phone"}}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
                f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode() + data +
                f"\r\n--{boundary}--\r\n".encode())
        file_id = self._call("POST", f"{UPLOAD_URL}?uploadType=multipart&fields=id", body,
                             {"Content-Type": f"multipart/related; boundary={boundary}"})["id"]
        try:
            self._call("POST", f"{FILES_URL}/{file_id}/permissions?fields=id",
                       json.dumps({"role": "reader", "type": "anyone"}).encode(),
                       {"Content-Type": "application/json"})
        except LinkError:
            self.delete(file_id)  # a file the phone cannot read is of no use
            raise
        return file_id

    def update(self, file_id, data):
        self._call("PATCH", f"{UPLOAD_URL}/{file_id}?uploadType=media&fields=id", data,
                   {"Content-Type": "application/octet-stream"})

    def delete(self, file_id):
        """Gone from the Drive (already gone is fine)."""
        try:
            self._call("DELETE", f"{FILES_URL}/{file_id}", ok=(200, 204))
        except FileGone:
            pass


def download_url(file_id):
    """Where the phone fetches its file, without signing in (shared as anyone with the link)."""
    return "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode(
        {"id": file_id, "export": "download", "confirm": "t"})
