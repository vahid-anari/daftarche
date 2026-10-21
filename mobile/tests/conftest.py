"""The app's code is in src/; Daftarche itself (for the cross-checks) never sees your real data."""

import asyncio
import importlib.util
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ["DAFTARCHE_HOME"] = tempfile.mkdtemp(prefix="daftarche-phone-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO = Path(__file__).resolve().parents[2]


# ── the app on the demo data, with a pretend page (no phone needed) ─────────
class FakePage(SimpleNamespace):
    def update(self, *controls):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        pass

    def run_task(self, *a, **k):
        pass


class FakeView(SimpleNamespace):
    async def confirm_pop(self, should_pop):
        self.answers.append(should_pop)


@pytest.fixture
def app(tmp_path):
    pytest.importorskip("daftarche")
    ft = pytest.importorskip("flet")  # the app itself (an environment without Flet skips these)
    import json
    from daftarche.db import Database
    from daftarche.phone import build_snapshot
    from daftarche_phone import link
    from daftarche_phone.app import PhoneApp
    from daftarche_phone.seal import key_to_text, new_key, seal
    spec = importlib.util.spec_from_file_location("make_demo_db", REPO / "tools" / "make_demo_db.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    db = Database(str(demo.make_demo(tmp_path / "demo", months=6, today=date.today())))
    key = new_key()
    os.environ["DAFTARCHE_PHONE_DATA"] = str(tmp_path / "phone-data")
    link.save_cache(seal(json.dumps(build_snapshot(db)).encode(), key))  # as fetched from the Drive
    db.conn.close()
    view = FakeView(controls=[], can_pop=True, on_confirm_pop=None, answers=[])
    page = FakePage(platform=ft.PagePlatform.MACOS, web=False, route="/", platform_brightness=ft.Brightness.DARK,
                    views=[view], controls=[], dialogs=[], navigation_bar=None, appbar=None)
    phone = PhoneApp(page)
    pairing = json.dumps({"v": "1", "f": "F1", "k": key_to_text(key), "n": "Test phone"})
    phone.prefs = SimpleNamespace(get=_async_get({"pairing": pairing}), set=_async(None))
    asyncio.run(phone.start())
    phone.load()
    phone.render()
    return phone, page, view


def _async_get(values):
    async def f(key, *a, **k):
        return values.get(key)
    return f


def _async(value):
    async def f(*a, **k):
        return value
    return f
