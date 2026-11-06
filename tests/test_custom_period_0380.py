"""0.38.0: Custom opens a window: a month, a year, or From – to; ◀ ▶ step a month or a year."""

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
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    sub = db.uncategorized_subcategory(food)["id"]
    today = datetime.date.today()
    last = today.replace(day=1) - datetime.timedelta(days=1)
    for d in (today, last):
        db.add_transaction(d.year, MONTHS_ORDER[d.month - 1], 1, "Expense", "Vahid-CIBC-Checking", 50, sub, food)
    yield keep(ChartsTab(db))


def test_the_months_with_data(db, charts):
    today = datetime.date.today()
    last = today.replace(day=1) - datetime.timedelta(days=1)
    assert db.months_with_data() == {today.strftime("%Y-%m"), last.strftime("%Y-%m")}
    assert charts._period._months() == db.months_with_data()


def test_a_chosen_month_steps_and_stops(charts):
    sel = charts._period
    today = datetime.date.today()
    last = today.replace(day=1) - datetime.timedelta(days=1)
    sel._custom = {"mode": "month", "start": last.replace(day=1)}
    sel._select_preset(sel._custom_idx())
    assert sel.get_range() == (last.replace(day=1), last)
    assert sel._preset_btns[-1].text().startswith(last.strftime("%b %Y"))
    assert not sel._step_back.isHidden() and not sel._step_back.isEnabled()  # no data before
    assert sel._step_on.isEnabled()
    sel._step(1)
    assert sel.get_range() == (today.replace(day=1), today)  # this month: up to today
    assert not sel._step_on.isEnabled()
    assert charts.f_chart_type.currentText() == "Donut"  # one month


def test_a_preset_hides_the_arrows_and_custom_is_custom_again(charts):
    sel = charts._period
    sel._custom = {"mode": "year", "start": datetime.date(datetime.date.today().year, 1, 1)}
    sel._select_preset(sel._custom_idx())
    assert sel._preset_btns[-1].text().startswith(str(datetime.date.today().year))
    sel._select_preset(1)
    assert sel._step_back.isHidden() and sel._preset_btns[-1].text() == "Custom"


def test_state_and_restore_keep_the_month(charts):
    sel = charts._period
    sel._custom = {"mode": "month", "start": datetime.date(2026, 3, 1)}
    sel._select_preset(sel._custom_idx())
    state = sel.state()
    sel._select_preset(1)
    sel.restore(state)
    assert sel.get_range()[0] == datetime.date(2026, 3, 1)
    sel.restore(state[:2])  # as saved by 0.37.0: still fine


def test_set_custom_range_is_from_to(charts):
    sel = charts._period
    sel._custom = {"mode": "month", "start": datetime.date(2026, 3, 1)}
    sel.set_custom_range(datetime.date(2026, 1, 1), datetime.date(2026, 2, 28))
    assert sel._custom["mode"] == "range" and sel._step_back.isHidden()


def test_the_window(charts):
    from PySide6.QtWidgets import QDialog
    from daftarche.widgets import PeriodDialog
    sel = charts._period
    today = datetime.date.today()
    dialog = keep(PeriodDialog("month", None, sel._range_widget.get_range(), {today.strftime("%Y-%m")}))
    assert dialog._pages.currentIndex() == 0  # nothing chosen yet: Month
    enabled = [b.text() for b in dialog._month_btns if b.isEnabled()]
    assert enabled == [today.strftime("%b")]
    assert not dialog._prev.isEnabled() and not dialog._next.isEnabled()
    dialog._month_btns[today.month - 1].click()
    assert dialog.result() == QDialog.Accepted and dialog.choice == ("month", today.replace(day=1))


def test_no_window_is_left_behind_and_return_picks_nothing(charts, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog
    from daftarche.widgets import PeriodDialog
    sel = charts._period
    assert sel._range_widget.parent() is sel  # owned, not a window of its own
    monkeypatch.setattr(PeriodDialog, "exec", lambda self: QDialog.Rejected)
    for _ in range(3):
        sel._open_custom()
    QApplication.sendPostedEvents(None, 0)
    from PySide6.QtCore import QEvent
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert not sel.window().findChildren(PeriodDialog)
    dialog = keep(PeriodDialog("month", None, sel._range_widget.get_range(), None))
    assert not any(b.autoDefault() for b in dialog._month_btns)


def test_no_transactions_means_no_limit(qapp, db):
    from daftarche.tabs.charts import ChartsTab
    tab = keep(ChartsTab(db))
    assert tab._period._months() is None


def test_a_period_chosen_after_a_jump_stays(qapp, db):
    from daftarche.tabs.transactions import TransactionsTab
    tab = keep(TransactionsTab(db))
    tab._period._select_preset(1)  # Today
    tab.show_matching(from_day="2026-01-01", to_day="2026-01-31", came_from=("Charts", lambda: None))
    tab._period._custom = {"mode": "month", "start": datetime.date(2026, 3, 1)}
    try:
        tab._period._choose(tab._period._custom_idx())  # chosen by you
        assert tab._period.get_range()[0] == datetime.date(2026, 3, 1)
    finally:  # the choice is saved: put back All for the other tests
        tab._period._custom = {"mode": "range"}
        tab._period._save_custom()
        tab._period._select_preset(0, emit=False)
