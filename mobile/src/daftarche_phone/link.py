"""The phone's side of the connection (no Flet here).

Daftarche on the Mac keeps this phone's copy of your data in a file of its own on the Mac's
Google Drive, sealed with this phone's key (seal.py). The QR code on the Mac gives the phone
the file's id and the key (``daftarche://pair?v=1&f=…&k=…&n=…``); the phone then downloads the
file by its link, without signing in to Google, and opens it with the key. A file that is
gone means the phone was disconnected on the Mac.
"""

from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .seal import SealError, is_sealed, key_from_text, open_sealed

TIMEOUT_S = 30
PAIR_PAGE = "https://vahid-anari.github.io/pair/"  # the QR code's web link; it opens the app
CACHE_NAME = "daftarche-phone.sealed"


class Disconnected(Exception):
    """The Mac disconnected this phone (its file is gone)."""


class FetchError(Exception):
    """Could not get the newest data now (offline, Google busy): the copy kept is shown."""


def parse_pairing(text):
    """{file, key, name} from the pairing link: the QR code's web link (pasted), the app's own
    link, or the route it becomes ("/?v=1&f=…"); None if it is not one (or its key is not readable)."""
    text = (text or "").strip()
    if text.startswith(PAIR_PAGE + "#"):  # the web link of the QR code, pasted
        rest = text.split("#", 1)[1]
    elif "?" in text and text.split("?", 1)[0].lower().rstrip("/") in ("daftarche://pair", ""):
        rest = text.split("?", 1)[1]  # the app's own link, or the route it becomes ("/?…")
    else:
        return None
    query = dict(urllib.parse.parse_qsl(rest))
    if query.get("v") != "1" or not query.get("f") or not query.get("k"):
        return None
    try:
        key_from_text(query["k"])
    except SealError:
        return None
    return {"file": query["f"], "key": query["k"], "name": query.get("n", "")}


def download_url(file_id):
    return "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode(
        {"id": file_id, "export": "download", "confirm": "t"})


def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(file_id, opener=None):
    """The sealed file, as Google gives it to anyone with its link."""
    req = urllib.request.Request(download_url(file_id), headers={"User-Agent": "daftarche-phone"})
    urlopen = opener or (lambda r: urllib.request.urlopen(r, timeout=TIMEOUT_S, context=_context()))
    try:
        with urlopen(req) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Disconnected("This phone was disconnected on the Mac.") from exc
        raise FetchError(f"Google Drive answered {exc.code}.") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise FetchError(f"No connection: {getattr(exc, 'reason', exc)}") from exc
    if not is_sealed(blob):
        raise FetchError("Google Drive did not give the file (try again later).")
    return blob


def open_blob(blob, key_text):
    """The snapshot's JSON bytes; SealError if the key does not fit."""
    return open_sealed(blob, key_from_text(key_text))


def cache_path():
    """Where the last copy waits, still sealed, for opening without a connection."""
    folder = os.environ.get("FLET_APP_STORAGE_DATA") or os.environ.get("DAFTARCHE_PHONE_DATA") or \
        str(Path.home() / ".daftarche-phone")
    Path(folder).mkdir(parents=True, exist_ok=True)
    return Path(folder) / CACHE_NAME


def save_cache(blob):
    path = cache_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)


def load_cache():
    try:
        return cache_path().read_bytes()
    except OSError:
        return None


def forget_cache():
    try:
        cache_path().unlink()
    except OSError:
        pass
