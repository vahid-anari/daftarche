"""Daftarche on the phone: four tabs like the desktop app, reading the phone snapshot.

Nothing here changes your data. Daftarche on the Mac keeps this phone's copy, sealed with this
phone's own key, in a file on its Google Drive; the phone was given the file and the key by
the QR code (link.py), fetches the newest copy when opened, and keeps the last one for when
there is no connection.
"""

from __future__ import annotations

import asyncio
import calendar
import urllib.parse
import copy
import json
import time
from datetime import date

import flet as ft

from . import __version__
from . import link
from .charts import LineChart, bar_chart, donut, legend, share_bar
from .nav import ASK_EXIT, DASHBOARD, EXIT, RESTORE, BackSteps
from .seal import SealError
from .snapshot import (MONTHS, NO_MERCHANT, PALETTE, PERIODS, Snapshot, SnapshotError, money, month_label,
                       period_range)
from .theme import FONT_FILES, THEME_CHOICES, material_theme, palette_for
from .update import check as check_for_update

TABS = (("Dashboard", ft.Icons.DASHBOARD_OUTLINED, ft.Icons.DASHBOARD),
        ("Transactions", ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG),
        ("Charts", ft.Icons.PIE_CHART_OUTLINE, ft.Icons.PIE_CHART),
        ("Accounts", ft.Icons.ACCOUNT_BALANCE_OUTLINED, ft.Icons.ACCOUNT_BALANCE),
        ("Settings", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS))
SETTINGS_TAB = 4
"""Settings is the last tab, as in Vahid's other phone apps."""
BOTTOM_ROOM = 96
"""Space under the last item of every tab: it clears Android's bar."""
PAGE_SIZE = 150
"""Transactions shown at first; "Show more" adds as many again."""
TOP_CATEGORIES = 7
"""Categories of their own in the stacked bars and the donut; the rest are "Other"."""


def no_filters(**chosen):
    """Transactions' "Show only" choices, all off but ``chosen``."""
    return {"kind": None, "account": None, "category": None, "tag": None, "merchant": None, "text": "",
            **chosen}


def month_range(key):
    """``"2026-09"`` → ``("2026-09-01", "2026-09-30")``."""
    y, m = (int(x) for x in key.split("-"))
    return f"{key}-01", f"{key}-{calendar.monthrange(y, m)[1]:02d}"


def long_month(key):
    """``"2026-09"`` → ``"September 2026"``."""
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"
NOT_PAIRED = "not paired"
"""``problem`` before the phone is connected to the Mac (or after it was disconnected)."""
DISCONNECTED = ("This phone was disconnected on the Mac, and its copy of your data was removed. To connect it "
                "again: on the Mac, Settings › Phone › Connect a Phone…, then scan the code.")


class PhoneApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self._period_rows = {}
        self.prefs = ft.SharedPreferences()
        self.snap: Snapshot | None = None
        self.problem = ""
        self.pairing = None  # {file, key, name}: this phone's file on the Mac's Google Drive
        self.disconnected = False
        self.fetching = False
        self._generation = 0  # goes up with every new connection: a download for an older one is ignored
        self.theme_choice = "system"
        self.tab = 0
        self.period = {"Dashboard": "This Month", "Transactions": "This Month", "Charts": "6 Months",
                       "Accounts": "All"}
        self.tx_filters = no_filters()
        self.tx_limit = PAGE_SIZE
        self.chart_kind = "Expense"
        self.dash_kind = "Expense"  # the Dashboard's donut and list: Expense or Income
        self.accounts_open = False  # the Dashboard's accounts under the total (remembered)
        self.chart_account = None
        self.chart_month = None  # a month tapped in the Charts bars ("2026-09"): its categories below
        self.tx_range = None  # Transactions shows one month from Charts: (first day, last day, label)
        self.open_category = None
        self.p = palette_for("system", page.platform_brightness)
        self.update_info = None
        self.nav = BackSteps()
        self._pager = None

    # ── start ────────────────────────────────────────────────────────────────
    async def start(self):
        page = self.page
        page.title = "Daftarche"
        page.fonts = FONT_FILES
        page.padding = 0
        page.on_platform_brightness_change = lambda e: self.render()
        page.on_app_lifecycle_state_change = self._lifecycle
        page.on_route_change = self._route_changed  # the QR code's link, opening the app
        try:
            self.pairing = link.parse_pairing("?" + urllib.parse.urlencode(
                json.loads((await self.prefs.get("pairing")) or "{}")))  # checked as a link is
        except (ValueError, TypeError):
            self.pairing = None
        self.theme_choice = (await self.prefs.get("theme")) or "system"
        self.accounts_open = (await self.prefs.get("accounts_open")) == "1"
        # Android's Back comes to the app (see nav.py) instead of always leaving it
        view = page.views[0]
        view.can_pop = False
        view.on_confirm_pop = self._back
        arrived = link.parse_pairing(getattr(page, "route", "") or "")
        if arrived:  # opened by the QR code's link
            await self._offer(arrived)
        else:
            self.load()
            self.render()
            if self.pairing:
                page.run_task(self._fetch)
        page.run_task(self._daily_update_check)

    def load(self, keep=False):
        """Open the copy kept on the phone (the newest one fetched). Returns the problem, or "".

        ``keep``: when it cannot be opened, keep showing the one shown before."""
        before = self.snap
        self.snap, self.problem = None, ""
        if not self.pairing:
            self.problem = NOT_PAIRED
            return self.problem
        blob = link.load_cache()
        if blob is None:
            self.problem = "Getting your data from Daftarche on the Mac…" if self.fetching else \
                "No data yet: connect to the internet, then tap ⟳."
        else:
            try:
                self.snap = Snapshot.from_json(link.open_blob(blob, self.pairing["key"]))
            except (SealError, SnapshotError) as exc:
                self.problem = str(exc)
        if self.snap is None and keep and before is not None:
            self.snap = before
        return self.problem

    async def _fetch(self, manual=False):
        """The newest copy from the Mac's Google Drive (in the background); kept for next time."""
        if not self.pairing or self.fetching:
            return
        self.fetching = True
        generation, pairing = self._generation, self.pairing
        problem = None
        try:
            blob = await asyncio.to_thread(link.fetch, pairing["file"])
            link.open_blob(blob, pairing["key"])  # it opens: keep it
        except link.Disconnected:
            blob, problem = None, "disconnected"
        except (link.FetchError, SealError) as exc:
            blob, problem = None, str(exc)
        if generation != self._generation:  # connected anew meanwhile: this answer is about the old one
            return
        self.fetching = False
        if problem == "disconnected":
            await self._forget(disconnected=True)
            return
        if problem:
            if manual or self.snap is None:
                self._toast(f"Could not get the newest data: {problem}")
            if self.snap is None:
                self.load()
                self.render()
            return
        link.save_cache(blob)
        self.load(keep=True)
        self.render()
        if manual:
            self._toast("Up to date")

    def _lifecycle(self, e):
        """Back in the app (later in the day): fetch the newest copy."""
        if getattr(e, "state", None) == ft.AppLifecycleState.RESUME and self.pairing:
            self.page.run_task(self._fetch)

    # ── connecting to the Mac ────────────────────────────────────────────────
    async def _route_changed(self, e):
        arrived = link.parse_pairing(getattr(e, "route", "") or "")
        if arrived:
            await self._offer(arrived)

    async def _offer(self, arrived):
        """A pairing link arrived. Already connected to another file: ask first (a link from
        anywhere else must not quietly replace yours)."""
        try:  # back to "/", so the same link can come again later (Flet ignores a repeated route)
            await self.page.push_route("/")
        except Exception:
            pass
        if not self.pairing or self.pairing["file"] == arrived["file"]:
            await self._pair(arrived)
            return

        async def replace(e):
            self.page.pop_dialog()
            await self._pair(arrived)

        p = self.p
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text("Connect to another copy?"),
            content=ft.Text(f"This phone is connected to “{self.pairing.get('name') or 'your Mac'}”. Connect it to "
                            f"“{arrived['name'] or 'the new one'}” instead? Only do this if the link came from "
                            "Daftarche on your own Mac.", color=p.text),
            actions=[ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                     ft.FilledButton("Connect", on_click=replace)]))

    async def _pair(self, arrived):
        """Connected by the QR code's link (or a pasted one): fetch this phone's copy."""
        self._generation += 1
        self.pairing = arrived
        self.disconnected = False
        await self.prefs.set("pairing", json.dumps({"v": "1", "f": arrived["file"], "k": arrived["key"],
                                                    "n": arrived["name"]}))
        link.forget_cache()
        self.snap = None
        self.fetching = False
        self.load()
        self.problem = "Getting your data from Daftarche on the Mac…"
        self.render()
        await self._fetch()

    async def _paste(self, e=None):
        arrived = link.parse_pairing(self._paste_field.value if self._paste_field else "")
        if not arrived:
            self._toast("That is not Daftarche's link: copy the whole link from the Mac (Copy Link).")
            return
        await self._offer(arrived)

    async def _forget(self, disconnected=False):
        """Not connected any more: the copy and the key are removed from the phone."""
        self._generation += 1
        self.fetching = False
        self.pairing = None
        self.disconnected = disconnected
        await self.prefs.set("pairing", "")
        link.forget_cache()
        self.snap = None
        self.load()
        self.render()

    async def _disconnect_here(self, e=None):
        await self._forget()

    # ── the frame ────────────────────────────────────────────────────────────
    def render(self):
        page, p = self.page, palette_for(self.theme_choice, self.page.platform_brightness)
        self.p = p
        page.theme = page.dark_theme = material_theme(p)
        page.theme_mode = ft.ThemeMode.DARK if p.bg == "#1e1c18" else ft.ThemeMode.LIGHT
        page.bgcolor = p.bg
        updated = self.snap.created.strftime("Updated %d %b, %H:%M") if self.snap and self.snap.created else ""
        page.appbar = ft.AppBar(
            title=ft.Column([ft.Text("Daftarche", size=20, weight=ft.FontWeight.BOLD, color=p.text),
                             ft.Text(updated, size=11, color=p.dim, visible=bool(updated))], spacing=0),
            bgcolor=p.bg, toolbar_height=60,
            actions=[ft.IconButton(ft.Icons.REFRESH, icon_color=p.dim, tooltip="Get the newest data",
                                   on_click=self._reload, visible=bool(self.pairing))])
        page.navigation_bar = ft.NavigationBar(
            selected_index=self.tab, bgcolor=p.surface, indicator_color=ft.Colors.with_opacity(0.3, p.accent),
            on_change=self._tab_changed,
            destinations=[ft.NavigationBarDestination(icon=i, selected_icon=s, label=n) for n, i, s in TABS])
        page.controls.clear()
        page.controls.append(ft.SafeArea(self._body(), expand=True))
        page.update()

    def _tab_changed(self, e):
        """A tab tapped in the bar."""
        self.nav.tab_chosen()
        self.tab = e.control.selected_index
        self.render()

    def _swiped(self, e):
        """A tab reached by swiping: only the bar follows (the pages are built already)."""
        index = int(e.data) if e.data is not None else e.control.selected_index
        if index == self.tab:
            return
        self.nav.tab_chosen()
        self.tab = index
        self.page.navigation_bar.selected_index = index
        self.page.navigation_bar.update()

    # ── Back (Android's button or gesture) ───────────────────────────────────
    def _state(self):
        """Where the person is now: restored when Back undoes a jump."""
        return copy.deepcopy({"tab": self.tab, "period": self.period, "tx_filters": self.tx_filters,
                              "tx_limit": self.tx_limit, "chart_kind": self.chart_kind,
                              "chart_account": self.chart_account, "open_category": self.open_category,
                              "chart_month": self.chart_month, "tx_range": self.tx_range})

    def _jump(self):
        """Call before going somewhere else from a tab (Show transactions, an account)."""
        self.nav.jumped(self._state())

    async def _back(self, e):
        action, state = self.nav.back(self.tab, time.monotonic())
        if action == EXIT:
            await e.control.confirm_pop(True)
            return
        await e.control.confirm_pop(False)
        if action == RESTORE:
            for key, value in state.items():
                setattr(self, key, value)
            self.render()
        elif action == DASHBOARD:
            self.tab = 0
            self.render()
        elif action == ASK_EXIT:
            self._toast("Press Back again to exit")

    def _reload(self, e=None):
        """⟳: the newest copy from the Mac, now."""
        if self.pairing:
            self.page.run_task(self._fetch, True)

    def _toast(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text), behavior=ft.SnackBarBehavior.FLOATING, duration=3000))

    def _body(self):
        if self.snap is None:  # not connected yet: the welcome, and Settings
            self._pager = None
            return self._settings() if self.tab == SETTINGS_TAB else self._welcome()
        # all five tabs, side by side: a swipe slides to the next one (the bar follows)
        self._period_rows = {}  # built afresh with the tabs
        self._pager = ft.PageView(self._tabs(), selected_index=self.tab, on_change=self._swiped, expand=True)
        return self._pager

    def _tabs(self):
        return [self._dashboard(), self._transactions(), self._charts(), self._accounts(), self._settings()]

    def _redraw(self):
        """Draw the tabs again in place, after a choice inside a tab (a period, a filter, a tapped
        category): each list keeps where it was scrolled to. render() builds new lists, which
        open at the top."""
        if self.snap is None or getattr(self, "_pager", None) is None:
            self.render()
            return
        for old, new in zip(self._pager.controls, self._tabs()):
            old.controls = new.controls
        self.page.update()

    def _sheet(self, content, **kwargs):
        """A sheet from the bottom whose content stays above Android's Back / Home buttons (Flet's
        own sheet keeps clear of the top and sides only); its background still reaches the edge."""
        return ft.BottomSheet(ft.SafeArea(content, avoid_intrusions_top=False, avoid_intrusions_left=False,
                                          avoid_intrusions_right=False), **kwargs)

    def _welcome(self):
        p = self.p
        self._paste_field = None
        if self.problem == NOT_PAIRED:
            title = "Your account book, on the phone"
            text = (DISCONNECTED if self.disconnected else
                    "Connect this phone to Daftarche on your Mac: there, open Settings › Phone › Connect a "
                    "Phone…, then point this phone's camera at the code it shows and tap the link.")
            self._paste_field = ft.TextField(label="Or paste the link from the Mac", dense=True, text_size=13,
                                             on_submit=self._paste)
            extra = [self._paste_field, ft.FilledButton("Connect", icon=ft.Icons.LINK, on_click=self._paste)]
        else:
            title = "Daftarche"
            text = self.problem
            extra = [ft.FilledButton("Try Again", icon=ft.Icons.REFRESH, on_click=self._reload,
                                     visible=not self.fetching)]
        return ft.Container(ft.Column([
            ft.Icon(ft.Icons.MENU_BOOK_ROUNDED, size=56, color=p.accent),
            ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=p.text, text_align=ft.TextAlign.CENTER),
            ft.Text(text, size=14, color=p.dim, text_align=ft.TextAlign.CENTER),
            *extra,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16, tight=True),
            padding=32, alignment=ft.Alignment.CENTER, expand=True)

    # ── shared pieces ────────────────────────────────────────────────────────
    def _page(self, controls):
        return ft.ListView(controls, padding=ft.Padding.only(left=16, right=16, top=4, bottom=BOTTOM_ROOM),
                           spacing=12, expand=True)

    def _card(self, content, padding=14, accent=None, on_click=None):
        p = self.p
        return ft.Container(content, bgcolor=p.surface, border_radius=14, padding=padding, on_click=on_click,
                            border=ft.Border.only(left=ft.BorderSide(4, accent)) if accent else None)

    def _heading(self, text, trailing=None):
        row = [ft.Text(text, size=15, weight=ft.FontWeight.BOLD, color=self.p.text, expand=True)]
        if trailing is not None:
            row.append(trailing)
        return ft.Row(row, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _periods(self, tab):
        p = self.p
        chips = []
        if tab == "Transactions" and self.tx_range:  # one month, from Charts: ✕ goes back to the chips
            chips.append(ft.Container(
                ft.Text(f"{self.tx_range[2]}  ✕", size=13, color="#ffffff", weight=ft.FontWeight.BOLD),
                bgcolor=p.accent, border_radius=16, padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                on_click=lambda e: self._set_period(tab, self.period[tab])))
        for name in PERIODS:
            chosen = self.period[tab] == name and not (tab == "Transactions" and self.tx_range)
            chips.append(ft.Container(
                ft.Text(name, size=13, color="#ffffff" if chosen else p.dim,
                        weight=ft.FontWeight.BOLD if chosen else None),
                bgcolor=p.accent if chosen else p.surface, border_radius=16,
                padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                on_click=lambda e, n=name: self._set_period(tab, n)))
        # the same row each time, with new chips: it stays scrolled where it was (a new row
        # started at the left, hiding the chip just tapped at the end)
        row = self._period_rows.get(tab)
        if row is None:
            row = self._period_rows[tab] = ft.Row(spacing=6, scroll=ft.ScrollMode.HIDDEN)
        row.controls = chips
        return row

    def _set_period(self, tab, name):
        self.period[tab] = name
        if tab == "Transactions":
            self.tx_limit = PAGE_SIZE
            self.tx_range = None
        if tab == "Charts":
            self.chart_month = None
        self._redraw()

    def _range(self, tab):
        if tab == "Transactions" and self.tx_range:
            return self.tx_range[0], self.tx_range[1]
        return period_range(self.period[tab], date.today())

    def _stat(self, label, value, colour):
        p = self.p
        return ft.Container(ft.Column([
            ft.Row([ft.Container(width=8, height=8, bgcolor=colour, border_radius=4),
                    ft.Text(label, size=12, color=p.dim)], spacing=6),
            ft.Text(value, size=17, weight=ft.FontWeight.BOLD, color=colour, no_wrap=True)], spacing=4),
            bgcolor=p.surface, border_radius=14, padding=12, expand=True)

    def _amount_text(self, tx, amount=None, size=15):
        p = self.p
        amount = tx["amount"] if amount is None else amount
        kind = tx["type"]
        if kind == "Expense":
            text, colour = money(-amount), p.expense if amount > 0 else p.income
        elif kind == "Income":
            text, colour = money(amount, sign=True), p.income if amount > 0 else p.expense
        else:
            text, colour = money(amount), p.transfer
        return ft.Text(text, size=size, weight=ft.FontWeight.BOLD, color=colour, no_wrap=True)

    def _badge(self, emoji, colour):
        p = self.p
        return ft.Container(ft.Text(emoji, size=17) if emoji else ft.Container(width=10, height=10, bgcolor=colour,
                                                                               border_radius=5),
                            width=38, height=38, border_radius=19, bgcolor=p.raised,
                            alignment=ft.Alignment.CENTER)

    # ── Dashboard ────────────────────────────────────────────────────────────
    def _dashboard(self):
        s, p = self.snap, self.p
        start, end = self._range("Dashboard")
        total = s.total_balance()
        accounts = [ft.Row([ft.Container(width=4, height=30, bgcolor=a["color"], border_radius=2),
                            ft.Text(a["name"], size=14, color=p.text, expand=True, no_wrap=True),
                            ft.Text(money(a["balance"]), size=14, weight=ft.FontWeight.BOLD,
                                    color=p.signed(a["balance"]))], spacing=10)
                    for a in s.accounts if a.get("visible", True)] if self.accounts_open else []
        top = self._card(ft.Column([
            ft.Row([ft.Column([ft.Text("Total Balance", size=13, color=p.dim),
                               ft.Text(money(total), size=30, weight=ft.FontWeight.BOLD, color=p.signed(total))],
                              spacing=2, expand=True),
                    ft.Icon(ft.Icons.EXPAND_LESS if self.accounts_open else ft.Icons.EXPAND_MORE, color=p.dim,
                            tooltip="Hide the accounts" if self.accounts_open else "Show the accounts")]),
            *([ft.Divider(height=14, color=p.border)] if accounts else []),
            *accounts], spacing=6), padding=16, on_click=self._toggle_accounts)

        sm = s.summary(start, end)
        stats = ft.Column([
            ft.Row([self._stat("Income", money(sm["income"]), p.income),
                    self._stat("Expense", money(sm["expense"]), p.expense)], spacing=10),
            ft.Row([self._stat("Net", money(sm["net"], sign=True), p.signed(sm["net"]) if sm["net"] else p.text),
                    self._stat("Transactions", f"{sm['count']:,}", p.transfer)], spacing=10)], spacing=10)

        kind = self.dash_kind
        rows = s.by_category(kind, start, end)
        colours = {c: PALETTE[i % len(PALETTE)] for i, (c, _) in enumerate(rows)}
        monthly = s.monthly(start, end)
        if len(monthly) <= 1:  # one month (This / Last Month): how it divides between categories, as in Charts
            month = monthly[0][0] if monthly else start[:7]
            shown = [(colours[c], v) for c, v in rows[:TOP_CATEGORIES]]
            rest = round(sum(v for _, v in rows[TOP_CATEGORIES:]), 2)
            if rest > 0:
                shown.append((p.dim, rest))
            chart = self._card(ft.Column([
                self._heading(f"{kind} in {long_month(month)}", self._kind_switch()),
                donut(p, shown, money(sm[kind.lower()]),
                      f"{len(rows)} categor{'y' if len(rows) == 1 else 'ies'}")],
                spacing=12))
        else:
            chart = self._card(ft.Column([
                self._heading("Income vs Expense"),
                legend(p, [(p.income, "Income"), (p.expense, "Expense")]),
                bar_chart(p, [month_label(m) for m, _, _ in monthly],
                          [(p.income, [i for _, i, _ in monthly]), (p.expense, [e for _, _, e in monthly])])],
                spacing=10))

        banner = self._update_banner()
        title = "Expenses by Category" if kind == "Expense" else "Income by Category"
        heading = None if len(monthly) <= 1 else self._heading(title, self._kind_switch())  # the switch, once
        return self._page([*([banner] if banner else []), top, self._periods("Dashboard"), stats, chart,
                           self._category_card(kind, start, end, title, colours=colours, heading=heading)])

    def _kind_switch(self):
        """Expense | Income, small: what the Dashboard's donut and list show."""
        p = self.p

        def chip(name):
            chosen = self.dash_kind == name
            return ft.Container(
                ft.Text(name, size=12, color="#ffffff" if chosen else p.dim,
                        weight=ft.FontWeight.BOLD if chosen else None),
                bgcolor=p.accent if chosen else p.raised, border_radius=12,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                on_click=lambda e, n=name: self._set_dash_kind(n))
        return ft.Row([chip("Expense"), chip("Income")], spacing=4, tight=True)

    def _set_dash_kind(self, kind):
        if kind != self.dash_kind:
            self.dash_kind = kind
            self._redraw()

    def _toggle_accounts(self, e=None):
        """The accounts under the Total Balance, shown or folded; remembered for next time."""
        self.accounts_open = not self.accounts_open
        self.page.run_task(self.prefs.set, "accounts_open", "1" if self.accounts_open else "")
        self._redraw()

    def _category_card(self, kind, start, end, title, account=None, expandable=False, colours=None,
                       heading=None):
        """``colours``: the chart's colours (a month of it keeps the period's); ``heading``: a
        control in place of the plain title."""
        s, p = self.snap, self.p
        rows = s.by_category(kind, start, end, account)
        own = {c: PALETTE[i % len(PALETTE)] for i, (c, _) in enumerate(rows)}
        colours = {c: (colours or {}).get(c, own[c]) for c, _ in rows}
        total = sum(v for _, v in rows if v > 0) or 1
        items = []
        for c, v in rows:
            name = s.category_name(c)
            icon = s.icon(c)
            head = ft.Row([ft.Container(width=10, height=10, bgcolor=colours[c], border_radius=5),
                           ft.Text(f"{icon} {name}".strip(), size=14, color=p.text, expand=True, no_wrap=True),
                           ft.Text(money(v), size=14, color=p.text, weight=ft.FontWeight.BOLD),
                           ft.Text(f"{v / total:.0%}", size=12, color=p.dim, width=36,
                                   text_align=ft.TextAlign.RIGHT)], spacing=8)
            block = [head, share_bar(p, v / total, colours[c])]
            if expandable and self.open_category == c:
                block.append(self._subcategories(c, kind, start, end, account, v))
            items.append(ft.Container(ft.Column(block, spacing=6), padding=ft.Padding.symmetric(vertical=4),
                                      on_click=lambda e, c=c: self._toggle_category(c) if expandable
                                      else self._show_category(c, kind)))
        if not items:
            items = [ft.Text("Nothing in this period", size=13, color=p.dim)]
        return self._card(ft.Column([heading or self._heading(title), *items], spacing=8))

    def _subcategories(self, category, kind, start, end, account, total):
        s, p = self.snap, self.p
        rows = s.by_subcategory(category, kind, start, end, account)
        lines = [ft.Row([ft.Text(s.subcategory_name(sub) or "—", size=13, color=p.dim, expand=True),
                         ft.Text(money(v), size=13, color=p.dim),
                         ft.Text(f"{v / (total or 1):.0%}", size=12, color=p.dim, width=36,
                                 text_align=ft.TextAlign.RIGHT)])
                 for sub, v in rows]
        lines.append(ft.TextButton("Show transactions", icon=ft.Icons.ARROW_FORWARD,
                                   on_click=lambda e: self._show_category(category, kind)))
        return ft.Container(ft.Column(lines, spacing=4), padding=ft.Padding.only(left=18, top=4))

    def _toggle_category(self, category):
        self.open_category = None if self.open_category == category else category
        self._redraw()

    def _show_category(self, category, kind):
        """The transactions of a category, in Transactions, over the same period."""
        self._jump()
        source = TABS[self.tab][0]
        self.period["Transactions"] = self.period.get(source, "This Month")
        self.tx_range = None
        if source == "Charts" and self.chart_month:  # a month tapped in the bars: that month only
            self.tx_range = (*month_range(self.chart_month), month_label(self.chart_month))
        self.tx_filters = no_filters(kind=kind, account=self.chart_account if source == "Charts" else None,
                                     category=category)
        self.tx_limit = PAGE_SIZE
        self._jump_to_transactions()

    def _jump_to_transactions(self):
        self.tab = 1
        self.render()

    # ── Transactions ─────────────────────────────────────────────────────────
    def _transactions(self):
        s, p, f = self.snap, self.p, self.tx_filters
        start, end = self._range("Transactions")
        txs = s.filter(start, end, f["kind"], f["account"], f["category"], f["tag"], f["text"], f["merchant"])

        search = ft.TextField(value=f["text"], hint_text="Search", prefix_icon=ft.Icons.SEARCH, dense=True,
                              border_radius=24, filled=True, fill_color=p.surface, border_color=p.surface,
                              expand=True, on_submit=self._search, on_blur=self._search,
                              content_padding=ft.Padding.symmetric(horizontal=12, vertical=8))
        n_filters = sum(1 for k in ("kind", "account", "category", "merchant", "tag") if f[k] is not None)
        filter_btn = ft.IconButton(ft.Icons.TUNE, icon_color=p.accent if n_filters else p.dim,
                                   badge=str(n_filters) if n_filters else None, on_click=self._filter_sheet)
        chips = self._filter_chips()

        income = sum(t["amount"] for t in txs if t["type"] == "Income")
        expense = sum(t["amount"] for t in txs if t["type"] == "Expense")
        summary = ft.Text(f"{len(txs):,} transaction{'s' if len(txs) != 1 else ''}  ·  "
                          f"in {money(income)}  ·  out {money(expense)}", size=12, color=p.dim)

        rows, last_date = [], None
        for tx in txs[:self.tx_limit]:
            if tx["date"] != last_date:
                last_date = tx["date"]
                d = date.fromisoformat(tx["date"])
                rows.append(ft.Text(d.strftime("%a, %d %b %Y"), size=12, weight=ft.FontWeight.BOLD, color=p.dim))
            rows.append(self._tx_row(tx))
        if len(txs) > self.tx_limit:
            rows.append(ft.TextButton(f"Show more ({len(txs) - self.tx_limit:,} left)",
                                      on_click=self._more))
        if not txs:
            rows.append(ft.Text("No transactions", size=14, color=p.dim))
        return self._page([ft.Row([search, filter_btn], spacing=4), self._periods("Transactions"),
                           *([chips] if chips else []), summary, *rows])

    def _filter_chips(self):
        s, p, f = self.snap, self.p, self.tx_filters
        names = {"kind": f["kind"], "account": s.account_name(f["account"]) if f["account"] is not None else None,
                 "category": s.category_name(f["category"]) if f["category"] is not None else None,
                 "merchant": f["merchant"],
                 "tag": s.tag.get(f["tag"], {}).get("name") if f["tag"] is not None else None}
        chips = [ft.Container(ft.Row([ft.Text(v, size=12, color=p.text),
                                      ft.Icon(ft.Icons.CLOSE, size=14, color=p.dim)], spacing=4, tight=True),
                              bgcolor=p.raised, border_radius=14, padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                              on_click=lambda e, k=k: self._clear_filter(k))
                 for k, v in names.items() if v]
        return ft.Row(chips, spacing=6, wrap=True) if chips else None

    def _clear_filter(self, key):
        self.tx_filters[key] = None
        self._redraw()

    def _search(self, e):
        if e.control.value != self.tx_filters["text"]:
            self.tx_filters["text"] = e.control.value
            self.tx_limit = PAGE_SIZE
            self._redraw()

    def _more(self, e):
        self.tx_limit += PAGE_SIZE
        self._redraw()

    def _tx_row(self, tx):
        s, p = self.snap, self.p
        if tx["type"] == "Transfer":
            sub = f"{s.account_name(tx['account']) or '—'} → {s.account_name(tx['to_account']) or '—'}"
            if tx.get("transfer") == "loan":
                sub = f"Loan  ·  {sub}"
        else:
            cat = "Split" if tx.get("parts") else s.category_name(tx["category"])
            sub_name = "" if tx.get("parts") else s.subcategory_name(tx["subcategory"])
            sub = f"{cat} › {sub_name}" if sub_name else cat
        emoji = "✂️" if tx.get("parts") else s.icon(tx["category"], tx["subcategory"])
        # the account on a line of its own: sharing the category's line, it was cut off
        account = "" if tx["type"] == "Transfer" else s.account_name(tx["account"]) or ""
        return ft.Container(ft.Row([
            self._badge(emoji, p.kind(tx["type"])),
            ft.Column([ft.Text(s.title(tx), size=14, color=p.text, no_wrap=True,
                               overflow=ft.TextOverflow.ELLIPSIS),
                       ft.Text(sub, size=12, color=p.dim, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                       ft.Text(account, size=11, color=p.dim, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                               visible=bool(account))],
                      spacing=1, expand=True),
            self._amount_text(tx)], spacing=10),
            bgcolor=p.surface, border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            on_click=lambda e, t=tx: self._tx_sheet(t))

    def _tx_sheet(self, tx):
        s, p = self.snap, self.p

        def line(label, value):
            return ft.Row([ft.Text(label, size=13, color=p.dim, width=96),
                           ft.Text(value, size=14, color=p.text, expand=True, selectable=True)],
                          vertical_alignment=ft.CrossAxisAlignment.START)

        d = date.fromisoformat(tx["date"])
        items = [ft.Text(s.title(tx), size=19, weight=ft.FontWeight.BOLD, color=p.text),
                 self._amount_text(tx, size=24),
                 ft.Divider(color=p.border),
                 line("Date", d.strftime("%A, %d %B %Y")),
                 line("Type", {"loan": "Transfer › Loan", "unmatched": "Transfer (not matched)"}.get(
                     tx.get("transfer"), tx["type"]))]
        if tx["type"] == "Transfer":
            items += [line("From", s.account_name(tx["account"]) or "—"),
                      line("To", s.account_name(tx["to_account"]) or "—")]
        else:
            items.append(line("Account", s.account_name(tx["account"])))
        if tx.get("parts"):
            items.append(ft.Text("Split into", size=13, color=p.dim))
            for part in tx["parts"]:
                cat = s.category_name(part["category"])
                sub = s.subcategory_name(part["subcategory"])
                items.append(ft.Row([
                    ft.Text(f"{cat} › {sub}" if sub else cat, size=14, color=p.text, expand=True),
                    self._amount_text(tx, part["amount"], size=14)]))
                if part.get("note"):
                    items.append(ft.Text(part["note"], size=12, color=p.dim, italic=True))
        else:
            cat, sub = s.category_name(tx["category"]), s.subcategory_name(tx["subcategory"])
            items.append(line("Category", f"{cat} › {sub}" if sub else cat))
        if tx.get("merchant"):
            items.append(line("Merchant", tx["merchant"]))
        if tx.get("name") and tx.get("name") != tx.get("merchant"):
            items.append(line("Bank text", tx["name"]))
        if tx.get("note"):
            items.append(line("Note", tx["note"]))
        if tx.get("tags"):
            items.append(line("Tags", ", ".join(s.tag[t]["name"] for t in tx["tags"] if t in s.tag)))
        self.page.show_dialog(self._sheet(
            ft.Container(ft.Column(items, spacing=8, tight=True, scroll=ft.ScrollMode.AUTO),
                         padding=ft.Padding.only(left=20, right=20, top=8, bottom=28)),
            bgcolor=p.surface, show_drag_handle=True))

    def _filter_sheet(self, e):
        s, p, f = self.snap, self.p, self.tx_filters

        def dropdown(label, key, options, search=False):
            current = f[key]
            return ft.Dropdown(label=label, value="" if current is None else str(current), expand=True,
                               editable=search, enable_filter=search, menu_height=360 if search else None,
                               options=[ft.DropdownOption(key="", text="All")] +
                               [ft.DropdownOption(key=str(k), text=t) for k, t in options],
                               on_select=lambda ev, k=key: self._set_filter(k, ev.control.value))

        kinds = [(k, k) for k in ("Income", "Expense", "Transfer")]
        accounts = [(a["id"], a["name"]) for a in s.accounts]
        categories = [(c["id"], f"{c['name']}  ({c['type'] or 'any'})") for c in
                      sorted(s.categories, key=lambda c: (c["type"], c["name"]))]
        tags = [(t["id"], t["name"]) for t in s.tags]
        sheet = self._sheet(ft.Container(ft.Column([
            ft.Text("Show only", size=17, weight=ft.FontWeight.BOLD, color=p.text),
            dropdown("Type", "kind", kinds), dropdown("Account", "account", accounts),
            dropdown("Category", "category", categories),
            dropdown("Merchant", "merchant", [(NO_MERCHANT, NO_MERCHANT)] + [(m, m) for m in s.merchants()],
                     search=True),  # many: typing narrows the list
            *([dropdown("Tag", "tag", tags)] if tags else []),
            ft.Row([ft.TextButton("Clear all", on_click=lambda ev: self._clear_filters(sheet)),
                    ft.FilledButton("Done", on_click=lambda ev: self.page.pop_dialog())],
                   alignment=ft.MainAxisAlignment.END)],
            spacing=12, tight=True), padding=ft.Padding.only(left=20, right=20, top=8, bottom=24)),
            bgcolor=p.surface, show_drag_handle=True, on_dismiss=lambda ev: self._redraw())
        self.page.show_dialog(sheet)

    def _set_filter(self, key, value):
        if key in ("kind", "merchant"):
            self.tx_filters[key] = value or None
        else:
            self.tx_filters[key] = int(value) if value else None
        self.tx_limit = PAGE_SIZE

    def _clear_filters(self, sheet):
        self.tx_filters = no_filters(text=self.tx_filters["text"])
        self.page.pop_dialog()

    # ── Charts ───────────────────────────────────────────────────────────────
    def _charts(self):
        s, p = self.snap, self.p
        start, end = self._range("Charts")
        kind, account = self.chart_kind, self.chart_account

        kinds = ft.SegmentedButton(
            segments=[ft.Segment(value=k, label=ft.Text(k)) for k in ("Expense", "Income")],
            selected=[kind], show_selected_icon=False, on_change=self._set_chart_kind)
        accounts = ft.Dropdown(value="" if account is None else str(account), dense=True, width=170,
                               options=[ft.DropdownOption(key="", text="All accounts")] +
                               [ft.DropdownOption(key=str(a["id"]), text=a["name"]) for a in s.accounts],
                               on_select=self._set_chart_account)

        months, per_cat = s.monthly_by_category(kind, start, end, account)
        order = [c for c, _ in s.by_category(kind, start, end, account)]
        colours = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(order)}
        groups = [(colours[c], per_cat[c]) for c in order[:TOP_CATEGORIES] if c in per_cat]
        rest = [c for c in per_cat if c not in order[:TOP_CATEGORIES]]
        if rest:
            groups.append((p.dim, [round(sum(per_cat[c][i] for c in rest), 2) for i in range(len(months))]))
        monthly_total = [round(sum(v[i] for _, v in groups), 2) for i in range(len(months))]
        if self.chart_month not in months:
            self.chart_month = None

        if len(months) == 1:  # one month: how it divides between categories
            chart = self._card(ft.Column([
                self._heading(f"{kind} in {long_month(months[0])}"),
                donut(p, [(c, v[0]) for c, v in groups], money(monthly_total[0]), f"{len(order)} categories")],
                spacing=12))
        else:
            average = sum(monthly_total) / len(monthly_total) if monthly_total else 0
            picked = months.index(self.chart_month) if self.chart_month else None
            chart = self._card(ft.Column([
                self._heading(f"Monthly {kind}", ft.Text(f"average {money(average)}", size=12, color=p.dim)),
                bar_chart(p, [month_label(m) for m in months], groups, height=190, bar_width=11, stacked=True,
                          selected=picked, on_tap=lambda i: self._pick_month(months[i]))],
                spacing=12))

        title, heading = "By Category  (tap for details)", None
        if self.chart_month:  # the tapped month's categories, in the period's colours
            start, end = month_range(self.chart_month)
            heading = ft.Row([
                ft.Text("By Category", size=15, weight=ft.FontWeight.BOLD, color=p.text, expand=True),
                ft.Container(ft.Text(f"{long_month(self.chart_month)}  ✕", size=12, color="#ffffff",
                                     weight=ft.FontWeight.BOLD),
                             bgcolor=p.accent, border_radius=12,
                             padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                             on_click=lambda e: self._pick_month(self.chart_month))])
        return self._page([ft.Row([kinds, accounts], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                           self._periods("Charts"), chart,
                           self._category_card(kind, start, end, title, account, expandable=True,
                                               colours=colours, heading=heading)])

    def _pick_month(self, month):
        """A month tapped in the bars: its categories below; tapped again (or ✕): the whole period."""
        self.chart_month = None if self.chart_month == month else month
        self.open_category = None
        self._redraw()

    def _set_chart_kind(self, e):
        self.chart_kind = list(e.control.selected)[0]
        self.open_category = None
        self.chart_month = None
        self._redraw()

    def _set_chart_account(self, e):
        self.chart_account = int(e.control.value) if e.control.value else None
        self._redraw()

    # ── Accounts ─────────────────────────────────────────────────────────────
    def _accounts(self):
        s, p = self.snap, self.p
        start, end = self._range("Accounts")
        months, series = s.balance_series(start, end)
        shown = s.shown_accounts()
        lines = [(a["color"], series.get(a["id"], [])) for a in shown]
        # the legend is the list: each account's colour, name, balance and change; a tap shows its transactions
        rows = []
        for a in shown:
            vs = series.get(a["id"], [])
            change = vs[-1] - vs[0] if len(vs) > 1 else None
            rows.append(ft.Container(ft.Row([
                ft.Container(width=10, height=10, bgcolor=a["color"], border_radius=5),
                ft.Column([ft.Text(a["name"], size=14, color=p.text, no_wrap=True,
                                   overflow=ft.TextOverflow.ELLIPSIS),
                           ft.Text(f"{money(change, sign=True)} in this period", size=12, color=p.dim,
                                   visible=change is not None)], spacing=1, expand=True),
                ft.Text(money(a["balance"]), size=15, weight=ft.FontWeight.BOLD, color=p.signed(a["balance"]))],
                spacing=10), padding=ft.Padding.symmetric(vertical=6),
                on_click=lambda e, i=a["id"]: self._show_account(i)))
        chart = self._card(ft.Column([
            self._heading("Balance by Month"),
            LineChart(p, [month_label(m) for m in months], lines),
            ft.Divider(height=8, color=p.border),
            *rows], spacing=6))

        return self._page([self._periods("Accounts"), chart, self._loans()])

    def _show_account(self, account_id):
        self._jump()
        self.tx_range = None
        self.tx_filters = no_filters(account=account_id)
        self.tx_limit = PAGE_SIZE
        self._jump_to_transactions()

    def _loans(self):
        s, p = self.snap, self.p
        if not s.loans:
            return ft.Container()
        you_owe, owed = s.loan_totals()
        rows = [ft.Row([self._stat("Owed to you", money(owed), p.income),
                        self._stat("You owe", money(you_owe), p.expense)], spacing=10)]
        for e in s.loans:
            b = e["balance"]
            state = "owes you" if b > 0 else "you owe" if b < 0 else "settled"
            last = date.fromisoformat(e["last"]).strftime("%d %b %Y") if e.get("last") else ""
            rows.append(ft.Row([
                ft.Column([ft.Text(e["person"] or "No person", size=14, color=p.text),
                           ft.Text(f"{state}  ·  last {last}" if last else state, size=12, color=p.dim)],
                          spacing=1, expand=True),
                ft.Text(money(abs(b)), size=15, weight=ft.FontWeight.BOLD,
                        color=p.income if b > 0 else p.expense if b < 0 else p.dim)]))
        return self._card(ft.Column([self._heading("Loans"), *rows], spacing=10))

    # ── Updates ──────────────────────────────────────────────────────────────
    async def _daily_update_check(self):
        """Once a day, quietly: is there a newer app? (Shown on the Dashboard.)"""
        today = date.today().isoformat()
        if self.page.web or (await self.prefs.get("update_checked")) == today:
            return
        try:
            self.update_info = await asyncio.to_thread(check_for_update, __version__)
        except (OSError, ValueError):
            return
        await self.prefs.set("update_checked", today)
        if self.update_info:
            self.render()

    async def _check_updates_now(self, e=None):
        try:
            self.update_info = await asyncio.to_thread(check_for_update, __version__)
        except (OSError, ValueError) as exc:
            self._toast(f"Could not reach GitHub: {exc}")
            return
        if self.update_info:
            self.render()  # Settings › Updates (and the Dashboard) offer it
        else:
            self._toast(f"Daftarche {__version__} is the newest version.")

    def _update_banner(self):
        info, p = self.update_info, self.p
        if not info:
            return None
        notes = info["notes"].splitlines()
        return self._card(ft.Column([
            ft.Text(f"Daftarche {info['version']} is available", size=15, weight=ft.FontWeight.BOLD, color=p.text),
            ft.Text("\n".join(notes[:6]), size=12, color=p.dim, visible=bool(notes)),
            ft.Text("Download it, then open the file to install it over this one: the connection to "
                    "your Mac and your settings stay.", size=12, color=p.dim),
            ft.Row([ft.TextButton("Later", on_click=self._dismiss_update),
                    ft.FilledButton("Download", icon=ft.Icons.DOWNLOAD, on_click=self._download_update)],
                   alignment=ft.MainAxisAlignment.END)], spacing=6), accent=p.accent)

    def _dismiss_update(self, e=None):
        self.update_info = None
        self.render()

    async def _download_update(self, e=None):
        await ft.UrlLauncher().launch_url(self.update_info["apk"], mode=ft.LaunchMode.EXTERNAL_APPLICATION)

    # ── Settings (the last tab) ──────────────────────────────────────────────
    def _section(self, title, *controls, note=None):
        """A part of Settings: its title, a short note under it, then its controls."""
        p = self.p
        head = [ft.Text(title, size=15, weight=ft.FontWeight.W_600, color=p.text)]
        if note:
            head.append(ft.Text(note, size=13, color=p.dim))
        return ft.Column([ft.Column(head, spacing=2), *controls], spacing=10)

    def _settings(self):
        s, p = self.snap, self.p
        name = (self.pairing or {}).get("name") or "this phone"
        connection = self._section(
            "Connection",
            ft.Text(f"Connected to Daftarche on the Mac as “{name}”." if self.pairing else "Not connected.",
                    size=14, color=p.text),
            ft.Row([ft.OutlinedButton("Get the Newest Data", icon=ft.Icons.REFRESH, on_click=self._reload),
                    ft.OutlinedButton("Disconnect", icon=ft.Icons.LINK_OFF, on_click=self._disconnect_here)],
                   wrap=True, visible=bool(self.pairing)),
            note="The Mac sends a new copy about a minute after each change; the app gets it when opened.")
        appearance = self._section(
            "Appearance",
            ft.SegmentedButton(segments=[ft.Segment(value=k, label=ft.Text(label), icon=icon)
                                         for k, label, icon in THEME_CHOICES],
                               selected=[self.theme_choice], show_selected_icon=False, on_change=self._set_theme),
            note="Phone: light or dark, as the phone is set.")
        info = self.update_info
        updates = self._section(
            "Updates",
            ft.Text(f"Daftarche {info['version']} is available: download it, then open the file to install it "
                    "over this one." if info else f"This is version {__version__}.", size=14, color=p.text),
            ft.FilledButton("Download", icon=ft.Icons.DOWNLOAD, on_click=self._download_update, visible=bool(info)),
            ft.OutlinedButton("Check for Updates", icon=ft.Icons.SYNC, on_click=self._check_updates_now),
            note="New versions come from this project's releases on GitHub.")
        updates.visible = not self.page.web
        rows = [("App", __version__)]
        if s and s.app_version:
            rows.append(("Data from", f"Daftarche {s.app_version} on the Mac"))
        about = self._section(
            "About",
            *[ft.Row([ft.Text(k, size=14, color=p.dim), ft.Text(v, size=14, color=p.text)],
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN) for k, v in rows],
            ft.Text("By Vahid Anari · MIT License", size=14, color=p.text),
            ft.Text("Read-only: nothing here changes your data.", size=13, color=p.dim))
        return ft.ListView([connection, appearance, updates, about], spacing=22, expand=True,
                           padding=ft.Padding.only(left=16, right=16, top=8, bottom=BOTTOM_ROOM))

    async def _set_theme(self, e):
        self.theme_choice = list(e.control.selected)[0]
        await self.prefs.set("theme", self.theme_choice)
        self.render()


async def main(page: ft.Page):
    await PhoneApp(page).start()
