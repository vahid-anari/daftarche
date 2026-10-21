"""Daftarche on the phone: four tabs like the desktop app, reading the phone snapshot.

Nothing here changes your data: the app shows ``daftarche-phone.json`` (written by Daftarche
on the Mac into a folder shared with the phone) and reads it again when asked.
"""

from __future__ import annotations

import asyncio
import calendar
import copy
import errno
import os
import time
from datetime import date
from pathlib import Path

import flet as ft

from . import __version__
from .charts import LineChart, bar_chart, donut, legend, share_bar
from .nav import ASK_EXIT, DASHBOARD, EXIT, RESTORE, BackSteps
from .snapshot import (MONTHS, PALETTE, PERIODS, SNAPSHOT_NAME, Snapshot, SnapshotError, money, month_label,
                       period_range)
from .theme import THEME_CHOICES, material_theme, palette_for
from .update import check as check_for_update

TABS = (("Dashboard", ft.Icons.DASHBOARD_OUTLINED, ft.Icons.DASHBOARD),
        ("Transactions", ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG),
        ("Charts", ft.Icons.PIE_CHART_OUTLINE, ft.Icons.PIE_CHART),
        ("Accounts", ft.Icons.ACCOUNT_BALANCE_OUTLINED, ft.Icons.ACCOUNT_BALANCE))
PAGE_SIZE = 150
"""Transactions shown at first; "Show more" adds as many again."""
TOP_CATEGORIES = 7
"""Categories of their own in the stacked bars and the donut; the rest are "Other"."""


def month_range(key):
    """``"2026-09"`` → ``("2026-09-01", "2026-09-30")``."""
    y, m = (int(x) for x in key.split("-"))
    return f"{key}-01", f"{key}-{calendar.monthrange(y, m)[1]:02d}"


def long_month(key):
    """``"2026-09"`` → ``"September 2026"``."""
    y, m = key.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"
NEED_ACCESS = "access"
"""``problem`` when Android has not allowed reading the folder yet."""


class PhoneApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.prefs = ft.SharedPreferences()
        self.picker = ft.FilePicker()
        self.snap: Snapshot | None = None
        self.problem = ""
        self.folder = ""
        self.theme_choice = "system"
        self.tab = 0
        self.period = {"Dashboard": "This Month", "Transactions": "This Month", "Charts": "6 Months",
                       "Accounts": "All"}
        self.tx_filters = {"kind": None, "account": None, "category": None, "tag": None, "text": ""}
        self.tx_limit = PAGE_SIZE
        self.chart_kind = "Expense"
        self.chart_account = None
        self.chart_month = None  # a month tapped in the Charts bars ("2026-09"): its categories below
        self.tx_range = None  # Transactions shows one month from Charts: (first day, last day, label)
        self.open_category = None
        self.p = palette_for("system", page.platform_brightness)
        self.android = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.ANDROID_TV) and not page.web
        self.permissions = None
        if self.android:  # an extension the Android build carries (not there in `flet run` on a Mac)
            from flet_permission_handler import PermissionHandler
            self.permissions = PermissionHandler()
        self.update_info = None
        self.nav = BackSteps()
        self._pager = None

    # ── start ────────────────────────────────────────────────────────────────
    async def start(self):
        page = self.page
        page.title = "Daftarche"
        page.padding = 0
        page.on_platform_brightness_change = lambda e: self.render()
        page.on_app_lifecycle_state_change = self._lifecycle
        self.folder = os.environ.get("DAFTARCHE_PHONE_FOLDER") or (await self.prefs.get("folder")) or ""
        self.theme_choice = (await self.prefs.get("theme")) or "system"
        # Android's Back comes to the app (see nav.py) instead of always leaving it
        view = page.views[0]
        view.can_pop = False
        view.on_confirm_pop = self._back
        self.load()
        self.render()
        page.run_task(self._daily_update_check)

    def load(self, keep=False):
        """Read the snapshot from the folder again.

        ``keep``: when it cannot be read now (Syncthing in the middle of copying it, say), keep
        showing the one read before. Returns the problem, or "".
        """
        before = self.snap
        self.snap, self.problem = None, ""
        if not self.folder:
            self.problem = "Choose the folder Daftarche on your Mac writes to (Settings › Phone)."
            return self.problem
        path = Path(self.folder) / SNAPSHOT_NAME
        try:
            self.snap = Snapshot.load(path)
        except FileNotFoundError:
            self.problem = (f"No {SNAPSHOT_NAME} in this folder yet. On the Mac, choose this folder in "
                            "Daftarche's Settings › Phone, or File › Update Phone Snapshot.")
        except PermissionError:
            self.problem = NEED_ACCESS
        except OSError as exc:
            self.problem = NEED_ACCESS if exc.errno in (errno.EACCES, errno.EPERM) else str(exc)
        except SnapshotError as exc:
            self.problem = str(exc)
        if self.snap is None and keep and before is not None:
            self.snap = before
        return self.problem

    def _lifecycle(self, e):
        """Back in the app (from Android's settings, or later in the day): read the file again."""
        if getattr(e, "state", None) == ft.AppLifecycleState.RESUME:
            self.load(keep=True)
            self.render()

    async def _allow_access(self, e=None):
        """Android's "All files access" page for this app; the file is read again on return."""
        if self.permissions is not None:
            from flet_permission_handler import Permission
            await self.permissions.request(Permission.MANAGE_EXTERNAL_STORAGE)
        self.load()
        self.render()

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
            actions=[ft.IconButton(ft.Icons.REFRESH, icon_color=p.dim, tooltip="Read again", on_click=self._reload),
                     ft.IconButton(ft.Icons.SETTINGS_OUTLINED, icon_color=p.dim, tooltip="Settings",
                                   on_click=self._settings)])
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
        problem = self.load(keep=True)
        self.render()
        if problem == NEED_ACCESS:
            return
        self._toast(f"Could not read it now: {problem}" if problem and self.snap else problem or "Read again")

    def _toast(self, text):
        self.page.show_dialog(ft.SnackBar(ft.Text(text), duration=2500))

    def _body(self):
        if self.snap is None:
            self._pager = None
            return self._welcome()
        # all four tabs, side by side: a swipe slides to the next one (the bar follows)
        self._pager = ft.PageView([self._dashboard(), self._transactions(), self._charts(), self._accounts()],
                                  selected_index=self.tab, on_change=self._swiped, expand=True)
        return self._pager

    def _redraw(self):
        """Draw the tabs again in place, after a choice inside a tab (a period, a filter, a tapped
        category): each list keeps where it was scrolled to. render() builds new lists, which
        open at the top."""
        if self.snap is None or getattr(self, "_pager", None) is None:
            self.render()
            return
        fresh = [self._dashboard(), self._transactions(), self._charts(), self._accounts()]
        for old, new in zip(self._pager.controls, fresh):
            old.controls = new.controls
        self.page.update()

    def _sheet(self, content, **kwargs):
        """A sheet from the bottom whose content stays above Android's Back / Home buttons (Flet's
        own sheet keeps clear of the top and sides only); its background still reaches the edge."""
        return ft.BottomSheet(ft.SafeArea(content, avoid_intrusions_top=False, avoid_intrusions_left=False,
                                          avoid_intrusions_right=False), **kwargs)

    def _welcome(self):
        p = self.p
        if self.problem == NEED_ACCESS:
            text = ("Daftarche needs your permission to read the folder with your data. On the next page, "
                    "turn on \u201cAllow access to manage all files\u201d for Daftarche, then come back.\n\n"
                    "The app only reads daftarche-phone.json; it never changes or sends anything.")
            button = ft.FilledButton("Allow Access", icon=ft.Icons.LOCK_OPEN, on_click=self._allow_access)
        else:
            text = self.problem
            button = ft.FilledButton("Choose Folder", icon=ft.Icons.FOLDER_OPEN, on_click=self._choose_folder)
        return ft.Container(ft.Column([
            ft.Icon(ft.Icons.MENU_BOOK_ROUNDED, size=56, color=p.accent),
            ft.Text("Your account book, on the phone", size=20, weight=ft.FontWeight.BOLD, color=p.text,
                    text_align=ft.TextAlign.CENTER),
            ft.Text(text, size=14, color=p.dim, text_align=ft.TextAlign.CENTER),
            button,
            ft.TextButton("Choose another folder", on_click=self._choose_folder,
                          visible=self.problem == NEED_ACCESS),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16, tight=True),
            padding=32, alignment=ft.Alignment.CENTER, expand=True)

    # ── shared pieces ────────────────────────────────────────────────────────
    def _page(self, controls):
        return ft.ListView(controls, padding=ft.Padding.only(left=16, right=16, top=4, bottom=24), spacing=12,
                           expand=True)

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
        return ft.Row(chips, spacing=6, scroll=ft.ScrollMode.HIDDEN)

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
                    for a in s.accounts if a.get("visible", True)]
        top = self._card(ft.Column([
            ft.Text("Total Balance", size=13, color=p.dim),
            ft.Text(money(total), size=30, weight=ft.FontWeight.BOLD, color=p.signed(total)),
            ft.Divider(height=14, color=p.border),
            *accounts], spacing=6), padding=16)

        sm = s.summary(start, end)
        stats = ft.Column([
            ft.Row([self._stat("Income", money(sm["income"]), p.income),
                    self._stat("Expense", money(sm["expense"]), p.expense)], spacing=10),
            ft.Row([self._stat("Net", money(sm["net"], sign=True), p.signed(sm["net"]) if sm["net"] else p.text),
                    self._stat("Transactions", f"{sm['count']:,}", p.transfer)], spacing=10)], spacing=10)

        rows = s.by_category("Expense", start, end)
        colours = {c: PALETTE[i % len(PALETTE)] for i, (c, _) in enumerate(rows)}
        monthly = s.monthly(start, end)
        if len(monthly) <= 1:  # one month (This / Last Month): how its spending divides, as in Charts
            month = monthly[0][0] if monthly else start[:7]
            shown = [(colours[c], v) for c, v in rows[:TOP_CATEGORIES]]
            rest = round(sum(v for _, v in rows[TOP_CATEGORIES:]), 2)
            if rest > 0:
                shown.append((p.dim, rest))
            chart = self._card(ft.Column([
                self._heading(f"Expense in {long_month(month)}"),
                donut(p, shown, money(sm["expense"]), f"{len(rows)} categor{'y' if len(rows) == 1 else 'ies'}")],
                spacing=12))
        else:
            chart = self._card(ft.Column([
                self._heading("Income vs Expense"),
                legend(p, [(p.income, "Income"), (p.expense, "Expense")]),
                bar_chart(p, [month_label(m) for m, _, _ in monthly],
                          [(p.income, [i for _, i, _ in monthly]), (p.expense, [e for _, _, e in monthly])])],
                spacing=10))

        banner = self._update_banner()
        return self._page([*([banner] if banner else []), top, self._periods("Dashboard"), stats, chart,
                           self._category_card("Expense", start, end, "Expenses by Category", colours=colours)])

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
        self.tx_filters = {"kind": kind, "account": self.chart_account if source == "Charts" else None,
                           "category": category, "tag": None, "text": ""}
        self.tx_limit = PAGE_SIZE
        self._jump_to_transactions()

    def _jump_to_transactions(self):
        self.tab = 1
        self.render()

    # ── Transactions ─────────────────────────────────────────────────────────
    def _transactions(self):
        s, p, f = self.snap, self.p, self.tx_filters
        start, end = self._range("Transactions")
        txs = s.filter(start, end, f["kind"], f["account"], f["category"], f["tag"], f["text"])

        search = ft.TextField(value=f["text"], hint_text="Search", prefix_icon=ft.Icons.SEARCH, dense=True,
                              border_radius=24, filled=True, fill_color=p.surface, border_color=p.surface,
                              expand=True, on_submit=self._search, on_blur=self._search,
                              content_padding=ft.Padding.symmetric(horizontal=12, vertical=8))
        n_filters = sum(1 for k in ("kind", "account", "category", "tag") if f[k] is not None)
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
            sub += f"  ·  {s.account_name(tx['account'])}"
        emoji = "✂️" if tx.get("parts") else s.icon(tx["category"], tx["subcategory"])
        return ft.Container(ft.Row([
            self._badge(emoji, p.kind(tx["type"])),
            ft.Column([ft.Text(s.title(tx), size=14, color=p.text, no_wrap=True,
                               overflow=ft.TextOverflow.ELLIPSIS),
                       ft.Text(sub, size=12, color=p.dim, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)],
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

        def dropdown(label, key, options):
            current = f[key]
            return ft.Dropdown(label=label, value="" if current is None else str(current), expand=True,
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
            *([dropdown("Tag", "tag", tags)] if tags else []),
            ft.Row([ft.TextButton("Clear all", on_click=lambda ev: self._clear_filters(sheet)),
                    ft.FilledButton("Done", on_click=lambda ev: self.page.pop_dialog())],
                   alignment=ft.MainAxisAlignment.END)],
            spacing=12, tight=True), padding=ft.Padding.only(left=20, right=20, top=8, bottom=24)),
            bgcolor=p.surface, show_drag_handle=True, on_dismiss=lambda ev: self._redraw())
        self.page.show_dialog(sheet)

    def _set_filter(self, key, value):
        if key == "kind":
            self.tx_filters[key] = value or None
        else:
            self.tx_filters[key] = int(value) if value else None
        self.tx_limit = PAGE_SIZE

    def _clear_filters(self, sheet):
        self.tx_filters = {"kind": None, "account": None, "category": None, "tag": None,
                           "text": self.tx_filters["text"]}
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
        chart = self._card(ft.Column([
            self._heading("Balance by Month"),
            LineChart(p, [month_label(m) for m in months], lines),
            legend(p, [(a["color"], a["name"]) for a in shown])], spacing=10))

        rows = []
        for a in shown:
            vs = series.get(a["id"], [])
            change = vs[-1] - vs[0] if len(vs) > 1 else 0.0
            rows.append(self._card(ft.Row([
                ft.Column([ft.Text(a["name"], size=15, weight=ft.FontWeight.BOLD, color=a["color"]),
                           ft.Text(f"{money(change, sign=True)} in this period" if len(vs) > 1 else "",
                                   size=12, color=p.dim, visible=len(vs) > 1)], spacing=2, expand=True),
                ft.Text(money(a["balance"]), size=17, weight=ft.FontWeight.BOLD, color=p.signed(a["balance"]))]),
                accent=a["color"], on_click=lambda e, i=a["id"]: self._show_account(i)))

        return self._page([self._periods("Accounts"), chart, *rows, self._loans()])

    def _show_account(self, account_id):
        self._jump()
        self.tx_range = None
        self.tx_filters = {"kind": None, "account": account_id, "category": None, "tag": None, "text": ""}
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
        self.page.pop_dialog()
        try:
            self.update_info = await asyncio.to_thread(check_for_update, __version__)
        except (OSError, ValueError) as exc:
            self._toast(f"Could not reach GitHub: {exc}")
            return
        if self.update_info:
            self.tab = 0
            self.render()
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
            ft.Text("Download it, then open the file to install it over this one: your folder and "
                    "settings stay.", size=12, color=p.dim),
            ft.Row([ft.TextButton("Later", on_click=self._dismiss_update),
                    ft.FilledButton("Download", icon=ft.Icons.DOWNLOAD, on_click=self._download_update)],
                   alignment=ft.MainAxisAlignment.END)], spacing=6), accent=p.accent)

    def _dismiss_update(self, e=None):
        self.update_info = None
        self.render()

    async def _download_update(self, e=None):
        await ft.UrlLauncher().launch_url(self.update_info["apk"], mode=ft.LaunchMode.EXTERNAL_APPLICATION)

    # ── Settings ─────────────────────────────────────────────────────────────
    def _settings(self, e=None):
        s, p = self.snap, self.p
        about = (f"App {__version__}  ·  data from Daftarche {s.app_version}" if s and s.app_version
                 else f"App {__version__}")
        self._path_field = path_field = ft.TextField(value=self.folder, label="Folder", dense=True,
                                                     on_submit=self._typed_folder,
                                  hint_text="/storage/emulated/0/Daftarche", text_size=14)
        sheet = self._sheet(ft.Container(ft.Column([
            ft.Text("Settings", size=17, weight=ft.FontWeight.BOLD, color=p.text),
            path_field,
            ft.Row([ft.OutlinedButton("Choose Folder", icon=ft.Icons.FOLDER_OPEN, on_click=self._choose_folder),
                    ft.TextButton("Use Typed Path", on_click=self._typed_folder)],
                   wrap=True),
            ft.Text("Theme", size=13, color=p.dim),
            ft.SegmentedButton(segments=[ft.Segment(value=k, label=ft.Text(v)) for k, v in THEME_CHOICES.items()],
                               selected=[self.theme_choice], show_selected_icon=False, on_change=self._set_theme),
            ft.Divider(color=p.border),
            ft.Row([ft.Text(about, size=12, color=p.dim, expand=True),
                    ft.TextButton("Check for Updates", on_click=self._check_updates_now,
                                  visible=not self.page.web)]),
            ft.Text("Read-only: nothing here changes your data. By Vahid Anari, MIT License.", size=12,
                    color=p.dim)], spacing=10, tight=True),
            padding=ft.Padding.only(left=20, right=20, top=8, bottom=28)), bgcolor=p.surface, show_drag_handle=True)
        self.page.show_dialog(sheet)

    async def _set_theme(self, e):
        self.theme_choice = list(e.control.selected)[0]
        await self.prefs.set("theme", self.theme_choice)
        self.render()

    async def _choose_folder(self, e=None):
        folder = await self.picker.get_directory_path(dialog_title="Folder with daftarche-phone.json")
        if folder:
            await self._use_folder(folder)

    async def _typed_folder(self, e=None):
        folder = (self._path_field.value or "").strip()
        if folder:
            await self._use_folder(folder)

    async def _use_folder(self, folder):
        self.folder = folder
        await self.prefs.set("folder", folder)
        try:
            self.page.pop_dialog()
        except Exception:  # no sheet open (the welcome page)
            pass
        if self.load() == NEED_ACCESS and self.permissions is not None:
            await self._allow_access()
            return
        self.render()


async def main(page: ft.Page):
    await PhoneApp(page).start()
