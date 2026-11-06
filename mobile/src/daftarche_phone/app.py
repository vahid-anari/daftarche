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
from .snapshot import (MONTHS, NO_MERCHANT, PALETTE, PERIODS, Snapshot, SnapshotError, custom_label,
                       custom_period, money, month_label, period_range, step_period)
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
FILTER_ROWS = (("account", "Account", ft.Icons.ACCOUNT_BALANCE_OUTLINED),
               ("category", "Category", ft.Icons.CATEGORY_OUTLINED),
               ("subcategory", "Subcategory", ft.Icons.ACCOUNT_TREE_OUTLINED),
               ("merchant", "Merchant", ft.Icons.STOREFRONT_OUTLINED),
               ("tag", "Tag", ft.Icons.SELL_OUTLINED))
"""The "Show only" page's lists, in order: (filter, title, icon)."""
SEARCHED = {"category", "subcategory", "merchant"}
"""The lists long enough for a search field above them."""
TOP_CATEGORIES = 7
"""Categories of their own in the stacked bars and the donut; the rest are "Other"."""


FILTERS = ("kind", "account", "category", "subcategory", "merchant", "tag")
"""Transactions' "Show only" choices: each a set of values (empty: all)."""


def no_filters(text="", **chosen):
    """Transactions' "Show only" choices, all off but ``chosen`` (a value, or several)."""
    filters = {key: set() for key in FILTERS}
    for key, value in chosen.items():
        if value is not None:
            filters[key] = set(value) if isinstance(value, (set, frozenset, list, tuple)) else {value}
    filters["text"] = text
    return filters


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
        self.chart_account = set()  # the Charts' accounts (none: all)
        self.chart_month = None  # a month tapped in the Charts bars ("2026-09"): its categories below
        self.custom = {}  # a tab's period chosen in Custom… (or a month from Charts): {mode, start, end}
        self.filter_view = None  # Transactions' "Show only" page: "main", or the list of one filter
        self.filter_search = ""  # what is typed above that list
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
                              "chart_month": self.chart_month, "custom": self.custom})

    def _jump(self):
        """Call before going somewhere else from a tab (Show transactions, an account)."""
        self.nav.jumped(self._state())

    async def _back(self, e):
        if self.tab == 1 and self.filter_view:  # the filter page: one step up, choices kept
            await e.control.confirm_pop(False)
            self._filter_up()
            return
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
        transactions = self._filter_page() if self.filter_view == "main" else \
            self._filter_list(self.filter_view) if self.filter_view else self._transactions()
        return [self._dashboard(), transactions, self._charts(), self._accounts(), self._settings()]

    def _redraw(self):
        """Draw the tabs again in place, after a choice inside a tab (a period, a filter, a tapped
        category): each list keeps where it was scrolled to. render() builds new lists, which
        open at the top."""
        if self.snap is None or getattr(self, "_pager", None) is None:
            self.render()
            return
        for i, (old, new) in enumerate(zip(self._pager.controls, self._tabs())):
            if old.data == new.data == "frame":  # the head's and the list's rows only: both keep their place
                old.controls[0].content.controls = new.controls[0].content.controls
                old.controls[1].controls = new.controls[1].controls
            elif type(old) is type(new) and old.data == new.data and isinstance(old, ft.ListView):
                old.controls = new.controls
            else:  # another kind of page (Transactions ↔ its filter page)
                self._pager.controls[i] = new
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

    def _frame(self, head, body):
        """A tab whose ``head`` (its period, search, totals) stays at the top while ``body`` scrolls."""
        top = ft.Container(ft.Column(head, spacing=12, tight=True),
                           padding=ft.Padding.only(left=16, right=16, top=4, bottom=8))
        return ft.Column([top, self._page(body)], spacing=0, expand=True, data="frame")

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
        custom = self.custom.get(tab)
        if custom:  # ‹ Sep 2026 › ✕ (a range: its days ✕); the name opens Custom… again
            chips.append(self._custom_chip(tab, custom))
        for name in PERIODS:
            chosen = self.period[tab] == name and not custom
            chips.append(ft.Container(
                ft.Text(name, size=13, color="#ffffff" if chosen else p.dim,
                        weight=ft.FontWeight.BOLD if chosen else None),
                bgcolor=p.accent if chosen else p.surface, border_radius=16,
                padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                on_click=lambda e, n=name: self._set_period(tab, n)))
        chips.append(ft.Container(ft.Text("Custom…", size=13, color=p.dim), bgcolor=p.surface, border_radius=16,
                                  padding=ft.Padding.symmetric(horizontal=12, vertical=7),
                                  on_click=lambda e: self._period_picker(tab)))
        # the same row each time, with new chips: it stays scrolled where it was (a new row
        # started at the left, hiding the chip just tapped at the end)
        row = self._period_rows.get(tab)
        if row is None:
            row = self._period_rows[tab] = ft.Row(spacing=6, scroll=ft.ScrollMode.HIDDEN)
        row.controls = chips
        return row

    def _custom_chip(self, tab, custom):
        p = self.p
        white = "#ffffff"

        def part(content, on_click, padding):
            return ft.Container(content, on_click=on_click, padding=padding)

        def arrow(icon, n):
            stepped = step_period(custom, n)
            ok = self._period_has_room(stepped)
            return part(ft.Icon(icon, size=18, color=white if ok else ft.Colors.with_opacity(0.35, white)),
                        (lambda e: self._set_custom(tab, stepped)) if ok else None,
                        ft.Padding.symmetric(horizontal=6, vertical=6))

        label = part(ft.Text(custom_label(custom), size=13, color=white, weight=ft.FontWeight.BOLD),
                     lambda e: self._period_picker(tab), ft.Padding.symmetric(horizontal=4, vertical=7))
        steps = custom["mode"] in ("month", "year")
        parts = [arrow(ft.Icons.CHEVRON_LEFT, -1), label, arrow(ft.Icons.CHEVRON_RIGHT, 1)] if steps else \
            [ft.Container(width=8), label]
        parts += [ft.Container(width=1, height=18, bgcolor=ft.Colors.with_opacity(0.35, white)),
                  part(ft.Icon(ft.Icons.CLOSE, size=18, color=white), lambda e: self._set_custom(tab, None),
                       ft.Padding.only(left=6, right=8, top=6, bottom=6))]
        return ft.Container(ft.Row(parts, spacing=0, tight=True), bgcolor=p.accent, border_radius=16)

    def _period_has_room(self, period):
        """A month or year to step to: not after this one, not before the first transaction."""
        first = self.snap.first_date() if self.snap else None
        return period["start"] <= date.today().isoformat() and (first is None or period["end"] >= first)

    def _set_period(self, tab, name):
        self.period[tab] = name
        self.custom.pop(tab, None)
        self._period_changed(tab)

    def _set_custom(self, tab, period):
        """A period chosen in Custom… (or stepped to with ‹ ›); None: back to the chips."""
        if period:
            self.custom[tab] = period
        else:
            self.custom.pop(tab, None)
        self._period_changed(tab)

    def _period_changed(self, tab):
        if tab == "Transactions":
            self.tx_limit = PAGE_SIZE
        if tab == "Charts":
            self.chart_month = None
            self.open_category = None
        self._redraw()

    def _range(self, tab):
        custom = self.custom.get(tab)
        if custom:
            return custom["start"], custom["end"]
        return period_range(self.period[tab], date.today())

    # ── Custom…: a month, a year, or from one day to another ─────────────────
    def _period_picker(self, tab, mode=None, year=None):
        s, p = self.snap, self.p
        custom = self.custom.get(tab)
        mode = mode or (custom["mode"] if custom else "month")
        today = date.today()
        first = date.fromisoformat(s.first_date()) if s.first_date() else today
        year = year or (int(custom["start"][:4]) if custom else today.year)
        year = min(max(year, first.year), today.year)
        has = s.months_with_data()

        def segment(name, key):
            on = key == mode
            return ft.Container(ft.Text(name, size=14, color="#ffffff" if on else p.text,
                                        weight=ft.FontWeight.BOLD if on else None),
                                bgcolor=p.accent if on else None, border_radius=16, expand=True,
                                alignment=ft.Alignment.CENTER, padding=ft.Padding.symmetric(vertical=8),
                                on_click=None if on else lambda e: self._switch_picker(tab, key, year))

        def cell(text, period, there, on):
            return ft.Container(
                ft.Text(text, size=15, color="#ffffff" if on else p.text if there else p.border,
                        weight=ft.FontWeight.BOLD if on else None),
                bgcolor=p.accent if on else p.raised if there else None, border_radius=12,
                alignment=ft.Alignment.CENTER, height=48, col=3,
                on_click=(lambda e: self._pick_period(tab, period)) if there else None)

        if mode == "month":
            cells = []
            for m in range(1, 13):
                key = f"{year}-{m:02d}"
                period = custom_period("month", key)
                on = bool(custom) and custom["mode"] == "month" and custom["start"] == period["start"]
                cells.append(cell(MONTHS[m - 1][:3], period, key in has, on))

            def year_arrow(icon, n):
                ok = first.year <= year + n <= today.year
                return ft.IconButton(icon, icon_color=p.text if ok else p.border, disabled=not ok,
                                     on_click=lambda e: self._switch_picker(tab, "month", year + n))
            choose = [ft.Row([year_arrow(ft.Icons.CHEVRON_LEFT, -1),
                              ft.Text(str(year), size=18, weight=ft.FontWeight.BOLD, color=p.text, expand=True,
                                      text_align=ft.TextAlign.CENTER),
                              year_arrow(ft.Icons.CHEVRON_RIGHT, 1)]),
                      ft.ResponsiveRow(cells, spacing=8, run_spacing=8)]
        elif mode == "range":
            now = custom_label(custom) if custom and custom["mode"] == "range" else "Any days you choose"
            choose = [ft.Text(now, size=15, color=p.text),
                      ft.Row([ft.FilledButton("Choose the days…", icon=ft.Icons.DATE_RANGE,
                                              on_click=lambda e: self._open_range(tab, custom, first, today))],
                             alignment=ft.MainAxisAlignment.END)]
        else:
            years = {int(m[:4]) for m in has}
            cells = []
            for y in range(today.year, first.year - 1, -1):
                period = custom_period("year", y)
                on = bool(custom) and custom["mode"] == "year" and custom["start"] == period["start"]
                cells.append(cell(str(y), period, y in years, on))
            choose = [ft.ResponsiveRow(cells, spacing=8, run_spacing=8)]

        tabs = ft.Container(ft.Row([segment("Month", "month"), segment("Year", "year"),
                                    segment("From – to", "range")], spacing=0),
                            bgcolor=p.raised, border_radius=18, padding=3)
        content = ft.Container(ft.Column([ft.Text("Choose a period", size=17, weight=ft.FontWeight.BOLD,
                                                  color=p.text), tabs, *choose], spacing=14, tight=True),
                               padding=ft.Padding.only(left=20, right=20, top=8, bottom=24))
        sheet = getattr(self, "_picker_sheet", None)
        if sheet is not None and getattr(self, "_picker_open", False):
            sheet.content.content = content  # another year or kind: the same sheet, new inside
            sheet.update()
            return
        self._picker_sheet = self._sheet(content, bgcolor=p.surface, show_drag_handle=True,
                                         on_dismiss=self._picker_closed)
        self._picker_open = True
        self.page.show_dialog(self._picker_sheet)

    def _picker_closed(self, e=None):
        self._picker_open = False

    def _switch_picker(self, tab, mode, year):
        self._period_picker(tab, mode, year)

    def _close_picker(self):
        """Closes this sheet only (pop_dialog would close whatever is on top, a message too)."""
        if getattr(self, "_picker_open", False):
            self._picker_open = False
            self._picker_sheet.open = False
            self._picker_sheet.update()

    def _open_range(self, tab, custom, first, today):
        self._close_picker()
        self._range_picker(tab, custom, first, today)

    def _pick_period(self, tab, period):
        self._close_picker()
        self._set_custom(tab, period)

    def _range_picker(self, tab, custom, first, today):
        """From – to: Android's own calendar for two days."""
        start = date.fromisoformat(custom["start"]) if custom else today.replace(day=1)
        end = date.fromisoformat(custom["end"]) if custom else today
        first = min(first, today)
        start, end = min(max(start, first), today), min(max(end, first), today)

        def day(value):  # Flet sends the day as a time in UTC: back to the phone's own day
            if getattr(value, "tzinfo", None) is not None:
                value = value.astimezone()
            return value.date() if hasattr(value, "date") else value

        def chosen(e):
            a, b = e.control.start_value, e.control.end_value
            if a and b:
                self._set_custom(tab, custom_period("range", (day(a), day(b))))
        self.page.show_dialog(ft.DateRangePicker(
            start_value=start, end_value=min(end, today), first_date=first, last_date=today,
            help_text="Choose the first and the last day", on_change=chosen))

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

    def _badge(self, emoji, colour, image=None, size=38):
        """The round mark at the start of a row: a logo or picture (on white, as on the desktop),
        else the emoji, else a dot in the row's colour."""
        p = self.p
        if image:
            inner = round(size * 0.74)
            return ft.Container(ft.Image(src=image, fit=ft.BoxFit.CONTAIN, width=inner, height=inner),
                                width=size, height=size, border_radius=size / 2, bgcolor="#ffffff",
                                alignment=ft.Alignment.CENTER, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
        dot = round(size * 0.26)
        return ft.Container(ft.Text(emoji, size=round(size * 0.45)) if emoji else
                            ft.Container(width=dot, height=dot, bgcolor=colour, border_radius=dot / 2),
                            width=size, height=size, border_radius=size / 2, bgcolor=p.raised,
                            alignment=ft.Alignment.CENTER)

    def _tx_badge(self, tx, size=38):
        """A transaction's mark: the merchant's logo; else its category's logo, picture or emoji
        (a split: ✂️); else a dot in its kind's colour."""
        s = self.snap
        split = bool(tx.get("parts"))
        image = s.merchant_image(tx.get("merchant")) or (
            None if split else s.category_image(tx["category"], tx["subcategory"]))
        emoji = "✂️" if split else s.icon(tx["category"], tx["subcategory"])
        return self._badge(emoji, self.p.kind(tx["type"]), image, size)

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
        return self._frame([self._periods("Dashboard")],
                           [*([banner] if banner else []), top, stats, chart,
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
            icon, image = s.icon(c), s.category_image(c)
            label = ft.Text(f"{'' if image else icon} {name}".strip(), size=14, color=p.text, expand=True,
                            no_wrap=True)
            if image:  # a logo or picture as the category's icon: small, before its name
                label = ft.Row([ft.Image(src=image, fit=ft.BoxFit.CONTAIN, width=18, height=18), label],
                               spacing=6, expand=True)
            head = ft.Row([ft.Container(width=10, height=10, bgcolor=colours[c], border_radius=5), label,
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
        self.custom.pop("Transactions", None)
        if self.custom.get(source):
            self.custom["Transactions"] = dict(self.custom[source])
        if source == "Charts" and self.chart_month:  # a month tapped in the bars: that month only
            days = self._chart_month_range()
            whole = days == month_range(self.chart_month)
            self.custom["Transactions"] = custom_period("month", self.chart_month) if whole else \
                custom_period("range", days)
        self.tx_filters = no_filters(kind=kind, account=self.chart_account if source == "Charts" else None,
                                     category=category)
        self.filter_view = None
        self.tx_limit = PAGE_SIZE
        self._jump_to_transactions()

    def _jump_to_transactions(self):
        self.tab = 1
        self.render()

    # ── Transactions ─────────────────────────────────────────────────────────
    def _chosen(self):
        """The filters as Snapshot.filter takes them."""
        return {k: self.tx_filters[k] for k in FILTERS}

    def _transactions(self):
        s, p, f = self.snap, self.p, self.tx_filters
        start, end = self._range("Transactions")
        txs = s.filter(start, end, text=f["text"], **self._chosen())

        search = ft.TextField(value=f["text"], hint_text="Search", prefix_icon=ft.Icons.SEARCH, dense=True,
                              border_radius=24, filled=True, fill_color=p.surface, border_color=p.surface,
                              expand=True, on_submit=self._search, on_blur=self._search,
                              content_padding=ft.Padding.symmetric(horizontal=12, vertical=8))
        n_filters = sum(len(f[k]) for k in FILTERS)
        filter_btn = ft.IconButton(ft.Icons.TUNE, icon_color=p.accent if n_filters else p.dim,
                                   badge=str(n_filters) if n_filters else None, on_click=self._open_filters)
        chips = self._filter_chips()

        # with a category chosen, only its parts of a split count (as Charts adds them up)
        line_ok = s.line_test(f["category"], f["subcategory"])
        lines = [(t["type"], t["amount"]) for t in txs] if line_ok is None else \
            [(line.tx["type"], line.amount) for line in s.lines(txs) if line_ok(line)]
        income = sum(a for k, a in lines if k == "Income")
        expense = sum(a for k, a in lines if k == "Expense")
        refunds = round(-sum(a for k, a in lines if k == "Expense" and a < 0), 2)
        summary = ft.Column([
            ft.Text(f"{len(txs):,} transaction{'s' if len(txs) != 1 else ''}", size=12, color=p.dim),
            ft.Row([self._total("Income", income, bool(refunds)),
                    self._total("Expense", -expense, bool(refunds),
                                f"incl. {money(refunds)} refunds" if refunds else None),
                    self._total("Net", income - expense, bool(refunds))], spacing=8)], spacing=6, tight=True)

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
        return self._frame([ft.Row([search, filter_btn], spacing=4), self._periods("Transactions"),
                            *([chips] if chips else []), summary], rows)

    def _total(self, label, value, tall=False, note=None):
        """One of Transactions' totals: green above 0, red below; ``note`` under it, small."""
        p = self.p
        value = round(value, 2) + 0.0
        return ft.Container(ft.Column([
            ft.Text(label, size=11, color=p.dim),
            ft.Text(money(value, sign=True), size=14, weight=ft.FontWeight.BOLD, color=p.signed(value), no_wrap=True),
            *([ft.Text(note, size=10, color=p.dim, no_wrap=True)] if note else [])],
            spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=True, bgcolor=p.surface, border_radius=10, height=64 if tall else None,
            alignment=ft.Alignment.CENTER, padding=ft.Padding.symmetric(horizontal=6, vertical=6))

    def _value_name(self, key, value):
        s = self.snap
        if key == "account":
            return s.account_name(value) or "—"
        if key == "category":
            return s.category_name(value)
        if key == "subcategory":
            return s.subcategory_name(value) or "—"
        if key == "tag":
            return s.tag.get(value, {}).get("name", "—")
        return str(value)

    def _filter_chips(self):
        p, f = self.p, self.tx_filters
        chips = [ft.Container(ft.Row([ft.Text(self._value_name(k, v), size=12, color=p.text),
                                      ft.Icon(ft.Icons.CLOSE, size=14, color=p.dim)], spacing=4, tight=True),
                              bgcolor=p.raised, border_radius=14, padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                              on_click=lambda e, k=k, v=v: self._clear_filter(k, v))
                 for k in FILTERS for v in sorted(f[k], key=lambda v, k=k: self._value_name(k, v).casefold())]
        return ft.Row(chips, spacing=6, wrap=True) if chips else None

    def _clear_filter(self, key, value=None):
        """✕ on a chip: that one choice; no value: every choice of ``key``."""
        gone = set(self.tx_filters[key]) if value is None else {value}
        self.tx_filters[key] -= gone
        if key == "category":  # its sub-categories go with it
            self._drop_subcategories_of(gone)
        self.tx_limit = PAGE_SIZE
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
        # the account on a line of its own: sharing the category's line, it was cut off
        account = "" if tx["type"] == "Transfer" else s.account_name(tx["account"]) or ""
        return ft.Container(ft.Row([
            self._tx_badge(tx),
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
        items = [ft.Row([self._tx_badge(tx, size=56),
                         ft.Column([ft.Text(s.title(tx), size=19, weight=ft.FontWeight.BOLD, color=p.text),
                                    self._amount_text(tx, size=24)], spacing=2, tight=True, expand=True)],
                        spacing=14),
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
                    self._badge(s.icon(part["category"], part["subcategory"]), p.kind(tx["type"]),
                                s.category_image(part["category"], part["subcategory"]), size=26),
                    ft.Text(f"{cat} › {sub}" if sub else cat, size=14, color=p.text, expand=True),
                    self._amount_text(tx, part["amount"], size=14)], spacing=10))
                if part.get("note"):  # under the part's name, past its mark
                    items.append(ft.Container(ft.Text(part["note"], size=12, color=p.dim, italic=True),
                                              padding=ft.Padding.only(left=36)))
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

    # ── Transactions' "Show only" page ───────────────────────────────────────
    # A page of its own (not a sheet), so Back goes one step at a time: a list → the page →
    # Transactions. Choices apply at once and stay when leaving.
    def _open_filters(self, e=None):
        self.filter_view, self.filter_search = "main", ""
        self._redraw()

    def _filter_up(self):
        self.filter_view = "main" if self.filter_view not in (None, "main") else None
        self.filter_search = ""
        self.tx_limit = PAGE_SIZE
        self._redraw()

    def _open_list(self, key):
        self.filter_view, self.filter_search = key, ""
        self._list_order = None  # set when the list is first drawn: a tick does not move a row
        self._redraw()

    def _filter_head(self, title, right=None):
        p = self.p
        return ft.Container(ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, icon_color=p.text, tooltip="Back",
                                                  on_click=lambda e: self._filter_up()),
                                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=p.text, expand=True),
                                    *([right] if right else [])], spacing=4),
                            padding=ft.Padding.only(left=4, right=8))

    def _bottom_button(self, text, on_click):
        return ft.Container(ft.FilledButton(text, width=10000, height=48, on_click=on_click),
                            padding=ft.Padding.only(left=16, right=16, top=4, bottom=16))

    def _filter_page(self):
        s, p, f = self.snap, self.p, self.tx_filters
        start, end = self._range("Transactions")
        chosen = self._chosen()
        kinds = s.counts("kind", start, end, text=f["text"], **chosen)

        def toggle(kind):
            on = kind in f["kind"]
            there = on or kinds.get(kind)
            return ft.Container(ft.Row([*([ft.Icon(ft.Icons.CHECK, size=16, color="#ffffff")] if on else []),
                                        ft.Text(kind, size=14, color="#ffffff" if on else p.text if there else p.border)],
                                       spacing=4, tight=True),
                                bgcolor=p.accent if on else p.surface, border_radius=18,
                                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
                                on_click=(lambda e: self._toggle_kind(kind)) if there else None)

        def row(key, title, icon):
            values = f[key]
            value = "All" if not values else self._value_name(key, next(iter(values))) if len(values) == 1 \
                else f"{len(values)} chosen"
            return ft.Container(ft.Row([
                ft.Icon(icon, color=p.dim, size=22),
                ft.Text(title, size=15, color=p.text, expand=True),
                ft.Text(value, size=14, color=p.accent if values else p.dim, no_wrap=True, max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS, width=150, text_align=ft.TextAlign.RIGHT),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=p.dim, size=20)], spacing=12),
                padding=ft.Padding.symmetric(horizontal=14, vertical=14), on_click=lambda e: self._open_list(key))

        rows = []
        for key, title, icon in FILTER_ROWS:
            if key == "tag" and not s.tags:
                continue
            if rows:
                rows.append(ft.Divider(height=1, color=p.border))
            rows.append(row(key, title, icon))
        n = len(s.filter(start, end, text=f["text"], **chosen))
        any_chosen = any(f[k] for k in FILTERS)
        return ft.Column([
            self._filter_head("Show only", ft.TextButton("Clear all", on_click=self._clear_all,
                                                         visible=any_chosen)),
            ft.Container(ft.ListView([
                ft.Text("Type", size=13, color=p.dim),
                ft.Row([toggle(k) for k in ("Income", "Expense", "Transfer")], spacing=8, wrap=True),
                ft.Container(height=4),
                ft.Container(ft.Column(rows, spacing=0), bgcolor=p.surface, border_radius=14)],
                spacing=10, padding=ft.Padding.symmetric(horizontal=16)), expand=True),
            self._bottom_button(f"Show {n:,} transaction{'' if n == 1 else 's'}", lambda e: self._close_filters())],
            spacing=8, expand=True, data="filters")

    def _close_filters(self):
        self.filter_view, self.filter_search = None, ""
        self.tx_limit = PAGE_SIZE
        self._redraw()

    def _toggle_kind(self, kind):
        self.tx_filters["kind"] ^= {kind}
        self._redraw()

    def _clear_all(self, e=None):
        self.tx_filters = no_filters(text=self.tx_filters["text"])
        self._redraw()

    def _filter_list(self, key):
        p = self.p
        title = dict((k, t) for k, t, _ in FILTER_ROWS)[key]
        self._flist = ft.ListView(self._filter_items(key), spacing=8,
                                  padding=ft.Padding.only(left=16, right=16, bottom=12))
        self._fcount = ft.Text(self._chosen_text(key), size=12, color=p.dim)
        top = [ft.Row([ft.TextField(value=self.filter_search,
                                    hint_text={"category": "Search categories", "subcategory": "Search subcategories",
                                               "merchant": "Search merchants"}.get(key, "Search"),
                                    prefix_icon=ft.Icons.SEARCH, dense=True, expand=True, border_radius=24,
                                    filled=True, fill_color=p.surface, border_color=p.surface,
                                    content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                                    on_change=lambda e: self._filter_typed(key, e.control.value))])] \
            if key in SEARCHED else []
        return ft.Column([
            self._filter_head(title, ft.TextButton("Clear", on_click=lambda e: self._clear_list(key))),
            ft.Container(ft.Column([*top, self._fcount], spacing=8), padding=ft.Padding.symmetric(horizontal=16)),
            ft.Container(self._flist, expand=True),
            self._bottom_button("Done", lambda e: self._filter_up())], spacing=8, expand=True, data="filters")

    def _chosen_text(self, key):
        n = len(self.tx_filters[key])
        if key == "subcategory" and self.tx_filters["category"]:
            return f"{n} chosen  ·  of the chosen categories"
        return f"{n} chosen" if n else "None chosen: all are shown"

    def _filter_items(self, key):
        """The list's rows: those with transactions under the other choices (and the chosen ones,
        even at 0, so they can be taken off), chosen first; how many transactions each would show."""
        s, p, f = self.snap, self.p, self.tx_filters
        start, end = self._range("Transactions")
        counts = s.counts(key, start, end, text=f["text"], **self._chosen())
        typed = self.filter_search.strip().casefold()

        def shown(v):
            return (counts.get(v) or v in f[key]) and (not typed or typed in self._value_name(key, v).casefold())

        def line(v, mark, extra=""):
            on = v in f[key]
            count = counts.get(v, 0)
            return ft.Container(ft.Row([
                mark,
                ft.Text(self._value_name(key, v), size=15, color=p.text, expand=True, no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(f"{extra}{count:,}", size=12, color=p.dim),
                ft.Icon(ft.Icons.CHECK_BOX if on else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                        color=p.accent if on else p.dim)], spacing=12),
                padding=ft.Padding.symmetric(horizontal=14, vertical=7),
                on_click=lambda e: self._toggle_choice(key, v))

        def card(lines):
            return ft.Container(ft.Column(lines, spacing=0), bgcolor=p.surface, border_radius=14)

        first = getattr(self, "_list_order", None)
        if first is None or first[0] != key:  # chosen first, then A to Z, as the list opened
            names = {v: self._value_name(key, v).casefold() for v in set(counts) | f[key]}
            first = self._list_order = (key, {v: i for i, v in enumerate(
                sorted(names, key=lambda v: (v not in f[key], names[v])))})

        def order(values):
            return sorted(values, key=lambda v: (first[1].get(v, len(first[1])), self._value_name(key, v).casefold()))

        if key == "subcategory":  # in groups, by category
            groups = []
            parents = {s.sub_category.get(v) for v in f[key]}  # a ticked one stays in view
            cats = (f["category"] | parents) if f["category"] else {s.sub_category.get(v) for v in counts} | parents
            for c in sorted((c for c in cats if c in s.category), key=lambda c: s.category_name(c).casefold()):
                subs = [sub["id"] for sub in s.category[c].get("subcategories", []) if shown(sub["id"])]
                if subs:
                    groups += [ft.Text(s.category_name(c), size=13, weight=ft.FontWeight.BOLD, color=p.dim),
                               card([line(v, self._badge(s.icon(c, v), p.dim, s.category_image(c, v), size=30))
                                     for v in order(subs)])]
            return groups or [ft.Text("Nothing here", size=14, color=p.dim)]

        values = order(v for v in set(counts) | f[key] if shown(v))
        lines = []
        for v in values:
            if key == "account":
                mark = ft.Container(ft.Container(width=12, height=12, bgcolor=s.account_color(v), border_radius=6),
                                    width=30, height=30, border_radius=15, bgcolor=p.raised,
                                    alignment=ft.Alignment.CENTER)
            elif key == "category":
                mark = self._badge(s.icon(v), p.dim, s.category_image(v), size=30)
            elif key == "merchant":
                logo = s.merchant_image(v) if v != NO_MERCHANT else None
                mark = self._badge(None, p.dim, logo, size=30) if logo else ft.Container(
                    ft.Text("—" if v == NO_MERCHANT else v[:1].upper(), size=13, weight=ft.FontWeight.BOLD,
                            color=p.dim), width=30, height=30, border_radius=15, bgcolor=p.raised,
                    alignment=ft.Alignment.CENTER)
            else:
                mark = ft.Container(ft.Icon(ft.Icons.SELL_OUTLINED, size=16, color=p.dim), width=30, height=30,
                                    border_radius=15, bgcolor=p.raised, alignment=ft.Alignment.CENTER)
            extra = ""
            if key == "category" and not f["kind"]:
                kind = (s.category.get(v) or {}).get("type")
                extra = f"{kind}  ·  " if kind else ""
            lines.append(line(v, mark, extra))
        return [card(lines)] if lines else [ft.Text("Nothing here", size=14, color=p.dim)]

    def _refresh_list(self, key):
        if getattr(self, "_flist", None) is None:
            self._redraw()
            return
        self._flist.controls = self._filter_items(key)
        self._fcount.value = self._chosen_text(key)
        self.page.update()

    def _toggle_choice(self, key, value):
        chosen = self.tx_filters[key]
        if value in chosen:
            chosen.discard(value)
            if key == "category":
                self._drop_subcategories_of({value})
        else:
            chosen.add(value)
        self.tx_limit = PAGE_SIZE
        self._refresh_list(key)

    def _drop_subcategories_of(self, categories):
        s = self.snap
        self.tx_filters["subcategory"] = {sub for sub in self.tx_filters["subcategory"]
                                          if s.sub_category.get(sub) not in categories}

    def _filter_typed(self, key, text):
        self.filter_search = text or ""
        self._refresh_list(key)

    def _clear_list(self, key):
        if key == "category":
            self._drop_subcategories_of(self.tx_filters["category"])
        self.tx_filters[key] = set()
        self._refresh_list(key)

    # ── Charts ───────────────────────────────────────────────────────────────
    def _charts(self):
        s, p = self.snap, self.p
        start, end = self._range("Charts")
        kind, account = self.chart_kind, self.chart_account

        kinds = ft.SegmentedButton(
            segments=[ft.Segment(value=k, label=ft.Text(k)) for k in ("Expense", "Income")],
            selected=[kind], show_selected_icon=False, on_change=self._set_chart_kind, width=196)
        label = "All accounts" if not account else s.account_name(next(iter(account))) if len(account) == 1 \
            else f"{len(account)} accounts"
        accounts = ft.Container(ft.Row([ft.Text(label, size=13, color=p.accent if account else p.text,
                                                no_wrap=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                                expand=True),
                                        ft.Icon(ft.Icons.ARROW_DROP_DOWN, color=p.dim)], spacing=2),
                                border=ft.Border.all(1, p.border), border_radius=10, expand=True, height=40,
                                padding=ft.Padding.only(left=12, right=4), on_click=self._chart_accounts)

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
            start, end = self._chart_month_range()
            heading = ft.Row([
                ft.Text("By Category", size=15, weight=ft.FontWeight.BOLD, color=p.text, expand=True),
                ft.Container(ft.Text(f"{long_month(self.chart_month)}  ✕", size=12, color="#ffffff",
                                     weight=ft.FontWeight.BOLD),
                             bgcolor=p.accent, border_radius=12,
                             padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                             on_click=lambda e: self._pick_month(self.chart_month))])
        return self._frame([ft.Row([kinds, accounts], spacing=10), self._periods("Charts")],
                           [chart, self._category_card(kind, start, end, title, account, expandable=True,
                                                       colours=colours, heading=heading)])

    def _chart_month_range(self):
        """The month tapped in the bars, within the period (a From – to may cut it)."""
        first, last = month_range(self.chart_month)
        start, end = self._range("Charts")
        return max(first, start or first), min(last, end or last)

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

    def _chart_accounts(self, e=None):
        """The Charts' accounts: one or several, ticked in a list (none ticked: all)."""
        p = self.p
        self._account_rows = ft.Column(self._chart_account_rows(), spacing=0, tight=True, scroll=ft.ScrollMode.AUTO)
        self.page.show_dialog(self._sheet(ft.Container(ft.Column([
            ft.Text("Accounts", size=17, weight=ft.FontWeight.BOLD, color=p.text),
            ft.Container(self._account_rows, bgcolor=p.raised, border_radius=14),
            ft.Row([ft.TextButton("All accounts", on_click=lambda ev: self._set_chart_accounts(set())),
                    ft.FilledButton("Done", on_click=lambda ev: self.page.pop_dialog())],
                   alignment=ft.MainAxisAlignment.END)], spacing=12, tight=True),
            padding=ft.Padding.only(left=20, right=20, top=8, bottom=24)), bgcolor=p.surface, show_drag_handle=True))

    def _chart_account_rows(self):
        s, p = self.snap, self.p
        rows = []
        for a in s.accounts:
            on = a["id"] in self.chart_account
            rows.append(ft.Container(ft.Row([
                ft.Container(width=12, height=12, bgcolor=a["color"], border_radius=6),
                ft.Text(a["name"], size=15, color=p.text, expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Icon(ft.Icons.CHECK_BOX if on else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                        color=p.accent if on else p.dim)], spacing=12),
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                on_click=lambda e, i=a["id"]: self._set_chart_accounts(self.chart_account ^ {i})))
        return rows

    def _set_chart_accounts(self, accounts):
        self.chart_account = set(accounts)
        self.open_category = None
        if getattr(self, "_account_rows", None) is not None:
            self._account_rows.controls = self._chart_account_rows()
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

        return self._frame([self._periods("Accounts")], [chart, self._loans()])

    def _show_account(self, account_id):
        self._jump()
        self.custom.pop("Transactions", None)
        self.filter_view = None
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
