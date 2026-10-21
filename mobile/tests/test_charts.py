"""Phone 0.2.1: Charts follow the period (a donut for one month), bars share the width, a tapped month."""

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from daftarche_phone.charts import SPREAD, bar_chart, donut  # noqa: E402
from daftarche_phone.theme import DARK  # noqa: E402


def _walk(control):
    """Every control inside ``control`` (its own content, controls and the like)."""
    yield control
    for name in ("content", "controls", "shapes"):
        inner = getattr(control, name, None)
        for child in inner if isinstance(inner, list) else [inner] if inner is not None else []:
            if isinstance(child, ft.BaseControl):
                yield from _walk(child)


def _bars(chart):
    return chart.controls[1].content


# ── the drawings ─────────────────────────────────────────────────────────────
def test_a_few_months_share_the_width():
    chart = bar_chart(DARK, ["Aug 26", "Sep 26", "Oct 26"], [("#111111", [1, 2, 3])], stacked=True)
    bars = _bars(chart)
    assert isinstance(bars, ft.Row) and [c.expand for c in bars.controls] == [1, 1, 1]


def test_many_months_scroll_and_open_at_the_newest():
    labels = [f"M{i}" for i in range(SPREAD + 4)]
    chart = bar_chart(DARK, labels, [("#111111", list(range(len(labels))))], stacked=True)
    bars = _bars(chart)
    assert isinstance(bars, ft.ListView) and bars.horizontal and bars.reverse
    first = bars.controls[0]  # shown first, at the right: the newest month
    assert any(isinstance(c, ft.Text) and c.value == labels[-1] for c in _walk(first))


def test_a_tapped_month_stays_bright_and_the_rest_dim():
    tapped = []
    chart = bar_chart(DARK, ["Aug 26", "Sep 26"], [("#111111", [1, 2])], stacked=True, selected=1,
                      on_tap=tapped.append)
    first, second = _bars(chart).controls
    assert (first.opacity, second.opacity) == (0.35, 1.0)
    first.on_click(None)
    assert tapped == [0]


def test_the_donut_draws_each_slice_above_zero():
    ring = donut(DARK, [("#111111", 30), ("#222222", 10), ("#333333", -5)], "$40.00", "3 categories")
    arcs = [c for c in _walk(ring) if type(c).__name__ == "Arc"]
    assert len(arcs) == 2 and arcs[0].sweep_angle > arcs[1].sweep_angle  # 30 is three times 10
    texts = [c.value for c in _walk(ring) if isinstance(c, ft.Text)]
    assert "$40.00" in texts and "3 categories" in texts
    assert isinstance(donut(DARK, [("#111111", -5)], "", ""), ft.Text)  # nothing to draw


# ── the Charts tab ───────────────────────────────────────────────────────────
def _charts(phone):
    phone.tab = 2
    phone.render()
    return list(_walk(phone._pager.controls[2]))


def test_one_month_shows_a_donut(app):
    phone, page, view = app
    phone.period["Charts"] = "Last Month"
    controls = _charts(phone)
    assert any(type(c).__name__ == "Arc" for c in controls)
    assert any(isinstance(c, ft.Text) and c.value.startswith("Expense in ") for c in controls)


def test_a_tapped_month_shows_its_categories_and_its_transactions(app):
    phone, page, view = app
    phone.period["Charts"] = "6 Months"
    _charts(phone)
    months, _ = phone.snap.monthly_by_category("Expense", *phone._range("Charts"))
    month = months[-2]
    phone._pick_month(month)
    controls = _charts(phone)
    label = next(c for c in controls if isinstance(c, ft.Text) and c.value.endswith("✕"))
    from daftarche_phone.app import long_month, month_range
    assert label.value.startswith(long_month(month))
    start, end = month_range(month)
    category = phone.snap.by_category("Expense", start, end)[0][0]
    phone._show_category(category, "Expense")
    assert phone.tab == 1 and phone._range("Transactions") == (start, end)
    asyncio.run(phone._back(SimpleNamespace(control=view)))
    assert phone.tab == 2 and phone.chart_month == month  # Back: the same month still tapped
    phone._pick_month(month)  # tapped again: the whole period
    assert phone.chart_month is None


def test_a_new_period_forgets_the_tapped_month(app):
    phone, page, view = app
    phone.period["Charts"] = "6 Months"
    months, _ = phone.snap.monthly_by_category("Expense", *phone._range("Charts"))
    phone._pick_month(months[0])
    phone._set_period("Charts", "3 Months")
    assert phone.chart_month is None


def test_the_month_chip_in_transactions_goes_back_to_the_period(app):
    phone, page, view = app
    phone.tx_range = ("2026-09-01", "2026-09-30", "Sep 26")
    phone._set_period("Transactions", phone.period["Transactions"])
    assert phone.tx_range is None and phone._range("Transactions") != ("2026-09-01", "2026-09-30")


# ── 0.2.2: the Dashboard's month, and staying where you were ─────────────────
def test_the_dashboard_shows_a_donut_for_one_month(app):
    phone, page, view = app
    phone.render()
    phone._set_period("Dashboard", "Last Month")
    controls = list(_walk(phone._pager.controls[0]))
    assert any(type(c).__name__ == "Arc" for c in controls)
    assert any(isinstance(c, ft.Text) and c.value.startswith("Expense in ") for c in controls)
    phone._set_period("Dashboard", "6 Months")
    controls = list(_walk(phone._pager.controls[0]))
    assert not any(type(c).__name__ == "Arc" for c in controls)
    assert any(isinstance(c, ft.Text) and c.value == "Income vs Expense" for c in controls)


def test_a_choice_inside_a_tab_keeps_its_list_where_it_was(app):
    phone, page, view = app
    phone.render()
    lists = list(phone._pager.controls)
    phone._set_period("Dashboard", "This Month")
    phone._set_period("Charts", "3 Months")
    phone._more(None)
    assert all(a is b for a, b in zip(lists, phone._pager.controls))  # the same lists: not back at the top
