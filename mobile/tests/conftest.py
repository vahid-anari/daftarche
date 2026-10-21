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
    from daftarche.db import Database
    from daftarche.phone import write_snapshot
    from daftarche_phone.app import PhoneApp
    spec = importlib.util.spec_from_file_location("make_demo_db", REPO / "tools" / "make_demo_db.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    db = Database(str(demo.make_demo(tmp_path / "demo", months=6, today=date.today())))
    write_snapshot(db, tmp_path)
    db.conn.close()
    view = FakeView(controls=[], can_pop=True, on_confirm_pop=None, answers=[])
    page = FakePage(platform=ft.PagePlatform.MACOS, web=False, platform_brightness=ft.Brightness.DARK,
                    views=[view], controls=[], dialogs=[], navigation_bar=None, appbar=None)
    phone = PhoneApp(page)
    phone.prefs = SimpleNamespace(get=_async(None), set=_async(None))
    phone.folder = str(tmp_path)
    asyncio.run(phone.start())
    phone.folder = str(tmp_path)
    phone.load()
    phone.render()
    return phone, page, view


def _async(value):
    async def f(*a, **k):
        return value
    return f
