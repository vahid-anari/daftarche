from datetime import date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QHeaderView, QAbstractItemView,
    QMenu, QMessageBox, QDialog, QFormLayout, QDialogButtonBox,
    QCheckBox, QFrame, QSizePolicy,
    QStyledItemDelegate, QStyle, QFileDialog, QApplication, QTextEdit,
    QListWidget, QListWidgetItem, QInputDialog
)
from PySide6.QtCore import Qt, QSize, QAbstractTableModel, QModelIndex, QItemSelectionModel, QTimer
from PySide6.QtGui import QColor, QAction, QBrush, QShortcut, QKeySequence, QIcon, QPainter, QPen, QPixmap

from daftarche.db import (
    MONTHS_ORDER, MONTH_NUM, TRANSFER_UNMATCHED, TRANSFER_MATCHED, SUB_MATCHED, UNCATEGORIZED_CAT, UNCATEGORIZED_SUB,
    CAT_LOANS,
)

from daftarche.widgets import (
    amount_color_key, money, add_subcategory_items, confirm_category,
    CheckComboBox, PeriodSelectorWidget, SymbolButton, SingleSelectCombo, ReadOnlyCopyDelegate,
    EditableTableView, DatePicker
)
from daftarche.category_dialog import CategoryDialog
from daftarche.style import get_settings
from daftarche.tag_picker import TagsDialog
from daftarche.icons import emoji_icon, set_category_icons

LOAN_OUT = "Out (I lent, or paid back)"
LOAN_IN = "In (I borrowed, or was paid back)"

COLUMNS = [
    "Date", "Type", "Account",
    "Amount", "Category", "Sub-Category", "Tags", "Name", "Memorandum", "FITID", "Note", "Merchant",
]
COL_DATE = 0
COL_TYPE = 1
COL_ACCOUNT = 2
COL_AMOUNT = 3
COL_CAT = 4
COL_SUBCAT = 5
COL_TAGS = 6
COL_NAME = 7
COL_MEMO = 8
COL_FITID = 9
COL_NOTE = 10  # model positions stay fixed; what you see is ordered by the header (movable)
COL_MERCHANT = 11
COLUMN_KEYS = ["date", "type", "account", "amount", "category", "subcategory", "tags", "name", "memo",
               "fitid", "note", "merchant"]  # by model column: settings save columns by these names
DEFAULT_ORDER = ["date", "type", "account", "amount", "merchant", "category", "subcategory", "tags", "name",
                 "memo", "note", "fitid"]


def column_settings(saved_visible, saved_order):
    """(visible {key: bool}, order [keys]) from the saved settings, which before 0.15.0 kept
    visibility by column position ({"9": false}) and had no order."""
    visible = {key: True for key in COLUMN_KEYS}
    for k, v in (saved_visible or {}).items():
        key = COLUMN_KEYS[int(k)] if str(k).isdigit() and int(k) < len(COLUMN_KEYS) else k
        if key in visible:
            visible[key] = bool(v)
    if saved_order:
        order = [k for k in saved_order if k in COLUMN_KEYS]
    elif saved_visible:  # an existing table: keep the order it had (Note last)
        order = [k for k in COLUMN_KEYS if k != "merchant"]
    else:
        order = list(DEFAULT_ORDER)
    for key in DEFAULT_ORDER:  # a column added since (Merchant): where it goes by default
        if key not in order:
            before = DEFAULT_ORDER[:DEFAULT_ORDER.index(key)]
            order.insert(max((order.index(k) + 1 for k in before if k in order), default=0), key)
    return visible, order
SORT_KEYS = ["date", "type", "account", "amount", "category", "subcategory", "tags", "name", "memorandum",
             "fitid", "note", "merchant"]  # by column


# NullDelegate  — suppresses any editor (nothing happens on double-click)

class NullDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return None


# AccountDelegate  — custom painter for the Account column (col 5)
#                    draws "From → To" for transfers using account colors
class AccountDelegate(QStyledItemDelegate):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

    def createEditor(self, parent, option, index):
        return None

    def paint(self, painter, option, index):
        if index.column() != COL_ACCOUNT:
            super().paint(painter, option, index)
            return

        row = self._model.get_row(index.row())
        painter.save()

        self.initStyleOption(option.__class__(), index)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        x = option.rect.x() + 4
        y = option.rect.y()
        h = option.rect.height()
        fm = painter.fontMetrics()

        if row["to_account"]:
            acc_color = QColor(row["account_color"] or "#f39c12")
            painter.setPen(acc_color)
            acc_text = row["account"] or ""
            painter.drawText(x, y, fm.horizontalAdvance(acc_text), h, Qt.AlignVCenter, acc_text)
            x += fm.horizontalAdvance(acc_text)

            painter.setPen(QColor(get_settings().get("transfer")))
            arrow = " → "
            painter.drawText(x, y, fm.horizontalAdvance(arrow), h, Qt.AlignVCenter, arrow)
            x += fm.horizontalAdvance(arrow)

            to_color = QColor(row["to_account_color"] or "#f39c12")
            painter.setPen(to_color)
            painter.drawText(x, y, fm.horizontalAdvance(row["to_account"]), h,
                             Qt.AlignVCenter, row["to_account"])
        else:
            painter.setPen(QColor(row["account_color"] or "#f39c12"))
            painter.drawText(option.rect.adjusted(4, 0, 0, 0), Qt.AlignVCenter, row["account"] or "")

        painter.restore()


def _category_only(row):
    """A category chosen without a sub-category (its sub-category is "Uncategorized")."""
    return row.get("subcategory") == UNCATEGORIZED_SUB and row.get("category") not in (None, UNCATEGORIZED_CAT)


# TxModel  — QAbstractTableModel backed by a list of transaction dicts
class TxModel(QAbstractTableModel):
    def __init__(self, rows=None):
        super().__init__()
        self._rows = rows or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        account_str = row["account"] or ""
        if row["to_account"]:
            account_str = f"{account_str} → {row['to_account']}"

        # Build date string
        date_val = row["date"] or ""
        if date_val:
            try:
                d = date.fromisoformat(date_val)
                wd = d.strftime("%A")
                date_str = f"{wd[:3]}  {MONTHS_ORDER[d.month - 1][:3]} {d.day}, {d.year}"
            except Exception:
                date_str = date_val
        else:
            date_str = ""

        keys_vals = [
            date_str,
            row["type"], account_str, row["amount"],
            row["category"], row["subcategory"],
            row.get("tags") or "",
            row["name"], row["memorandum"], row["fitid"], row.get("note"), row.get("merchant"),
        ]
        val = keys_vals[col]
        parts = row.get("parts") or []
        if parts and col in (COL_CAT, COL_SUBCAT):  # split: "Split (n)", the parts on hover
            shared = len({p["category"] for p in parts}) == 1
            if role == Qt.DisplayRole:
                if col == COL_CAT:
                    return parts[0]["category"] if shared else f"Split ({len(parts)})"
                return f"Split ({len(parts)})" if shared else "—"
            if role == Qt.ToolTipRole:
                return "\n".join(f"{money(p['amount'])}   {p['category']} › {p['subcategory']}"
                                 + (f"  ·  {p['note']}" if p.get("note") else "") for p in parts)
            if role == Qt.ForegroundRole:
                return QBrush(QColor(get_settings().get("accent")))
            if role == Qt.DecorationRole and col == COL_CAT and shared and self.icons:
                return emoji_icon(self.icons["cat"].get(parts[0].get("category_id"))) or None
            return None
        no_sub = col == COL_SUBCAT and _category_only(row)

        if role == Qt.DecorationRole:
            if not self.icons or col not in (COL_CAT, COL_SUBCAT) or no_sub:
                return None
            icon = (self.icons["cat"].get(row.get("category_id")) if col == COL_CAT
                    else self.icons["sub"].get(row.get("subcategory_id")))
            return emoji_icon(icon) if icon else None

        if role == Qt.DisplayRole:
            if col == COL_AMOUNT:
                return money(val)
            if no_sub:
                return "—"  # a category without a sub-category: nothing missing
            return str(val) if val is not None else ""

        if role == Qt.ToolTipRole and no_sub:
            return "No sub-category (that is fine: it counts in its category)"

        if role == Qt.ForegroundRole:
            s = get_settings()
            type_ = row["type"] or ""
            if no_sub:
                return QBrush(QColor(s.get("text_dim")))
            if col == COL_AMOUNT or col == COL_TYPE:
                key = amount_color_key(type_, row["amount"] if col == COL_AMOUNT else 0)
                if key:
                    return QBrush(QColor(s.get(key)))
            if col == COL_ACCOUNT and row["to_account"]:
                return QBrush(QColor(s.get("transfer")))
            if col == COL_ACCOUNT and row["account_color"]:
                return QBrush(QColor(row["account_color"]))

        if role == Qt.EditRole and col == COL_NOTE:
            return row.get("note") or ""

        if role == Qt.TextAlignmentRole:
            if col in (COL_DATE, COL_AMOUNT): return Qt.AlignRight | Qt.AlignVCenter

        return None

    on_note_edited = None  # set by the tab: (row, text) → save
    icons = None  # set by the tab: db.get_icons(), the icons beside category names

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or index.column() != COL_NOTE or not self.on_note_edited:
            return False
        row = self._rows[index.row()]
        text = (value or "").strip() or None
        if text != row.get("note"):
            self.on_note_edited(row, text)
            row["note"] = text
            self.dataChanged.emit(index, index)
        return True

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx]

    def sort(self, column, order=Qt.AscendingOrder):
        self.beginResetModel()
        reverse = (order == Qt.DescendingOrder)
        key = SORT_KEYS[column] if column < len(SORT_KEYS) else "date"

        def sort_key(r):
            base = r["date"] or ""
            if key == "date":   return base
            if key == "amount": return (r["amount"] or 0, base)
            return (str(r.get(key) or "").lower(), base)

        self._rows = sorted(self._rows, key=sort_key, reverse=reverse)
        self.endResetModel()

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable


# TransactionsTab
class TransactionsTab(QWidget):
    def __init__(self, db, on_change_cb=None):
        super().__init__()
        self.db = db
        self._on_change_cb = on_change_cb
        self._updating = False
        self._navigating = False  # set while a jump (show_matching…) sets the filters: the bar stays
        self._came_from = None  # (label, go back) of the place that sent you here
        self._review = False  # the To review list: no category, sorted by type
        self._only_ids = None  # just these transactions (e.g. those just imported)
        self._only_merchants = None  # just these merchants (from Manage → Merchants)
        self._period_before = None  # the period you had before a jump changed it: back after it
        self._current_rows = []
        self._sort_config = [
            {"col": COL_DATE, "desc": True},
        ]
        saved = get_settings().get("transactions_columns")
        order = get_settings().get("transactions_column_order")
        self._visible_columns, self._column_order = column_settings(
            saved if isinstance(saved, dict) else None, order if isinstance(order, list) else None)
        saved_sf = get_settings().get("search_fields")
        if saved_sf and isinstance(saved_sf, dict):
            # Note and Merchant came later: searched unless turned off
            self._search_fields = {"note": True, "merchant": True, **saved_sf}
        else:
            self._search_fields = {"name": True, "memo": True, "category": True, "subcategory": True, "tags": False,
                                   "fitid": False, "note": True, "merchant": True}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Toolbar ───────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        btn_add = QPushButton("🆕 Add")
        btn_edit_cat = QPushButton("✏️ Edit")
        btn_match = QPushButton("🔄 Match Transfers")
        btn_sort = QPushButton("↕️ Sort...")
        btn_resort = QPushButton("🔁 Resort")
        btn_cols = QPushButton("📋 Columns")
        btn_exp = QPushButton("💾 Export")
        btn_refresh = QPushButton("Refresh")
        self.btn_review = QPushButton()
        self.btn_review.setToolTip("Income and expenses with no category yet (e.g. a merchant-only rule "
                                   "matched them): click to show them")
        self.btn_review.clicked.connect(self.show_to_review)
        self.f_search = QLineEdit()
        self.f_search.setPlaceholderText("🔍  Search...")

        btn_edit_cat.setProperty("class", "secondary")
        btn_match.setProperty("class", "secondary")
        btn_sort.setProperty("class", "secondary")
        btn_resort.setProperty("class", "secondary")
        btn_cols.setProperty("class", "secondary")
        btn_exp.setProperty("class", "secondary")
        btn_refresh.setProperty("class", "secondary")

        btn_resort.setToolTip("Re-apply current sort")

        btn_add.clicked.connect(self.add_transaction)
        btn_edit_cat.clicked.connect(self._edit_selected)
        btn_match.clicked.connect(self._match_transfers)
        btn_sort.clicked.connect(self._open_sort_dialog)
        btn_resort.clicked.connect(self._apply_sort)
        btn_cols.clicked.connect(self._open_columns_dialog)
        btn_exp.clicked.connect(self.export)
        btn_refresh.clicked.connect(self.refresh)
        # filter once typing pauses, not on every keystroke (each pass reloads the table)
        self._search_timer = QTimer(self, singleShot=True, interval=300)
        self._search_timer.timeout.connect(self._on_any_filter_changed)
        self.f_search.textChanged.connect(lambda *_: self._search_timer.start())

        # inside the search box, at its right end: what the search looks in (takes no room in the row)
        self.search_fields_action = self.f_search.addAction(_filter_icon(), QLineEdit.TrailingPosition)
        self.search_fields_action.triggered.connect(self._open_search_fields_dialog)
        self._update_search_fields_label()

        for btn in [btn_add, btn_edit_cat, btn_match, btn_sort, btn_resort, btn_cols, btn_exp, btn_refresh]:
            title_row.addWidget(btn)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        title_row.addWidget(self.f_search, 1)
        self.f_search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addLayout(title_row)

        # ── Period selector ───────────────────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._period = PeriodSelectorWidget(mode="day", config_key="period_transactions")
        self._period.rangeChanged.connect(lambda *_: self._on_any_filter_changed())
        row1.addWidget(self._period)
        row1.addStretch()
        row1.addWidget(self.btn_review)  # in the free space of the period row: it sets the filters
        layout.addLayout(row1)

        # ── Filter combos ─────────────────────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.f_type = self._make_check_combo("All Types")
        self.f_account = self._make_check_combo("All Accounts")
        self.f_category = self._make_check_combo("All Categories", searchable=True)
        self.f_subcat = self._make_check_combo("All Sub-Cats", searchable=True)
        self.f_tags = self._make_check_combo("All Tags", searchable=True)

        for lbl_txt, combo, stretch in [
            ("Type:", self.f_type, 1),
            ("Account:", self.f_account, 2),
            ("Category:", self.f_category, 2),
            ("Sub-Cat:", self.f_subcat, 2),
            ("Tags:", self.f_tags, 2),
        ]:
            lbl = QLabel(lbl_txt)
            lbl.setProperty("class", "filter-label")
            row2.addWidget(lbl)
            row2.addWidget(combo, stretch)
            row2.addSpacing(20)

        btn_reset = QPushButton("🧹 Reset")
        btn_reset.setProperty("class", "secondary")
        btn_reset.setMinimumWidth(80)
        btn_reset.clicked.connect(self.reset_filters)
        row2.addStretch(1)
        row2.addWidget(btn_reset)
        layout.addLayout(row2)

        # ── Where you came from / what this list is ──────────────────────────
        self.nav_bar = QFrame()
        self.nav_bar.setObjectName("summary_bar")
        nav = QHBoxLayout(self.nav_bar)
        nav.setContentsMargins(8, 4, 8, 4)
        nav.setSpacing(10)
        self.btn_back = QPushButton("← Back")
        self.btn_back.setProperty("class", "secondary")
        self.btn_back.clicked.connect(self.go_back)
        self.nav_label = QLabel()
        btn_nav_close = SymbolButton("close", size=26)
        btn_nav_close.setToolTip("Show all transactions again")
        btn_nav_close.clicked.connect(self.reset_filters)
        nav.addWidget(self.btn_back)
        nav.addWidget(self.nav_label, 1)
        nav.addWidget(btn_nav_close)
        self.nav_bar.hide()
        layout.addWidget(self.nav_bar)

        # ── Table ─────────────────────────────────────────────────────────────
        self.model = TxModel()
        self.table = EditableTableView()
        self.table.setIconSize(QSize(18, 18))  # the category icons
        self.table.setModel(self.model)
        self.table.setItemDelegate(NullDelegate(self.table))
        self.table.setItemDelegateForColumn(COL_ACCOUNT, AccountDelegate(self.model, self.table))
        for col in (COL_NAME, COL_MEMO, COL_FITID):
            self.table.setItemDelegateForColumn(col, ReadOnlyCopyDelegate(self.table))
        self.table.setItemDelegateForColumn(COL_NOTE, QStyledItemDelegate(self.table))  # typed in place
        self.model.on_note_edited = self._save_note
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.selectionModel().selectionChanged.connect(self._update_rows_info)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(COL_DATE, Qt.DescendingOrder)
        header.setSectionsMovable(True)  # drag a header to move its column
        header.setFirstSectionMovable(True)
        header.sortIndicatorChanged.connect(self._on_header_sort)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._on_cell_double_clicked)

        QShortcut(QKeySequence.Delete, self.table, activated=self._delete_selected)
        QShortcut(QKeySequence.Copy, self.table, activated=self._copy_selected)
        QShortcut(QKeySequence(Qt.Key_Return), self.table, activated=self._edit_selected)
        QShortcut(QKeySequence(Qt.Key_Enter), self.table, activated=self._edit_selected)

        layout.addWidget(self.table, 1)
        self._apply_column_visibility()
        self._apply_column_order()
        header.sectionMoved.connect(self._on_column_moved)

        # ── Summary bar ───────────────────────────────────────────────────────
        summary_frame = QFrame()
        summary_frame.setObjectName("summary_bar")
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(12, 4, 12, 4)
        summary_layout.setSpacing(28)

        self.lbl_rows_info = QLabel("Rows: 0")
        self.lbl_selected_sum = QLabel("")
        self.lbl_rows_info.setProperty("class", "dim-label")
        self.lbl_selected_sum.setProperty("class", "dim-label")
        summary_layout.addWidget(self.lbl_rows_info)
        summary_layout.addWidget(self.lbl_selected_sum)
        summary_layout.addStretch()

        self.lbl_income = QLabel("Income: $0")
        self.lbl_expense = QLabel("Expense: $0")
        self.lbl_net = QLabel("Net: $0")
        self.lbl_transfer = QLabel("Transfer: $0")

        self.lbl_income.setObjectName("summary_income")
        self.lbl_expense.setObjectName("summary_expense")
        self.lbl_net.setObjectName("summary_net")
        self.lbl_transfer.setObjectName("summary_transfer")

        summary_layout.addWidget(self.lbl_income)
        summary_layout.addWidget(self.lbl_expense)
        summary_layout.addWidget(self.lbl_net)
        summary_layout.addWidget(self.lbl_transfer)
        layout.addWidget(summary_frame, 0)

    def _update_rows_info(self):
        total = len(self._current_rows)
        selected = self.table.selectedIndexes()

        if selected:
            sel_rows = sorted(set(idx.row() for idx in selected))
            amount_selected = any(idx.column() == COL_AMOUNT for idx in selected)

            self.lbl_rows_info.setText(f"Rows: {total}  |  Selected: {len(sel_rows)}")

            if amount_selected:
                sel_sum = sum(
                    (r["amount"] or 0) * (
                        1 if r["type"] and "Income" in r["type"] else
                        -1 if r["type"] and "Expense" in r["type"] else 0
                    )
                    for i in sel_rows
                    for r in [self.model.get_row(i)]
                )
                s = get_settings()
                color = s.get("income") if sel_sum >= 0 else s.get("expense")
                sign = "+" if sel_sum > 0 else ""
                self.lbl_selected_sum.setText(f"Sum: {sign}{money(sel_sum)}")
                self.lbl_selected_sum.setStyleSheet(f"color: {color}; font-weight: bold;")
            else:
                self.lbl_selected_sum.setText("")
                self.lbl_selected_sum.setStyleSheet("")
        else:
            self.lbl_rows_info.setText(f"Rows: {total}")
            self.lbl_selected_sum.setText("")
            self.lbl_selected_sum.setStyleSheet("")

    # ── Filter helpers ────────────────────────────────────────────────────────
    def _make_check_combo(self, placeholder, searchable=False):
        cb = CheckComboBox(placeholder, searchable=searchable)
        cb.selectionChanged.connect(lambda vals: self._on_any_filter_changed())
        return cb

    def _on_any_filter_changed(self):
        if self._updating:
            return
        if not self._navigating:  # you changed the filters yourself: no longer the list you jumped to
            self.clear_navigation()
        self._updating = True
        try:
            filters = self._get_filters()
            options = self.db.get_filter_options(filters)
            for combo, key in ((self.f_category, "category"), (self.f_subcat, "subcategory")):
                combo.blockSignals(True)
                combo.populate(options.get(key, []), keep_selection=True)
                combo.blockSignals(False)
        finally:
            self._updating = False
        self._apply_filters()

    def _get_filters(self):
        return {**self._shown_filters(), "ids": self._only_ids, "merchant": self._only_merchants}

    def _shown_filters(self):
        from_date, to_date = self._period.get_range()
        if from_date is None:
            return {
                "from_day": None,
                "to_day": None,
                "type": self.f_type.get_selected(),
                "account": self.f_account.get_selected(),
                "category": self.f_category.get_selected(),
                "subcategory": self.f_subcat.get_selected(),
                "tags": self.f_tags.get_selected(),
                "search": self.f_search.text().strip(),
                "search_fields": self._search_fields,
            }
        from_year = from_date.year
        from_day = from_date.day
        to_year = to_date.year
        to_day = to_date.day
        return {
            "from_day": f"{from_year:04d}-{from_date.month:02d}-{from_day:02d}",
            "to_day": f"{to_year:04d}-{to_date.month:02d}-{to_day:02d}",
            "type": self.f_type.get_selected(),
            "account": self.f_account.get_selected(),
            "category": self.f_category.get_selected(),
            "subcategory": self.f_subcat.get_selected(),
            "tags": self.f_tags.get_selected(),
            "search": self.f_search.text().strip(),
            "search_fields": self._search_fields,
        }

    # ── Refresh ───────────────────────────────────────────────────────────────
    def refresh(self):
        self._period.refresh_style()
        for combo in (self.f_type, self.f_account, self.f_category, self.f_subcat, self.f_tags):
            combo.refresh_style()
        self._updating = True
        try:
            # save current selections
            saved_filters = self._get_filters()

            # populate all combos fresh from full list
            options = self.db.get_filter_options({})
            self.f_type.populate(options.get("type", []))
            self.f_account.populate(options.get("account", []))
            self.f_category.populate(options.get("category", []))
            self.f_subcat.populate(options.get("subcategory", []))
            self.f_tags.populate([t["name"] for t in self.db.get_tags()])

            # restore type & account
            self.f_type.set_selected(saved_filters["type"])
            self.f_account.set_selected(saved_filters["account"])
            self.f_tags.set_selected(saved_filters.get("tags", []))

            # cascade category using saved type+account directly
            filtered_options = self.db.get_filter_options({
                "from_day": saved_filters["from_day"],
                "to_day": saved_filters["to_day"],
                "type": saved_filters["type"],
                "account": saved_filters["account"],
                "search": saved_filters["search"],
            })
            self.f_category.populate(filtered_options.get("category", []))
            self.f_category.set_selected(saved_filters["category"])

            # cascade subcat using saved type+account+category directly
            filtered_options = self.db.get_filter_options({
                "from_day": saved_filters["from_day"],
                "to_day": saved_filters["to_day"],
                "type": saved_filters["type"],
                "account": saved_filters["account"],
                "category": saved_filters["category"],
                "search": saved_filters["search"],
            })
            self.f_subcat.populate(filtered_options.get("subcategory", []))
            self.f_subcat.set_selected(saved_filters["subcategory"])
        finally:
            self._updating = False
        self._apply_filters()

    def _update_review_button(self):
        n = self.db.get_to_review_count()
        self.btn_review.setText(f"📝 Review ({n})")
        self.btn_review.setVisible(n > 0)

    def _apply_filters(self):
        self._update_review_button()
        rows = self.db.get_transactions(self._get_filters())
        self._current_rows = list(rows)
        self.model.icons = self.db.get_icons()
        self.model.set_rows(self._current_rows)
        self._update_rows_info()
        self._update_summary()
        self._apply_sort()
        if self._review:
            self._update_review_text()

    # ── Jumps: where you came from, and the list you are working through ─────
    def _set_navigation(self, text, came_from=None):
        self._came_from = came_from
        self.btn_back.setText(f"← Back to {came_from[0]}" if came_from else "← Back")
        self.btn_back.setVisible(came_from is not None)
        self.nav_label.setText(text)
        self.nav_bar.show()

    def clear_navigation(self, keep_period=False):
        self._came_from = None
        self._review = False
        self._only_ids = None
        self._only_merchants = None
        self.nav_bar.hide()
        if self._period_before is not None and not keep_period:
            self._period.restore(self._period_before)  # the jump's dates were for the moment only
            self._period_before = None

    def go_back(self):
        """Back where the jump came from (⌘[): that tab or window, as you left it."""
        came_from = self._came_from
        if came_from is None:
            return
        self.reset_filters()
        came_from[1]()

    def _update_review_text(self):
        counts = {}
        for r in self._current_rows:
            counts[r["type"]] = counts.get(r["type"], 0) + 1
        if counts:
            parts = " · ".join(f"{t} {n}" for t, n in sorted(counts.items()))
            self.nav_label.setText(f"<b>To review</b>: {parts}. Give each one a category (double-click it); "
                                   "it then leaves this list.")
        else:
            self.nav_label.setText("<b>To review</b>: all done ✓")

    def show_to_review(self, came_from=None):
        """Every income and expense without a category, expenses first, to give each one."""
        self.show_matching(categories=[UNCATEGORIZED_CAT], came_from=came_from, text="<b>To review</b>")
        self._review = True
        self._sort_config = [{"col": COL_TYPE, "desc": False}, {"col": COL_DATE, "desc": True}]
        self._apply_filters()

    def show_ids(self, ids, text, came_from=None):
        """Only these transactions (e.g. the ones just imported), with ``text`` above them."""
        self.show_matching(came_from=came_from, text=text)
        self._only_ids = list(ids)
        self._apply_filters()

    def _update_summary(self):
        # a split row filtered by category counts only its parts in that category
        income = sum(r.get("shown_amount", r["amount"]) for r in self._current_rows if r["type"] and "Income" in r["type"])
        expense = sum(r.get("shown_amount", r["amount"]) for r in self._current_rows
                      if r["type"] and "Expense" in r["type"])
        transfer = sum(r["amount"] for r in self._current_rows if r["type"] and "Transfer" in r["type"])
        net = income - expense

        self.lbl_income.setText(f"Income: {money(income)}")
        self.lbl_expense.setText(f"Expense: {money(expense)}")
        self.lbl_transfer.setText(f"Transfer: {money(transfer)}")
        self.lbl_net.setText(f"Net: {money(net)}")

        s = get_settings()
        color = s.get("income") if net >= 0 else s.get("expense")
        self.lbl_net.setStyleSheet(f"color: {color};")

    def show_matching(self, types=(), accounts=(), categories=(), subcategories=(), came_from=None, text=None,
                      from_day=None, to_day=None, merchants=()):
        """All-time view of the transactions with these types, accounts, categories and
        sub-categories (empty = any); used by the overview windows, the Dashboard and Charts.
        ``from_day``/``to_day`` ("YYYY-MM-DD"): only those dates (the months a chart showed).
        ``came_from``: (label, go back) for the "← Back to …" bar."""
        period_before = self._period_before or self._period.state()
        self.clear_navigation(keep_period=True)
        self._period_before = period_before
        self._navigating = True
        try:
            self._show_matching(types, accounts, categories, subcategories, from_day, to_day)
        finally:
            self._navigating = False
        shown = [", ".join(v) for v in (types, accounts, categories, subcategories, merchants) if v]
        if merchants:
            self._only_merchants = list(merchants)
            self._apply_filters()
        if came_from or text:
            self._set_navigation(text or ("Showing: " + " · ".join(shown) if shown else "Showing everything"),
                                 came_from)

    def _show_matching(self, types, accounts, categories, subcategories, from_day=None, to_day=None):
        self._updating = True
        try:
            self.f_search.blockSignals(True)
            self.f_search.clear()
            self.f_search.blockSignals(False)
            for combo in (self.f_type, self.f_account, self.f_category, self.f_subcat, self.f_tags):
                combo.clear_selection()
            if from_day and to_day:
                self._period.set_custom_range(date.fromisoformat(from_day), date.fromisoformat(to_day))
            else:
                self._period._select_preset(0, emit=False, persist=False)  # "All", for the moment
        finally:
            self._updating = False
        self.refresh()
        self._updating = True
        try:
            for combo, values in ((self.f_type, types), (self.f_account, accounts),
                                  (self.f_category, categories), (self.f_subcat, subcategories)):
                combo.set_selected(list(values))
        finally:
            self._updating = False
        self._on_any_filter_changed()

    def reset_filters(self):
        self.clear_navigation()
        self._updating = True
        try:
            self.f_search.blockSignals(True)
            self.f_search.clear()
            self.f_search.blockSignals(False)
            for combo in (self.f_type, self.f_account, self.f_category, self.f_subcat, self.f_tags):
                combo.clear_selection()
        finally:
            self._updating = False
        self.refresh()

    # ── Search fields ────────────────────────────────────────────────────────
    def _update_search_fields_label(self):
        on = [label for key, label in _SEARCH_FIELD_LABELS.items() if self._search_fields.get(key)]
        if len(on) == len(_SEARCH_FIELD_LABELS):
            text = "all fields"
        elif not on:  # the search then falls back to name, memo, category and sub-category
            text = "Name, Memo +2"
        else:
            text = ", ".join(on[:2]) + (f" +{len(on) - 2}" if len(on) > 2 else "")
        self.f_search.setPlaceholderText(f"Search in {text}…")
        tip = "The search looks in: " + (", ".join(on) or "Name, Memo, Category, Sub-Category")
        self.f_search.setToolTip(tip)
        self.search_fields_action.setToolTip(tip + ". Click to change.")

    def _open_search_fields_dialog(self):
        dlg = SearchFieldsDialog(self._search_fields, self)
        if dlg.exec():
            self._search_fields = dlg.result_map()
            get_settings().set("search_fields", self._search_fields)
            self._update_search_fields_label()
            self._apply_filters()

    # ── Column visibility ─────────────────────────────────────────────────────
    def _apply_column_visibility(self):
        for key, visible in self._visible_columns.items():
            self.table.setColumnHidden(COLUMN_KEYS.index(key), not visible)

    def _apply_column_order(self):
        header = self.table.horizontalHeader()
        header.blockSignals(True)
        for position, key in enumerate(self._column_order):
            header.moveSection(header.visualIndex(COLUMN_KEYS.index(key)), position)
        header.blockSignals(False)

    def _visual_columns(self):
        """Model columns in the order they are shown."""
        header = self.table.horizontalHeader()
        return [header.logicalIndex(v) for v in range(header.count())]

    def _on_column_moved(self, *_):
        self._column_order = [COLUMN_KEYS[c] for c in self._visual_columns()]
        get_settings().set("transactions_column_order", self._column_order)

    def _open_columns_dialog(self):
        dlg = ColumnVisibilityDialog(self._visible_columns, self._column_order, self)
        if dlg.exec():
            self._visible_columns, self._column_order = dlg.result()
            get_settings().set("transactions_columns", self._visible_columns)
            get_settings().set("transactions_column_order", self._column_order)
            self._apply_column_visibility()
            self._apply_column_order()

    # ── Context menu ──────────────────────────────────────────────────────────
    def _context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        selected = self._get_selected_row_indices()
        if not selected:
            return
        menu = QMenu(self)
        n = len(selected)

        if n == 1:
            row_idx = selected[0]
            menu.addAction(QAction(
                "✏️  Edit", self,
                triggered=lambda: self._edit_row(self.model.index(row_idx, 0))
            ))

        edit_label = "✏️  Edit Merchant / Category" if n == 1 else "✏️  Bulk Edit Merchant / Category"
        menu.addAction(QAction(edit_label, self, triggered=self._bulk_edit_cat))
        if n == 1:
            parts = self.model.get_row(selected[0]).get("parts")
            menu.addAction(QAction("✂️  Change Split…" if parts else "✂️  Split…", self,
                                   triggered=lambda: self.split_row(selected[0])))
        rows = [self.model.get_row(i) for i in selected]
        if all(r["type"] and ("Income" in r["type"] or "Expense" in r["type"]) and not r.get("parts") for r in rows):
            menu.addAction(QAction("🤝  Make It a Loan…" if n == 1 else f"🤝  Make Them Loans ({n})…", self,
                                   triggered=lambda: self.make_loans(selected)))
        menu.addAction(QAction("🏷️  Add Tags", self, triggered=self._add_tags_to_selected))
        menu.addSeparator()
        menu.addAction(QAction(f"📋  Copy {n} row{'s' if n > 1 else ''}", self, triggered=self._copy_selected))
        menu.addAction(QAction("✅  Select All", self, triggered=self.table.selectAll))
        menu.addSeparator()
        menu.addAction(QAction(f"🗑️  Delete {n} row{'s' if n > 1 else ''}", self, triggered=self._delete_selected))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def make_loans(self, row_indices):
        """Income and expense rows → Transfer › Loans with a person (money in stays in, out stays out)."""
        rows = [self.model.get_row(i) for i in row_indices]
        names = {(r.get("merchant") or "").strip() for r in rows} - {""}
        merchants = self.db.get_merchants()
        current = next(iter(names)) if len(names) == 1 else ""
        items = ([current] if current else []) + [m for m in merchants if m != current]
        person, ok = QInputDialog.getItem(
            self, "Make It a Loan",
            f"{len(rows)} row{'s' if len(rows) > 1 else ''} become Transfer › {CAT_LOANS}: money that "
            "came in was borrowed or paid back to you, money that went out was lent or paid back.\n\n"
            "The person (their merchant):", items, 0, True)
        if not ok:
            return
        person = " ".join(person.split())
        person = next((m for m in merchants if m.casefold() == person.casefold()), person)
        try:
            self.db.make_loan([r["id"] for r in rows], person)
        except ValueError as e:
            QMessageBox.warning(self, "Make It a Loan", str(e))
            return
        self._notify_change()

    def _get_selected_row_indices(self):
        return sorted(set(idx.row() for idx in self.table.selectedIndexes()))

    # ── Edit / add / delete ───────────────────────────────────────────────────
    def _edit_selected(self):
        selected = self._get_selected_row_indices()
        if len(selected) == 1:
            self._edit_row(self.model.index(selected[0], 0))

    def _edit_row(self, index):
        row = self.model.get_row(index.row())
        row_id = row["id"]
        self.table.selectRow(index.row())
        dlg = TransactionDialog(self.db, row=dict(row), parent=self)
        if dlg.exec():
            scroll_pos = self.table.verticalScrollBar().value()
            self._notify_change()
            self.table.verticalScrollBar().setValue(scroll_pos)
            for i, r in enumerate(self.model._rows):
                if r["id"] == row_id:
                    self.table.selectRow(i)
                    break

    def _on_cell_double_clicked(self, index):
        if not index.isValid():
            return
        col = index.column()
        if col in (COL_DATE, COL_TYPE, COL_ACCOUNT, COL_AMOUNT):
            self._edit_row(index)
        elif col in (COL_CAT, COL_SUBCAT) and self.model.get_row(index.row()).get("parts"):
            self.split_row(index.row())
        elif col == COL_MERCHANT and self.model.get_row(index.row()).get("parts"):
            self._edit_row(index)  # the whole window: it keeps the split
        elif col in (COL_CAT, COL_SUBCAT, COL_MERCHANT):
            self._bulk_edit_cat_for_row(index.row())
        elif col == COL_TAGS:
            self._edit_tags_for_row(index.row())
        elif col in (COL_NAME, COL_MEMO, COL_FITID, COL_NOTE):
            self.table.edit(index)

    def split_row(self, row_idx):
        """Split (or change the parts of, or join again) the transaction in this row."""
        row = self.model.get_row(row_idx)
        if not row["type"] or "Transfer" in row["type"]:
            QMessageBox.information(self, "Split", "Transfers are not split.")
            return
        from daftarche.split_dialog import SplitDialog
        about = "  ·  ".join(x for x in (row.get("merchant") or row.get("name"), row.get("account"), row["date"]) if x)
        dlg = SplitDialog(self.db, row["type"], row["amount"], parts=row.get("parts") or (),
                          category=row.get("category"), subcategory=row.get("subcategory"), about=about,
                          parent=self)
        if not dlg.exec() or dlg.result_parts is None:
            return
        scroll_pos = self.table.verticalScrollBar().value()
        try:
            self.db.set_splits(row["id"], dlg.result_parts)
        except ValueError as exc:
            QMessageBox.warning(self, "Split", str(exc))
            return
        self._notify_change()
        self.table.verticalScrollBar().setValue(scroll_pos)

    def _save_note(self, row, text):
        with self.db.transaction():
            self.db.update_transaction(row["id"], note=text)

    def _bulk_edit_cat_for_row(self, row_idx):
        self._edit_categories([row_idx])

    def _category_dialog(self, row_type, rows):
        """Edit Category / Sub-Category for ``rows`` (all of ``row_type``), with the rules."""
        first = rows[0]
        if len(rows) == 1:
            about = "  ·  ".join(x for x in (first.get("name") or first.get("memorandum"), first.get("account"),
                                             money(first.get("amount")))
                                 if x)
        else:
            about = f"{len(rows)} transactions"
        own = {r["id"] for r in rows}
        candidates = [{"key": c["id"], "account": c["account"], "name": c["name"], "memo": c["memorandum"]}
                      for c in self.db.get_uncategorized_rows(row_type) if c["id"] not in own]
        same = len({(r.get("category"), r.get("subcategory")) for r in rows}) == 1
        merchants = {(r.get("merchant") or "") for r in rows}
        return CategoryDialog(
            self.db, row_type, self,
            preset_cat=first.get("category") if same else None,
            preset_sub=first.get("subcategory") if same else None,
            about=about,
            default_rule=(first.get("name") or "", first.get("memorandum") or "") if len(rows) == 1 else None,
            candidates=candidates,
            preset_merchant=merchants.pop() if len(merchants) == 1 else None,
            merchant_mixed=len(merchants) > 1,
            can_flip=True,
        )

    def _edit_categories(self, row_indices):
        rows = [self.model.get_row(i) for i in row_indices]
        row_type = rows[0]["type"] or ""
        split = [r for r in rows if r.get("parts")]
        if split and QMessageBox.question(
                self, "Split Transactions",
                f"{len(split)} of these {'are' if len(split) != 1 else 'is'} split. Giving one category "
                "joins the parts again. Go on?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        dlg = self._category_dialog(row_type, rows)
        if not dlg.exec():
            return
        cat = self.db.get_category_by_name(dlg.cat_name, type_name=dlg.row_type)
        sub = self.db.get_subcategory_by_name(dlg.sub_name, cat["id"]) if cat else None
        ids = [r["id"] for r in rows]
        scroll_pos = self.table.verticalScrollBar().value()
        with self.db.transaction():
            for r in rows:
                if r.get("parts"):
                    self.db.set_splits(r["id"], [])  # one category again
                changes = {"category_id": cat["id"] if cat else None, "subcategory_id": sub["id"] if sub else None}
                if dlg.merchant_changed:
                    changes["merchant"] = dlg.merchant
                if dlg.flipped and r["type"] != dlg.row_type:  # money back of the other type: same amount, negative
                    changes["type_name"] = dlg.row_type
                    changes["amount"] = -(r["amount"] or 0)
                self.db.update_transaction(r["id"], **changes)
            for tx_id in dlg.apply_keys:
                changes = {"category_id": cat["id"] if cat else None, "subcategory_id": sub["id"] if sub else None}
                if dlg.apply_merchants.get(tx_id):
                    changes["merchant"] = dlg.apply_merchants[tx_id]
                self.db.update_transaction(tx_id, **changes)
        self._notify_change()
        self.table.verticalScrollBar().setValue(scroll_pos)
        self.table.clearSelection()
        for i, r in enumerate(self.model._rows):
            if r["id"] in ids:
                self.table.selectionModel().select(
                    self.model.index(i, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _edit_tags_for_row(self, row_idx):
        row = self.model.get_row(row_idx)
        dlg = TagPickerDialog(self.db, row, self)
        if dlg.exec():
            selected_names = dlg.get_selected()
            tag_name_to_id = {t["name"]: t["id"] for t in self.db.get_tags()}
            selected_tag_ids = [tag_name_to_id[n] for n in selected_names if n in tag_name_to_id]
            row_id = row["id"]
            scroll_pos = self.table.verticalScrollBar().value()
            self.db.set_tags_for_transaction(row["id"], selected_tag_ids)
            self._notify_change()
            self.table.verticalScrollBar().setValue(scroll_pos)
            for i, r in enumerate(self.model._rows):
                if r["id"] == row_id:
                    self.table.selectRow(i)
                    break

    def _bulk_edit_cat(self):
        selected = self._get_selected_row_indices()
        if not selected:
            QMessageBox.information(self, "Select", "Select one or more rows first.")
            return
        types = set(self.model.get_row(i)["type"] for i in selected)
        if len(types) > 1:
            QMessageBox.warning(self, "Mixed Types",
                                "All selected rows must have the same type (Income/Expense/Transfer).\n"
                                f"You selected: {', '.join(sorted(types))}")
            return
        self._edit_categories(selected)

    def _add_tags_to_selected(self):
        selected = self._get_selected_row_indices()
        if not selected:
            return
        dlg = BulkAddTagsDialog(self.db, self)
        if not dlg.exec():
            return
        tag_names = dlg.get_selected()
        if not tag_names:
            return
        tag_name_to_id = {t["name"]: t["id"] for t in self.db.get_tags()}
        new_tag_ids = [tag_name_to_id[n] for n in tag_names if n in tag_name_to_id]
        scroll_pos = self.table.verticalScrollBar().value()
        for row_idx in selected:
            row = self.model.get_row(row_idx)
            existing = {t["id"] for t in self.db.get_tags_for_transaction(row["id"])}
            merged = list(existing | set(new_tag_ids))
            self.db.set_tags_for_transaction(row["id"], merged)
        self._notify_change()
        self.table.verticalScrollBar().setValue(scroll_pos)

    def _delete_selected(self):
        selected = self._get_selected_row_indices()
        if not selected:
            return
        reply = QMessageBox.question(
            self, "Delete",
            f"Delete {len(selected)} transaction{'s' if len(selected) > 1 else ''}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for row_idx in sorted(selected, reverse=True):
                self.db.delete_transaction(self.model.get_row(row_idx)["id"])
            self._notify_change()

    def _notify_change(self):
        self._apply_filters()
        if self._on_change_cb:
            self._on_change_cb()

    # ── Sorting ───────────────────────────────────────────────────────────────
    def _on_header_sort(self, col, order):
        desc = (order == Qt.DescendingOrder)
        if self._sort_config and self._sort_config[0]["col"] == col:
            self._sort_config[0]["desc"] = desc
        else:
            self._sort_config = [{"col": col, "desc": desc}]
        self._apply_sort()

    def _apply_sort(self):
        if not self._sort_config or not self._current_rows:
            return
        rows = list(self._current_rows)
        keys = SORT_KEYS

        def get_val(r, k):
            try:
                return r[k]
            except (KeyError, IndexError):
                return None

        for level in reversed(self._sort_config):
            col = level["col"]
            desc = level["desc"]
            key = keys[col] if col < len(keys) else "date"

            def sort_key(r, key=key):
                if key == "date":
                    return r["date"] or ""
                if key == "amount":
                    return r["amount"] or 0
                return str(get_val(r, key) or "").lower()

            rows = sorted(rows, key=sort_key, reverse=desc)

        self.model.beginResetModel()
        self.model._rows = rows
        self.model.endResetModel()

        if self._sort_config:
            first = self._sort_config[0]
            col = first["col"]
            if not self.table.isColumnHidden(col):
                order = Qt.DescendingOrder if first["desc"] else Qt.AscendingOrder
                self.table.horizontalHeader().setSortIndicator(col, order)

    def _open_sort_dialog(self):
        dlg = SortDialog(self._sort_config, self)
        if dlg.exec():
            self._sort_config = dlg.get_config()
            self._apply_sort()

    # ── Copy ──────────────────────────────────────────────────────────────────
    def _copy_selected(self):
        selected = self._get_selected_row_indices()
        if not selected:
            return
        visible_cols = [i for i in self._visual_columns() if not self.table.isColumnHidden(i)]  # as shown
        lines = ["\t".join(COLUMNS[i] for i in visible_cols)]
        for row_idx in selected:
            row = self.model.get_row(row_idx)
            account_str = row["account"] or ""
            if row["to_account"]:
                account_str += f" → {row['to_account']}"
            date_val = row["date"] or ""
            if date_val:
                try:
                    d2 = date.fromisoformat(date_val)
                    wd2 = d2.strftime("%A")
                    date_str = f"{wd2[:3]}  {MONTHS_ORDER[d2.month - 1][:3]} {d2.day}, {d2.year}"
                except Exception:
                    date_str = date_val
            else:
                date_str = ""
            all_values = [
                date_str,
                str(row["type"] or ""),
                account_str,
                money(row["amount"]),
                str(row["category"] or ""),
                str(row["subcategory"] or ""),
                str(row.get("tags") or ""),
                str(row["name"] or ""),
                str(row["memorandum"] or ""),
                str(row["fitid"] or ""),
                str(row.get("note") or ""),
                str(row.get("merchant") or ""),
            ]
            lines.append("\t".join(all_values[i] for i in visible_cols))
        QApplication.clipboard().setText("\n".join(lines))

    # ── Match transfers ───────────────────────────────────────────────────────
    def _match_transfers(self):
        matched = self.db.match_unmatched_transfers()
        remaining_rows = self.db.get_unmatched_transfers()

        if matched == 0 and not remaining_rows:
            QMessageBox.information(self, "Match Transfers", "No unmatched transfers found.")
            return

        s = get_settings()
        dlg = QDialog(self)
        dlg.setWindowTitle("Match Transfers")
        dlg.setMinimumWidth(560)
        dlg.setMinimumHeight(360)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)

        summary = QLabel(f"✅ Matched {matched} transfer pair{'s' if matched != 1 else ''}.")
        summary.setStyleSheet("font-weight: bold;")
        lay.addWidget(summary)

        if remaining_rows:
            lbl = QLabel(
                f"⚠️ {len(remaining_rows)} unmatched transfer{'s' if len(remaining_rows) != 1 else ''} still remain:")
            lbl.setStyleSheet(f"color: {s.get('expense')};")
            lay.addWidget(lbl)

            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setStyleSheet("font-family: monospace;")
            lines = []
            for r in remaining_rows:
                acc = r["account"] or r["to_account"] or "?"
                memo = r["memorandum"] or r["name"] or ""
                lines.append(f"{r['date']}  {acc:<30}  ${r['amount']:>10,.2f}  {memo}")
            txt.setPlainText("\n".join(lines))
            lay.addWidget(txt, 1)
        else:
            ok_lbl = QLabel("✅ All transfers matched!")
            ok_lbl.setStyleSheet(f"color: {s.get('income')};")
            lay.addWidget(ok_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()
        self._notify_change()

    def add_transaction(self):
        dlg = TransactionDialog(self.db, parent=self)
        if dlg.exec():
            self._notify_change()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "export.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:  # the rows as shown: same filters, same order
            self.db.export_to_xlsx(path, rows=list(self.model._rows))
        except OSError as exc:  # e.g. the file is open in Excel
            QMessageBox.warning(self, "Export Failed", f"Could not write {path}:\n{exc}")
            return
        QMessageBox.information(self, "Done", f"Exported to {path}")


def _filter_icon():
    """Three shrinking lines (a filter), drawn in the theme's text colour: no emoji or font needed."""
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(get_settings().get("text_dim") or "#999"), 3.2, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    for i, (y, half) in enumerate(((9, 11), (16, 7), (23, 3))):
        p.drawLine(size // 2 - half, y, size // 2 + half, y)
    p.end()
    return QIcon(pixmap)


# ColumnVisibilityDialog
class ColumnVisibilityDialog(QDialog):
    """Which columns show, and in what order (▲ ▼, or drag the table's headers)."""

    def __init__(self, visible, order, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Columns")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("Show, hide and order the columns")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        hint = QLabel("Tip: you can also drag a column's header in the table.")
        hint.setProperty("class", "dim-label")
        layout.addWidget(hint)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        for key in order:
            item = QListWidgetItem(COLUMNS[COLUMN_KEYS.index(key)])
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            item.setCheckState(Qt.Checked if visible.get(key, True) else Qt.Unchecked)
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.setMinimumHeight(self.list.sizeHintForRow(0) * len(order) + 8)

        st = get_settings()
        self.list.setStyleSheet(
            f"QListWidget::indicator {{ width: 14px; height: 14px; border-radius: 3px; "
            f"border: 1px solid {st.get('border')}; background: {st.get('bg_raised')}; }}"
            f"QListWidget::indicator:checked {{ background: {st.get('accent')}; border-color: {st.get('accent')}; }}")
        side = QVBoxLayout()
        for shape, tip, slot in (("up", "Move up", lambda: self._move(-1)), ("down", "Move down", lambda: self._move(1))):
            b = SymbolButton(shape, size=32)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            side.addWidget(b)
        side.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.list, 1)
        row.addLayout(side)
        layout.addLayout(row, 1)

        btn_row = QHBoxLayout()
        for text, slot in (("✓ All", lambda: self._check_all(True)), ("✕ None", lambda: self._check_all(False)),
                           ("Reset", self._reset)):
            b = QPushButton(text)
            b.setProperty("class", "secondary")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _move(self, step):
        row = self.list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def _check_all(self, checked):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _reset(self):
        """The default order, every column shown."""
        items = {self.list.item(i).data(Qt.UserRole): self.list.item(i) for i in range(self.list.count())}
        while self.list.count():
            self.list.takeItem(0)
        for key in DEFAULT_ORDER:
            items[key].setCheckState(Qt.Checked)
            self.list.addItem(items[key])
        self.list.setCurrentRow(0)

    def result(self):
        """(visible {key: bool}, order [keys])."""
        items = [self.list.item(i) for i in range(self.list.count())]
        return ({it.data(Qt.UserRole): it.checkState() == Qt.Checked for it in items},
                [it.data(Qt.UserRole) for it in items])


# TransactionDialog  — Add / Edit single transaction
class TransactionDialog(QDialog):
    def __init__(self, db, row=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.row = row
        self.setWindowTitle("Edit Transaction" if row else "Add Transaction")
        self.setMinimumWidth(440)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        # Date field
        if self.row and self.row["date"]:
            try:
                d = date.fromisoformat(self.row["date"])
                year, month, day = d.year, MONTHS_ORDER[d.month - 1], d.day
            except Exception:
                today = date.today()
                year, month, day = today.year, MONTHS_ORDER[today.month - 1], today.day
        else:
            today = date.today()
            year, month, day = today.year, MONTHS_ORDER[today.month - 1], today.day

        self.f_date = DatePicker()
        self.f_date.set_date(year, month, day)

        self.f_type = SingleSelectCombo()
        for t in self.db.get_types():
            self.f_type.addItem(t["name"])
        if self.row and self.row["type"]:
            idx = self.f_type.findText(self.row["type"])
            if idx >= 0:
                self.f_type.setCurrentIndex(idx)
        self.f_type.currentTextChanged.connect(self._on_type_changed)
        self.f_type.setMaxVisibleItems(15)

        # all accounts (closed ones too), and the row's own value even if empty:
        # a combo must never fall back to some other account on Save
        account_names = [a["name"] for a in self.db.get_accounts()]
        self.f_account = SingleSelectCombo()
        self.f_account.setEditable(True)
        self._fill_account_combo(self.f_account, account_names,
                                 self.row["account"] if self.row else None,
                                 blank=bool(self.row) and not self.row["account"])
        self.f_account.setMaxVisibleItems(15)

        # Transfer › Loans: one account, and which way the money went
        self.lbl_dir = QLabel("Money:")
        self.f_dir = SingleSelectCombo()
        self.f_dir.addItems([LOAN_OUT, LOAN_IN])
        r = self.row
        money_in = bool(r) and ((not r["account"] and bool(r["to_account"]))
                                or (bool(r["type"]) and "Income" in r["type"] and (r["amount"] or 0) >= 0)
                                or (bool(r["type"]) and "Expense" in r["type"] and (r["amount"] or 0) < 0))
        self.f_dir.setCurrentIndex(1 if money_in else 0)
        self._loan_shown = False

        self.lbl_to = QLabel("To Account:")
        self.f_to_account = SingleSelectCombo()
        self.f_to_account.setEditable(True)
        self._fill_account_combo(self.f_to_account, account_names,
                                 self.row["to_account"] if self.row else None, blank=True)
        self.f_to_account.setMaxVisibleItems(15)

        self.f_amount = QLineEdit(str(self.row["amount"]) if self.row and self.row["amount"] is not None else "")
        self.f_amount.setPlaceholderText("0.00 (money back, e.g. a refund: -30.00)")
        self.f_amount.setToolTip("Money back of this type is negative: a refund is a negative Expense in the "
                                 "category it was spent in, and is taken off that category's total.")

        self.f_merchant = SingleSelectCombo()
        self.f_merchant.allow_typing()
        self.f_merchant.addItems(self.db.get_merchants())
        self.f_merchant.setCurrentText((self.row.get("merchant") or "") if self.row else "")
        self.f_merchant.lineEdit().setPlaceholderText("The shop or person (e.g. Amazon, Zahra)")
        self.f_merchant.setMaxVisibleItems(15)

        self.f_category = SingleSelectCombo()
        self.f_category.allow_typing()
        self.f_category.currentTextChanged.connect(self._refresh_subcats)
        self.f_category.setMaxVisibleItems(15)

        self.f_subcat = SingleSelectCombo()
        self.f_subcat.allow_typing()
        self.f_subcat.setMaxVisibleItems(15)

        # populated later by _on_type_changed → _refresh_cats
        self._preset_cat = self.row["category"] if self.row else None
        self._preset_sub = self.row["subcategory"] if self.row else None

        self.f_name = QLineEdit((self.row["name"] or "") if self.row else "")
        self.f_name.setPlaceholderText("Name (from the bank)")

        self.f_memo = QLineEdit((self.row["memorandum"] or "") if self.row else "")
        self.f_memo.setPlaceholderText("Bank memorandum (e.g. location)")

        self.f_note = QLineEdit((self.row.get("note") or "") if self.row else "")
        self.f_note.setPlaceholderText("Your note: what it was (e.g. USB cable, phone case)")

        self.f_fitid = QLineEdit((self.row["fitid"] or "") if self.row else "")
        self.f_fitid.setReadOnly(True)
        self.f_fitid.setPlaceholderText("No FITID")

        # Tags
        all_tags = self.db.get_tags()
        current_tag_ids = set()
        if self.row:
            current_tag_ids = {t["id"] for t in self.db.get_tags_for_transaction(self.row["id"])}

        self.f_tags = CheckComboBox("No tags", allow_new=True)
        self.f_tags.populate([t["name"] for t in all_tags])
        self.f_tags.set_selected([t["name"] for t in all_tags if t["id"] in current_tag_ids])

        form.addRow("Date:", self.f_date)
        form.addRow("Type:", self.f_type)
        form.addRow("Account:", self.f_account)
        form.addRow(self.lbl_dir, self.f_dir)
        form.addRow(self.lbl_to, self.f_to_account)
        form.addRow("Amount:", self.f_amount)
        form.addRow("Merchant:", self.f_merchant)
        form.addRow("Category:", self.f_category)
        form.addRow("Sub-Category:", self.f_subcat)
        self._parts = [(p["category"], p["subcategory"], p["amount"], p.get("note")) for p in
                       (self.row.get("parts") or [])] if self.row else []
        self._parts_changed = False
        split_row = QHBoxLayout()
        self.lbl_split = QLabel()
        self.lbl_split.setProperty("class", "dim-label")
        self.btn_split = QPushButton("✂️ Split…")
        self.btn_split.setProperty("class", "secondary")
        self.btn_split.setToolTip("Put parts of this amount in different categories")
        self.btn_split.clicked.connect(self._split)
        split_row.addWidget(self.lbl_split, 1)
        split_row.addWidget(self.btn_split)
        form.addRow("", split_row)
        form.addRow("Name:", self.f_name)
        form.addRow("Memorandum:", self.f_memo)
        form.addRow("Note:", self.f_note)
        form.addRow("FITID:", self.f_fitid)
        form.addRow("Tags:", self.f_tags)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.f_category.currentTextChanged.connect(self._sync_loan_mode)
        self._on_type_changed(self.f_type.currentText())
        self._show_split()

    def _show_split(self):
        n = len(self._parts)
        self.lbl_split.setText(f"Split into {n} parts: " + ", ".join(f"{p[0]} {money(p[2])}" for p in self._parts)
                               if n else "")
        self.lbl_split.setToolTip("\n".join(f"{money(p[2])}   {p[0]} › {p[1]}" for p in self._parts))
        self.f_category.setEnabled(not n)
        self.f_subcat.setEnabled(not n)
        self.btn_split.setText("✂️ Change Split…" if n else "✂️ Split…")

    def _split(self):
        from daftarche.split_dialog import SplitDialog
        try:
            amount = float(self.f_amount.text())
        except ValueError:
            QMessageBox.warning(self, "Split", "Write the amount first.")
            return
        type_name = self.f_type.currentText()
        if "Transfer" in type_name:
            QMessageBox.information(self, "Split", "Transfers are not split.")
            return
        parts = [{"category": c, "subcategory": sname, "amount": a, "note": nt} for c, sname, a, nt in self._parts]
        dlg = SplitDialog(self.db, type_name, amount, parts=parts, category=self.f_category.currentText(),
                          subcategory=self.f_subcat.currentText(), parent=self)
        if dlg.exec() and dlg.result_parts is not None:
            self._parts = [(self.db.get_category_by_id(c)["name"],
                            (self.db.get_subcategory_by_id(sid) or {"name": UNCATEGORIZED_SUB})["name"], a, nt)
                           for c, sid, a, nt in dlg.result_parts]
            self._split_ids = dlg.result_parts
            self._parts_changed = True
            self._show_split()

    @staticmethod
    def _fill_account_combo(combo, names, current, blank):
        if blank:
            combo.addItem("")
        combo.addItems(names)
        if current and combo.findText(current) < 0:
            combo.addItem(current)
        combo.setCurrentIndex(combo.findText(current) if current else 0)

    def _validate_date(self, date_str):
        try:
            date.fromisoformat(date_str)
        except ValueError:
            raise ValueError(f"Invalid date: {date_str}")

    def _on_type_changed(self, type_name):
        self._refresh_cats(type_name)
        self._sync_loan_mode()

    def _is_loan(self):
        return ("Transfer" in self.f_type.currentText()
                and self.f_category.currentText().strip().casefold() == CAT_LOANS.casefold())

    def _sync_loan_mode(self, *_):
        """A loan has one account and a direction (Money: out / in) instead of From and To."""
        if not hasattr(self, "f_dir"):
            return
        loan = self._is_loan()
        is_transfer = "Transfer" in self.f_type.currentText()
        if loan and not self._loan_shown:
            text = self.f_amount.text().strip()
            if text.startswith("-"):  # money back: the direction (Money) already says which way
                self.f_amount.setText(text[1:])
            # an incoming one-sided transfer keeps its account in To: show it as the account
            if not self.f_account.currentText().strip() and self.f_to_account.currentText().strip():
                self.f_account.setCurrentText(self.f_to_account.currentText())
                self.f_dir.setCurrentIndex(1)
            self.f_to_account.setCurrentText("")
        elif not loan and self._loan_shown and self.f_dir.currentIndex() == 1 and is_transfer:
            self.f_to_account.setCurrentText(self.f_account.currentText())  # money in: the To side
            self.f_account.setCurrentText("")
        self._loan_shown = loan
        self.lbl_dir.setVisible(loan)
        self.f_dir.setVisible(loan)
        self.lbl_to.setVisible(is_transfer and not loan)
        self.f_to_account.setVisible(is_transfer and not loan)

    def _refresh_cats(self, type_name=None):
        type_name = type_name or self.f_type.currentText()
        type_filter = (
            "Income" if "Income" in type_name else
            "Expense" if "Expense" in type_name else None
        )
        cur_cat = self.f_category.currentText()
        # use preset on first load
        if not cur_cat and hasattr(self, "_preset_cat") and self._preset_cat:
            cur_cat = self._preset_cat

        self.f_category.blockSignals(True)
        self.f_category.clear()
        for c in self.db.get_categories():
            if type_filter is None or (c["type_name"] and type_filter in c["type_name"]):
                self.f_category.addItem(c["name"])
        if cur_cat and self.f_category.findText(cur_cat) < 0:
            # e.g. Uncategorized (no type): keep it, never fall back to another category
            self.f_category.insertItem(0, cur_cat)
        idx = self.f_category.findText(cur_cat)
        if idx >= 0:
            self.f_category.setCurrentIndex(idx)
        set_category_icons(self.f_category, self.db, type_filter)
        self.f_category.blockSignals(False)

        self._refresh_subcats(self.f_category.currentText())

    def _refresh_subcats(self, cat_name=None):
        if not hasattr(self, "f_subcat"):
            return
        cat_name = cat_name or self.f_category.currentText()
        cur_sub = self.f_subcat.currentText()
        # use preset on first load
        if not cur_sub and hasattr(self, "_preset_sub") and self._preset_sub:
            cur_sub = self._preset_sub

        self.f_subcat.blockSignals(True)
        self.f_subcat.clear()
        cat = self.db.get_category_by_name(cat_name, type_name=self.f_type.currentText())
        if cat:
            add_subcategory_items(self.f_subcat, self.db, cat["id"])
        if cur_sub and cat and self.f_subcat.findText(cur_sub) < 0 and cat_name == self._preset_cat:
            self.f_subcat.insertItem(0, cur_sub)
        idx = self.f_subcat.findText(cur_sub)
        if idx >= 0:
            self.f_subcat.setCurrentIndex(idx)
        self.f_subcat.blockSignals(False)

    def _save(self):
        try:
            year, month, day = self.f_date.get_year(), self.f_date.get_month(), self.f_date.get_day()
            mn = MONTH_NUM[month]
            date_str = f"{year:04d}-{mn:02d}-{day:02d}"
            self._validate_date(date_str)
            type_name = self.f_type.currentText()
            account = self.f_account.currentText().strip() or None
            to_acc = (self.f_to_account.currentText().strip() or None) if "Transfer" in type_name else None
            amount = float(self.f_amount.text())
            name = self.f_name.text().strip() or None
            memo = self.f_memo.text().strip() or None
            merchant = self.f_merchant.currentText().strip()
            merchant = next((m for m in self.db.get_merchants() if m.casefold() == merchant.casefold()),
                            merchant) or None  # "amazon" is the Amazon already there
            if self._is_loan():
                if amount < 0:
                    raise ValueError("a loan's amount is positive: Money (In or Out) says which way it went")
                if not account:
                    raise ValueError("choose the account the money left or came into")
                if not merchant:
                    raise ValueError("a loan needs a person: write it as the merchant")
                if self.f_dir.currentIndex() == 1:
                    account, to_acc = None, account
                else:
                    to_acc = None
            elif not account and not to_acc:
                raise ValueError("choose an account")
            if self._parts and "Transfer" in type_name:
                raise ValueError("a transfer is not split: Join Again in Change Split… first")
            if self._parts and not self._parts_changed and self.row and type_name != self.row["type"]:
                raise ValueError(f"the parts are in {self.row['type']} categories: change the split "
                                 "(or Join Again) for the new type too")
            if self._parts and round(sum(p[2] for p in self._parts), 2) != round(amount, 2):
                raise ValueError(f"the parts add up to {money(sum(p[2] for p in self._parts))}, not "
                                 f"{money(amount)}: change the split too")
            if self._parts:
                names = self._parts[0][:2]
            else:
                names = confirm_category(self, self.db, type_name,
                                         self.f_category.currentText(), self.f_subcat.currentText())
            if not names:
                return
            cat_name, sub_name = names
            cat = self.db.get_category_by_name(cat_name, type_name=type_name)
            cat_id = cat["id"]
            sub = self.db.get_subcategory_by_name(sub_name, cat_id)
            sub_id = sub["id"] if sub else None

            with self.db.transaction():  # the transaction, its parts and tags: all or nothing
                if self.row and self._parts_changed:
                    self.db.set_splits(self.row["id"], [])  # the new parts are set after the new amount
                if self.row:
                    transfer_status = None
                    if "Transfer" in type_name:
                        is_matched = bool(account and to_acc) or sub_name == SUB_MATCHED
                        transfer_status = TRANSFER_MATCHED if is_matched else TRANSFER_UNMATCHED
                    self.db.update_transaction(
                        self.row["id"], year=year, month=month, day=day,
                        type_name=type_name, account_name=account,
                        to_account_name=to_acc, amount=amount,
                        subcategory_id=sub_id, category_id=cat_id,
                        name=name, memorandum=memo, note=self.f_note.text().strip() or None,
                        transfer_status=transfer_status, merchant=merchant,
                    )
                    tx_id = self.row["id"]
                else:
                    tx_id = self.db.add_transaction(year, month, day, type_name, account,
                                                    amount, sub_id, cat_id,
                                                    name=name, memorandum=memo,
                                                    to_account_name=to_acc, merchant=merchant,
                                                    note=self.f_note.text().strip() or None)
                if self._parts_changed:
                    self.db.set_splits(tx_id, self._split_ids)

                selected_names = self.f_tags.get_selected()
                for new_tag in self.f_tags.new_items:  # typed in the tag box
                    if new_tag in selected_names:
                        self.db.add_tag(new_tag)
                tag_name_to_id = {t["name"]: t["id"] for t in self.db.get_tags()}
                self.db.set_tags_for_transaction(
                    tx_id, [tag_name_to_id[n] for n in selected_names if n in tag_name_to_id])

            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Error", f"Invalid input: {e}")


# TagPickerDialog  — the tags of one transaction (find, tick, or add a new one)
class TagPickerDialog(TagsDialog):
    def __init__(self, db, row, parent=None):
        cat, sub = row.get("category") or "", row.get("subcategory") or ""
        ctx = f"{cat} → {sub}" if cat and sub else cat or sub or "Transaction"
        current = [t["name"] for t in db.get_tags_for_transaction(row["id"])]
        super().__init__(db, current, "Edit Tags", hint=ctx, parent=parent)


# BulkAddTagsDialog  — add tags to multiple transactions (does not remove existing)
class BulkAddTagsDialog(TagsDialog):
    def __init__(self, db, parent=None):
        super().__init__(db, (), "Add Tags", hint="Tags to add to the selected transactions:", parent=parent)


# SearchFieldsDialog
_SEARCH_FIELD_LABELS = {
    "name": "Name",
    "memo": "Memo",
    "category": "Category",
    "subcategory": "Sub-Category",
    "tags": "Tags",
    "fitid": "FITID",
    "note": "Note",
    "merchant": "Merchant",
}


class SearchFieldsDialog(QDialog):
    def __init__(self, current_map, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Fields")
        self.setMinimumWidth(280)
        self._map = dict(current_map)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Search in these fields:")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        self._checks = {}
        for key, label in _SEARCH_FIELD_LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(self._map.get(key, False))
            self._checks[key] = cb
            layout.addWidget(cb)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        layout.addWidget(line2)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def result_map(self):
        return {key: cb.isChecked() for key, cb in self._checks.items()}


# SortDialog
SORT_COLUMNS = [
    "Date", "Type", "Account", "Amount", "Merchant",
    "Category", "Sub-Category", "Name", "Memorandum", "Note", "FITID", "Tags",
]

_SORT_ORDERS = {
    "Date": [("Newest first", True), ("Oldest first", False)],
    "Amount": [("Highest first", True), ("Lowest first", False)],
    "Type": [("Z → A", True), ("A → Z", False)],
    "Account": [("Z → A", True), ("A → Z", False)],
    "Category": [("Z → A", True), ("A → Z", False)],
    "Sub-Category": [("Z → A", True), ("A → Z", False)],
    "Name": [("Z → A", True), ("A → Z", False)],
    "Merchant": [("Z → A", True), ("A → Z", False)],
    "Memorandum": [("Z → A", True), ("A → Z", False)],
    "FITID": [("Z → A", True), ("A → Z", False)],
    "Tags": [("Z → A", True), ("A → Z", False)],
}

_PRESETS = {
    "Newest first": [{"col": 0, "desc": True}],
    "Oldest first": [{"col": 0, "desc": False}],
    "Highest amount": [{"col": 3, "desc": True}],
    "Lowest amount": [{"col": 3, "desc": False}],
    "By account (A→Z)": [{"col": 2, "desc": False}, {"col": 0, "desc": True}],
    "By category (A→Z)": [{"col": 4, "desc": False}, {"col": 5, "desc": False}],
}


class SortDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sort")
        self.setMinimumWidth(480)
        self._config = [dict(c) for c in current_config]
        self._rows_widgets = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top = QHBoxLayout()
        btn_add = QPushButton("＋ Add level")
        btn_add.clicked.connect(self._add_level)
        top.addWidget(btn_add)
        top.addStretch()
        self.preset_combo = SingleSelectCombo()
        self.preset_combo.addItem("Presets...")
        for name in _PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        self.preset_combo.setMaxVisibleItems(15)
        top.addWidget(self.preset_combo)
        layout.addLayout(top)

        hdr = QHBoxLayout()
        hdr.addSpacing(68)
        for lbl_text, stretch in [("Column", 3), ("Order", 2), ("", 1)]:
            lbl = QLabel(lbl_text)
            lbl.setProperty("class", "dim-label")
            hdr.addWidget(lbl, stretch)
        layout.addLayout(hdr)

        self._levels_layout = QVBoxLayout()
        self._levels_layout.setSpacing(6)
        layout.addLayout(self._levels_layout)

        for level in self._config:
            self._add_level_widget(level["col"], level["desc"])

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _add_level(self):
        self._add_level_widget(0, True)

    def _add_level_widget(self, col_idx, desc):
        row_w = QWidget()
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(6)

        btn_up = SymbolButton("up")
        btn_dn = SymbolButton("down")
        btn_rm = SymbolButton("close")
        for b in (btn_up, btn_dn, btn_rm):
            b.setFixedSize(28, 28)
        row_l.addWidget(btn_up)
        row_l.addWidget(btn_dn)

        col_combo = SingleSelectCombo()
        for c in SORT_COLUMNS:
            col_combo.addItem(c)
        name = COLUMNS[col_idx] if col_idx < len(COLUMNS) else "Date"  # col_idx: a table column
        col_combo.setCurrentIndex(max(SORT_COLUMNS.index(name), 0) if name in SORT_COLUMNS else 0)
        col_combo.setMaxVisibleItems(15)

        order_combo = SingleSelectCombo()
        self._populate_order_combo(order_combo, col_combo.currentText(), desc)
        order_combo.setMaxVisibleItems(15)

        col_combo.currentTextChanged.connect(
            lambda text, oc=order_combo: self._populate_order_combo(oc, text, True))

        row_l.addWidget(col_combo, 3)
        row_l.addWidget(order_combo, 2)
        row_l.addWidget(btn_rm, 1)

        btn_up.clicked.connect(lambda _, w=row_w: self._move_level(w, -1))
        btn_dn.clicked.connect(lambda _, w=row_w: self._move_level(w, +1))
        btn_rm.clicked.connect(lambda _, w=row_w: self._remove_level(w))

        self._levels_layout.addWidget(row_w)
        self._rows_widgets.append(row_w)
        row_w._col_combo = col_combo
        row_w._order_combo = order_combo

    def _populate_order_combo(self, combo, col_name, default_desc):
        combo.blockSignals(True)
        combo.clear()
        orders = _SORT_ORDERS.get(col_name, [("Z → A", True), ("A → Z", False)])
        for label, _ in orders:
            combo.addItem(label)
        target_idx = 0 if default_desc else 1
        combo.setCurrentIndex(min(target_idx, combo.count() - 1))
        combo.blockSignals(False)

    def _move_level(self, widget, direction):
        idx = self._rows_widgets.index(widget)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._rows_widgets):
            return
        self._rows_widgets[idx], self._rows_widgets[new_idx] = \
            self._rows_widgets[new_idx], self._rows_widgets[idx]
        for w in self._rows_widgets:
            self._levels_layout.removeWidget(w)
        for w in self._rows_widgets:
            self._levels_layout.addWidget(w)

    def _remove_level(self, widget):
        if widget in self._rows_widgets:
            self._rows_widgets.remove(widget)
        self._levels_layout.removeWidget(widget)
        widget.deleteLater()

    def _apply_preset(self, name):
        if name not in _PRESETS:
            return
        for w in list(self._rows_widgets):
            self._levels_layout.removeWidget(w)
            w.deleteLater()
        self._rows_widgets.clear()
        for level in _PRESETS[name]:
            self._add_level_widget(level["col"], level["desc"])
        self.preset_combo.setCurrentIndex(0)

    def _save_and_accept(self):
        self._config = []
        for w in self._rows_widgets:
            col_name = w._col_combo.currentText()
            col_idx = COLUMNS.index(col_name)  # the table column, as clicking a header gives
            orders = _SORT_ORDERS.get(col_name, [("Z → A", True), ("A → Z", False)])
            order_idx = w._order_combo.currentIndex()
            desc = orders[order_idx][1] if order_idx < len(orders) else True
            self._config.append({"col": col_idx, "desc": desc})
        self.accept()

    def get_config(self):
        return self._config
