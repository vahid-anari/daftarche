"""Phone 0.4.0: the shape shared by Vahid's phone apps (Dot Matrix, Daftarche, Spoolbook)."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")
ASSETS = Path(__file__).resolve().parents[1] / "src" / "assets"


def texts(control):
    """Every Text value inside a control."""
    found = []

    def walk(c):
        if isinstance(c, ft.Text) and c.value:
            found.append(c.value)
        for name in ("controls", "content", "label"):
            child = getattr(c, name, None)
            for x in (child if isinstance(child, list) else [child]):
                if isinstance(x, ft.Control):
                    walk(x)
    walk(control)
    return found


def test_settings_is_the_last_tab_and_not_a_button(app):
    phone, page, view = app
    labels = [d.label for d in page.navigation_bar.destinations]
    assert labels == ["Dashboard", "Transactions", "Charts", "Accounts", "Settings"]
    assert [a.icon for a in page.appbar.actions] == [ft.Icons.REFRESH]  # no ⚙
    assert page.appbar.title.controls[0].value == "Daftarche"
    settings = phone._pager.controls[-1]
    assert [t for t in texts(settings) if t in ("Connection", "Appearance", "Updates", "About")] == [
        "Connection", "Appearance", "Updates", "About"]
    assert "By Vahid Anari · MIT License" in texts(settings)


def test_back_from_settings_goes_to_the_dashboard(app):
    phone, page, view = app
    page.navigation_bar.update = lambda: None
    phone._swiped(SimpleNamespace(data="4", control=phone._pager))
    asyncio.run(phone._back(SimpleNamespace(control=view)))
    assert phone.tab == 0 and view.answers == [False]


def test_the_theme_choice_phone_light_dark_with_icons(app):
    phone, page, view = app
    seg = next(c for c in phone._pager.controls[-1].controls[1].controls if isinstance(c, ft.SegmentedButton))
    assert [(s.value, s.icon) for s in seg.segments] == [
        ("system", ft.Icons.SMARTPHONE), ("light", ft.Icons.LIGHT_MODE), ("dark", ft.Icons.DARK_MODE)]
    assert seg.show_selected_icon is False and seg.selected == ["system"]


def test_room_at_the_bottom_of_every_tab(app):
    phone, page, view = app
    assert all(tab.padding.bottom == 96 for tab in phone._pager.controls)


def test_toasts_float_for_three_seconds(app):
    phone, page, view = app
    phone._toast("Hello")
    bar = page.dialogs[-1]
    assert bar.behavior == ft.SnackBarBehavior.FLOATING and bar.duration == 3000


def test_the_font_is_ibm_plex_sans(app):
    phone, page, view = app
    assert page.fonts == {"Plex": "IBMPlexSans.ttf"} and page.theme.font_family == "Plex"
    assert (ASSETS / "IBMPlexSans.ttf").stat().st_size > 100_000
    assert "SIL Open Font License" in (ASSETS / "IBMPlexSans-OFL.txt").read_text()


def test_settings_without_a_connection(app):
    phone, page, view = app
    asyncio.run(phone._forget())
    phone.tab = 4
    phone.render()
    body = page.controls[-1].content
    assert "Not connected." in texts(body) and "Appearance" in texts(body)
