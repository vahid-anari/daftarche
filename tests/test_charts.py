"""Charts tab: the chart choices follow the range (one month or several)."""

import datetime

import pytest


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
    tab = ChartsTab(db)
    yield tab
    tab.deleteLater()


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
