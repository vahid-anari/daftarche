"""Reading the phone snapshot and adding it up (no Flet here, so it is easy to test).

The file is written by Daftarche on the Mac (docs/phone-snapshot.md). Balances and loans come
ready-made; this module only filters transactions and adds up their amounts, the way the
desktop tabs do: totals by kind from the transactions, totals by category from their parts.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

FORMAT = "daftarche-phone"
VERSION = 1
SNAPSHOT_NAME = "daftarche-phone.json"

KINDS = ("Income", "Expense", "Transfer")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")

NO_MERCHANT = "(no merchant)"
"""The Merchant filter's choice for the transactions without one."""

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
           "#bcbd22", "#17becf", "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5", "#c49c94",
           "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5"]
"""Category colours, in order of size: the desktop charts use the same."""


def _as_set(value):
    """A filter's choice as a set (None or an empty one: no filter); one value is a set of one."""
    if value is None:
        return None
    if isinstance(value, (set, frozenset, list, tuple)):
        return set(value) or None
    return {value}


class SnapshotError(ValueError):
    """The file is not a phone snapshot, or one this app is too old to read."""


# ── Periods ───────────────────────────────────────────────────────────────────
PERIODS = ("This Month", "Last Month", "3 Months", "6 Months", "This Year", "All")


def _add_months(year, month, n):
    i = year * 12 + (month - 1) + n
    return i // 12, i % 12 + 1


def _month_end(year, month):
    y, m = _add_months(year, month, 1)
    return date.fromordinal(date(y, m, 1).toordinal() - 1)


def period_range(name, today=None):
    """``(first day, last day)`` of a period as ISO strings; ``All`` is ``(None, None)``.

    "3 Months" is this month and the two before it, as on the desktop.
    """
    today = today or date.today()
    y, m = today.year, today.month
    if name == "All":
        return None, None
    if name == "This Month":
        start, end = (y, m), (y, m)
    elif name == "Last Month":
        start = end = _add_months(y, m, -1)
    elif name == "3 Months":
        start, end = _add_months(y, m, -2), (y, m)
    elif name == "6 Months":
        start, end = _add_months(y, m, -5), (y, m)
    elif name == "This Year":
        start, end = (y, 1), (y, m)
    else:
        raise ValueError(f"Unknown period {name!r}")
    return date(*start, 1).isoformat(), _month_end(*end).isoformat()


def custom_period(mode, value):
    """A period chosen in Custom…: ``mode`` "month" (value "2026-09"), "year" (value 2026) or
    "range" (value ``(first day, last day)``, dates or ISO strings). → ``{mode, start, end}``."""
    if mode == "month":
        y, m = (int(x) for x in str(value).split("-"))
        return {"mode": mode, "start": date(y, m, 1).isoformat(), "end": _month_end(y, m).isoformat()}
    if mode == "year":
        y = int(value)
        return {"mode": mode, "start": f"{y}-01-01", "end": f"{y}-12-31"}
    if mode == "range":
        first, last = (v if isinstance(v, str) else v.isoformat() for v in value)
        first, last = min(first, last), max(first, last)
        return {"mode": mode, "start": first[:10], "end": last[:10]}
    raise ValueError(f"Unknown kind of period {mode!r}")


def custom_label(period):
    """"Sep 2026", "2026", or "12 Oct – 3 Nov 2026"."""
    start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
    if period["mode"] == "month":
        return f"{MONTHS[start.month - 1][:3]} {start.year}"
    if period["mode"] == "year":
        return str(start.year)
    first = f"{start.day} {MONTHS[start.month - 1][:3]}" + ("" if start.year == end.year else f" {start.year}")
    return f"{first} – {end.day} {MONTHS[end.month - 1][:3]} {end.year}"


def step_period(period, n):
    """The month (or year) ``n`` before (< 0) or after a chosen one; a range does not step."""
    start = date.fromisoformat(period["start"])
    if period["mode"] == "month":
        y, m = _add_months(start.year, start.month, n)
        return custom_period("month", f"{y}-{m:02d}")
    if period["mode"] == "year":
        return custom_period("year", start.year + n)
    return period


def month_label(key):
    """``"2026-10"`` → ``"Oct 26"``."""
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1][:3]} {y[2:]}"


def money(value, sign=False):
    """$1,234.50, -$30.00 (and +$5.00 with ``sign``)."""
    value = round(value or 0, 2) + 0.0
    text = f"${abs(value):,.2f}"
    if value < 0:
        return "-" + text
    return ("+" + text) if sign and value > 0 else text


# ── The snapshot ──────────────────────────────────────────────────────────────
@dataclass
class Line:
    """One line of a transaction for totals by category: the whole of it, or one part."""

    tx: dict
    amount: float
    category: int | None
    subcategory: int | None
    note: str | None
    tags: frozenset = frozenset()  # the transaction's own tags, and a part's (0.36.0 on the Mac)


class Snapshot:
    """A loaded ``daftarche-phone.json``."""

    def __init__(self, data):
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise SnapshotError("This is not a Daftarche phone file.")
        if int(data.get("version", 0)) > VERSION:
            raise SnapshotError("This data is from a newer Daftarche. Please update the app.")
        self.data = data
        self.accounts = data.get("accounts", [])
        self.account = {a["id"]: a for a in self.accounts}
        self.categories = data.get("categories", [])
        self.category = {c["id"]: c for c in self.categories}
        self.subcategory = {s["id"]: s for c in self.categories for s in c.get("subcategories", [])}
        self.sub_category = {s["id"]: c["id"] for c in self.categories for s in c.get("subcategories", [])}
        self._images = data.get("images") or {}  # key → base64 PNG (0.5.0; older files have none)
        self._decoded = {}
        self.tags = data.get("tags", [])
        self.tag = {t["id"]: t for t in self.tags}
        self.transactions = data.get("transactions", [])  # newest first
        self.loans = data.get("loans", [])
        self.balances = data.get("balances", {"months": [], "by_account": {}})
        self.app_version = data.get("app_version", "")
        try:
            self.created = datetime.fromisoformat(data.get("created", ""))
        except ValueError:
            self.created = None

    @classmethod
    def from_json(cls, raw):
        """From the snapshot's JSON bytes (opened from the sealed file)."""
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError(f"Could not read the data: {exc}") from exc
        return cls(data)

    @classmethod
    def load(cls, path):
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, ValueError) as exc:
            raise SnapshotError(f"Could not read {path.name}: {exc}") from exc
        return cls(data)

    # ── names ──
    def account_name(self, account_id):
        a = self.account.get(account_id)
        return a["name"] if a else ""

    def account_color(self, account_id):
        a = self.account.get(account_id)
        return a["color"] if a else "#7c6af7"

    def category_name(self, category_id):
        c = self.category.get(category_id)
        return c["name"] if c else "Uncategorized"

    def subcategory_name(self, subcategory_id):
        s = self.subcategory.get(subcategory_id)
        return s["name"] if s else ""

    def icon(self, category_id, subcategory_id=None):
        s = self.subcategory.get(subcategory_id)
        if s and (s.get("icon") or s.get("image")):  # its own (an image: category_image has it)
            return s.get("icon") or ""
        c = self.category.get(category_id)
        return (c or {}).get("icon") or ""

    def image(self, key):
        """The PNG bytes of an image in the file, or None."""
        if not key or key not in self._images:
            return None
        if key not in self._decoded:
            try:
                self._decoded[key] = base64.b64decode(self._images[key], validate=True)
            except (binascii.Error, ValueError, TypeError):
                self._decoded[key] = None
        return self._decoded[key]

    def merchant_image(self, merchant):
        """The merchant's logo (PNG bytes), or None."""
        return self.image("logo:" + merchant.strip().casefold()) if merchant else None

    def category_image(self, category_id, subcategory_id=None):
        """The logo or picture used as the icon of a sub-category, else of its category (PNG bytes),
        or None when that icon is an emoji or there is none."""
        s = self.subcategory.get(subcategory_id)
        if s and (s.get("image") or s.get("icon")):
            return self.image(s.get("image"))
        c = self.category.get(category_id)
        return self.image((c or {}).get("image"))

    def title(self, tx):
        """What a row is called: the merchant, else the bank's text."""
        return tx.get("merchant") or tx.get("name") or tx.get("note") or "—"

    # ── balances ──
    def shown_accounts(self):
        """The accounts on the Accounts tab (as on the desktop), in name order."""
        return [a for a in self.accounts if a.get("show_in_accounts", True)]

    def total_balance(self):
        return round(sum(a["balance"] for a in self.accounts), 2)

    def balance_series(self, start=None, end=None):
        """``(months, {account id: [balance at each month's end]})``, months within the period."""
        months = self.balances.get("months", [])
        keep = [i for i, m in enumerate(months)
                if (start is None or m >= start[:7]) and (end is None or m <= end[:7])]
        series = {int(k): [v[i] for i in keep] for k, v in self.balances.get("by_account", {}).items()}
        return [months[i] for i in keep], series

    # ── transactions ──
    def filter(self, start=None, end=None, kind=None, account=None, category=None, tag=None, text="",
               merchant=None, subcategory=None):
        """Transactions (newest first) in a period, of a kind, touching an account, with a
        category or sub-category (in any part), a tag, a merchant (NO_MERCHANT: none), or text in
        their names, note, category or amount.

        Each choice may be one value or several (a set: any of them); None or an empty set is no
        filter. Sub-categories narrow their own category only: with Groceries and Health chosen and
        the sub-category Bakery, Groceries shows Bakery alone and Health all of it."""
        text = (text or "").strip().casefold()
        kinds, accounts, merchants = (_as_set(v) for v in (kind, account, merchant))
        line_ok = self.line_test(category, subcategory, tag)
        out = []
        for tx in self.transactions:
            d = tx["date"]
            if (start and d < start) or (end and d > end):
                continue
            if kinds and tx["type"] not in kinds:
                continue
            if accounts and not ({tx["account"], tx["to_account"]} & accounts):
                continue
            if line_ok and not any(line_ok(line) for line in self.lines([tx])):
                continue
            if merchants and (tx.get("merchant") or NO_MERCHANT) not in merchants:
                continue
            if text and text not in self._search_text(tx):
                continue
            out.append(tx)
        return out

    def line_test(self, categories=None, subcategories=None, tags=None):
        """Whether a line (a transaction, or one part of it) has a chosen category / sub-category
        and a chosen tag (its own, or the transaction's); None when none is chosen."""
        categories, subcategories, tags = _as_set(categories), _as_set(subcategories), _as_set(tags)
        in_categories = self._category_test(categories, subcategories)
        if tags is None:
            return in_categories
        if in_categories is None:
            return lambda line: bool(line.tags & tags)
        return lambda line: bool(line.tags & tags) and in_categories(line)

    def _category_test(self, categories, subcategories):
        if not categories and not subcategories:
            return None
        subs = subcategories or set()
        narrowed = {self.sub_category.get(sub) for sub in subs}  # categories with sub-categories chosen
        allowed = (categories or set()) | narrowed
        return lambda line: line.category in allowed and (line.category not in narrowed or line.subcategory in subs)

    def counts(self, key, start=None, end=None, **chosen):
        """``{value: transactions}`` for one filter (``key``: kind, account, category, subcategory,
        merchant or tag), with every other choice applied: what each value would show. A category's
        count leaves the sub-categories out too; a sub-category's keeps the categories chosen."""
        others = {k: v for k, v in chosen.items() if k != key and not (key == "category" and k == "subcategory")}
        if key == "subcategory" and _as_set(chosen.get("category")):  # the chosen ones' categories count too
            others["category"] = _as_set(chosen["category"]) | {self.sub_category.get(v)
                                                                for v in _as_set(chosen.get("subcategory")) or ()}
        in_categories = self.line_test(others.get("category")) if key == "subcategory" else None
        # a split's parts count for what they have: a category's parts with the chosen tag, a tag's
        # parts in the chosen categories
        parts_ok = self.line_test(tags=others.get("tag")) if key in ("category", "subcategory") else \
            self.line_test(others.get("category"), others.get("subcategory")) if key == "tag" else None
        out = {}
        for tx in self.filter(start, end, **others):
            lines = [line for line in self.lines([tx]) if parts_ok is None or parts_ok(line)]
            if key == "kind":
                values = {tx["type"]}
            elif key == "account":
                values = {tx["account"], tx["to_account"]} - {None}
            elif key == "category":
                values = {line.category for line in lines} - {None}
            elif key == "subcategory":
                values = {line.subcategory for line in lines if line.subcategory is not None
                          and (in_categories is None or in_categories(line))}
            elif key == "merchant":
                values = {tx.get("merchant") or NO_MERCHANT}
            elif key == "tag":
                values = set().union(*(line.tags for line in lines))
            else:
                raise ValueError(f"Unknown filter {key!r}")
            for v in values:
                out[v] = out.get(v, 0) + 1
        return out

    def months_with_data(self):
        """``{"2026-09", …}``: the months that have transactions."""
        return {tx["date"][:7] for tx in self.transactions}

    def first_date(self):
        """The oldest transaction's day (ISO), or None."""
        return min((tx["date"] for tx in self.transactions), default=None)

    def merchants(self):
        """Every merchant of the transactions, A to Z."""
        return sorted({tx["merchant"] for tx in self.transactions if tx.get("merchant")},
                      key=lambda m: (m.casefold(), m))

    def _search_text(self, tx):
        words = [tx.get("merchant"), tx.get("name"), tx.get("note"), f"{tx['amount']:.2f}",
                 self.account_name(tx["account"]), self.account_name(tx["to_account"])]
        tags = set()
        for line in self.lines([tx]):
            words += [self.category_name(line.category), self.subcategory_name(line.subcategory), line.note]
            tags |= line.tags
        words += [self.tag[t]["name"] for t in sorted(tags) if t in self.tag]
        return " ".join(w for w in words if w).casefold()

    @staticmethod
    def lines(transactions):
        """Every transaction as lines: its parts when split, else itself."""
        for tx in transactions:
            own = frozenset(tx.get("tags") or ())
            if tx.get("parts"):
                for p in tx["parts"]:
                    yield Line(tx, p["amount"], p["category"], p["subcategory"], p.get("note") or tx.get("note"),
                               own | frozenset(p.get("tags") or ()))
            else:
                yield Line(tx, tx["amount"], tx["category"], tx["subcategory"], tx.get("note"), own)

    # ── totals ──
    def summary(self, start=None, end=None):
        """Income, expense, net and how many transactions: the Dashboard's cards."""
        txs = self.filter(start, end)
        income = round(sum(t["amount"] for t in txs if t["type"] == "Income"), 2)
        expense = round(sum(t["amount"] for t in txs if t["type"] == "Expense"), 2)
        return {"income": income, "expense": expense, "net": round(income - expense, 2), "count": len(txs)}

    def monthly(self, start=None, end=None):
        """``[(month, income, expense)]`` for every month with income or expenses, oldest first."""
        sums = {}
        for t in self.filter(start, end):
            if t["type"] in ("Income", "Expense"):
                row = sums.setdefault(t["date"][:7], [0.0, 0.0])
                row[0 if t["type"] == "Income" else 1] += t["amount"]
        return [(m, round(i, 2), round(e, 2)) for m, (i, e) in sorted(sums.items())]

    def by_category(self, kind="Expense", start=None, end=None, account=None):
        """``[(category id, total)]`` of a kind, largest first (money back can make a total < 0)."""
        sums = {}
        for line in self.lines(self.filter(start, end, kind=kind, account=account)):
            sums[line.category] = sums.get(line.category, 0.0) + line.amount
        rows = [(c, round(v, 2)) for c, v in sums.items() if round(v, 2) != 0]
        return sorted(rows, key=lambda r: -r[1])

    def by_subcategory(self, category, kind="Expense", start=None, end=None, account=None):
        """``[(sub-category id, total)]`` inside one category, largest first."""
        sums = {}
        for line in self.lines(self.filter(start, end, kind=kind, account=account)):
            if line.category == category:
                sums[line.subcategory] = sums.get(line.subcategory, 0.0) + line.amount
        rows = [(s, round(v, 2)) for s, v in sums.items() if round(v, 2) != 0]
        return sorted(rows, key=lambda r: -r[1])

    def monthly_by_category(self, kind="Expense", start=None, end=None, account=None):
        """``(months, {category id: [total in each month]})`` for the stacked bars."""
        sums = {}
        for line in self.lines(self.filter(start, end, kind=kind, account=account)):
            m = line.tx["date"][:7]
            sums.setdefault(line.category, {})
            sums[line.category][m] = sums[line.category].get(m, 0.0) + line.amount
        months = sorted({m for per in sums.values() for m in per})
        return months, {c: [round(per.get(m, 0.0), 2) for m in months] for c, per in sums.items()}

    def category_colors(self, kind="Expense", start=None, end=None, account=None):
        """``{category id: colour}``, the biggest first, as the desktop charts colour them."""
        return {c: PALETTE[i % len(PALETTE)] for i, (c, _) in enumerate(self.by_category(kind, start, end, account))}

    def loan_totals(self):
        """``(you owe, owed to you)``, both positive."""
        return (round(-sum(e["balance"] for e in self.loans if e["balance"] < 0), 2),
                round(sum(e["balance"] for e in self.loans if e["balance"] > 0), 2))
