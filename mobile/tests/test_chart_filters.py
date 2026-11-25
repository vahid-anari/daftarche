"""Phone 0.8.0: Charts' own "Show only" filters, and one category shown by its sub-categories."""

from types import SimpleNamespace

import pytest

ft = pytest.importorskip("flet")

from daftarche_phone.app import TABS  # noqa: E402


def _category(snap, name):
    return next(c for c in snap.category if snap.category_name(c) == name)


def _chart_sum(phone):
    start, end = phone._range("Charts")
    return round(sum(v for _, v in phone.snap.by_category(phone.chart_kind, start, end,
                                                           **phone._chart_chosen())), 2)


def test_charts_filters_are_their_own(app):
    phone, page, view = app
    g = _category(phone.snap, "Groceries")
    phone._open_filters(owner="Charts")
    phone._open_list("category", "Charts")
    phone._toggle_choice("category", g, "Charts")
    assert phone.chart_filters["category"] == {g} and phone.tx_filters["category"] == set()
    assert phone.filter_view is None  # Transactions' page is not opened


def test_one_category_shows_its_subcategories_and_sums_to_it(app):
    phone, page, view = app
    s = phone.snap
    g = _category(s, "Groceries")
    start, end = phone._range("Charts")
    whole = dict(s.by_category("Expense", start, end))[g]
    phone.chart_filters["category"] = {g}
    rows = s.by_category("Expense", start, end, by="subcategory", **phone._chart_chosen())
    assert all(s.sub_category.get(sub) == g for sub, _ in rows if sub is not None)
    assert round(sum(v for _, v in rows), 2) == whole
    assert "Monthly Expense  ·  Groceries" in str([c.value for c in _texts(phone._charts())])


def _texts(control):
    out = []
    stack = [control]
    while stack:
        c = stack.pop()
        if isinstance(c, ft.Text):
            out.append(c)
        for name in ("content", "controls"):
            inner = getattr(c, name, None)
            stack += inner if isinstance(inner, list) else [inner] if isinstance(inner, ft.BaseControl) else []
    return out


def test_a_sub_category_row_opens_its_transactions_with_the_same_total(app):
    phone, page, view = app
    s = phone.snap
    g = _category(s, "Groceries")
    phone.tab = 2
    phone.chart_filters["category"] = {g}
    start, end = phone._range("Charts")
    sub, total = s.by_category("Expense", start, end, by="subcategory", **phone._chart_chosen())[0]
    phone._show_category(g, "Expense", subcategory=sub)
    assert phone.tab == 1 and phone.tx_filters["subcategory"] == {sub}
    t0, t1 = phone._range("Transactions")
    f = phone.tx_filters
    line_ok = s.line_test(f["category"], f["subcategory"], f["tag"])
    shown = sum(line.amount for line in s.lines(s.filter(t0, t1, **phone._chosen())) if line_ok(line))
    assert round(shown, 2) == total


def test_show_transactions_takes_the_charts_filters(app):
    phone, page, view = app
    s = phone.snap
    a = s.accounts[0]["id"]
    phone.tab = 2
    phone.chart_filters["account"] = {a}
    start, end = phone._range("Charts")
    category, total = s.by_category("Expense", start, end, **phone._chart_chosen())[0]
    phone._show_category(category, "Expense")
    assert phone.tx_filters["account"] == {a} and phone.tx_filters["category"] == {category}
    t0, t1 = phone._range("Transactions")
    f = phone.tx_filters
    line_ok = s.line_test(f["category"], f["subcategory"], f["tag"])
    assert round(sum(l.amount for l in s.lines(s.filter(t0, t1, **phone._chosen())) if line_ok(l)), 2) == total


def test_income_drops_expense_categories(app):
    phone, page, view = app
    g = _category(phone.snap, "Groceries")
    phone.chart_filters["category"] = {g}
    phone._set_chart_kind(SimpleNamespace(control=SimpleNamespace(selected=["Income"])))
    assert phone.chart_filters["category"] == set() and _chart_sum(phone) > 0


def test_back_leaves_the_charts_filter_page_a_step_at_a_time(app):
    import asyncio
    phone, page, view = app
    phone.tab = 2
    assert TABS[2][0] == "Charts"
    phone._open_filters(owner="Charts")
    phone._open_list("merchant", "Charts")
    e = SimpleNamespace(control=view)
    asyncio.run(phone._back(e))
    assert phone._fstate["Charts"]["view"] == "main"
    asyncio.run(phone._back(e))
    assert phone._fstate["Charts"]["view"] is None and phone.tab == 2 and view.answers == [False, False]


def test_charts_filters_leave_transactions_show_more_alone(app):
    phone, page, view = app
    phone.tx_limit = 300
    a = phone.snap.accounts[0]["id"]
    phone._open_filters(owner="Charts")
    phone._open_list("account", "Charts")
    phone._toggle_choice("account", a, "Charts")
    phone._filter_up("Charts")
    phone._close_filters("Charts")
    phone._clear_filter("account", a, "Charts")
    assert phone.tx_limit == 300
