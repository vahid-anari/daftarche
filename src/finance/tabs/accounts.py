from datetime import date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QApplication, QFrame, QSizePolicy, QCheckBox, QPushButton,
)
from PySide6.QtCore import Qt, QObject, QEvent, QPointF, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QKeySequence, QShortcut, QPen, QPainter, QFontMetrics
from PySide6.QtCharts import (
    QLineSeries, QSplineSeries, QBarSeries, QBarSet,
    QStackedBarSeries, QScatterSeries
)

from finance.db import MONTHS_ORDER, MONTH_NUM
from finance.style import get_settings
from finance.widgets import PeriodSelectorWidget, ReadOnlyCopyDelegate
from finance.chart_utils import (
    HoverChartView, make_chart, make_x_axis, make_y_axis,
    style_chart_view, StackedOverlay
)

# ── View definitions ──────────────────────────────────────────────────────────
_VIEWS = ["Balance", "Income", "Expense", "Transfer"]
_VIEW_DEFAULT_CHART = {
    "Balance": "Line",
    "Income": "Stacked Bars",
    "Expense": "Stacked Bars",
    "Transfer": "Line",
}
_VIEW_ALLOW_STACK = {"Income", "Expense"}
_CHART_TYPES = ["Line", "Spline", "Grouped Bars", "Stacked Bars"]


# _AccVerticalHeader  — custom vertical header with account colors + hover
class _AccVerticalHeader(QHeaderView):

    def __init__(self, colors_fn, parent=None):
        super().__init__(Qt.Vertical, parent)
        self._colors_fn = colors_fn

    def paintSection(self, painter, rect, logical_index):
        s = get_settings()
        name = self.model().headerData(logical_index, Qt.Vertical, Qt.DisplayRole) or ""
        color = self._colors_fn().get(name, s.get("text"))

        painter.save()

        bg = QColor(s.get("bg_raised"))
        painter.fillRect(rect, bg)

        painter.setPen(QPen(QColor(s.get("border"))))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomRight())

        painter.setPen(QColor(color))
        font = QFont(s.get("font_family"), s.get("font_size"))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            rect.adjusted(8, 0, -4, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            name
        )
        painter.restore()

    def sectionSizeHint(self, logical_index):
        s = get_settings()
        name = self.model().headerData(logical_index, Qt.Vertical, Qt.DisplayRole) or ""
        w = QFontMetrics(QFont(s.get("font_family"), s.get("font_size"))).horizontalAdvance(name) + 20
        return w


def _make_cb_stylesheet(color_hex):
    s = get_settings()
    c = QColor(color_hex)
    lighter = c.lighter(140).name()
    return f"""
        QCheckBox {{ spacing: 6px; }}
        QCheckBox::indicator {{
            width: 13px; height: 13px; border-radius: 3px;
        }}
        QCheckBox::indicator:unchecked {{
            background: {s.get('bg_raised')};
            border: 1px solid {s.get('border')};
        }}
        QCheckBox::indicator:unchecked:hover {{
            border: 1px solid {color_hex};
        }}
        QCheckBox::indicator:checked {{
            background: {color_hex};
            border: 1px solid {lighter};
        }}
        QCheckBox::indicator:checked:hover {{
            background: {lighter};
            border: 1px solid {lighter};
        }}
    """


# AccountsTab
class AccountsTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db

        # Data caches
        self._snapshots = {}
        self._income_data = {}
        self._expense_data = {}
        self._transfer_data = {}
        self._all_periods = []
        self._all_accounts = []
        self._account_colors = {}

        # Chart state
        self._current_view = "Balance"
        self._current_chart_type = "Line"
        self._acc_cbs = {}  # name -> (cb, amt_item)
        self._line_series_data = {}
        self._line_series_objects = {}
        self._overlay_series = None
        self._hover_dot_series = None
        self._highlighted_acc = None
        self._last_hover_key = None
        self._active_bar_hover = None
        self._last_mouse_pos = None
        self._ignore_cb_changed = False
        self._refreshing_chart = False
        self._stack_overlay_widget = None

        self._build_ui()
        self.refresh()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        s = get_settings()
        fs = s.get("font_size")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Row 1: Period selector ────────────────────────────────────────────
        self._period = PeriodSelectorWidget(mode="month", config_key="period_accounts")
        self._period.rangeChanged.connect(lambda *_: self.refresh())
        layout.addWidget(self._period)

        # ── Row 2: View buttons + Chart type ─────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self._view_btns = {}
        for view in _VIEWS:
            btn = QPushButton(view)
            btn.setCheckable(True)
            btn.setProperty("class", "period-preset-btn")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _, v=view: self._on_view_changed(v))
            row2.addWidget(btn)
            self._view_btns[view] = btn

        row2.addSpacing(20)

        self._chart_type_btns = {}
        for ct in _CHART_TYPES:
            btn = QPushButton(ct)
            btn.setCheckable(True)
            btn.setProperty("class", "period-preset-btn")
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _, c=ct: self._on_chart_type_changed(c))
            row2.addWidget(btn)
            self._chart_type_btns[ct] = btn

        row2.addStretch(1)
        layout.addLayout(row2)

        # ── Chart area + account panel ────────────────────────────────────────
        self.chart_view = HoverChartView()
        self.chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chart_view.mouseMoved.connect(self._on_mouse_move)
        self.chart_view.mouseLeft.connect(self._on_mouse_leave)

        # Account checkbox panel
        self._acc_lbl = QLabel("Accounts")
        self._acc_lbl.setFont(QFont(s.get("font_family"), fs, QFont.Bold))

        btn_all = QPushButton("All")
        btn_none = QPushButton("None")
        btn_all.setProperty("class", "secondary")
        btn_none.setProperty("class", "secondary")
        btn_all.clicked.connect(self._select_all_accs)
        btn_none.clicked.connect(self._select_no_accs)

        self._acc_table = QTableWidget(0, 2)
        self._acc_table.horizontalHeader().setVisible(False)
        self._acc_table.verticalHeader().setVisible(False)
        self._acc_table.setShowGrid(False)
        self._acc_table.setSelectionMode(QTableWidget.NoSelection)
        self._acc_table.setFocusPolicy(Qt.NoFocus)
        self._acc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._acc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._acc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._acc_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._acc_table.setFrameShape(QFrame.NoFrame)
        self._acc_table.setStyleSheet(
            "QTableWidget { background: transparent; border: none; outline: none; }"
            "QTableWidget::item { background: transparent; border: none; padding: 2px 4px; }"
            "QTableWidget::item:selected { background: transparent; }"
        )
        self._acc_table.cellClicked.connect(self._on_acc_table_clicked)

        acc_panel = QFrame()
        acc_panel.setObjectName("cat_panel")
        acc_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        acc_outer = QVBoxLayout(acc_panel)
        acc_outer.setContentsMargins(10, 10, 10, 10)
        acc_outer.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)

        acc_outer.addWidget(self._acc_lbl)
        acc_outer.addSpacing(4)
        acc_outer.addLayout(btn_row)
        acc_outer.addWidget(self._acc_table, 1)

        chart_layout = QVBoxLayout()
        chart_layout.addWidget(self.chart_view, 1)

        mid_layout = QHBoxLayout()
        mid_layout.addLayout(chart_layout)
        mid_layout.addWidget(acc_panel)
        layout.addLayout(mid_layout, 1)

        # ── Table ─────────────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.setItemDelegate(ReadOnlyCopyDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Custom vertical header — handles hover + colored account names
        v_header = _AccVerticalHeader(lambda: self._account_colors, self.table)
        v_header.setDefaultSectionSize(32)
        v_header.setSectionResizeMode(QHeaderView.Fixed)
        v_header.setSectionsClickable(True)
        v_header.sectionClicked.connect(lambda row: self.table.selectRow(row))
        self.table.setVerticalHeader(v_header)

        QShortcut(QKeySequence.Copy, self.table, activated=self._copy_table)
        layout.addWidget(self.table, 1)

        # Init button states
        self._set_view("Balance", emit=False)

    # ── View / chart type selection ───────────────────────────────────────────
    def _set_view(self, view, emit=True):
        self._current_view = view
        for v, btn in self._view_btns.items():
            btn.setChecked(v == view)

        # Update chart type buttons — disable Stacked for Balance/Transfer
        allow_stack = view in _VIEW_ALLOW_STACK
        for ct, btn in self._chart_type_btns.items():
            btn.setEnabled(ct != "Stacked Bars" or allow_stack)

        # Auto-switch chart type to default for this view
        default_ct = _VIEW_DEFAULT_CHART[view]
        self._set_chart_type(default_ct, emit=False)

        if emit:
            self._refresh_chart()
            self._fill_table()

    def _set_chart_type(self, chart_type, emit=True):
        # If Stacked not allowed and requested, fall back to Grouped Bars
        if chart_type == "Stacked Bars" and self._current_view not in _VIEW_ALLOW_STACK:
            chart_type = "Grouped Bars"
        self._current_chart_type = chart_type
        for ct, btn in self._chart_type_btns.items():
            btn.setChecked(ct == chart_type)
        if emit:
            self._refresh_chart()

    def _on_view_changed(self, view):
        self._set_view(view)

    def _on_chart_type_changed(self, chart_type):
        self._set_chart_type(chart_type)

    # ── Refresh ───────────────────────────────────────────────────────────────
    def refresh(self):
        s = get_settings()
        self.chart_view.refresh_hover_style()
        self._period.refresh_style()

        from_date, to_date = self._period.get_range()
        if from_date is None:
            from_date, to_date = self.db.get_data_date_range()
        from_year = from_date.year
        from_month = MONTHS_ORDER[from_date.month - 1]
        to_year = to_date.year
        to_month = MONTHS_ORDER[to_date.month - 1]

        # Fetch all data
        snapshots, _ = self.db.get_account_monthly_balance()

        all_accounts = [a for a in self.db.get_accounts() if a["show_in_accounts"]]
        self._all_accounts = all_accounts
        self._account_colors = {a["name"]: a["color"] or "#7c6af7" for a in all_accounts}

        # Filter periods to selected range
        all_periods = sorted(
            [
                (y, m) for y, m in snapshots.keys()
                if (y, MONTH_NUM.get(m, 0)) >= (from_year, MONTH_NUM.get(from_month, 1))
                   and (y, MONTH_NUM.get(m, 0)) <= (to_year, MONTH_NUM.get(to_month, 12))
            ],
            key=lambda ym: (ym[0], MONTH_NUM.get(ym[1], 0))
        )
        self._all_periods = all_periods
        self._snapshots = snapshots

        # Income / Expense
        for acc in all_accounts:
            self._income_data[acc["name"]] = self.db.get_account_monthly_inout(acc["id"], "Income", "account_id")
            self._expense_data[acc["name"]] = self.db.get_account_monthly_inout(acc["id"], "Expense", "account_id")
            self._transfer_data[acc["name"]] = self.db.get_account_monthly_transfer_net(acc["id"])

        self._refresh_acc_list()
        self._refresh_chart()
        self._fill_table()

    # ── Account checkbox panel ────────────────────────────────────────────────
    def _refresh_acc_list(self):
        s = get_settings()
        fs = s.get("font_size")

        saved = get_settings().get("accounts_selection") or {}
        old_states = {name: cb.isChecked() for name, (cb, _) in self._acc_cbs.items()}
        # Merge: saved takes priority, old_states as fallback for new accounts
        states = {**old_states, **saved}

        self._ignore_cb_changed = True
        self._acc_table.setRowCount(0)
        self._acc_cbs = {}

        class _CbHoverFilter(QObject):
            def __init__(self_, cb, name):
                super().__init__(cb)
                self_._cb = cb
                self_._name = name

            def eventFilter(self_, obj, event):
                if event.type() == QEvent.Enter:
                    if self_._cb.isChecked():
                        self._set_highlighted(self_._name)
                elif event.type() == QEvent.Leave:
                    if self._highlighted_acc == self_._name:
                        self._clear_highlight()
                return False

        for row, acc in enumerate(self._all_accounts):
            name = acc["name"]
            color = self._account_colors.get(name, "#7c6af7")
            checked = states.get(name, True)

            self._acc_table.insertRow(row)
            self._acc_table.setRowHeight(row, 28)

            cb = QCheckBox(name)
            cb.setChecked(checked)
            cb.toggled.connect(lambda chk, n=name: self._on_cb_toggled(n, chk))
            cb.clicked.connect(lambda _=None, n=name: self._on_cb_clicked(n))
            cb.installEventFilter(_CbHoverFilter(cb, name))

            cb_container = QWidget()
            cb_container.setStyleSheet("background: transparent;")
            cb_lay = QHBoxLayout(cb_container)
            cb_lay.setContentsMargins(4, 0, 0, 0)
            cb_lay.setSpacing(0)
            cb_lay.addWidget(cb)
            cb_container.installEventFilter(_CbHoverFilter(cb, name))
            self._acc_table.setCellWidget(row, 0, cb_container)

            amt_item = QTableWidgetItem("")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._acc_table.setItem(row, 1, amt_item)

            self._apply_cb_style(cb, name, checked)
            self._acc_cbs[name] = (cb, amt_item)

        self._ignore_cb_changed = False

    def _apply_cb_style(self, cb, name, checked):
        s = get_settings()
        fs = s.get("font_size") or 11
        color = self._account_colors.get(name, "#7c6af7")
        text_color = s.get("text") if checked else (s.get("text_dim") or "#888")
        cb.setStyleSheet(
            _make_cb_stylesheet(color) +
            f" QCheckBox {{ color: {text_color}; font-size: {fs}pt; spacing: 6px; }}"
        )
        entry = self._acc_cbs.get(name)
        if entry:
            _, amt_item = entry
            amt_item.setForeground(QColor(text_color))

    def _highlight_cb(self, acc_name):
        s = get_settings()
        fs = s.get("font_size") or 11
        for name, (cb, amt_item) in self._acc_cbs.items():
            if name == acc_name and cb.isChecked():
                color = self._account_colors.get(name, "#7c6af7")
                cb.setStyleSheet(
                    _make_cb_stylesheet(color) +
                    f" QCheckBox {{ color: {s.get('text')}; font-size: {fs + 2}pt; font-weight: bold; spacing: 6px; }}"
                )
                f = amt_item.font()
                f.setPointSize(fs + 2)
                f.setBold(True)
                amt_item.setFont(f)
                amt_item.setForeground(QColor(s.get("text")))
            else:
                self._apply_cb_style(cb, name, cb.isChecked())
                amt_item.setFont(QFont())

    def _get_selected_accs(self):
        return [name for name, (cb, _) in self._acc_cbs.items() if cb.isChecked()]

    def _select_all_accs(self):
        self._ignore_cb_changed = True
        for name, (cb, _) in self._acc_cbs.items():
            cb.setChecked(True)
            self._apply_cb_style(cb, name, True)
        self._ignore_cb_changed = False
        self._clear_highlight()
        self._refresh_chart()
        self._fill_table()

    def _select_no_accs(self):
        self._ignore_cb_changed = True
        for name, (cb, _) in self._acc_cbs.items():
            cb.setChecked(False)
            self._apply_cb_style(cb, name, False)
        self._ignore_cb_changed = False
        self._clear_highlight()
        self._refresh_chart()
        self._fill_table()

    def _on_cb_toggled(self, name, checked):
        if self._ignore_cb_changed:
            return
        # Save selection state
        current = {n: cb.isChecked() for n, (cb, _) in self._acc_cbs.items()}
        current[name] = checked
        get_settings().set("accounts_selection", current)
        entry = self._acc_cbs.get(name)
        if entry:
            cb, _ = entry
            self._apply_cb_style(cb, name, checked)
        if not checked and name == self._highlighted_acc:
            self._clear_highlight()
        self._refresh_chart()
        self._fill_table()

    def _on_cb_clicked(self, name):
        entry = self._acc_cbs.get(name)
        if not entry:
            self._clear_highlight()
            return
        cb, _ = entry
        if not cb.isChecked():
            self._clear_highlight()
            return
        if name == self._highlighted_acc:
            self._clear_highlight()
        else:
            self._set_highlighted(name)

    def _on_acc_table_clicked(self, row, col):
        items = list(self._acc_cbs.keys())
        if row < len(items):
            name = items[row]
            cb, _ = self._acc_cbs[name]
            cb.setChecked(not cb.isChecked())

    # ── Data helper ───────────────────────────────────────────────────────────
    def _get_view_data(self, acc_name):
        """Return {period: value} for current view and account."""
        view = self._current_view
        if view == "Balance":
            acc = next((a for a in self._all_accounts if a["name"] == acc_name), None)
            if not acc:
                return {}
            return {p: self._snapshots.get(p, {}).get(acc["id"], 0.0)
                    for p in self._all_periods}
        elif view == "Income":
            return {p: self._income_data.get(acc_name, {}).get(p, 0.0)
                    for p in self._all_periods}
        elif view == "Expense":
            return {p: self._expense_data.get(acc_name, {}).get(p, 0.0)
                    for p in self._all_periods}
        else:  # Transfer
            return {p: self._transfer_data.get(acc_name, {}).get(p, 0.0)
                    for p in self._all_periods}

    # ── Chart ─────────────────────────────────────────────────────────────────
    def _refresh_chart(self):
        if self._refreshing_chart:
            return
        self._refreshing_chart = True
        try:
            self._do_refresh_chart()
        finally:
            self._refreshing_chart = False

    def _reset_hover_state(self):
        self._line_series_data = {}
        self._line_series_objects = {}
        self._highlighted_acc = None
        self._overlay_series = None
        self._hover_dot_series = None
        self._last_hover_key = None
        self.chart_view.hide_hover()
        if self._stack_overlay_widget:
            try:
                self._stack_overlay_widget.hide()
            except Exception:
                pass

    def _do_refresh_chart(self):
        selected = self._get_selected_accs()
        if not self._all_periods or not selected:
            self._reset_hover_state()
            self.chart_view.setChart(make_chart("No data"))
            style_chart_view(self.chart_view)
            return

        self._reset_hover_state()

        labels = [f"{m[:3]} {str(y)[2:]}" for y, m in self._all_periods]
        chart_type = self._current_chart_type
        view = self._current_view

        # Auto-switch stacked if not allowed
        if chart_type == "Stacked Bars" and view not in _VIEW_ALLOW_STACK:
            chart_type = "Line"

        # Single period → force bars
        if chart_type in ("Line", "Spline") and len(self._all_periods) == 1:
            chart_type = "Grouped Bars"
            self._set_chart_type("Grouped Bars", emit=False)

        self._current_chart_type = chart_type

        animated = chart_type not in ("Line", "Spline")
        chart = make_chart(f"Account {view} by Month", animated=animated)
        chart.legend().setVisible(False)

        ax_x = make_x_axis(labels)
        chart.addAxis(ax_x, Qt.AlignBottom)
        ax_y = make_y_axis()

        # Compute y range
        if chart_type == "Stacked Bars":
            all_vals = [
                sum(self._get_view_data(name).get(p, 0) for name in selected)
                for p in self._all_periods
            ]
        else:
            all_vals = [
                self._get_view_data(name).get(p, 0)
                for name in selected
                for p in self._all_periods
            ]
        max_val = max((abs(v) for v in all_vals), default=0)
        min_val = min(all_vals, default=0)
        ax_y.setRange(min(0, min_val * 1.1), max_val * 1.1 or 1)
        chart.addAxis(ax_y, Qt.AlignLeft)

        if chart_type in ("Line", "Spline"):
            for name in selected:
                color = QColor(self._account_colors.get(name, "#7c6af7"))
                data = self._get_view_data(name)
                series = QSplineSeries() if chart_type == "Spline" else QLineSeries()
                series.setName(name)
                pen = QPen(color)
                pen.setWidth(2)
                series.setPen(pen)
                points = []
                for pi, period in enumerate(self._all_periods):
                    val = float(data.get(period, 0))
                    series.append(pi, val)
                    points.append((pi, val, labels[pi]))
                self._line_series_data[name] = points
                self._line_series_objects[name] = series
                chart.addSeries(series)
                series.attachAxis(ax_x)
                series.attachAxis(ax_y)

        elif chart_type == "Grouped Bars":
            bar_series = QBarSeries()
            for name in selected:
                color = QColor(self._account_colors.get(name, "#7c6af7"))
                data = self._get_view_data(name)
                bar_set = QBarSet(name)
                bar_set.setColor(color)
                for period in self._all_periods:
                    bar_set.append(data.get(period, 0))

                def _make_hover(bs, labels_ref, acc_name):
                    def on_hover(state, idx):
                        if state and 0 <= idx < bs.count():
                            text = f"{bs.label()}\n{labels_ref[idx]}   ${bs.at(idx):,.2f}"
                            self._active_bar_hover = (text, self._account_colors.get(acc_name))
                            self.chart_view.show_hover(text, self._last_mouse_pos,
                                                       self._account_colors.get(acc_name))
                            self._highlight_cb(acc_name)
                        else:
                            self._active_bar_hover = None
                            self.chart_view.hide_hover()
                            self._highlight_cb(None)

                    return on_hover

                bar_set.hovered.connect(_make_hover(bar_set, labels, name))
                bar_series.append(bar_set)

            chart.addSeries(bar_series)
            bar_series.attachAxis(ax_x)
            bar_series.attachAxis(ax_y)

        else:  # Stacked Bars — use _StackedOverlay like charts tab
            # Build data dict keyed by period
            chart_data = {}
            for period in self._all_periods:
                chart_data[period] = {}
                for name in selected:
                    val = self._get_view_data(name).get(period, 0.0)
                    if val > 0:
                        chart_data[period][name] = val

            per_month_order = []
            for period in self._all_periods:
                sorted_accs = sorted(
                    selected,
                    key=lambda n, p=period: chart_data[p].get(n, 0),
                    reverse=True,
                )
                per_month_order.append(sorted_accs)

            # Dummy series to drive the axes
            dummy_series = QStackedBarSeries()
            dummy_set = QBarSet("")
            dummy_set.setColor(QColor(0, 0, 0, 0))
            dummy_set.setBorderColor(QColor(0, 0, 0, 0))
            for period in self._all_periods:
                dummy_set.append(sum(chart_data[period].get(n, 0) for n in selected))
            dummy_series.append(dummy_set)
            chart.addSeries(dummy_series)
            dummy_series.attachAxis(ax_x)
            dummy_series.attachAxis(ax_y)

            self._stacked_paint_data = {
                "all_periods": self._all_periods,
                "per_month_order": per_month_order,
                "data": chart_data,
                "labels": labels,
                "cat_colors": {name: self._account_colors.get(name, "#7c6af7")
                               for name in selected},
            }

            if self._stack_overlay_widget:
                try:
                    self._stack_overlay_widget.deleteLater()
                except Exception:
                    pass

            self._stack_overlay_widget = StackedOverlay(
                self.chart_view,
                self._stacked_paint_data,
                on_hover_cb=self._on_stack_overlay_hover,
            )
            self._stack_overlay_widget.show()

        self.chart_view.setChart(chart)
        style_chart_view(self.chart_view)

    # ── Stacked overlay hover ─────────────────────────────────────────────────
    def _on_stack_overlay_hover(self, hit):
        if hit is None:
            self.chart_view.hide_hover()
            self._highlight_cb(None)
            return
        pi, acc_name, val, baseline, vp_pos = hit
        labels = [f"{m[:3]} {str(y)[2:]}" for y, m in self._all_periods]
        month_lbl = labels[pi] if pi < len(labels) else ""
        color = self._account_colors.get(acc_name)
        self.chart_view.show_hover(
            f"{acc_name}\n{month_lbl}   ${val:,.2f}",
            vp_pos, color,
        )
        self._highlight_cb(acc_name)

    # ── Mouse events ──────────────────────────────────────────────────────────
    def _on_mouse_move(self, pos):
        self._last_mouse_pos = pos
        if self._current_chart_type in ("Grouped Bars", "Stacked Bars"):
            if self._active_bar_hover:
                text, color = self._active_bar_hover
                self.chart_view.show_hover(text, pos, color)
        else:
            self._on_chart_mouse_move(pos)

    def _on_mouse_leave(self):
        self._last_mouse_pos = None
        self._active_bar_hover = None
        self._clear_highlight()

    # ── Line hover ────────────────────────────────────────────────────────────
    def _on_chart_mouse_move(self, pos):
        if self._current_chart_type not in ("Line", "Spline") or not self._line_series_data:
            return
        chart = self.chart_view.chart()
        if not chart:
            return
        try:
            scene_pos = self.chart_view.mapToScene(pos)
            chart_pos = chart.mapFromScene(scene_pos)
            if not chart.plotArea().contains(chart_pos):
                self._clear_highlight()
                return
            result = self._nearest_line_at_position(chart, chart_pos)
            if result is None:
                self._clear_highlight()
                return
            name, x, label, value, dist_sq = result
            if dist_sq <= 18 ** 2:
                hover_key = (name, x, value)
                if hover_key == self._last_hover_key:
                    return
                self._last_hover_key = hover_key
                self._set_highlighted(name, hover_point=(x, value))
                dot_chart_pos = self._map_to_chart_position(chart, name, x, value)
                dot_scene_pos = chart.mapToScene(dot_chart_pos)
                dot_vp_pos = self.chart_view.mapFromScene(dot_scene_pos)
                self.chart_view.show_hover(
                    f"{name}\n{label}   ${value:,.2f}",
                    dot_vp_pos,
                    self._account_colors.get(name),
                )
            else:
                self._clear_highlight()
        except Exception as exc:
            pass

    def _nearest_line_at_position(self, chart, chart_pos):
        best, best_dist_sq = None, float("inf")
        for name, points in self._line_series_data.items():
            if not points:
                continue
            mapped = [(self._map_to_chart_position(chart, name, x, y), x, y, label)
                      for x, y, label in points]
            if len(mapped) == 1:
                p, x, y, label = mapped[0]
                d = self._point_dist_sq(chart_pos, p)
                if d < best_dist_sq:
                    best, best_dist_sq = (name, x, label, y, d), d
                continue
            for i in range(len(mapped) - 1):
                p1, x1, y1, l1 = mapped[i]
                p2, x2, y2, l2 = mapped[i + 1]
                d = self._seg_dist_sq(chart_pos, p1, p2)
                nx, nl, nv = (x1, l1, y1) if self._point_dist_sq(chart_pos, p1) <= self._point_dist_sq(chart_pos,
                                                                                                       p2) else (x2, l2,
                                                                                                                 y2)
                if d < best_dist_sq:
                    best, best_dist_sq = (name, nx, nl, nv, d), d
        return best

    def _map_to_chart_position(self, chart, name, x, y):
        series = self._line_series_objects.get(name)
        try:
            return chart.mapToPosition(QPointF(float(x), float(y)), series)
        except TypeError:
            return chart.mapToPosition(QPointF(float(x), float(y)))

    @staticmethod
    def _point_dist_sq(p1, p2):
        return (p1.x() - p2.x()) ** 2 + (p1.y() - p2.y()) ** 2

    @staticmethod
    def _seg_dist_sq(p, a, b):
        ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
        px, py = p.x(), p.y()
        vx, vy = bx - ax, by - ay
        denom = vx * vx + vy * vy
        if denom <= 0:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / denom))
        return (px - (ax + t * vx)) ** 2 + (py - (ay + t * vy)) ** 2

    def _clear_highlight(self):
        self._last_hover_key = None
        self._set_highlighted(None)
        self.chart_view.hide_hover()

    def _set_highlighted(self, acc_name, hover_point=None):
        chart = self.chart_view.chart()
        if not chart:
            return

        if self._overlay_series is not None:
            try:
                chart.removeSeries(self._overlay_series)
            except RuntimeError:
                pass
            self._overlay_series = None

        if self._hover_dot_series is not None:
            try:
                chart.removeSeries(self._hover_dot_series)
            except RuntimeError:
                pass
            self._hover_dot_series = None

        self._highlighted_acc = acc_name

        if acc_name and self._current_chart_type in ("Line", "Spline") \
                and acc_name in self._line_series_data:
            color = QColor(self._account_colors.get(acc_name, "#7c6af7"))
            overlay = QSplineSeries() if self._current_chart_type == "Spline" else QLineSeries()
            overlay.setName(f"__overlay_{acc_name}")
            pen = QPen(color)
            pen.setWidth(5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            overlay.setPen(pen)
            for x, y, _ in self._line_series_data[acc_name]:
                overlay.append(x, y)
            chart.addSeries(overlay)
            axes_x = chart.axes(Qt.Horizontal)
            axes_y = chart.axes(Qt.Vertical)
            if axes_x: overlay.attachAxis(axes_x[0])
            if axes_y: overlay.attachAxis(axes_y[0])
            self._overlay_series = overlay

            if hover_point is not None:
                x, y = hover_point
                dot = QScatterSeries()
                dot.setName(f"__dot_{acc_name}")
                dot.setMarkerSize(12.0)
                dot.setColor(color)
                dot.setBorderColor(color)
                try:
                    dot.setMarkerShape(QScatterSeries.MarkerShape.MarkerShapeCircle)
                except AttributeError:
                    dot.setMarkerShape(QScatterSeries.MarkerShapeCircle)
                dot.append(float(x), float(y))
                chart.addSeries(dot)
                if axes_x: dot.attachAxis(axes_x[0])
                if axes_y: dot.attachAxis(axes_y[0])
                self._hover_dot_series = dot

        self._highlight_cb(acc_name)

    # ── Table ─────────────────────────────────────────────────────────────────
    def _fill_table(self):
        s = get_settings()
        selected = self._get_selected_accs()
        all_periods = self._all_periods
        view = self._current_view

        if not all_periods:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        col_labels = [f"{m[:3]} {str(y)[2:]}" for y, m in all_periods]
        accs = [a for a in self._all_accounts if a["name"] in selected]
        n_rows = len(accs) + 1

        self.table.setRowCount(n_rows)
        self.table.setColumnCount(len(col_labels))
        self.table.setHorizontalHeaderLabels(col_labels)

        row_labels = [a["name"] for a in accs]
        row_labels.append("Total")
        self.table.setVerticalHeaderLabels(row_labels)

        for ri, acc in enumerate(accs):
            name = acc["name"]
            color = self._account_colors.get(name, "#7c6af7")
            data = self._get_view_data(name)

            for ci, period in enumerate(all_periods):
                val = data.get(period, 0.0)
                self.table.setItem(ri, ci, self._make_item(
                    f"${val:,.2f}" if val else "",
                    self._value_color(val, view, s),
                ))

            hdr = self.table.verticalHeaderItem(ri)
            if hdr:
                hdr.setForeground(QBrush(QColor(color)))
                hdr.setData(Qt.UserRole, name)
                f = hdr.font()
                f.setBold(False)
                hdr.setFont(f)

        # Total row
        total_row = len(accs)
        for ci, period in enumerate(all_periods):
            total = sum(self._get_view_data(a["name"]).get(period, 0.0) for a in accs)
            self.table.setItem(total_row, ci, self._make_item(
                f"${total:,.2f}",
                self._value_color(total, view, s),
                bold=True, s=s,
            ))
        hdr = self.table.verticalHeaderItem(total_row)
        if hdr:
            hdr.setData(Qt.UserRole, "Total")
            hdr.setFont(QFont(s.get("font_family"), s.get("font_size"), QFont.Bold))
            hdr.setForeground(QBrush(QColor(s.get("text"))))

        # Scroll to latest
        last = self.table.columnCount() - 1
        if last >= 0 and self.table.item(0, last):
            self.table.scrollToItem(self.table.item(0, last))

    def _value_color(self, val, view, s):
        if view == "Balance":
            return s.get("income") if val > 0 else s.get("expense") if val < 0 else s.get("text_dim")
        elif view == "Income":
            return s.get("income") if val else s.get("text_dim")
        elif view == "Expense":
            return s.get("expense") if val else s.get("text_dim")
        else:  # Transfer
            return s.get("income") if val > 0 else s.get("expense") if val < 0 else s.get("text_dim")

    def _make_item(self, text, color, bold=False, s=None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        item.setForeground(QBrush(QColor(color)))
        if bold and s:
            item.setFont(QFont(s.get("font_family"), s.get("font_size"), QFont.Bold))
        return item

    def _copy_table(self):
        selected = self.table.selectedIndexes()
        sel_rows = sorted(set(i.row() for i in selected)) if selected else list(range(self.table.rowCount()))
        sel_cols = sorted(set(i.column() for i in selected)) if selected else list(range(self.table.columnCount()))
        if not sel_rows or not sel_cols:
            return
        lines = ["\t".join(
            [""] + [(self.table.horizontalHeaderItem(c).text()
                     if self.table.horizontalHeaderItem(c) else "") for c in sel_cols]
        )]
        for r in sel_rows:
            hdr = self.table.verticalHeaderItem(r)
            lines.append("\t".join(
                [hdr.text() if hdr else ""] +
                [(self.table.item(r, c).text() if self.table.item(r, c) else "") for c in sel_cols]
            ))
        QApplication.clipboard().setText("\n".join(lines))
