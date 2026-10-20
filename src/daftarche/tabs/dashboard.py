from datetime import date
import calendar

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy, QScrollArea, QPushButton, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QDialogButtonBox, QTextEdit
)
from PySide6.QtCore import Qt, QSize, QMargins
from PySide6.QtGui import QColor, QBrush
from PySide6.QtCharts import (
    QBarSeries, QBarSet, QPieSeries, QPieSlice
)

from daftarche.db import MONTHS_ORDER, MONTH_NUM
from daftarche.style import get_settings, TAB20_COLORS
from daftarche.widgets import AccountCard, SummaryCard, PeriodSelectorWidget, money
from daftarche.chart_utils import HoverChartView, make_chart, make_x_axis, make_y_axis, style_chart_view
from daftarche.icons import emoji_icon


class DashboardTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._refreshing = False

        # Bar-hover state
        self._last_bar_mouse_pos = None
        self._active_bar_hover = None

        # Donut-hover state
        self._last_donut_mouse_pos = None
        self._active_donut_hover = None

        self._donut_total = 0

        self._build_ui()
        self.refresh()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        s = get_settings()
        gl = QGridLayout(self)
        gl.setSpacing(10)
        gl.setContentsMargins(16, 16, 16, 16)

        gl.addWidget(self._build_total_balance_card(), 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        gl.addWidget(self._build_account_scroll(), 1, 0, 2, 1)
        gl.addWidget(self._build_period_selector(), 0, 1)
        gl.addLayout(self._build_stat_cards_row(s), 1, 1)
        gl.addWidget(self._build_bar_chart_widget(), 2, 1)
        gl.addWidget(self._build_donut_chart_layout(s), 1, 2, 2, 1)
        gl.addWidget(self._build_alert_strip(s), 3, 0, 1, 3)

        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 2)
        gl.setColumnStretch(2, 1)

    # ── Total balance card ────────────────────────────────────────────────────
    def _build_total_balance_card(self):
        frame = QFrame()
        frame.setFixedWidth(250)
        frame.setObjectName("total_balance_card")
        frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        lbl = QLabel("Total Balance:")
        lbl.setObjectName("total_balance_label")
        val = QLabel("$0.00")
        val.setObjectName("total_balance_value")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(lbl)
        layout.addStretch(1)
        layout.addWidget(val)

        self._total_balance_value = val
        return frame

    def _update_total_balance_card(self, value):
        self._total_balance_value.setText(f"${value:,.2f}")
        self._total_balance_value.setProperty(
            "balanceState", "positive" if value >= 0 else "negative"
        )
        self._total_balance_value.style().unpolish(self._total_balance_value)
        self._total_balance_value.style().polish(self._total_balance_value)

    # ── Account cards ─────────────────────────────────────────────────────────
    def _build_account_scroll(self):
        self.account_scroll = QScrollArea()
        self.account_scroll.setWidgetResizable(True)
        self.account_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.account_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.account_cards_widget = QWidget()
        self.account_cards_layout = QVBoxLayout(self.account_cards_widget)
        self.account_cards_layout.setSpacing(10)
        self.account_cards_layout.setContentsMargins(0, 0, 20, 0)
        self.account_cards_layout.addStretch(1)

        self.account_scroll.setWidget(self.account_cards_widget)
        return self.account_scroll

    def _refresh_account_cards(self):
        while self.account_cards_layout.count() > 1:
            item = self.account_cards_layout.takeAt(0)
            if item.widget():
                item.widget().hide()  # out of sight now: deleteLater waits for the event loop
                item.widget().deleteLater()

        total_balance = self.db.get_current_total_balance()
        self._update_total_balance_card(total_balance)

        latest_balances = self.db.get_latest_account_balances(visible_only=True)
        if not latest_balances:
            return

        for acc in self.db.get_accounts(visible_only=True):
            balance = latest_balances.get(acc["id"], 0.0)
            card = AccountCard(
                name=acc["name"],
                balance=balance,
                color=acc["color"] or "#7c6af7",
                min_size=(250, 78),
            )
            self.account_cards_layout.insertWidget(
                self.account_cards_layout.count() - 1, card
            )

    # ── Period selector ───────────────────────────────────────────────────────
    def _build_period_selector(self):
        self._period = PeriodSelectorWidget(
            mode="month",
            config_key="period_dashboard",
            inline=False,
        )
        self._period.rangeChanged.connect(self._on_period_changed)
        return self._period

    def _on_period_changed(self, from_date: date, to_date: date):
        self.refresh()

    def _get_effective_range(self):
        """Return (from_date, to_date) as Python date objects."""
        from_date, to_date = self._period.get_range()
        if from_date is None:
            # Use full data range from DB
            from_date, to_date = self.db.get_data_date_range()
        return from_date, to_date

    # ── Stat cards row ────────────────────────────────────────────────────────
    def _build_stat_cards_row(self, s):
        row = QHBoxLayout()
        row.setSpacing(10)
        self._card_income = SummaryCard("Income", s.get("income"))
        self._card_expense = SummaryCard("Expense", s.get("expense"))
        self._card_net = SummaryCard("Net", s.get("accent"))
        self._card_tx = SummaryCard("Transactions", s.get("transfer"))
        for card in (self._card_income, self._card_expense, self._card_net, self._card_tx):
            row.addWidget(card, 1)
        return row

    # ── Bar chart widget ──────────────────────────────────────────────────────
    def _build_bar_chart_widget(self):
        self.bar_view = HoverChartView()
        self.bar_view.setMinimumHeight(300)
        self.bar_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bar_view.mouseMoved.connect(self._on_bar_mouse_move)
        self.bar_view.mouseLeft.connect(self._on_bar_mouse_leave)
        return self.bar_view

    # ── Donut chart widgets ───────────────────────────────────────────────────
    def _build_donut_chart_widget(self):
        self.donut_view = HoverChartView()
        self.donut_view.setMinimumHeight(300)
        self.donut_view.setFrameShape(QFrame.NoFrame)
        self.donut_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.donut_view.mouseMoved.connect(self._on_donut_mouse_move)
        self.donut_view.mouseLeft.connect(self._on_donut_mouse_leave)
        return self.donut_view

    def _build_donut_legend_widget(self, s):
        panel = QFrame()
        panel.setFrameShape(QFrame.NoFrame)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._donut_legend_table = QTableWidget(0, 4)
        self._donut_legend_table.horizontalHeader().setVisible(False)
        self._donut_legend_table.verticalHeader().setVisible(False)
        self._donut_legend_table.setShowGrid(False)
        self._donut_legend_table.setSelectionMode(QTableWidget.NoSelection)
        self._donut_legend_table.setFocusPolicy(Qt.NoFocus)
        self._donut_legend_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._donut_legend_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._donut_legend_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._donut_legend_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._donut_legend_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._donut_legend_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._donut_legend_table.setFrameShape(QFrame.NoFrame)
        self._donut_legend_table.setStyleSheet(
            "QTableWidget { background: transparent; border: none; outline: none; }"
            "QTableWidget::item { border: none; padding: 2px 6px; }"
            "QTableWidget::item:selected { background: transparent; }"
        )
        self._donut_legend_table.setMouseTracking(True)
        self._donut_legend_table.viewport().setMouseTracking(True)
        self._donut_legend_table.cellEntered.connect(self._on_legend_cell_entered)
        self._donut_legend_table.leaveEvent = self._on_legend_leave
        layout.addWidget(self._donut_legend_table)
        return panel

    def _build_donut_chart_layout(self, s):
        qf = QFrame()
        qf.setObjectName("cat_panel")
        qf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        l = QVBoxLayout(qf)
        l.setContentsMargins(8, 8, 8, 8)
        l.setSpacing(4)
        l.addWidget(self._build_donut_chart_widget(), 1)
        l.addWidget(self._build_donut_legend_widget(s), 1)
        return qf

    # ── Alert strip ───────────────────────────────────────────────────────────
    def _build_alert_strip(self, s):
        self._alert_frame = QFrame()
        self._alert_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        alert_layout = QHBoxLayout(self._alert_frame)
        alert_layout.setContentsMargins(12, 6, 12, 6)
        alert_layout.setSpacing(16)

        self._alert_lbl = QLabel("")
        alert_layout.addWidget(self._alert_lbl)
        alert_layout.addStretch(1)

        self._alert_btn = QPushButton("Review →")
        self._alert_btn.setProperty("class", "secondary")
        self._alert_btn.clicked.connect(self._on_alert_clicked)
        alert_layout.addWidget(self._alert_btn)

        self._alert_frame.hide()
        return self._alert_frame

    def _refresh_alert_strip(self):
        s = get_settings()
        from_date, to_date = self._get_effective_range()

        from_year, from_month = from_date.year, MONTHS_ORDER[from_date.month - 1]
        to_year, to_month = to_date.year, MONTHS_ORDER[to_date.month - 1]

        try:
            uncategorized = self.db.get_uncategorized_count(
                from_year, from_month, to_year, to_month
            )
        except Exception:
            uncategorized = 0

        try:
            unmatched = self.db.get_unmatched_transfer_count(
                from_year, from_month, to_year, to_month
            )
        except Exception:
            unmatched = 0

        self._alert_uncategorized = uncategorized
        if uncategorized == 0 and unmatched == 0:
            self._alert_frame.hide()
            return

        parts = []
        if uncategorized > 0:
            parts.append(f"⚠  {uncategorized} uncategorized")
        if unmatched > 0:
            parts.append(f"🔗  {unmatched} unmatched transfers")

        self._alert_lbl.setText("   ·   ".join(parts))
        self._alert_lbl.setStyleSheet(
            f"color:{s.get('transfer')}; font-weight:bold;"
            f" font-size:{s.get('font_size')}pt; background:transparent; border:none;"
        )
        self._alert_frame.setStyleSheet(
            f"QFrame {{ background:{s.get('bg_raised')};"
            f" border:1px solid {s.get('transfer')}66;"
            f" border-left:3px solid {s.get('transfer')};"
            f" border-radius:6px; }}"
        )
        self._alert_frame.show()

    open_overview = None  # set by the window: open_overview(uncategorized: bool)

    def _on_alert_clicked(self):
        if self.open_overview:
            self.open_overview(self._alert_uncategorized > 0)
            return
        s = get_settings()
        from_date, to_date = self._get_effective_range()
        from_year  = from_date.year
        from_month = MONTHS_ORDER[from_date.month - 1]
        to_year    = to_date.year
        to_month   = MONTHS_ORDER[to_date.month - 1]

        # Fetch uncategorized transactions
        uncat_cat_id, _ = self.db.get_uncategorized_ids()
        from_str = f"{from_year:04d}-{MONTH_NUM[from_month]:02d}-01"
        last_day = calendar.monthrange(to_year, MONTH_NUM[to_month])[1]
        to_str = f"{to_year:04d}-{MONTH_NUM[to_month]:02d}-{last_day:02d}"

        uncat_rows = self.db.get_uncategorized_transactions(from_str, to_str)
        unmatched_rows = self.db.get_unmatched_transfer_transactions(from_str, to_str)

        if not uncat_rows and not unmatched_rows:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Review", "✅ No issues found in this period.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Review Issues")
        dlg.setMinimumWidth(640)
        dlg.setMinimumHeight(480)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)

        if uncat_rows:
            lbl = QLabel(f"⚠️  {len(uncat_rows)} uncategorized transaction{'s' if len(uncat_rows) != 1 else ''}:")
            lbl.setStyleSheet(f"font-weight: bold; color: {s.get('expense')};")
            lay.addWidget(lbl)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setStyleSheet("font-family: monospace;")
            lines = []
            for r in uncat_rows:
                name = r["name"] or r["memorandum"] or ""
                lines.append(f"{r['date']}  {(r['account'] or ''):<25}  {money(r['amount']):>11}  {name}")
            txt.setPlainText("\n".join(lines))
            lay.addWidget(txt, 1)

        if unmatched_rows:
            lbl2 = QLabel(f"🔗  {len(unmatched_rows)} unmatched transfer{'s' if len(unmatched_rows) != 1 else ''}:")
            lbl2.setStyleSheet(f"font-weight: bold; color: {s.get('transfer')};")
            lay.addWidget(lbl2)
            txt2 = QTextEdit()
            txt2.setReadOnly(True)
            txt2.setStyleSheet("font-family: monospace;")
            lines2 = []
            for r in unmatched_rows:
                acc = r["account"] or r["to_account"] or "?"
                name = r["name"] or r["memorandum"] or ""
                lines2.append(f"{r['date']}  {acc:<25}  {money(r['amount']):>11}  {name}")
            txt2.setPlainText("\n".join(lines2))
            lay.addWidget(txt2, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    # ── Refresh ───────────────────────────────────────────────────────────────
    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._do_refresh()
        finally:
            self._refreshing = False

    def _do_refresh(self):
        from_date, to_date = self._get_effective_range()

        # Convert to (year, month_name) for DB calls that still use that API
        from_year = from_date.year
        from_month = MONTHS_ORDER[from_date.month - 1]
        to_year = to_date.year
        to_month = MONTHS_ORDER[to_date.month - 1]

        s = get_settings()

        # Stat cards
        summary = self.db.get_dashboard_summary(from_year, from_month, to_year, to_month)
        income = summary["income"]
        expense = summary["expense"]
        net = summary["net"]
        tx_count = summary["tx_count"]

        net_color = s.get("income") if net >= 0 else s.get("expense")
        self._card_income.set_value(f"${income:,.2f}", color=s.get("income"))
        self._card_expense.set_value(f"${expense:,.2f}", color=s.get("expense"))
        self._card_net.set_value(f"${net:+,.2f}", color=net_color)
        self._card_tx.set_value(str(tx_count), color=s.get("transfer"))

        # Account cards
        self._refresh_account_cards()

        # Charts
        self.bar_view.refresh_hover_style()
        self.donut_view.refresh_hover_style()
        self._build_bar_chart(from_year, from_month, to_year, to_month)
        self._build_donut_chart(from_year, from_month, to_year, to_month)

        # Alert strip
        self._refresh_alert_strip()

        # Refresh period selector styles
        self._period.refresh_style()

    # ── Bar hover ─────────────────────────────────────────────────────────────
    def _show_bar_hover(self, text, viewport_pos=None, color=None):
        self.bar_view.show_hover(text, viewport_pos, border_color=color)

    def _move_active_bar_hover_label(self):
        if not self._active_bar_hover or self._last_bar_mouse_pos is None:
            return
        text, color = self._active_bar_hover
        self._show_bar_hover(text, self._last_bar_mouse_pos, color=color)

    def _on_bar_mouse_move(self, pos):
        self._last_bar_mouse_pos = pos
        self._move_active_bar_hover_label()

    def _on_bar_mouse_leave(self):
        self._last_bar_mouse_pos = None
        self._active_bar_hover = None
        self.bar_view.hide_hover()

    # ── Donut hover ───────────────────────────────────────────────────────────
    def _show_donut_hover(self, text, viewport_pos=None, color=None):
        self.donut_view.show_hover(text, viewport_pos, border_color=color)

    def _move_active_donut_hover_label(self):
        if not self._active_donut_hover or self._last_donut_mouse_pos is None:
            return
        text, color = self._active_donut_hover
        self._show_donut_hover(text, self._last_donut_mouse_pos, color=color)

    def _on_donut_mouse_move(self, pos):
        self._last_donut_mouse_pos = pos
        self._move_active_donut_hover_label()

    def _on_donut_mouse_leave(self):
        self._last_donut_mouse_pos = None
        self._active_donut_hover = None
        self.donut_view.hide_hover()

    # ── Bar chart ─────────────────────────────────────────────────────────────
    def _get_periods(self, from_year, from_month, to_year, to_month, monthly):
        return sorted(
            [
                (y, m) for y, m in monthly.keys()
                if (y, MONTH_NUM.get(m, 0)) >= (from_year, MONTH_NUM.get(from_month, 1))
                   and (y, MONTH_NUM.get(m, 0)) <= (to_year, MONTH_NUM.get(to_month, 12))
            ],
            key=lambda ym: (ym[0], MONTH_NUM.get(ym[1], 0))
        )

    def _build_bar_chart(self, from_year, from_month, to_year, to_month):
        s = get_settings()
        monthly = self.db.get_monthly_summary_for_range(
            from_year, from_month, to_year, to_month
        )
        periods = self._get_periods(from_year, from_month, to_year, to_month, monthly)

        self._active_bar_hover = None
        self._last_bar_mouse_pos = None
        self.bar_view.hide_hover()

        if not periods:
            self.bar_view.setChart(make_chart("No data for selected range"))
            style_chart_view(self.bar_view)
            return

        labels = [f"{m[:3]} {str(y)[2:]}" for y, m in periods]

        inc_set = QBarSet("Income")
        inc_set.setColor(QColor(s.get("income")))

        exp_set = QBarSet("Expense")
        exp_set.setColor(QColor(s.get("expense")))

        for y, m in periods:
            d = monthly.get((y, m), {"income": 0, "expense": 0})
            inc_set.append(d["income"])
            exp_set.append(d["expense"])

        def _make_hover(bar_set, labels_ref, color_hex):
            def on_hover(state, idx):
                if state and 0 <= idx < bar_set.count():
                    label = labels_ref[idx] if idx < len(labels_ref) else ""
                    value = bar_set.at(idx)
                    text = f"{bar_set.label()}  {label}\n${value:,.2f}"
                    self._active_bar_hover = (text, color_hex)
                    self._show_bar_hover(text, self._last_bar_mouse_pos, color=color_hex)
                else:
                    self._active_bar_hover = None
                    self._show_bar_hover(None, None)

            return on_hover

        inc_set.hovered.connect(_make_hover(inc_set, labels, s.get("income")))
        exp_set.hovered.connect(_make_hover(exp_set, labels, s.get("expense")))

        series = QBarSeries()
        series.append(inc_set)
        series.append(exp_set)

        chart = make_chart("Income vs Expense")
        chart.legend().setAlignment(Qt.AlignTop)

        chart.addSeries(series)

        ax_x = make_x_axis(labels)
        chart.addAxis(ax_x, Qt.AlignBottom)
        series.attachAxis(ax_x)

        max_val = max(
            max((monthly.get((y, m), {"income": 0})["income"] for y, m in periods), default=0),
            max((monthly.get((y, m), {"expense": 0})["expense"] for y, m in periods), default=0),
        )
        ax_y = make_y_axis(min_val=0, max_val=max_val * 1.1)
        chart.addAxis(ax_y, Qt.AlignLeft)
        series.attachAxis(ax_y)

        self.bar_view.setChart(chart)
        style_chart_view(self.bar_view)

    # ── Donut chart ───────────────────────────────────────────────────────────
    def _build_donut_chart(self, from_year, from_month, to_year, to_month):
        s = get_settings()
        fs = s.get("font_size")
        self._donut_total = 0
        self._donut_slices = {}  # cat_name -> QPieSlice
        self._donut_colors = {}  # cat_name -> color_hex

        self._active_donut_hover = None
        self._last_donut_mouse_pos = None
        self.donut_view.hide_hover()

        # Clear legend table
        self._donut_legend_table.setRowCount(0)

        totals = self.db.get_category_totals_for_range(
            from_year, from_month, to_year, to_month
        )
        expense_totals = [
            r for r in totals
            if r["type_name"] and "Expense" in r["type_name"] and r["total"] > 0
        ][:10]

        if not expense_totals:
            self.donut_view.setChart(make_chart("No expense data"))
            style_chart_view(self.donut_view, bordered=False)
            return

        series = QPieSeries()
        series.setHoleSize(0.45)
        series.setPieSize(0.78)

        total_exp = sum(r["total"] for r in expense_totals)
        self._donut_total = total_exp

        for i, r in enumerate(expense_totals):
            color_hex = TAB20_COLORS[i % len(TAB20_COLORS)]
            pct = r["total"] / total_exp * 100
            category = str(r["category"])
            slc = QPieSlice(f"{pct:.1f}%   {category}", r["total"])
            slc.setColor(QColor(color_hex))
            slc.setBorderColor(QColor(s.get("bg_surface")))
            slc.setBorderWidth(2)
            slc.hovered.connect(
                self._make_donut_hover(slc, category, r["total"], pct, color_hex, i)
            )
            series.append(slc)
            self._donut_slices[category] = slc
            self._donut_colors[category] = color_hex

        chart = make_chart("Expenses by Category", animated=True)
        chart.setMargins(QMargins(4, 4, 4, 4))
        chart.setBackgroundBrush(QBrush(Qt.transparent))
        chart.addSeries(series)
        chart.legend().setVisible(False)

        # ── Build legend table ────────────────────────────────────────────────
        # Keep a row→cat_name map for hover lookups
        self._donut_row_to_cat = {}

        for i, r in enumerate(expense_totals):
            color_hex = TAB20_COLORS[i % len(TAB20_COLORS)]
            pct = r["total"] / total_exp * 100
            category = str(r["category"])

            self._donut_legend_table.insertRow(i)
            self._donut_legend_table.setRowHeight(i, 26)
            self._donut_row_to_cat[i] = category

            # Col 0 — color dot
            swatch_widget = QWidget()
            swatch_widget.setStyleSheet("background: transparent;")
            sw_lay = QHBoxLayout(swatch_widget)
            sw_lay.setContentsMargins(4, 0, 4, 0)
            sw_lay.setAlignment(Qt.AlignCenter)
            dot = QLabel()
            dot.setFixedSize(QSize(fs, fs))
            dot.setStyleSheet(f"background: {color_hex}; border-radius: {fs // 2}px;")
            sw_lay.addWidget(dot)
            self._donut_legend_table.setCellWidget(i, 0, swatch_widget)

            # Col 1 — category name
            name_item = QTableWidgetItem(category)
            name_item.setForeground(QColor(s.get("text")))
            icon = self.db.category_icon(category, "Expense")
            if icon:
                name_item.setIcon(emoji_icon(icon))
            self._donut_legend_table.setItem(i, 1, name_item)

            # Col 2 — amount
            amt_item = QTableWidgetItem(money(r['total']))
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amt_item.setForeground(QColor(s.get("text_dim")))
            self._donut_legend_table.setItem(i, 2, amt_item)

            # Col 3 — percent
            pct_item = QTableWidgetItem(f"{pct:.1f}%")
            pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct_item.setForeground(QColor(s.get("text_dim")))
            self._donut_legend_table.setItem(i, 3, pct_item)

        # Resize all columns to content, then stretch col 1
        self._donut_legend_table.resizeColumnsToContents()
        self._donut_legend_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.donut_view.setChart(chart)
        style_chart_view(self.donut_view, bordered=False)

    def _on_legend_cell_entered(self, row, col):
        cat = getattr(self, "_donut_row_to_cat", {}).get(row)
        if cat and cat != getattr(self, "_donut_hovered_cat", None):
            # Clear previous
            prev = getattr(self, "_donut_hovered_cat", None)
            if prev:
                self._donut_legend_highlight(prev, False)
            self._donut_hovered_cat = cat
            self._donut_legend_highlight(cat, True)

    def _on_legend_leave(self, event):
        cat = getattr(self, "_donut_hovered_cat", None)
        if cat:
            self._donut_legend_highlight(cat, False)
            self._donut_hovered_cat = None

    def _donut_legend_highlight(self, cat_name, entering):
        """Explode the slice and tint the legend row — no floating tooltip."""
        slc = self._donut_slices.get(cat_name)
        if slc:
            slc.setExploded(entering)
            slc.setExplodeDistanceFactor(0.06)

        # Tint the row
        for row, cat in getattr(self, "_donut_row_to_cat", {}).items():
            if cat == cat_name:
                self._donut_legend_row_tint(row, entering)
                break

    def _make_donut_hover(self, slc, cat_name, value, pct, color_hex, row_idx):
        def on_hover(state):
            slc.setExploded(state)
            slc.setExplodeDistanceFactor(0.06)
            if state:
                text = f"{cat_name}\n${value:,.2f}   {pct:.1f}%"
                self._active_donut_hover = (text, color_hex)
                self._show_donut_hover(text, self._last_donut_mouse_pos, color=color_hex)
            else:
                self._active_donut_hover = None
                self._show_donut_hover(None, None)
            # Sync legend row highlight
            self._donut_legend_row_tint(row_idx, state)

        return on_hover

    def _donut_legend_row_tint(self, row_idx, active):
        """Highlight a legend row — brighter text + bold when active."""
        s = get_settings()
        fs = s.get("font_size")
        txt = QColor(s.get("text"))
        dim = QColor(s.get("text_dim"))

        name_item = self._donut_legend_table.item(row_idx, 1)
        amt_item = self._donut_legend_table.item(row_idx, 2)
        pct_item = self._donut_legend_table.item(row_idx, 3)

        if active:
            bold_font = name_item.font() if name_item else None
            if bold_font:
                bold_font.setPointSize(fs + 1)
                bold_font.setBold(True)
            for item in (name_item, amt_item, pct_item):
                if item:
                    item.setForeground(txt)
                    if bold_font:
                        item.setFont(bold_font)
        else:
            normal_font = name_item.font() if name_item else None
            if normal_font:
                normal_font.setPointSize(fs)
                normal_font.setBold(False)
            if name_item:
                name_item.setForeground(txt)
                if normal_font: name_item.setFont(normal_font)
            for item in (amt_item, pct_item):
                if item:
                    item.setForeground(dim)
                    if normal_font: item.setFont(normal_font)