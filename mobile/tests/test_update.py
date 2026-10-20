"""The phone app finds its own releases (``phone-vX.Y.Z`` with an APK), not the desktop ones."""

import re
from pathlib import Path

import daftarche_phone
from daftarche_phone.update import newest_release, parse_version


def release(tag, apk=True, draft=False, body="notes"):
    assets = [{"name": f"daftarche-{tag}.apk", "browser_download_url": f"https://x/{tag}.apk"}] if apk else []
    return {"tag_name": tag, "draft": draft, "body": body, "assets": assets, "html_url": f"https://x/{tag}"}


def test_the_newest_phone_release():
    releases = [release("v0.30.0"), release("phone-v0.3.0", draft=True), release("phone-v0.2.10"),
                release("phone-v0.2.9"), release("phone-v0.4.0", apk=False), release("phone-v0.1.0")]
    found = newest_release(releases, "0.1.0")
    assert (found["version"], found["apk"], found["notes"]) == ("0.2.10", "https://x/phone-v0.2.10.apk", "notes")
    assert newest_release(releases, "0.2.10") is None
    assert newest_release({"message": "rate limited"}, "0.1.0") is None


def test_versions():
    assert parse_version("0.2.10") > parse_version("0.2.9")
    assert parse_version("0.2.0-beta") == ()


def test_one_version_number():
    """pyproject.toml (the APK's version) and the app's own (what it compares) are the same."""
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert re.search(r'^version = "([^"]+)"', text, re.M).group(1) == daftarche_phone.__version__
