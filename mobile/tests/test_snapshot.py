"""The phone adds up the snapshot the way the desktop tabs do."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from daftarche_phone.snapshot import Snapshot, SnapshotError, money, month_label, period_range

REPO = Path(__file__).resolve().parents[2]
TODAY = date(2026, 10, 19)


@pytest.fixture(scope="module")
def desktop(tmp_path_factory):
    """The demo database (tools/make_demo_db.py) with a split, a tag and a loan, and its snapshot."""
    pytest.importorskip("daftarche")
    from daftarche.db import Database
    from daftarche.phone import build_snapshot
    spec = importlib.util.spec_from_file_location("make_demo_db", REPO / "tools" / "make_demo_db.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    db = Database(str(demo.make_demo(tmp_path_factory.mktemp("demo"), months=12, today=TODAY)))
    tx_id, amount, cat = db.conn.execute("SELECT id, amount, category_id FROM transactions "
                                         "WHERE merchant = 'Maple Grocer' ORDER BY date DESC LIMIT 1").fetchone()
    sub = db.conn.execute("SELECT subcategory_id FROM transactions WHERE id = ?", (tx_id,)).fetchone()[0]
    shop = db.get_category_by_name("Shopping", type_name="Expense")["id"]
    household = db.get_subcategory_by_name("Household", shop)["id"]
    db.set_splits(tx_id, [(cat, sub, round(amount - 20, 2), None), (shop, household, 20, "soap")])
    db.add_tag("Trip")
    db.set_tags_for_transaction(tx_id, [db.get_tags()[0]["id"]])
    lent = db.add_transaction(2026, "September", 14, "Expense", "Demo Bank Chequing", 300, sub, cat,
                              merchant="Sahar")
    db.make_loan([lent], "Sahar")
    yield db, Snapshot(build_snapshot(db, "0.26.0")), tx_id, shop
    db.conn.close()


def test_totals_match_the_desktop(desktop):
    db, snap, _, _ = desktop
    start, end = period_range("6 Months", TODAY)
    s = snap.summary(start, end)
    d = db.get_dashboard_summary(2026, "May", 2026, "October")
    assert (s["income"], s["expense"], s["net"], s["count"]) == (d["income"], d["expense"], d["net"], d["tx_count"])
    phone = {snap.category_name(c): v for c, v in snap.by_category("Expense", start, end)}
    assert phone == db.get_period_totals_by_group(2026, "May", 2026, "October", "Expense")
    assert snap.total_balance() == db.get_current_total_balance()
    months = snap.monthly(start, end)
    by_month = db.get_monthly_summary_for_range(2026, "May", 2026, "October")
    assert [(i, e) for _, i, e in months] == [(v["income"], v["expense"]) for v in by_month.values()]


def test_splits_count_in_each_category(desktop):
    db, snap, tx_id, shop = desktop
    tx = next(t for t in snap.transactions if t["id"] == tx_id)
    assert [p["amount"] for p in tx["parts"]][1] == 20
    assert tx in snap.filter(category=shop)  # found by the category of a part
    assert snap.by_subcategory(shop, start=tx["date"], end=tx["date"]) == [
        (tx["parts"][1]["subcategory"], 20.0)]


def test_filters(desktop):
    db, snap, tx_id, _ = desktop
    assert [t["id"] for t in snap.filter(text="trip")] == [tx_id]  # by tag
    assert [t["id"] for t in snap.filter(tag=snap.tags[0]["id"])] == [tx_id]
    assert all(t["type"] == "Transfer" for t in snap.filter(kind="Transfer"))
    visa = next(a["id"] for a in snap.accounts if a["name"] == "Demo Visa")
    assert snap.filter(kind="Transfer", account=visa)  # card payments arrive in the Visa account
    dates = [t["date"] for t in snap.filter()]
    assert dates == sorted(dates, reverse=True)


def test_balances_and_loans(desktop):
    db, snap, _, _ = desktop
    months, series = snap.balance_series(*period_range("3 Months", TODAY))
    assert months == ["2026-08", "2026-09", "2026-10"]
    assert sum(v[-1] for v in series.values()) == pytest.approx(snap.total_balance())
    assert [(e["person"], e["balance"]) for e in snap.loans] == [("Sahar", 300)]
    assert snap.loan_totals() == (0, 300)


def test_periods_and_words():
    assert period_range("This Month", TODAY) == ("2026-10-01", "2026-10-31")
    assert period_range("Last Month", date(2026, 1, 5)) == ("2025-12-01", "2025-12-31")
    assert period_range("3 Months", date(2026, 2, 28)) == ("2025-12-01", "2026-02-28")
    assert period_range("This Year", TODAY) == ("2026-01-01", "2026-10-31")
    assert period_range("All", TODAY) == (None, None)
    assert month_label("2026-02") == "Feb 26"
    assert (money(1234.5), money(-30), money(5, sign=True), money(-0.001)) == ("$1,234.50", "-$30.00", "+$5.00",
                                                                             "$0.00")


def test_refuses_what_it_cannot_read():
    with pytest.raises(SnapshotError, match="not a Daftarche"):
        Snapshot({"format": "something else"})
    with pytest.raises(SnapshotError, match="newer Daftarche"):
        Snapshot({"format": "daftarche-phone", "version": 99})


def test_logos_and_pictures():
    """0.5.0: the merchant's logo, else the logo or picture of the sub-category or category;
    a file from before 0.37 (no "images") still opens, with emoji only."""
    import base64
    png = b"\x89PNG fake"
    data = {"format": "daftarche-phone", "version": 1, "images": {"logo:maple grocer": base64.b64encode(png).decode(),
                                                                  "pic:3": base64.b64encode(png + b"3").decode(),
                                                                  "logo:broken": "not base64!"},
            "categories": [{"id": 1, "name": "Home", "type": "Expense", "icon": None, "image": "pic:3",
                            "subcategories": [{"id": 2, "name": "Cleaning", "icon": "🧽", "image": None},
                                              {"id": 4, "name": "Garden", "icon": None, "image": "pic:3"}]},
                           {"id": 5, "name": "Food", "type": "Expense", "icon": "🛒", "image": None,
                            "subcategories": []}]}
    s = Snapshot(data)
    assert s.merchant_image("Maple Grocer") == png and s.merchant_image("MAPLE GROCER") == png
    assert s.merchant_image("Other") is None and s.merchant_image(None) is None
    assert s.merchant_image("Broken") is None  # a damaged image: no logo, no crash
    assert s.category_image(1) == png + b"3" and s.category_image(1, 4) == png + b"3"
    assert s.category_image(1, 2) is None and s.icon(1, 2) == "🧽"  # its own emoji comes first
    assert s.category_image(5) is None and s.icon(5) == "🛒"
    old = Snapshot({"format": "daftarche-phone", "version": 1, "categories": data["categories"][1:]})
    assert old.merchant_image("Maple Grocer") is None and old.icon(5) == "🛒"


# ── 0.6.0: several choices per filter, sub-categories, counts, Custom… ───────
def test_several_choices_of_a_filter(desktop):
    _, snap, _, _ = desktop
    a, b = snap.accounts[0]["id"], snap.accounts[1]["id"]
    both = snap.filter(account={a, b})
    assert both and {t["id"] for t in both} == {t["id"] for t in snap.filter(account=a)} | \
        {t["id"] for t in snap.filter(account=b)}
    assert snap.filter(account=set()) == snap.filter()  # nothing chosen: all
    assert {t["type"] for t in snap.filter(kind={"Income", "Transfer"})} == {"Income", "Transfer"}


def test_a_subcategory_narrows_only_its_own_category(desktop):
    _, snap, tx_id, shop = desktop
    groceries = next(c for c in snap.categories if c["name"] == "Groceries")
    health = next(c for c in snap.categories if c["name"] == "Health")
    sub = groceries["subcategories"][0]["id"]
    got = snap.filter(category={groceries["id"], health["id"]}, subcategory={sub})
    lines = list(snap.lines(got))
    assert any(line.subcategory == sub for line in lines)
    assert any(line.category == health["id"] for line in lines)  # Health: all of it
    for tx in got:  # each has a line in Health, or in the chosen sub-category of Groceries
        assert any(line.category == health["id"] or line.subcategory == sub for line in snap.lines([tx]))
    only = snap.filter(subcategory={sub})  # no category chosen: that sub-category alone
    assert only and all(any(line.subcategory == sub for line in snap.lines([t])) for t in only)
    split = next(t for t in snap.transactions if t["id"] == tx_id)
    household = split["parts"][1]["subcategory"]
    assert split in snap.filter(subcategory={household})  # by a part


def test_counts_leave_out_their_own_filter(desktop):
    _, snap, _, _ = desktop
    m = snap.merchants()[:2]
    counts = snap.counts("merchant", merchant={m[0]})
    assert counts[m[1]] == len(snap.filter(merchant=m[1]))  # the others still counted
    kind_counts = snap.counts("category", kind={"Income"})
    assert all(snap.category[c]["type"] == "Income" for c in kind_counts)
    groceries = next(c for c in snap.categories if c["name"] == "Groceries")
    sub = groceries["subcategories"][0]["id"]
    assert snap.counts("category", subcategory={sub}) == snap.counts("category")  # its subs left out too
    subs = snap.counts("subcategory", category={groceries["id"]})
    assert subs and all(snap.sub_category[s] == groceries["id"] for s in subs)


def test_custom_periods():
    from daftarche_phone.snapshot import custom_label, custom_period, step_period
    sep = custom_period("month", "2026-09")
    assert (sep["start"], sep["end"], custom_label(sep)) == ("2026-09-01", "2026-09-30", "Sep 2026")
    assert custom_label(step_period(sep, -9)) == "Dec 2025" and custom_label(step_period(sep, 4)) == "Jan 2027"
    year = custom_period("year", 2025)
    assert (year["start"], year["end"], custom_label(step_period(year, 1))) == ("2025-01-01", "2025-12-31", "2026")
    days = custom_period("range", (date(2026, 11, 3), date(2026, 10, 12)))  # either order
    assert (days["start"], days["end"], custom_label(days)) == ("2026-10-12", "2026-11-03", "12 Oct – 3 Nov 2026")
    assert custom_label(custom_period("range", ("2025-12-30", "2026-01-02"))) == "30 Dec 2025 – 2 Jan 2026"
    assert step_period(days, 1) == days  # a range does not step


def test_a_parts_own_tag_finds_its_split(desktop):
    """0.6.2: a part's own tags (Daftarche 0.36.0) count, in the filter, the counts and the search."""
    db, snap, tx_id, shop = desktop
    split = next(t for t in snap.transactions if t["id"] == tx_id)
    tag = {"id": 999, "name": "Gift"}
    snap.tags.append(tag)
    snap.tag[999] = tag
    split["parts"][1]["tags"] = [999]
    try:
        assert snap.filter(tag={999}) == [split]
        assert snap.counts("tag")[999] == 1
        assert snap.counts("category", tag={999}) == {shop: 1}  # only the part with the tag
        assert split in snap.filter(text="gift")
        part_ok = snap.line_test(tags={999})
        assert [line.amount for line in snap.lines([split]) if part_ok(line)] == [20]
    finally:
        split["parts"][1]["tags"] = []
        snap.tags.remove(tag)
        del snap.tag[999]
