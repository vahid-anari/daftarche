"""Phone 0.2.1: Charts follow the period (a donut for one month), bars share the width, a tapped month."""

import asyncio
from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from daftarche_phone.charts import SPREAD, bar_chart, donut  # noqa: E402
from daftarche_phone.app import month_range, no_filters  # noqa: E402
from daftarche_phone.snapshot import MONTHS, custom_period  # noqa: E402

MONTHS_SHORT = [m[:3] for m in MONTHS]


def month_range_of(key):
    return month_range(key)
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
    phone.custom["Transactions"] = custom_period("month", "2026-09")
    assert phone._range("Transactions") == ("2026-09-01", "2026-09-30")
    phone._set_period("Transactions", phone.period["Transactions"])
    assert "Transactions" not in phone.custom and phone._range("Transactions") != ("2026-09-01", "2026-09-30")


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


def test_the_period_chips_stay_scrolled_where_they_were(app):
    phone, page, view = app
    phone.render()
    row = phone._periods("Dashboard")
    phone._set_period("Dashboard", "1 Year" if "1 Year" in [c.content.value for c in row.controls] else
                      row.controls[-2].content.value)  # the last period (Custom… is after it)
    again = phone._periods("Dashboard")
    assert again is row  # the same row, so it does not jump back to the left
    chosen = [c.content.value for c in again.controls if c.content.weight == ft.FontWeight.BOLD]
    assert chosen == [phone.period["Dashboard"]]


# ── 0.2.5: the Merchant filter, the account on its own line ──────────────────
def test_the_merchant_filter(app):
    from daftarche_phone.snapshot import NO_MERCHANT
    phone, page, view = app
    s = phone.snap
    merchant = s.merchants()[0]
    assert all(t["merchant"] == merchant for t in s.filter(merchant=merchant)) and s.filter(merchant=merchant)
    assert all(not t.get("merchant") for t in s.filter(merchant=NO_MERCHANT))
    phone._open_filters()
    assert "Merchant" in _texts(phone._pager.controls[1])  # a row of the "Show only" page
    phone._open_list("merchant")
    assert merchant in _texts(phone._pager.controls[1])
    phone._toggle_choice("merchant", merchant)
    assert phone.tx_filters["merchant"] == {merchant}
    phone._clear_filter("merchant")
    assert phone.tx_filters["merchant"] == set()


def test_the_account_has_a_line_of_its_own(app):
    phone, page, view = app
    tx = next(t for t in phone.snap.transactions if t["type"] == "Expense")
    texts = [c.value for c in _walk(phone._tx_row(tx)) if isinstance(c, ft.Text)]
    name = phone.snap.account_name(tx["account"])
    assert name in texts and not any("·" in t and name in t for t in texts)


# ── 0.3.1: accounts folded, Expense | Income on the Dashboard, the Accounts list in its card ─
def _texts(control):
    return [c.value for c in _walk(control) if isinstance(c, ft.Text)]


def test_the_dashboards_accounts_start_folded_and_open_on_a_tap(app):
    phone, page, view = app
    phone.render()
    name = phone.snap.accounts[0]["name"]
    assert "Total Balance" in _texts(phone._pager.controls[0]) and name not in _texts(phone._pager.controls[0])
    phone._toggle_accounts()
    assert phone.accounts_open and name in _texts(phone._pager.controls[0])
    phone._toggle_accounts()
    assert name not in _texts(phone._pager.controls[0])


def test_the_dashboard_switches_to_income(app):
    phone, page, view = app
    phone._set_period("Dashboard", "Last Month")
    assert any(t.startswith("Expense in ") for t in _texts(phone._pager.controls[0]))
    phone._set_dash_kind("Income")
    texts = _texts(phone._pager.controls[0])
    assert any(t.startswith("Income in ") for t in texts) and "Income by Category" in texts
    phone._set_period("Dashboard", "6 Months")  # the bars: the switch moves to the list's title
    texts = _texts(phone._pager.controls[0])
    assert "Income vs Expense" in texts and "Income by Category" in texts


def test_the_accounts_list_is_in_the_chart_card(app):
    phone, page, view = app
    phone.period["Accounts"] = "6 Months"
    phone.tab = 3
    phone.render()
    page_ = phone._pager.controls[3]
    shown = phone.snap.shown_accounts()
    cards = [c for c in page_.controls if isinstance(c, ft.Container) and c.on_click is not None]
    assert cards == []  # no separate account cards any more
    rows = [c for c in _walk(page_) if isinstance(c, ft.Container) and c.on_click is not None]
    assert len(rows) >= len(shown)
    texts = _texts(page_)
    assert all(a["name"] in texts for a in shown) and any(t.endswith("in this period") for t in texts)
    page.navigation_bar.update = lambda: None
    rows[-1].on_click(None)  # the last row: an account → its transactions
    assert phone.tab == 1 and phone.tx_filters["account"]


def test_a_merchants_logo_is_the_rows_mark(app):
    """0.5.0: a transaction row shows the merchant's logo, on white, in place of the emoji."""
    import base64
    import flet as ft
    phone, page, view = app
    tx = next(t for t in phone.snap.transactions if t.get("merchant") and not t.get("parts"))
    plain = phone._tx_row(tx).content.controls[0]
    assert not isinstance(plain.content, ft.Image)
    phone.snap._images["logo:" + tx["merchant"].casefold()] = base64.b64encode(b"\x89PNG logo").decode()
    mark = phone._tx_row(tx).content.controls[0]
    assert isinstance(mark.content, ft.Image) and mark.content.src == b"\x89PNG logo" and mark.bgcolor == "#ffffff"


def test_a_split_row_and_the_category_list_with_pictures(app):
    """A split row: the merchant's logo, else ✂️ (not a category's picture); a category with a
    picture shows it before its name in the list."""
    import base64
    import flet as ft
    phone, page, view = app
    split = next((t for t in phone.snap.transactions if t.get("parts")), None)
    if split is not None:
        mark = phone._tx_row(split).content.controls[0]
        assert not isinstance(mark.content, ft.Image)
    cat = next(c for c in phone.snap.categories if c.get("type") == "Expense")
    cat["image"] = "pic:7"
    phone.snap._images["pic:7"] = base64.b64encode(b"\x89PNG pic").decode()
    assert phone.snap.category_image(cat["id"]) == b"\x89PNG pic"


# ── 0.6.0: heads that stay, totals, the "Show only" page, Custom… ────────────
def test_the_heads_stay_and_the_lists_keep_their_place(app):
    phone, page, view = app
    phone.render()
    frames = [phone._pager.controls[i] for i in range(4)]
    assert all(f.data == "frame" for f in frames)
    lists = [f.controls[1] for f in frames]
    phone._set_period("Transactions", "Last Month")
    assert [phone._pager.controls[i].controls[1] for i in range(4)] == lists  # the same lists


def test_the_totals_and_their_refunds(app):
    phone, page, view = app
    phone.custom["Transactions"] = None
    txs = phone.snap.filter(*phone._range("Transactions"))
    texts = _texts(phone._transactions().controls[0])
    assert {"Income", "Expense", "Net"} <= set(texts)
    refunds = -sum(t["amount"] for t in txs if t["type"] == "Expense" and t["amount"] < 0)
    assert any(t.startswith("incl. ") for t in texts) == bool(refunds)


def test_the_show_only_page_and_back(app):
    phone, page, view = app
    phone.tab = 1
    phone.render()
    phone._open_filters()
    assert phone._pager.controls[1].data == "filters"
    phone._open_list("category")
    groceries = next(c["id"] for c in phone.snap.categories if c["name"] == "Groceries")
    sub = next(c for c in phone.snap.categories if c["id"] == groceries)["subcategories"][0]["id"]
    phone._toggle_choice("category", groceries)
    phone.tx_filters["subcategory"].add(sub)
    asyncio.run(phone._back(SimpleNamespace(control=view)))  # the list → the page
    assert phone.filter_view == "main" and view.answers == [False]
    asyncio.run(phone._back(SimpleNamespace(control=view)))  # the page → Transactions, choices kept
    assert phone.filter_view is None and phone.tab == 1 and phone.tx_filters["category"] == {groceries}
    assert phone._pager.controls[1].data == "frame"
    assert "Groceries" in _texts(phone._pager.controls[1])  # its chip
    phone._clear_filter("category", groceries)  # ✕: its sub-categories go with it
    assert phone.tx_filters["category"] == set() and phone.tx_filters["subcategory"] == set()


def test_a_tick_does_not_move_a_row(app):
    phone, page, view = app
    phone.period["Transactions"] = "6 Months"
    phone._open_filters()
    phone._open_list("merchant")

    def names():
        return [t for t in _texts(phone._flist) if t in phone.snap.merchants()]
    before = names()
    phone._toggle_choice("merchant", before[-1])
    assert names() == before and phone.tx_filters["merchant"] == {before[-1]}
    phone._filter_typed("merchant", before[0][:4])
    assert before[0] in names() and len(names()) < len(before)


def test_custom_months_step_and_stop(app):
    from datetime import date
    phone, page, view = app
    this = custom_period("month", date.today().strftime("%Y-%m"))
    phone._set_custom("Dashboard", this)
    chip = phone._periods("Dashboard").controls[0]
    left, label, right = chip.content.controls[:3]
    assert label.content.value == f"{MONTHS_SHORT[date.today().month - 1]} {date.today().year}"
    assert right.on_click is None and left.on_click is not None  # no month after this one
    left.on_click(None)
    assert phone.custom["Dashboard"]["start"] < this["start"]
    chip.content.controls[-1].on_click(None)  # ✕
    assert "Dashboard" not in phone.custom


def test_a_month_from_charts_is_a_custom_month_in_transactions(app):
    phone, page, view = app
    phone.tab = 2
    phone.period["Charts"] = "6 Months"
    months, _ = phone.snap.monthly_by_category("Expense", *phone._range("Charts"))
    phone._pick_month(months[0])
    category = phone.snap.by_category("Expense", *month_range_of(months[0]))[0][0]
    phone._show_category(category, "Expense")
    assert phone.custom["Transactions"]["mode"] == "month"
    assert phone._range("Transactions") == month_range_of(months[0])


def test_the_charts_take_several_accounts(app):
    phone, page, view = app
    a, b = (x["id"] for x in phone.snap.accounts[:2])
    phone._chart_accounts()
    phone._set_chart_accounts({a, b})
    assert "2 accounts" in _texts(phone._charts().controls[0])
    start, end = phone._range("Charts")
    both = dict(phone.snap.by_category("Expense", start, end, {a, b}))
    one = dict(phone.snap.by_category("Expense", start, end, a))
    assert sum(both.values()) >= sum(one.values())


def test_the_sheet_shows_the_mark_big_and_each_parts(app):
    phone, page, view = app
    tx = phone.snap.transactions[0]
    phone._tx_sheet(tx)
    marks = [c for c in _walk(page.dialogs[-1]) if isinstance(c, ft.Container) and c.width == 56]
    assert len(marks) == 1


def test_a_ticked_subcategory_stays_in_its_list(app):
    phone, page, view = app
    s = phone.snap
    phone.period["Transactions"] = "6 Months"
    groceries = next(c for c in s.categories if c["name"] == "Groceries")
    health = next(c for c in s.categories if c["name"] == "Health")
    sub = groceries["subcategories"][0]
    phone.tx_filters["subcategory"] = {sub["id"]}
    phone.tx_filters["category"] = {health["id"]}
    phone._open_filters()
    phone._open_list("subcategory")
    texts = _texts(phone._flist)
    assert "Groceries" in texts and sub["name"] in texts


def test_a_tapped_month_keeps_within_a_from_to(app):
    phone, page, view = app
    phone.tab = 2
    phone._set_custom("Charts", custom_period("range", ("2026-09-12", "2026-10-03")))
    phone._pick_month("2026-09")
    assert phone._chart_month_range() == ("2026-09-12", "2026-09-30")
    phone._show_category(phone.snap.categories[0]["id"], "Expense")
    assert phone.custom["Transactions"]["mode"] == "range"
    assert phone._range("Transactions") == ("2026-09-12", "2026-09-30")


def test_the_totals_of_a_category_count_its_parts_only(app):
    phone, page, view = app
    s = phone.snap
    split = {"id": -1, "date": "2026-09-15", "type": "Expense", "amount": 150.0, "account": s.accounts[0]["id"],
             "to_account": None, "category": None, "subcategory": None, "merchant": "Test", "name": None,
             "note": None, "tags": [],
             "parts": [{"amount": 100.0, "category": s.categories[0]["id"], "subcategory": None},
                       {"amount": 50.0, "category": s.categories[1]["id"], "subcategory": None}]}
    s.transactions.insert(0, split)
    phone._set_custom("Transactions", custom_period("range", ("2026-09-15", "2026-09-15")))
    phone.tx_filters = no_filters(category=s.categories[1]["id"], merchant="Test")
    texts = _texts(phone._transactions().controls[0])
    assert "-$50.00" in texts and "-$150.00" not in texts


def test_the_picker_closes_only_itself(app):
    phone, page, view = app
    phone._period_picker("Transactions")
    sheet = phone._picker_sheet
    sheet.update = lambda: None
    phone._pick_period("Transactions", custom_period("month", "2026-09"))
    assert sheet.open is False and phone.custom["Transactions"]["start"] == "2026-09-01"
    phone._period_picker("Transactions")  # opens again, on the month chosen
    assert phone._picker_open


# ── 0.6.1: a tapped month stays in view; a period at the end of its row shows ─
def test_the_bars_are_kept_while_a_month_is_tapped(app):
    phone, page, view = app
    holder = {}
    labels = [f"M{i}" for i in range(12)]  # more than SPREAD: a row that scrolls
    first = bar_chart(DARK, labels, [("#f00", [1] * 12)], holder=holder)
    bars = holder["bars"]
    bar_chart(DARK, labels, [("#f00", [2] * 12)], selected=3, holder=holder)
    assert holder["bars"] is bars and len(bars.controls) == 12 and first is not None
    bars.on_scroll(SimpleNamespace(pixels=140.0))
    assert holder["offset"] == 140.0
    phone._chart_bars = holder
    tasks = []
    page.run_task = lambda f, *a: tasks.append((f.__name__, a))
    months, _ = phone.snap.monthly_by_category("Expense", *phone._range("Charts"))
    phone._pick_month(months[0])
    assert ("_bars_back", (140.0,)) in tasks
    phone._set_period("Charts", "6 Months")
    assert phone._chart_bars == {}  # other months: a new row, at the newest


def test_a_period_at_the_end_of_its_row_is_scrolled_to(app):
    phone, page, view = app
    tasks = []
    page.run_task = lambda f, *a: tasks.append(f.__name__)
    phone.period["Accounts"] = "All"
    phone.render()
    assert "_show_chosen_periods" in tasks
    scrolled = []

    async def scroll_to(**kw):
        scrolled.append(kw)
    row = phone._period_rows["Accounts"]
    row.scroll_to = scroll_to
    for other in phone._period_rows.values():
        if other is not row:
            other.scroll_to = lambda **kw: asyncio.sleep(0)
    asyncio.run(phone._show_chosen_periods())
    assert {"offset": -1} in scrolled
