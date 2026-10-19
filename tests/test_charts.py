"""Charts tab: the chart choices follow the range (one month or several)."""

import datetime

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def charts(qapp, db):
    from daftarche.db import MONTHS_ORDER
    from daftarche.tabs.charts import ChartsTab

    food = _category(db, "Food")
    rent = _category(db, "Rent")
    today = datetime.date.today()
    last = today.replace(day=1) - datetime.timedelta(days=1)
    for d, cat, amount in ((today, food, 120), (today, rent, 900), (last, food, 80), (last, rent, 900)):
        sub = db.uncategorized_subcategory(cat)["id"]
        db.add_transaction(d.year, MONTHS_ORDER[d.month - 1], 1, "Expense", "Vahid-CIBC-Checking", amount, sub, cat)
    yield keep(ChartsTab(db))


def _category(db, name):
    db.add_category(name, "Expense")
    return db.get_category_by_name(name, type_name="Expense")["id"]


def _choices(tab):
    return [tab.f_chart_type.itemText(i) for i in range(tab.f_chart_type.count())]


def test_one_month_offers_donut_and_bars(charts):
    charts._period._select_preset(3)  # 3 Months
    assert _choices(charts) == ["Line", "Spline", "Grouped Bars", "Stacked Bars", "Donut"]
    assert charts._current_chart_type == "Line"
    charts._period._select_preset(1)  # This Month
    assert _choices(charts) == ["Donut", "Bars", "Stacked Bars"]
    assert charts.f_chart_type.currentText() == "Donut"
    assert charts._current_chart_type == "Donut"
    assert not charts.chk_custom_y.isEnabled()


def test_each_chart_draws_for_one_month(charts):
    charts._period._select_preset(1)
    charts.f_chart_type.setCurrentText("Bars")
    assert charts._current_chart_type == "Grouped Bars"
    assert charts.chart_view.chart().axes()[0].categories() == ["Rent", "Food"]  # largest first
    assert charts.chk_custom_y.isEnabled()
    charts.f_chart_type.setCurrentText("Stacked Bars")
    assert charts._current_chart_type == "Stacked Bars"


def test_the_pick_comes_back_with_the_range(charts):
    charts._period._select_preset(3)
    charts.f_chart_type.setCurrentText("Spline")
    charts._period._select_preset(1)
    assert charts.f_chart_type.currentText() == "Donut"  # a line needs two months
    charts._period._select_preset(3)
    assert charts.f_chart_type.currentText() == "Spline"
    charts._period._select_preset(1)
    charts.f_chart_type.setCurrentText("Bars")
    charts._period._select_preset(3)
    assert charts.f_chart_type.currentText() == "Grouped Bars"


def test_donut_over_several_months_sums_the_range(charts):
    charts._period._select_preset(3)
    charts.f_chart_type.setCurrentText("Donut")
    assert charts._current_chart_type == "Donut"
    assert {c: s.value() for c, s in charts._donut_slices.items()} == {"Rent": 1800, "Food": 200}


def test_total_row_adds_up_the_ticked_categories(charts):
    charts._period._select_preset(3)
    assert charts._total_item.text() == "$2,000"
    charts._cat_cbs["Food"][0].setChecked(False)
    assert charts._total_item.text() == "$1,800"
    charts._select_no_cats()
    assert charts._total_item.text() == "$0"
    charts._select_all_cats()
    assert charts._total_item.text() == "$2,000"


def test_hover_label_shows_the_month_total(charts):
    charts._period._select_preset(3)
    i = len(charts._month_totals) - 1  # this month: food 120 + rent 900
    assert charts._with_month_total("Food", i) == "Food\nMonth total   $1,020.00"
    charts._cat_cbs["Food"][0].setChecked(False)  # one category: its value is the total
    assert charts._with_month_total("Rent", i) == "Rent"


@pytest.fixture
def detailed(qapp, db):
    """Food › Groceries and Food › Restaurants, this month and last month."""
    from daftarche.db import MONTHS_ORDER
    from daftarche.tabs.charts import ChartsTab
    food = _category(db, "Food")
    for sub in ("Groceries", "Restaurants"):
        db.add_subcategory(sub, food)
    today = datetime.date.today()
    last = today.replace(day=1) - datetime.timedelta(days=1)
    for d, sub, amount, name in ((today, "Groceries", 60, "NOFRILLS"), (today, "Restaurants", 40, "PHO"),
                                 (last, "Groceries", 100, "COSTCO")):
        db.add_transaction(d.year, MONTHS_ORDER[d.month - 1], 2, "Expense", "Vahid-CIBC-Checking", amount,
                           db.get_subcategory_by_name(sub, food)["id"], food, name=name)
    return keep(ChartsTab(db))


def _panel_rows(tab):
    t = tab.detail.table
    return [tuple(t.item(r, c).text() if t.item(r, c) else "" for c in range(3)) for r in range(t.rowCount())]


def test_detail_shows_subcategories_for_the_range_or_a_month(detailed):
    tab = detailed
    tab._period._select_preset(3)  # 3 months
    assert tab.detail.hint.isVisibleTo(tab.detail) and not tab.detail.pin.isEnabled()
    tab._detail("Food")  # list hover: whole range
    assert _panel_rows(tab) == [("80%", "Groceries", "$160.00"), ("20%", "Restaurants", "$40.00")]
    assert "$200.00" in tab.detail.title.text()
    tab._detail("Food", len(tab._chart_periods) - 1)  # chart hover on this month
    assert _panel_rows(tab) == [("60%", "Groceries", "$60.00"), ("40%", "Restaurants", "$40.00")]


def test_detail_pins_and_lists_transactions_of_a_subcategory(detailed):
    tab = detailed
    tab._period._select_preset(3)
    tab.f_cat_selector.set_items(["Food"], include_all=True, selected="Food")
    tab._on_category_pick_changed()
    tab._detail("Groceries")
    rows = _panel_rows(tab)
    assert [r[1:] for r in rows] == [("NOFRILLS", "$60.00"), ("COSTCO", "$100.00")]
    assert "2 transactions" in tab.detail.title.text()
    tab.chart_view.mousePressed.emit(None)  # a click on the chart pins
    assert tab.detail.pinned and tab.detail.pin.text() == "Pinned"
    tab._detail("Restaurants")
    assert [r[1] for r in _panel_rows(tab)] == ["NOFRILLS", "COSTCO"]  # unchanged while pinned
    tab.detail.set_pinned(False)
    tab._detail("Restaurants")
    assert [r[1] for r in _panel_rows(tab)] == ["PHO"]
    seen = []
    tab.detail.openRequested.connect(seen.append)
    tab.detail.table.cellDoubleClicked.emit(0, 1)
    assert seen and seen[0]["categories"] == ["Food"] and seen[0]["subcategories"] == ["Restaurants"]
    tab._period._select_preset(1)  # a new range clears it
    assert tab.detail.key is None and not tab.detail.pinned


def test_money_back_shows_as_a_negative_line(qapp, db):
    """Insurance paying back more than was spent there: a negative sub-category, still listed."""
    from daftarche.db import MONTHS_ORDER
    from daftarche.tabs.charts import ChartsTab
    health = _category(db, "Health")
    for sub in ("Pharmacy", "Insurance Claims"):
        db.add_subcategory(sub, health)
    today = datetime.date.today()
    for sub, amount in (("Pharmacy", 100), ("Insurance Claims", -40)):
        db.add_transaction(today.year, MONTHS_ORDER[today.month - 1], 1, "Expense", "Card", amount,
                           db.get_subcategory_by_name(sub, health)["id"], health)
    tab = keep(ChartsTab(db))
    tab._period._select_preset(3)
    tab._detail("Health")
    assert _panel_rows(tab) == [("100%", "Pharmacy", "$100.00"), ("", "Insurance Claims", "-$40.00")]
    assert "$60.00" in tab.detail.title.text()  # the rows add up to the category
    tab.f_cat_selector.set_items(["Health"], include_all=True, selected="Health")
    tab._on_category_pick_changed()
    assert tab._cat_cbs["Insurance Claims"][1].text() == "-$40"
    assert tab._total_item.text() == "$60"
