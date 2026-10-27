"""Phone 0.2.0: Back goes back a step, swiping changes tabs, sheets stay above Android's buttons."""

import asyncio
from types import SimpleNamespace

import pytest

from daftarche_phone.nav import ASK_EXIT, DASHBOARD, EXIT, EXIT_WINDOW, RESTORE, BackSteps


# ── the rules ────────────────────────────────────────────────────────────────
def test_back_undoes_jumps_then_goes_to_the_dashboard_then_asks_before_leaving():
    nav = BackSteps()
    nav.jumped({"tab": 2, "open_category": 7})
    assert nav.back(1, 0.0) == (RESTORE, {"tab": 2, "open_category": 7})
    assert nav.back(2, 1.0) == (DASHBOARD, None)
    assert nav.back(0, 2.0) == (ASK_EXIT, None)
    assert nav.back(0, 2.0 + EXIT_WINDOW) == (EXIT, None)


def test_a_slow_second_back_asks_again():
    nav = BackSteps()
    assert nav.back(0, 0.0) == (ASK_EXIT, None)
    assert nav.back(0, EXIT_WINDOW + 0.5) == (ASK_EXIT, None)  # too late: asked again
    assert nav.back(0, EXIT_WINDOW + 1.0) == (EXIT, None)


def test_jumps_undo_in_reverse_order():
    nav = BackSteps()
    nav.jumped({"tab": 3})
    nav.jumped({"tab": 1, "tx_filters": {"account": 2}})
    assert nav.back(1, 0)[1] == {"tab": 1, "tx_filters": {"account": 2}}
    assert nav.back(1, 0)[1] == {"tab": 3}
    assert nav.depth == 0


def test_choosing_a_tab_forgets_the_jumps():
    nav = BackSteps()
    nav.jumped({"tab": 2})
    nav.tab_chosen()
    assert nav.back(3, 0) == (DASHBOARD, None)


def test_a_jump_cancels_a_pending_exit_question():
    nav = BackSteps()
    assert nav.back(0, 0.0) == (ASK_EXIT, None)
    nav.jumped({"tab": 0})
    assert nav.back(1, 0.5)[0] == RESTORE
    assert nav.back(0, 1.0) == (ASK_EXIT, None)  # asked afresh, not leaving


def test_the_app_takes_back_from_android(app):
    phone, page, view = app
    assert view.can_pop is False and view.on_confirm_pop == phone._back


def test_back_from_show_transactions_returns_to_the_open_category(app):
    phone, page, view = app
    phone.tab = 2
    phone.render()
    kind = phone.chart_kind
    category = phone.snap.by_category(kind, *phone._range("Charts"))[0][0]
    phone._toggle_category(category)
    phone._show_category(category, kind)
    assert phone.tab == 1 and phone.tx_filters["category"] == category
    asyncio.run(phone._back(SimpleNamespace(control=view)))
    assert view.answers == [False]  # stays in the app
    assert phone.tab == 2 and phone.open_category == category and phone.tx_filters["category"] is None
    asyncio.run(phone._back(SimpleNamespace(control=view)))
    assert phone.tab == 0  # then the Dashboard
    asyncio.run(phone._back(SimpleNamespace(control=view)))
    assert page.dialogs[-1].content.value == "Press Back again to exit"
    asyncio.run(phone._back(SimpleNamespace(control=view)))
    assert view.answers[-1] is True  # leaves


def test_swiping_changes_the_tab_and_the_bar_follows(app):
    phone, page, view = app
    page.navigation_bar.update = lambda: None
    phone._jump()
    phone._swiped(SimpleNamespace(data="3", control=phone._pager))
    assert phone.tab == 3 and page.navigation_bar.selected_index == 3 and phone.nav.depth == 0
    assert len(phone._pager.controls) == 5 and phone._pager.selected_index == 0  # built once, not again


def test_sheets_keep_clear_of_androids_buttons(app):
    import flet as ft  # there: the fixture needs it
    phone, page, view = app
    phone._filter_sheet(None)
    phone._tx_sheet(phone.snap.transactions[0])
    for sheet in page.dialogs:
        area = sheet.content
        assert isinstance(area, ft.SafeArea)
        assert area.avoid_intrusions_bottom and not area.avoid_intrusions_top


def test_androids_bars_take_the_apps_colours():
    ft = pytest.importorskip("flet")
    from daftarche_phone.theme import DARK, LIGHT, material_theme
    dark, light = material_theme(DARK).system_overlay_style, material_theme(LIGHT).system_overlay_style
    assert dark.system_navigation_bar_color == DARK.surface
    assert dark.system_navigation_bar_icon_brightness == ft.Brightness.LIGHT
    assert light.system_navigation_bar_color == LIGHT.surface
    assert light.system_navigation_bar_icon_brightness == ft.Brightness.DARK
