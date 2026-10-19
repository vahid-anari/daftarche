from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSizePolicy, QCheckBox, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QPoint, QPointF, QObject, QEvent
from PySide6.QtGui import QFont, QColor, QPen, QKeySequence, QShortcut
from PySide6.QtCharts import (
    QBarSeries, QBarSet, QStackedBarSeries,
    QSplineSeries, QLineSeries, QScatterSeries,
    QPieSeries, QPieSlice
)
from daftarche.db import MONTH_NUM, MONTHS_ORDER
from daftarche.widgets import money, plain_label, PeriodSelectorWidget, StepSpinBox, CheckComboBox, SingleSelectCombo
from daftarche.style import get_settings, TAB20_COLORS
from daftarche.tabs.chart_detail import DetailPanel
from daftarche.chart_utils import HoverChartView, StackedOverlay, make_chart, make_x_axis, make_y_axis, style_chart_view


# Helpers
def _make_cb_stylesheet(color_hex):
    """Per-category QCheckBox stylesheet using the item's color and theme colors."""
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


# ChartsTab

def _month_key(ym):
    return ym[0], MONTH_NUM.get(ym[1], 0)


def _months_between(first, last):
    """Every (year, month name) from ``first`` to ``last``, both included."""
    year, month = first[0], MONTH_NUM[first[1]]
    end = _month_key(last)
    out = []
    while (year, month) <= end:
        out.append((year, MONTHS_ORDER[month - 1]))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


MULTI_MONTH_CHARTS = ["Line", "Spline", "Grouped Bars", "Stacked Bars", "Donut"]
ONE_MONTH_CHARTS = ["Donut", "Bars", "Stacked Bars"]
_SAME_CHART = {"Bars": "Grouped Bars", "Grouped Bars": "Bars"}  # one name per list for the same view


class ChartsTab(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self._cat_colors = {}
        self._cat_totals = {}
        self._cat_cbs = {}

        self._line_series_data = {}
        self._line_series_objects = {}
        self._highlighted_cat = None
        self._overlay_series = None
        self._hover_dot_series = None
        self._ignore_cb_changed = False
        self._current_chart_type = "Line"
        self._hover_threshold_px = 18
        self._last_mouse_pos = None
        self._active_bar_hover = None
        self._last_hover_key = None
        self._stack_overlay_widget = None
        self._refreshing_chart = False
        self._chart_periods = []
        self._n_chart_cats = 0
        self._wanted_chart = "Line"  # the last chart picked by hand; a one-month range shows Donut instead of a line
        self._one_month = None
        self._month_totals = []  # per month of the chart: the ticked categories added up
        self._total_item = None


        self._build_ui()
        self.refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        s = get_settings()
        ff = s.get("font_family")
        fs = s.get("font_size")

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Row 1: Period | Account ───────────────────────────────────────────
        self._period = PeriodSelectorWidget(mode="month", config_key="period_charts")
        self.f_account = CheckComboBox("All Accounts")

        self.f_account.selectionChanged.connect(lambda *_: self._on_range_or_account_changed())
        self._period.rangeChanged.connect(lambda *_: self._on_range_or_account_changed())

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._period)
        row1.addSpacing(20)
        row1.addWidget(QLabel("Account:"))
        row1.addWidget(self.f_account)
        row1.addStretch(1)
        layout.addLayout(row1)

        # ── Row 2: Type | Category | Chart | Y range ──────────────────────────
        self.f_type = SingleSelectCombo()
        self.f_type.addItems(["Expense", "Income"])
        self.f_cat_selector = SingleSelectCombo("All")
        self.f_chart_type = SingleSelectCombo()
        self.f_chart_type.addItems(MULTI_MONTH_CHARTS)
        self.chk_custom_y = QCheckBox("Use custom y")
        self.f_y_min = StepSpinBox(value=0, min_val=-999999, max_val=999999, step=100)
        self.f_y_min.setMinimumWidth(100)
        self.f_y_min.setEnabled(False)

        self.f_y_max = StepSpinBox(value=5000, min_val=0, max_val=9999999, step=100)
        self.f_y_max.setMinimumWidth(100)
        self.f_y_max.setEnabled(False)

        self.f_type.currentTextChanged.connect(self._on_type_changed)
        self.f_cat_selector.selectionChanged.connect(lambda *_: self._on_category_pick_changed())
        self.f_chart_type.currentTextChanged.connect(self._on_chart_type_picked)
        self.chk_custom_y.stateChanged.connect(self._on_custom_y_toggle)
        self.f_y_min.valueChanged.connect(self._refresh_chart)
        self.f_y_max.valueChanged.connect(self._refresh_chart)

        self.f_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("Type:"))
        row2.addWidget(self.f_type)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Category:"))
        row2.addWidget(self.f_cat_selector)
        row2.addStretch(1)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Chart:"))
        row2.addWidget(self.f_chart_type)
        row2.addSpacing(20)
        row2.addWidget(self.chk_custom_y)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Min:"))
        row2.addWidget(self.f_y_min, 0)
        row2.addSpacing(20)
        row2.addWidget(QLabel("Max:"))
        row2.addWidget(self.f_y_max, 0)

        layout.addLayout(row2)

        # ── Chart area ────────────────────────────────────────────────────────
        self.chart_view = HoverChartView()
        self.chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chart_view.mouseMoved.connect(self._on_mouse_move)
        self.chart_view.mouseLeft.connect(self._on_mouse_leave)

        # ── Category panel ────────────────────────────────────────────────────
        self.cat_lbl = QLabel("Categories")
        self.cat_lbl.setFont(QFont(ff, fs, QFont.Bold))
        btn_all = QPushButton("All")
        btn_none = QPushButton("None")

        self._cat_table = QTableWidget(0, 2)
        self._cat_table.horizontalHeader().setVisible(False)
        self._cat_table.verticalHeader().setVisible(False)
        self._cat_table.setShowGrid(False)
        self._cat_table.setSelectionMode(QTableWidget.NoSelection)
        self._cat_table.setFocusPolicy(Qt.NoFocus)
        self._cat_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._cat_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._cat_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._cat_table.setFrameShape(QFrame.NoFrame)
        self._cat_table.setStyleSheet(
            "QTableWidget { background: transparent; border: none; outline: none; }"
            "QTableWidget::item { background: transparent; border: none; padding: 2px 4px; }"
            "QTableWidget::item:selected { background: transparent; }"
        )

        btn_all.clicked.connect(self._select_all_cats)
        btn_none.clicked.connect(self._select_no_cats)
        self._cat_table.cellClicked.connect(self._on_table_cell_clicked)

        cat_panel = QFrame()
        cat_panel.setObjectName("cat_panel")
        cat_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        cat_outer = QVBoxLayout(cat_panel)
        cat_outer.setContentsMargins(10, 10, 10, 10)
        cat_outer.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)

        cat_outer.addWidget(self.cat_lbl)
        cat_outer.addSpacing(4)
        cat_outer.addLayout(btn_row)
        cat_outer.addWidget(self._cat_table, 1)

        chart_layout = QVBoxLayout()
        chart_layout.addWidget(self.chart_view, 1)

        # ── Detail panel: what is inside the category under the mouse ────────
        self.detail = DetailPanel()
        self.chart_view.mousePressed.connect(lambda _pos: self.detail.toggle_pinned())
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=lambda: self.detail.set_pinned(False))

        bottom_layout = QHBoxLayout()
        bottom_layout.addLayout(chart_layout)
        bottom_layout.addWidget(cat_panel)
        bottom_layout.addWidget(self.detail)
        layout.addLayout(bottom_layout, 1)

    # ── Styling helpers ───────────────────────────────────────────────────────

    def _set_default_hover_info(self, chart_type):
        self.chart_view.hide_hover()

    # ── Mouse event handlers ──────────────────────────────────────────────────

    def _on_mouse_move(self, pos):
        self._last_mouse_pos = pos
        if self._current_chart_type in ("Grouped Bars", "Stacked Bars", "Donut"):
            self._move_active_hover_label()
        else:
            self._on_chart_mouse_move(pos)

    def _on_mouse_leave(self):
        self._last_mouse_pos = None
        self._active_bar_hover = None
        self._clear_highlight()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_custom_y_toggle(self, state):
        self._update_custom_y_enabled()
        self._refresh_chart()

    def _update_custom_y_enabled(self):
        has_y = self.f_chart_type.currentText() != "Donut"
        self.chk_custom_y.setEnabled(has_y)
        self.f_y_min.setEnabled(has_y and self.chk_custom_y.isChecked())
        self.f_y_max.setEnabled(has_y and self.chk_custom_y.isChecked())

    def _on_chart_type_picked(self, text):
        if text:
            self._wanted_chart = text
        self._update_custom_y_enabled()
        self._refresh_chart()

    def _refresh_chart_choices(self):
        """One month: Donut, Bars, Stacked Bars. Several: Line, Spline, both bars and Donut."""
        from_year, from_month, to_year, to_month = self._get_range()
        one_month = bool(from_year) and (from_year, from_month) == (to_year, to_month)
        if one_month == self._one_month:
            return
        self._one_month = one_month
        items = ONE_MONTH_CHARTS if one_month else MULTI_MONTH_CHARTS
        wanted = self._wanted_chart
        pick = wanted if wanted in items else _SAME_CHART.get(wanted)
        if pick not in items:
            pick = "Donut"
        self.f_chart_type.set_items(items, include_all=False, selected=pick, emit=False)
        self._update_custom_y_enabled()

    def _on_range_or_account_changed(self):
        self.detail.clear()
        self._refresh_chart_choices()
        self._refresh_category_picker()
        self._refresh_cat_list()
        self._refresh_chart()

    def _on_type_changed(self):
        self.detail.clear()
        self._refresh_category_picker()
        self._refresh_cat_list()
        self._refresh_chart()

    def _on_category_pick_changed(self):
        self.detail.clear()
        self._refresh_cat_list()
        self._refresh_chart()

    def _on_table_cell_clicked(self, row, col):
        items_in_order = list(self._cat_cbs.keys())
        if row < len(items_in_order):
            name = items_in_order[row]
            cb, _ = self._cat_cbs[name]
            cb.setChecked(not cb.isChecked())

    def _on_cb_toggled(self, name, checked):
        if self._ignore_cb_changed:
            return
        entry = self._cat_cbs.get(name)
        if entry:
            cb, _ = entry
            self._apply_cb_style(cb, name, checked)
        self._update_total_row()
        if not checked and name == self._highlighted_cat:
            self._clear_highlight()
        self._refresh_chart()

    def _on_cb_clicked(self, name):
        entry = self._cat_cbs.get(name)
        if not entry:
            self._clear_highlight()
            return
        cb, _ = entry
        if not cb.isChecked():
            self._clear_highlight()
            return
        if name == self._highlighted_cat:
            self._clear_highlight()
        else:
            self._set_highlighted(name)

    def _move_active_hover_label(self):
        if not self._active_bar_hover or self._last_mouse_pos is None:
            return
        text, color = self._active_bar_hover
        self.chart_view.show_hover(text, self._last_mouse_pos, color)

    # ── Checkbox helpers ──────────────────────────────────────────────────────

    def _apply_cb_style(self, cb: QCheckBox, name: str, checked: bool):
        s = get_settings()
        fs = s.get("font_size") or 11
        color = self._cat_colors.get(name)
        text_color = s.get("text") if checked else (s.get("text_dim") or "#888")
        dim_color = s.get("text_dim") or "#888"
        cb.setStyleSheet(
            (_make_cb_stylesheet(color) if color else "") +
            f" QCheckBox {{ color: {text_color}; font-size: {fs}pt; spacing: 6px; }}"
        )
        entry = self._cat_cbs.get(name)
        if entry and isinstance(entry, tuple):
            _, amt_item = entry
            total = self._cat_totals.get(name, 0)
            amt_item.setText(f"{money(total, 0)}" if total else "")
            amt_item.setForeground(QColor(s.get("income") if total < 0 else dim_color))  # money back: green

    def _select_all_cats(self):
        self._ignore_cb_changed = True
        for name, (cb, _) in self._cat_cbs.items():
            cb.setChecked(True)
            self._apply_cb_style(cb, name, True)
        self._ignore_cb_changed = False
        self._update_total_row()
        self._clear_highlight()
        self._refresh_chart()

    def _select_no_cats(self):
        self._ignore_cb_changed = True
        for name, (cb, _) in self._cat_cbs.items():
            cb.setChecked(False)
            self._apply_cb_style(cb, name, False)
        self._ignore_cb_changed = False
        self._update_total_row()
        self._clear_highlight()
        self._refresh_chart()

    def _update_total_row(self):
        if self._total_item is not None:
            self._total_item.setText(f"{money(sum(self._cat_totals.get(n, 0) for n in self._get_selected_cats()), 0)}")

    def _with_month_total(self, text, period_index):
        """Adds 'Month total' to a hover label when the chart has more than one category."""
        if self._n_chart_cats > 1 and 0 <= period_index < len(self._month_totals):
            text += f"\nMonth total   {money(self._month_totals[period_index])}"
        return text

    def _get_selected_cats(self):
        return [name for name, (cb, _) in self._cat_cbs.items() if cb.isChecked()]

    def _highlight_cb(self, cat_name):
        s = get_settings()
        fs = s.get("font_size") or 11
        for name, (cb, amt_item) in self._cat_cbs.items():
            if name == cat_name and cb.isChecked():
                color = self._cat_colors.get(name, "#7c6af7")
                cb.setStyleSheet(
                    _make_cb_stylesheet(color) +
                    f" QCheckBox {{ color: {s.get('text')}; font-size: {fs + 2}pt; font-weight: bold; spacing: 6px; }}"
                )
                total = self._cat_totals.get(name, 0)
                amt_item.setText(f"{money(total, 0)}" if total else "")
                amt_item.setForeground(QColor(s.get("text")))
                f = amt_item.font()
                f.setPointSize(fs + 2)
                f.setBold(True)
                amt_item.setFont(f)
            else:
                self._apply_cb_style(cb, name, cb.isChecked())
                amt_item.setFont(QFont())

    # ── Data refresh ──────────────────────────────────────────────────────────

    def _refresh_account_filter(self):
        self.f_account.blockSignals(True)
        self.f_account.populate([a["name"] for a in self.db.get_accounts(visible_only=True)], keep_selection=True)
        self.f_account.blockSignals(False)

    def _refresh_category_picker(self):
        type_filter = "Expense" if "Expense" in self.f_type.currentText() else "Income"
        from_year, from_month, to_year, to_month = self._get_range()
        current = self.f_cat_selector.current_text() if hasattr(self, "f_cat_selector") else "All"

        if from_year:
            selected_accounts = self.f_account.get_selected() if hasattr(self, "f_account") else []
            cats = self.db.get_categories_in_month_range(
                from_year, from_month, to_year, to_month,
                type_filter,
                account_names=selected_accounts or None,
            )
        else:
            cats = sorted(set(
                c["name"] for c in self.db.get_categories()
                if type_filter in (c["type_name"] or "")
            ))

        selected = current if current in cats else "All"
        # every caller refreshes the list and the chart itself right after: no signal, no second pass
        self.f_cat_selector.set_items(cats, include_all=True, selected=selected, emit=False)

    def refresh(self):
        s = get_settings()
        ff = s.get("font_family")
        fs = s.get("font_size")

        self.cat_lbl.setFont(QFont(ff, fs, QFont.Bold))
        self.chart_view.refresh_hover_style()

        self._refresh_account_filter()
        self._refresh_chart_choices()
        self._refresh_category_picker()
        self._refresh_cat_list()
        self._period.refresh_style()
        self.f_account.refresh_style()
        self._refresh_chart()

    def _refresh_cat_list(self):
        self._cat_colors = {}
        type_filter = "Expense" if "Expense" in self.f_type.currentText() else "Income"
        selected_cat = self.f_cat_selector.current_text() if hasattr(self, "f_cat_selector") else "All"
        from_year, from_month, to_year, to_month = self._get_range()

        old_states = {name: cb.isChecked() for name, (cb, _) in self._cat_cbs.items()}

        self._cat_totals = {}
        if from_year:
            selected_accounts = self.f_account.get_selected() if hasattr(self, "f_account") else []
            self._cat_totals = self.db.get_period_totals_by_group(
                from_year, from_month, to_year, to_month,
                type_filter=type_filter,
                account_names=selected_accounts or None,
                category_name=None if selected_cat == "All" else selected_cat,
                group_by="category" if selected_cat == "All" else "subcategory",
            )

        if selected_cat == "All":
            self.cat_lbl.setText("Categories")
            all_items = sorted(set(
                c["name"] for c in self.db.get_categories()
                if type_filter in (c["type_name"] or "")
            ))
        else:
            self.cat_lbl.setText(f"Sub-Categories ({selected_cat})")
            cat_obj = self.db.get_category_by_name(selected_cat)
            all_items = sorted(set(
                s["name"] for s in self.db.get_subcategories(cat_obj["id"])
            )) if cat_obj else []

        items = sorted(
            [n for n in all_items if round(self._cat_totals.get(n, 0), 2) != 0],  # money back can make one negative
            key=lambda n: self._cat_totals.get(n, 0), reverse=True,
        )

        for ci, name in enumerate(items):
            if name not in self._cat_colors:
                idx = len(self._cat_colors)
                self._cat_colors[name] = TAB20_COLORS[idx % len(TAB20_COLORS)]

        self._ignore_cb_changed = True
        self._cat_table.setRowCount(0)
        self._cat_cbs = {}

        class _CbHoverFilter(QObject):
            def __init__(self_, cb, name):
                super().__init__(cb)
                self_._cb = cb
                self_._name = name

            def eventFilter(self_, obj, event):
                if event.type() == QEvent.Enter:
                    self._detail(self_._name)  # the whole range
                    if self_._cb.isChecked():
                        if self._current_chart_type == "Donut":
                            self._donut_highlight_from_cb(self_._name, True)
                        elif self._current_chart_type in ("Line", "Spline"):
                            self._set_highlighted(self_._name)
                        else:
                            self._highlight_cb(self_._name)
                elif event.type() == QEvent.Leave:
                    if self._current_chart_type == "Donut":
                        self._donut_highlight_from_cb(self_._name, False)
                    elif self._current_chart_type in ("Line", "Spline"):
                        if self._highlighted_cat == self_._name:
                            self._clear_highlight()
                    else:
                        self._highlight_cb(None)
                return False

        for row, name in enumerate(items):
            checked = old_states.get(name, True)
            total = self._cat_totals.get(name, 0)

            self._cat_table.insertRow(row)

            cb = QCheckBox(plain_label(name))
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
            self._cat_table.setCellWidget(row, 0, cb_container)

            amt_item = QTableWidgetItem(f"{money(total, 0)}" if total else "")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._cat_table.setItem(row, 1, amt_item)

            self._cat_table.setRowHeight(row, 28)
            self._apply_cb_style(cb, name, checked)
            self._cat_cbs[name] = (cb, amt_item)

        self._add_total_row()
        self._ignore_cb_changed = False

    def _add_total_row(self):
        """A line, then 'Total': the ticked categories over the whole range."""
        s = get_settings()
        self._total_item = None
        if not self._cat_cbs:
            return
        row = self._cat_table.rowCount()
        self._cat_table.insertRow(row)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {s.get('border')};")
        self._cat_table.setSpan(row, 0, 1, 2)
        self._cat_table.setCellWidget(row, 0, rule)
        self._cat_table.setRowHeight(row, 9)

        bold = QFont()
        bold.setBold(True)
        row += 1
        self._cat_table.insertRow(row)
        label = QTableWidgetItem("Total")
        label.setFont(bold)
        label.setForeground(QColor(s.get("text")))
        self._cat_table.setItem(row, 0, label)
        self._total_item = QTableWidgetItem()
        self._total_item.setFont(bold)
        self._total_item.setForeground(QColor(s.get("text")))
        self._total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._cat_table.setItem(row, 1, self._total_item)
        self._cat_table.setRowHeight(row, 28)
        self._update_total_row()

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _detail(self, name, period_index=None):
        """Show what is inside ``name`` (a category: its sub-categories; a sub-category: its
        transactions), in the month ``period_index`` of the chart or over the whole range."""
        if self.detail.pinned or not name:
            return
        type_filter = "Expense" if "Expense" in self.f_type.currentText() else "Income"
        selected_cat = self.f_cat_selector.current_text()
        accounts = self.f_account.get_selected()
        if period_index is not None and 0 <= period_index < len(self._chart_periods):
            fy, fm = ty, tm = self._chart_periods[period_index]
        else:
            fy, fm, ty, tm = self._get_range()
            if not fy:
                return
        when = f"{fm[:3]} {fy}" if (fy, fm) == (ty, tm) else f"{fm[:3]} {fy} – {tm[:3]} {ty}"
        key = (name, fy, fm, ty, tm, type_filter, selected_cat, tuple(accounts))
        if key == self.detail.key:
            return
        base = {"types": [type_filter], "accounts": list(accounts)}
        if selected_cat == "All":
            totals = self.db.get_period_totals_by_group(fy, fm, ty, tm, type_filter=type_filter,
                                                        account_names=accounts or None, category_name=name,
                                                        group_by="subcategory")
            items = sorted(((k, v) for k, v in totals.items() if v), key=lambda kv: kv[1], reverse=True)
            spent = sum(v for _, v in items if v > 0) or 1  # shares of what was spent; money back has none
            rows = [(f"{v / spent * 100:.0f}%" if v > 0 else "", sub, v,
                     {**base, "categories": [name], "subcategories": [sub]}) for sub, v in items]
            title = f"<b>{name}</b><br>{when}<br>{money(sum(v for _, v in items))}"
        else:
            from_day, to_day = self.db._month_range_dates(fy, fm, ty, tm)
            filters = {"type": [type_filter], "category": [selected_cat], "subcategory": [name],
                       "from_day": from_day, "to_day": to_day}
            if accounts:
                filters["account"] = list(accounts)
            txs = self.db.get_transactions(filters)
            open_filters = {**base, "categories": [selected_cat], "subcategories": [name]}
            rows = [(f"{MONTHS_ORDER[int(t['date'][5:7]) - 1][:3]} {int(t['date'][8:10])}",
                     ": ".join(x for x in (t["merchant"], t["note"]) if x) or t["name"] or t["memorandum"] or "",
                     t["amount"], open_filters) for t in txs]
            n = len(rows)
            title = (f"<b>{selected_cat} › {name}</b><br>{when}<br>{n} transaction{'s' if n != 1 else ''}"
                     f"  ·  {money(sum(r[2] for r in rows))}")
        self.detail.show_rows(key, title, rows)

    # ── Range helper ──────────────────────────────────────────────────────────

    def _get_range(self):
        from_date, to_date = self._period.get_range()
        if from_date is None:
            from_date, to_date = self.db.get_data_date_range()
        return (
            from_date.year,
            MONTHS_ORDER[from_date.month - 1],
            to_date.year,
            MONTHS_ORDER[to_date.month - 1],
        )

    # ── Chart refresh ─────────────────────────────────────────────────────────

    def _reset_hover_state_for_new_chart(self):
        self._line_series_data = {}
        self._line_series_objects = {}
        self._highlighted_cat = None
        self._overlay_series = None
        self._hover_dot_series = None
        self._last_hover_key = None
        self._donut_slices = {}
        self.chart_view.hide_hover()
        if self._stack_overlay_widget:
            try:
                self._stack_overlay_widget.hide()
            except Exception:
                pass

    def _show_empty_chart(self, message, animated=False):
        self._reset_hover_state_for_new_chart()
        self.chart_view.setChart(make_chart(message, animated=animated))
        style_chart_view(self.chart_view)

    def _refresh_chart(self):
        if self._refreshing_chart:
            return
        self._refreshing_chart = True
        try:
            self._do_refresh_chart()
        finally:
            self._refreshing_chart = False

    def _do_refresh_chart(self):
        from_year, from_month, to_year, to_month = self._get_range()
        if not from_year:
            return

        type_filter = "Expense" if "Expense" in self.f_type.currentText() else "Income"
        selected_cats = self._get_selected_cats()
        selected_accounts = self.f_account.get_selected() if hasattr(self, "f_account") else []
        selected_cat = self.f_cat_selector.current_text() if hasattr(self, "f_cat_selector") else "All"
        chart_type = self.f_chart_type.currentText()

        self._set_default_hover_info(chart_type)
        self._reset_hover_state_for_new_chart()

        animated = chart_type not in ("Line", "Spline")

        if not selected_cats:
            self._show_empty_chart("No categories selected", animated=animated)
            return

        if selected_cat == "All":
            data = self.db.get_monthly_category_totals(
                from_year, from_month, to_year, to_month,
                type_filter=type_filter,
                account_names=selected_accounts or None,
                category_name=None, group_by="category",
            )
            data = {k: {c: v for c, v in v.items() if c in selected_cats} for k, v in data.items()}
        else:
            data = self.db.get_monthly_category_totals(
                from_year, from_month, to_year, to_month,
                type_filter=type_filter,
                account_names=selected_accounts or None,
                category_name=selected_cat, group_by="subcategory",
            )
            data = {k: {c: v for c, v in v.items() if c in selected_cats} for k, v in data.items()}

        if not data:
            self._show_empty_chart("No data for selected range", animated=animated)
            return

        all_periods = _months_between(min(data, key=_month_key), max(data, key=_month_key))
        self._chart_periods = all_periods
        for period in all_periods:  # a month without data is a zero, not a gap the line skips over
            data.setdefault(period, {})
        labels = [f"{m[:3]} {str(y)[2:]}" for y, m in all_periods]
        all_cats = sorted({cat for pd in data.values() for cat in pd.keys()})
        all_cats = [c for c in all_cats if c in selected_cats]

        if not all_cats:
            self._show_empty_chart("No data for selected categories", animated=animated)
            return

        title = (f"Monthly {type_filter} by Category" if selected_cat == "All"
                 else f"Monthly {type_filter} - {selected_cat} (by Sub-Category)")

        self._month_totals = [sum(data[p].get(c, 0) for c in all_cats) for p in all_periods]
        self._n_chart_cats = len(all_cats)
        one_period = len(all_periods) == 1
        period_label = labels[0] if one_period else f"{labels[0]} – {labels[-1]}"
        if chart_type == "Bars":
            chart_type = "Grouped Bars"
        if chart_type in ("Line", "Spline") and one_period:  # a line needs two months
            chart_type = "Donut"

        if chart_type == "Donut":  # the whole range: each category's total
            totals = {cat: sum(data[p].get(cat, 0) for p in all_periods) for cat in all_cats}
            if not one_period:
                title = title.removeprefix("Monthly ")
            self._build_donut_chart(totals, all_cats, period_label, title)
            return

        if one_period:
            title = f"{title}  —  {period_label}"
            if chart_type == "Grouped Bars":
                self._build_one_month_bars(data[all_periods[0]], all_cats, title)
                return

        chart = make_chart(title, animated=animated)
        chart.legend().setVisible(False)

        ax_x = make_x_axis(labels)
        chart.addAxis(ax_x, Qt.AlignBottom)
        ax_y = make_y_axis()
        if self.chk_custom_y.isChecked():
            ax_y.setRange(self.f_y_min.value(), self.f_y_max.value())
        else:
            if chart_type == "Stacked Bars":
                all_vals = [sum(data[p].get(cat, 0) for cat in all_cats) for p in all_periods]
            else:
                all_vals = [data[p].get(cat, 0) for p in all_periods for cat in all_cats]
            max_val = max(all_vals) if all_vals else 0
            min_val = min(all_vals + [0])  # below 0 only when money back is more than spending
            ax_y.setRange(min_val * 1.1, max(max_val * 1.1, 1))
        chart.addAxis(ax_y, Qt.AlignLeft)

        self._current_chart_type = chart_type

        if chart_type in ("Line", "Spline"):
            for ci, cat in enumerate(all_cats):
                series = QSplineSeries() if chart_type == "Spline" else QLineSeries()
                series.setName(cat)
                color = QColor(self._cat_colors.get(cat, TAB20_COLORS[ci % len(TAB20_COLORS)]))
                pen = QPen(color)
                pen.setWidth(2)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                series.setPen(pen)

                points = []
                for pi, period in enumerate(all_periods):
                    val = float(data[period].get(cat, 0))
                    series.append(pi, val)
                    points.append((pi, val, labels[pi]))

                self._line_series_data[cat] = points
                self._line_series_objects[cat] = series
                chart.addSeries(series)
                series.attachAxis(ax_x)
                series.attachAxis(ax_y)

        elif chart_type == "Grouped Bars":
            series = QBarSeries()
            for ci, cat in enumerate(all_cats):
                bar_set = QBarSet(cat)
                bar_set.setColor(QColor(self._cat_colors.get(cat, TAB20_COLORS[ci % len(TAB20_COLORS)])))
                for period in all_periods:
                    bar_set.append(data[period].get(cat, 0))

                def _make_bar_hover(bs, labels_ref, cat_color):
                    def on_hover(state, idx):
                        if state and 0 <= idx < bs.count():
                            month_label = labels_ref[idx] if idx < len(labels_ref) else ""
                            value = bs.at(idx)
                            text = self._with_month_total(f"{bs.label()}\n{month_label}   {money(value)}", idx)
                            self._active_bar_hover = (text, cat_color)
                            self.chart_view.show_hover(text, self._last_mouse_pos, cat_color)
                            self._highlight_cb(bs.label())
                            self._detail(bs.label(), idx)
                        else:
                            self._active_bar_hover = None
                            self.chart_view.hide_hover()
                            self._highlight_cb(None)

                    return on_hover

                bar_color = self._cat_colors.get(cat, TAB20_COLORS[ci % len(TAB20_COLORS)])
                bar_set.hovered.connect(_make_bar_hover(bar_set, labels, bar_color))
                series.append(bar_set)

            chart.addSeries(series)
            series.attachAxis(ax_x)
            series.attachAxis(ax_y)

        else:  # Stacked Bars
            per_month_order = []
            for period in all_periods:
                sorted_cats = sorted(all_cats, key=lambda c, p=period: data[p].get(c, 0), reverse=True)
                per_month_order.append(sorted_cats)

            dummy_series = QStackedBarSeries()
            dummy_set = QBarSet("")
            dummy_set.setColor(QColor(0, 0, 0, 0))
            dummy_set.setBorderColor(QColor(0, 0, 0, 0))
            for period in all_periods:
                dummy_set.append(sum(data[period].get(c, 0) for c in all_cats))
            dummy_series.append(dummy_set)
            chart.addSeries(dummy_series)
            dummy_series.attachAxis(ax_x)
            dummy_series.attachAxis(ax_y)

            self._stacked_paint_data = {
                "all_periods": all_periods,
                "per_month_order": per_month_order,
                "data": data,
                "labels": labels,
                "cat_colors": dict(self._cat_colors),
            }

            if hasattr(self, "_stack_overlay_widget") and self._stack_overlay_widget:
                try:
                    self._stack_overlay_widget.deleteLater()
                except Exception:
                    pass

            self._stack_overlay_widget = StackedOverlay(
                self.chart_view, self._stacked_paint_data,
                on_hover_cb=self._on_stack_overlay_hover,
            )
            self._stack_overlay_widget.show()

        self.chart_view.setChart(chart)
        for name, (cb, _) in self._cat_cbs.items():
            self._apply_cb_style(cb, name, cb.isChecked())
        style_chart_view(self.chart_view)

    # ── Stacked overlay hover ─────────────────────────────────────────────────

    def _on_stack_overlay_hover(self, hit):
        if hit is None:
            self.chart_view.hide_hover()
            self._highlight_cb(None)
            return
        pi, cat, val, baseline, vp_pos = hit
        self._detail(cat, pi)
        labels = self._stacked_paint_data.get("labels", [])
        month_label = labels[pi] if pi < len(labels) else ""
        cat_color = self._cat_colors.get(cat)
        self.chart_view.show_hover(
            self._with_month_total(f"{cat}\n{month_label}   {money(val)}", pi),
            vp_pos, cat_color,
        )
        self._highlight_cb(cat)

    # ── One month as bars: a bar per category, largest first ──────────────────

    def _build_one_month_bars(self, values, all_cats, title):
        cats = [c for c in sorted(all_cats, key=lambda c: values.get(c, 0), reverse=True) if round(values.get(c, 0), 2)]
        if not cats:
            self._show_empty_chart("No data for selected period", animated=True)
            return
        self._current_chart_type = "Grouped Bars"
        chart = make_chart(title, animated=True)
        chart.legend().setVisible(False)
        ax_x = make_x_axis(cats)
        chart.addAxis(ax_x, Qt.AlignBottom)
        ax_y = make_y_axis()
        if self.chk_custom_y.isChecked():
            ax_y.setRange(self.f_y_min.value(), self.f_y_max.value())
        else:
            ax_y.setRange(min(min(values.values(), default=0), 0) * 1.1, max(values[cats[0]] * 1.1, 1))
        chart.addAxis(ax_y, Qt.AlignLeft)

        # one set per category, zero everywhere but its own place: every bar keeps its colour and full width
        series = QStackedBarSeries()
        for i, cat in enumerate(cats):
            color = self._cat_colors.get(cat, TAB20_COLORS[i % len(TAB20_COLORS)])
            bar_set = QBarSet(cat)
            bar_set.setColor(QColor(color))
            for j in range(len(cats)):
                bar_set.append(values[cat] if j == i else 0)

            def on_hover(state, idx, c=cat, v=values[cat], col=color, own=i):
                if state and idx == own:
                    text = self._with_month_total(f"{c}\n{money(v)}", 0)
                    self._active_bar_hover = (text, col)
                    self.chart_view.show_hover(text, self._last_mouse_pos, col)
                    self._highlight_cb(c)
                    self._detail(c, 0)
                else:
                    self._active_bar_hover = None
                    self.chart_view.hide_hover()
                    self._highlight_cb(None)

            bar_set.hovered.connect(on_hover)
            series.append(bar_set)
        series.setBarWidth(0.6)
        chart.addSeries(series)
        series.attachAxis(ax_x)
        series.attachAxis(ax_y)
        self.chart_view.setChart(chart)
        style_chart_view(self.chart_view)

    # ── Donut chart (totals over the range) ───────────────────────────────────

    def _donut_center_pos(self):
        chart = self.chart_view.chart()
        if not chart:
            return None
        return self.chart_view.mapFromScene(
            chart.mapToScene(chart.plotArea().center())
        )

    def _donut_highlight_from_cb(self, cat_name, entering):
        slc = self._donut_slices.get(cat_name)
        if slc:
            slc.setExploded(entering)
            slc.setExplodeDistanceFactor(0.06)
        if entering and slc:
            val = slc.value()
            total = sum(s.value() for s in self._donut_slices.values()) or 1
            pct = val / total * 100
            color = self._cat_colors.get(cat_name)
            # Adjust center so label ends up centered over the donut hole
            center = self._donut_center_pos()
            if center:
                lbl = self.chart_view._hover_label
                lbl.setText(f"{cat_name}\n{money(val)}   {pct:.1f}%")
                lbl.adjustSize()
                w, h = lbl.width(), lbl.height()
                # Shift pos so show_hover's +12/-h-8 offset results in centered position
                adjusted = QPoint(center.x() - 12 - w // 2, center.y() + h // 2 + 8)
            else:
                adjusted = None
            self.chart_view.show_hover(
                f"{cat_name}\n{money(val)}   {pct:.1f}%",
                adjusted,
                color,
            )
            self._highlight_cb(cat_name)
        else:
            self.chart_view.hide_hover()
            self._highlight_cb(None)

    def _build_donut_chart(self, period_data, all_cats, period_label, title):
        s = get_settings()
        self._current_chart_type = "Donut"

        all_cats = sorted(
            all_cats,
            key=lambda c: period_data.get(c, 0),
            reverse=True
        )
        # a category with more money back than spent (net negative) has no slice
        total = sum(max(period_data.get(cat, 0), 0) for cat in all_cats)
        if not total:
            self._show_empty_chart("No data for selected period")
            return

        series = QPieSeries()
        series.setHoleSize(0.45)
        series.setPieSize(0.78)

        for cat in all_cats:
            val = period_data.get(cat, 0)
            if val <= 0:
                continue
            color_hex = self._cat_colors.get(cat, TAB20_COLORS[0])
            pct = val / total * 100
            slc = QPieSlice(f"{pct:.1f}%  {cat}", val)
            slc.setColor(QColor(color_hex))
            slc.setBorderColor(QColor(s.get("bg_surface")))
            slc.setBorderWidth(2)
            self._donut_slices[cat] = slc

            def _make_hover(s_=slc, c=cat, v=val, p=pct, col=color_hex):
                def on_hover(state):
                    s_.setExploded(state)
                    s_.setExplodeDistanceFactor(0.06)
                    if state:
                        self._detail(c)  # a donut covers the range
                        self.chart_view.show_hover(
                            f"{c}\n{money(v)}   {p:.1f}%",
                            self._last_mouse_pos,
                            col,
                        )
                        self._highlight_cb(c)
                    else:
                        self.chart_view.hide_hover()
                        self._highlight_cb(None)

                return on_hover

            slc.hovered.connect(_make_hover())
            series.append(slc)

        chart = make_chart(f"{title}  —  {period_label}", animated=True)
        chart.addSeries(series)
        chart.legend().setVisible(False)

        self.chart_view.setChart(chart)
        style_chart_view(self.chart_view)

    # ── Line hover / highlight helpers ────────────────────────────────────────

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
            cat, x, label, value, dist_sq = result
            if dist_sq <= self._hover_threshold_px ** 2:
                hover_key = (cat, x, value)
                if hover_key == self._last_hover_key:
                    return
                self._last_hover_key = hover_key
                self._set_highlighted(cat, hover_point=(x, value))
                self._detail(cat, int(x))
                dot_chart_pos = self._map_to_chart_position(chart, cat, x, value)
                dot_scene_pos = chart.mapToScene(dot_chart_pos)
                dot_vp_pos = self.chart_view.mapFromScene(dot_scene_pos)
                self.chart_view.show_hover(
                    self._with_month_total(f"{cat}\n{label}   {money(value)}", x),
                    dot_vp_pos,
                    self._cat_colors.get(cat),
                )
            else:
                self._clear_highlight()
        except Exception as exc:
            print("monthly chart hover error:", exc)

    def _nearest_line_at_position(self, chart, chart_pos):
        best = None
        best_dist_sq = float("inf")

        for cat, points in self._line_series_data.items():
            if not points:
                continue
            mapped = [
                (self._map_to_chart_position(chart, cat, x, y), x, y, label)
                for x, y, label in points
            ]
            if len(mapped) == 1:
                p, x, y, label = mapped[0]
                dist_sq = self._point_distance_sq(chart_pos, p)
                if dist_sq < best_dist_sq:
                    best, best_dist_sq = (cat, x, label, y, dist_sq), dist_sq
                continue
            for i in range(len(mapped) - 1):
                p1, x1, y1, label1 = mapped[i]
                p2, x2, y2, label2 = mapped[i + 1]
                dist_sq = self._segment_distance_sq(chart_pos, p1, p2)
                if self._point_distance_sq(chart_pos, p1) <= self._point_distance_sq(chart_pos, p2):
                    nx, nl, nv = x1, label1, y1
                else:
                    nx, nl, nv = x2, label2, y2
                if dist_sq < best_dist_sq:
                    best, best_dist_sq = (cat, nx, nl, nv, dist_sq), dist_sq

        return best

    def _map_to_chart_position(self, chart, cat, x, y):
        value = QPointF(float(x), float(y))
        series = self._line_series_objects.get(cat)
        try:
            return chart.mapToPosition(value, series)
        except TypeError:
            return chart.mapToPosition(value)

    @staticmethod
    def _point_distance_sq(p1, p2):
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        return dx * dx + dy * dy

    @staticmethod
    def _segment_distance_sq(p, a, b):
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        px, py = p.x(), p.y()
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        denom = vx * vx + vy * vy
        if denom <= 0:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
        return (px - (ax + t * vx)) ** 2 + (py - (ay + t * vy)) ** 2

    def _clear_highlight(self):
        self._last_hover_key = None
        self._set_highlighted(None)
        self.chart_view.hide_hover()

    def _set_highlighted(self, cat_name, hover_point=None):
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

        self._highlighted_cat = cat_name

        if (cat_name and self._current_chart_type in ("Line", "Spline")
                and cat_name in self._line_series_data):
            color = QColor(self._cat_colors.get(cat_name, "#ffffff"))
            overlay = QSplineSeries() if self._current_chart_type == "Spline" else QLineSeries()
            overlay.setName(f"__overlay_{cat_name}")
            pen = QPen(color)
            pen.setWidth(5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            overlay.setPen(pen)
            for x, y, _label in self._line_series_data[cat_name]:
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
                dot.setName(f"__hover_dot_{cat_name}")
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

        self._highlight_cb(cat_name)
