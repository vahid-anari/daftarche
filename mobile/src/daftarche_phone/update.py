"""Is there a newer phone app? (GitHub releases tagged ``phone-vX.Y.Z``; no Flet here.)

The phone app is released from the Daftarche repository with tags of its own, ``phone-v0.2.0``,
each carrying the signed APK. The desktop releases (``v0.26.0``) are left alone.
"""

from __future__ import annotations

import json
import ssl
import urllib.request

REPO = "vahid-anari/daftarche"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases?per_page=50"
TAG_PREFIX = "phone-v"
TIMEOUT_S = 8


def parse_version(text):
    """``"0.2.10"`` → ``(0, 2, 10)``; ``()`` for anything else."""
    try:
        return tuple(int(p) for p in text.strip().split("."))
    except ValueError:
        return ()


def newest_release(releases, current):
    """The newest phone release after ``current`` as ``{version, notes, apk, page}``, else ``None``.

    Drafts and releases without an APK are skipped.
    """
    best, best_v = None, parse_version(current)
    for rel in releases if isinstance(releases, list) else []:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        tag = str(rel.get("tag_name") or "")
        if not tag.startswith(TAG_PREFIX):
            continue
        version = tag[len(TAG_PREFIX):]
        v = parse_version(version)
        apk = next((a.get("browser_download_url") for a in rel.get("assets") or []
                    if str(a.get("name", "")).endswith(".apk")), None)
        if v and v > best_v and apk:
            best, best_v = {"version": version, "notes": str(rel.get("body") or "").strip(), "apk": apk,
                            "page": rel.get("html_url") or f"https://github.com/{REPO}/releases"}, v
    return best


def _context():
    """Certificates from certifi when it is there (Python on a phone has no system store)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def check(current):
    """The newest phone release after ``current``, or ``None``. Raises ``OSError`` when offline."""
    request = urllib.request.Request(RELEASES_API, headers={"User-Agent": f"daftarche-phone/{current}",
                                                            "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=_context()) as response:
        data = json.loads(response.read().decode("utf-8"))
    return newest_release(data, current)
