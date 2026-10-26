import html

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QInputDialog,
    QColorDialog, QCheckBox, QFormLayout, QLineEdit,
    QDialogButtonBox, QFrame, QSizePolicy, QAbstractScrollArea, QRadioButton, QButtonGroup
)
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QBrush, QPalette

from daftarche.style import get_settings
from daftarche.widgets import SingleSelectCombo
from daftarche.icons import IconPickerDialog, SuggestIconsDialog, emoji_icon


NO_MERCHANT = "(no merchant)"
YOU_CHOOSE = "— you choose (To review)"


def _icon_buttons(items):
    """A row of small buttons under a list: (emoji, tooltip, slot). The emoji are drawn as
    pictures (as the category icons are): as text, they were taller than the button's line and
    got cut off. ＋ stays a plain sign, in the theme's colour."""
    row = QHBoxLayout()
    row.setSpacing(6)
    buttons = []
    for label, tip, slot in items:
        btn = QPushButton(label if label == "＋" else "")
        if label != "＋":
            btn.setIcon(emoji_icon(label))
            btn.setIconSize(QSize(20, 20))
        btn.setFixedHeight(34)
        btn.setFixedWidth(50)
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        if "🗑" in label:
            btn.setProperty("class", "danger")
        elif label != "＋":
            btn.setProperty("class", "secondary")
        btn.clicked.connect(slot)
        row.addWidget(btn)
        buttons.append(btn)
    row.addStretch()
    return row, buttons


def rule_text(rule):
    """The bank text a rule looks for, as one line: "AMAZON", "AMAZON  /  memo: REFUND"."""
    parts = [rule.get("name") or ""]
    if rule.get("memorandum"):
        parts.append(f"memo: {rule['memorandum']}")
    return "  /  ".join(p for p in parts if p) or "—"


def rule_sets(rule):
    """What a rule sets besides the merchant: "Cat › Sub", "Cat", or you choose (To review)."""
    from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB, SUB_MATCHED, SUB_UNMATCHED
    cat, sub = rule.get("category"), rule.get("subcategory")
    if not cat or cat == UNCATEGORIZED_CAT:
        return YOU_CHOOSE
    if not sub or sub in (UNCATEGORIZED_SUB, SUB_MATCHED, SUB_UNMATCHED):
        return cat
    return f"{cat} › {sub}"


def _apply_selection_palette(widget):
    s = get_settings()
    hi = QColor(s.get("accent"))
    hi.setAlpha(90)
    pal = widget.palette()
    pal.setColor(QPalette.Highlight, hi)
    pal.setColor(QPalette.HighlightedText, QColor(s.get("text")))
    widget.setPalette(pal)


# ManageDialog

def _confirm_merge(parent, kind, old, new, what):
    """Renaming onto an existing name merges the two; ask first."""
    return QMessageBox.question(
        parent, f"Merge {kind}",
        f"There is already a {kind} named '{new}'.\n\n"
        f"Move all {what} of '{old}' into '{new}', and delete '{old}'?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

class ManageDialog(QDialog):
    def __init__(self, db, on_change_cb, parent=None, show_merchant=None, show_transactions=None):
        super().__init__(parent)
        self.db = db
        self.on_change_cb = on_change_cb
        self._show_merchant = show_merchant  # (merchant) → its transactions in the main window
        self._show_transactions = show_transactions  # (text, panel, **filters) → the main window
        self.setWindowTitle("Manage")
        self.setMinimumSize(1200, 620)
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.accounts_panel = AccountsPanel(self.db, self._changed)
        self.cats_panel = CatsRulesPanel(self.db, self._changed, open_merchant=self.open_merchant,
                                         show_transactions=self._show_in_window)
        self.tags_panel = TagsPanel(self.db, self._changed)
        self.merchants_panel = MerchantsPanel(self.db, self._changed, self._show_merchant, notify=self.notify)

        self.tabs.addTab(self.accounts_panel, "🏦  Accounts")
        self.tabs.addTab(self.cats_panel, "🏷️  Categories")
        self.tabs.addTab(self.merchants_panel, "🏪  Merchants")
        self.tabs.addTab(self.tags_panel, "🔖  Tags")

        layout.addWidget(self.tabs)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 12)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setProperty("class", "secondary")
        btn_refresh.setMinimumWidth(90)
        btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(btn_refresh)

        btn_suggest = QPushButton("✨ Suggest Icons…")
        btn_suggest.setProperty("class", "secondary")
        btn_suggest.setToolTip("Icons for the categories with none, from their names: you check them first")
        btn_suggest.clicked.connect(self._suggest_icons)
        btn_row.addWidget(btn_suggest)

        self.note = QLabel()
        self.note.setProperty("class", "dim-label")
        btn_row.addWidget(self.note)
        btn_row.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "secondary")
        btn_close.setMinimumWidth(90)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def refresh(self):
        self.accounts_panel.refresh()
        self.cats_panel.refresh()
        self.merchants_panel.refresh()
        self.tags_panel.refresh()

    def _changed(self):
        self.note.setText("")
        self.refresh()
        self.on_change_cb()

    def notify(self, text):
        """A line at the bottom, until the next change (e.g. how many transactions a rule changed)."""
        self.note.setText(text)

    def open_merchant(self, name):
        """The Merchants tab, with this merchant and its rules."""
        self.tabs.setCurrentWidget(self.merchants_panel)
        self.merchants_panel.find.clear()
        self.merchants_panel.select(name)

    def _show_in_window(self, text, **filters):
        if self._show_transactions:
            self._show_transactions(text, "cats", **filters)

    def _suggest_icons(self):
        dlg = SuggestIconsDialog(self.db, self)
        if dlg.exec():
            self._changed()


# AccountsPanel
class AccountsPanel(QWidget):
    COL_NAME, COL_ACCTID, COL_ACCTTYPE, COL_BANKID, COL_COLOR, \
        COL_ACTIVE, COL_DASHBOARD, COL_TX = range(8)
    EDITABLE_COLS = {COL_NAME, COL_ACCTID, COL_ACCTTYPE, COL_BANKID}

    def __init__(self, db, on_change):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self._editing = False
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Account", "Account ID", "Type", "Bank ID",
            "Color", "Active", "Dashboard", "# Tx"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        for i in (5, 6, 7):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.itemChanged.connect(self._on_item_changed)
        _apply_selection_palette(self.table)
        layout.addWidget(self.table, 3)

        btn_panel = QVBoxLayout()
        btn_panel.setSpacing(8)
        for label, slot in [
            ("＋ Add", self.add),
            ("✏️  Edit", self.edit),
            ("🗑️  Delete", self.delete),
        ]:
            btn = QPushButton(label)
            if "Delete" in label:
                btn.setProperty("class", "danger")
            elif "Add" not in label:
                btn.setProperty("class", "secondary")
            btn.clicked.connect(slot)
            btn_panel.addWidget(btn)
        btn_panel.addStretch()
        layout.addLayout(btn_panel)

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        bank_map = {}
        for r in self.db.get_all_account_ids():
            aid = self.db.get_account_by_name(r["account_name"])
            if aid:
                bank_map[aid["id"]] = r

        for a in self.db.get_accounts():
            count = self.db.get_transaction_count_for_account(a["id"])
            bank = bank_map.get(a["id"])
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(a["name"])
            name_item.setData(Qt.UserRole, a["id"])
            self.table.setItem(row, self.COL_NAME, name_item)

            self.table.setItem(row, self.COL_ACCTID, QTableWidgetItem(bank["acctid"] if bank else ""))
            self.table.setItem(row, self.COL_ACCTTYPE, QTableWidgetItem(bank["accttype"] if bank else ""))
            self.table.setItem(row, self.COL_BANKID, QTableWidgetItem(bank["bankid"] if bank else ""))

            color_item = QTableWidgetItem("  ●  " + (a["color"] or ""))
            color_item.setForeground(QBrush(QColor(a["color"] or "#888")))
            self.table.setItem(row, self.COL_COLOR, color_item)

            for col, key, cb in [
                (self.COL_ACTIVE, "active", self._toggle_active),
                (self.COL_DASHBOARD, "visible", self._toggle_visible),
            ]:
                chk = QCheckBox()
                val = a[key] if key in a.keys() else 1
                chk.setChecked(bool(val))
                chk.stateChanged.connect(lambda state, aid=a["id"], fn=cb: fn(aid, state))
                w = QWidget()
                l = QHBoxLayout(w)
                l.addWidget(chk)
                l.setAlignment(Qt.AlignCenter)
                l.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row, col, w)

            cnt = QTableWidgetItem(str(count))
            cnt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_TX, cnt)

        self.table.blockSignals(False)

    def _on_double_click(self, row, col):
        if col == self.COL_COLOR:
            self._pick_color_for_row(row)
        elif col in self.EDITABLE_COLS:
            self.table.editItem(self.table.item(row, col))

    def _on_item_changed(self, item):
        if self._editing:
            return
        row = item.row()
        col = item.column()
        if col not in self.EDITABLE_COLS:
            return

        acc_id = self.table.item(row, self.COL_NAME).data(Qt.UserRole)
        if acc_id is None:
            return

        self._editing = True
        try:
            if col == self.COL_NAME:
                new_name = item.text().strip()
                if new_name:
                    old_name = self.db.get_account_name_by_id(acc_id)
                    if old_name and old_name != new_name:
                        if self.db.get_account_by_name(new_name) and not _confirm_merge(
                                self, "account", old_name, new_name, "transactions, bank IDs and rules"):
                            item.setText(old_name)
                            return
                        self.db.rename_account(old_name, new_name)
                        self.on_change()
            else:
                acctid = self.table.item(row, self.COL_ACCTID).text().strip()
                accttype = self.table.item(row, self.COL_ACCTTYPE).text().strip()
                bankid = self.table.item(row, self.COL_BANKID).text().strip()
                acc_name = self.db.get_account_name_by_id(acc_id)
                if acc_name and acctid:
                    self.db.save_account_id(acctid, acc_name, accttype or None, bankid or None)
                elif acc_name and not acctid:
                    self.db.delete_account_id_by_account(acc_id)
        finally:
            self._editing = False

    def _pick_color_for_row(self, row):
        acc_id = self.table.item(row, self.COL_NAME).data(Qt.UserRole)
        if acc_id is None:
            return
        current_color = self.db.get_account_color_by_id(acc_id)
        color = QColorDialog.getColor(
            QColor(current_color or "#7c6af7"), self.window(), "Choose color"
        )
        if color.isValid():
            self.db.update_account(acc_id, color=color.name())
            self.on_change()
        self.window().raise_()
        self.window().activateWindow()

    def _toggle_active(self, aid, state):
        self.db.update_account(aid, active=1 if state == Qt.Checked.value else 0)
        self.on_change()

    def _toggle_visible(self, aid, state):
        self.db.update_account(aid, visible=1 if state == Qt.Checked.value else 0)
        self.on_change()

    def _selected_row(self):
        rows = self.table.selectedItems()
        if not rows:
            return None, None
        row = rows[0].row()
        acc_id = self.table.item(row, self.COL_NAME).data(Qt.UserRole)
        return row, acc_id

    def add(self):
        dlg = AccountEditDialog(self.db, parent=self)
        if dlg.exec():
            name, acctid, accttype, bankid = dlg.values()
            if name:
                self.db.get_or_create_account(name)
                if acctid:
                    self.db.save_account_id(acctid, name, accttype or None, bankid or None)
                self.on_change()

    def edit(self):
        row, acc_id = self._selected_row()
        if acc_id is None:
            QMessageBox.information(self, "Select", "Select an account first.")
            return
        acc, bank = self.db.get_account_with_bank_by_id(acc_id)
        dlg = AccountEditDialog(
            self.db,
            name=acc["name"],
            acctid=bank["acctid"] if bank else "",
            accttype=bank["accttype"] if bank else "",
            bankid=bank["bankid"] if bank else "",
            parent=self
        )
        if dlg.exec():
            new_name, acctid, accttype, bankid = dlg.values()
            if new_name and new_name != acc["name"]:
                if self.db.get_account_by_name(new_name) and not _confirm_merge(
                        self, "account", acc["name"], new_name, "transactions, bank IDs and rules"):
                    return
                self.db.rename_account(acc["name"], new_name)
            if acctid:
                self.db.save_account_id(acctid, new_name or acc["name"], accttype or None, bankid or None)
            elif bank:
                self.db.delete_account_id_by_account(acc_id)
            self.on_change()

    def delete(self):
        _, acc_id = self._selected_row()
        if acc_id is None:
            QMessageBox.information(self, "Select", "Select an account first.")
            return
        name = self.db.get_account_name_by_id(acc_id)
        if not name:
            return
        count = self.db.get_transaction_count_for_account(acc_id)
        msg = f"Delete account '{name}'?"
        if count:
            msg += f"\n\n⚠️ This will affect {count} transaction(s).\nThose transactions will have no account assigned."
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_account(acc_id)
            self.on_change()


class AccountEditDialog(QDialog):
    def __init__(self, db, name="", acctid="", accttype="", bankid="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Account")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.f_name = QLineEdit(name)
        self.f_acctid = QLineEdit(acctid)
        self.f_accttype = QLineEdit(accttype)
        self.f_bankid = QLineEdit(bankid)

        self.f_name.setPlaceholderText("e.g. Person-Bank-Checking")
        self.f_acctid.setPlaceholderText("e.g. 1234567")
        self.f_accttype.setPlaceholderText("e.g. CHECKING")
        self.f_bankid.setPlaceholderText("e.g. 010")

        form.addRow("Name:", self.f_name)
        form.addRow("Account ID:", self.f_acctid)
        form.addRow("Type:", self.f_accttype)
        form.addRow("Bank ID:", self.f_bankid)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _save(self):
        if not self.f_name.text().strip():
            QMessageBox.warning(self, "Required", "Account name is required.")
            return
        self.accept()

    def values(self):
        return (
            self.f_name.text().strip(),
            self.f_acctid.text().strip(),
            self.f_accttype.text().strip(),
            self.f_bankid.text().strip(),
        )


# CatsRulesPanel
class CatsRulesPanel(QWidget):
    """Types, categories, sub-categories, and the merchants whose money goes there."""
    M_NAME, M_TX, M_TOTAL, M_RULES = range(4)

    def __init__(self, db, on_change, open_merchant=None, show_transactions=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.open_merchant = open_merchant  # (name) → Merchants tab
        self.show_transactions = show_transactions  # (text, **filters) → the main window
        self._build()

    def _build(self):
        lists_row = QHBoxLayout(self)
        lists_row.setContentsMargins(10, 10, 10, 10)
        lists_row.setSpacing(4)

        self.type_table, type_col, type_w = self._make_table_col("Type", ["Name", "Tx", "Cats"])
        self.type_table.itemSelectionChanged.connect(self._on_type_selected)
        self.type_table.cellDoubleClicked.connect(lambda r, c: self._rename_type())
        type_col.addLayout(self._make_btns([
            ("＋", self._add_type),
            ("✏️", self._rename_type),
            ("🗑️", self._delete_type),
        ], "Type"))
        lists_row.addWidget(type_w)
        lists_row.addWidget(self._vline())

        self.cat_table, cat_col, cat_w = self._make_table_col("Category", ["Name", "Tx", "Subs"])
        self.cat_table.itemSelectionChanged.connect(self._on_cat_selected)
        self.cat_table.cellDoubleClicked.connect(lambda r, c: self._rename_cat())
        # a click on the category (again): its merchants, all sub-categories together
        self.cat_table.cellClicked.connect(lambda r, c: self.sub_table.clearSelection())
        cat_col.addLayout(self._make_btns([
            ("＋", self._add_cat),
            ("✏️", self._rename_cat),
            ("😀", self._set_cat_icon),
            ("🗑️", self._delete_cat),
        ], "Category"))
        lists_row.addWidget(cat_w)
        lists_row.addWidget(self._vline())

        self.sub_table, sub_col, sub_w = self._make_table_col("Sub-Category", ["Name", "Tx"])
        self.sub_table.itemSelectionChanged.connect(self._on_sub_selected)
        self.sub_table.cellDoubleClicked.connect(lambda r, c: self._rename_sub())
        self.sub_table.setSelectionMode(QTableWidget.ExtendedSelection)
        sub_col.addLayout(self._make_btns([
            ("＋", self._add_sub),
            ("✏️", self._rename_sub),
            ("😀", self._set_sub_icon),
            ("🔀", self._reparent_sub),
            ("🗑️", self._delete_sub),
        ], "Sub-Category"))
        lists_row.addWidget(sub_w)
        lists_row.addWidget(self._vline())

        self.merchant_table, m_col, m_w = self._make_table_col("Merchants", ["Merchant", "Tx", "Total", "Rules"])
        self.merchant_title = m_col.itemAt(0).widget()
        h = self.merchant_table.horizontalHeader()
        h.setSectionResizeMode(self.M_NAME, QHeaderView.Stretch)
        self.merchant_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.merchant_table.cellDoubleClicked.connect(self._merchant_double_clicked)
        hint = QLabel("Double-click a merchant to see and edit its rules (Merchants tab); double-click its "
                      "numbers to see those transactions. Rules: how many of its rules send money here.")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        m_col.addWidget(hint)
        m_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lists_row.addWidget(m_w, 1)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_table_col(self, title, header):
        col = QVBoxLayout()
        col.setSpacing(6)
        col.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(title)
        lbl.setProperty("class", "dim-label")
        col.addWidget(lbl)

        n_cols = len(header)
        tbl = QTableWidget(0, n_cols)
        tbl.setHorizontalHeaderLabels(header)
        self._add_scrollbar_gap(tbl, gap=8, scrollbar_width=12)
        h = tbl.horizontalHeader()
        h.setStretchLastSection(False)

        for i in range(n_cols):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setSelectionMode(QTableWidget.SingleSelection)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)

        tbl.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        tbl.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        _apply_selection_palette(tbl)
        col.addWidget(tbl, 1)

        w = QWidget()
        w.setLayout(col)
        w.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

        return tbl, col, w

    def _make_btns(self, pairs, what):
        """The small buttons under a list, with tooltips."""
        tips = {"＋": f"Add {what}", "✏️": f"Rename {what}", "😀": "Icon…", "🔀": "Move to Another Category",
                "🗑️": f"Delete {what}"}
        return _icon_buttons([(label, tips.get(label, ""), slot) for label, slot in pairs])[0]

    def _vline(self, left=8, right=8):
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(left, 0, right, 0)
        lay.setSpacing(0)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay.addWidget(line)
        return wrap

    def _add_scrollbar_gap(self, tbl, gap=8, scrollbar_width=12):
        vbar = tbl.verticalScrollBar()
        vbar.setFixedWidth(gap + scrollbar_width)
        vbar.setStyleSheet(f"""
            QScrollBar:vertical {{
                width: {scrollbar_width}px;
                margin-left: {gap}px;
            }}
        """)

    def _select_by_name(self, table, name):
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.text() == name:
                table.setCurrentCell(row, 0)
                table.scrollToItem(item)
                break

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        sel_type = self._selected_data(self.type_table)
        sel_cat = self._selected_data(self.cat_table)
        sel_sub = self._selected_data(self.sub_table)
        self._reload_types(sel_type, sel_cat, sel_sub)

    def _reload_types(self, sel_type=None, sel_cat=None, sel_sub=None):
        self.type_table.blockSignals(True)
        self.type_table.setRowCount(0)

        for t in self.db.get_types():
            tx = self.db.get_transaction_count_for_type(t["id"])
            cats = self.db.get_category_count_for_type(t["id"])

            row = self.type_table.rowCount()
            self.type_table.insertRow(row)
            for col, val in enumerate([t["name"], str(tx), str(cats)]):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, t)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.type_table.setItem(row, col, item)

        self.type_table.blockSignals(False)
        self._restore_selection(self.type_table, sel_type, key="id")

        selected_type = self._selected_data(self.type_table)
        type_id = selected_type["id"] if selected_type else None
        self._reload_cats(type_id, sel_cat, sel_sub)

    def _reload_cats(self, type_id=None, sel_cat=None, sel_sub=None):
        self.cat_table.blockSignals(True)
        self.cat_table.setRowCount(0)

        cats = self.db.get_categories(type_id) if type_id else []
        for c in cats:
            tx = self.db.get_transaction_count_for_category(c["id"])
            subs = self.db.get_subcategory_count_for_category(c["id"])

            row = self.cat_table.rowCount()
            self.cat_table.insertRow(row)
            for col, val in enumerate([c["name"], str(tx), str(subs)]):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, c)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                elif c["icon"]:
                    item.setIcon(emoji_icon(c["icon"]))
                self.cat_table.setItem(row, col, item)

        self.cat_table.blockSignals(False)
        self._restore_selection(self.cat_table, sel_cat, key="id")

        selected_cat = self._selected_data(self.cat_table)
        cat_id = selected_cat["id"] if selected_cat else None
        self._reload_subs(cat_id, sel_sub)

    def _reload_subs(self, cat_id=None, sel_sub=None):
        self.sub_table.blockSignals(True)
        self.sub_table.setRowCount(0)

        subs = self.db.get_subcategories(cat_id) if cat_id else []
        for s in subs:
            tx = self.db.get_transaction_count_for_subcategory(s["id"])

            row = self.sub_table.rowCount()
            self.sub_table.insertRow(row)
            for col, val in enumerate([s["name"], str(tx)]):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, s)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                elif s["icon"]:  # its own: the others show their category's elsewhere
                    item.setIcon(emoji_icon(s["icon"]))
                self.sub_table.setItem(row, col, item)

        self.sub_table.blockSignals(False)
        # nothing chosen: the merchants of the whole category; a click narrows them to one sub-category
        self._restore_selection(self.sub_table, sel_sub, key="id", fallback=False)
        self._on_sub_selected()

    def _reload_merchants(self, cat_data=None, sub_data=None):
        from daftarche.widgets import money
        table = self.merchant_table
        table.setRowCount(0)
        if not cat_data:
            self.merchant_title.setText("Merchants")
            return
        where = sub_data or cat_data
        self.merchant_title.setText(f"Merchants in {where['name']}" +
                                    ("" if sub_data else "  (all its sub-categories)"))
        dim = QBrush(QColor(get_settings().get("text_dim") or "#999"))
        for m in self.db.get_merchants_in(cat_data["id"], sub_data["id"] if sub_data else None):
            row = table.rowCount()
            table.insertRow(row)
            none = not m["merchant"]
            values = [NO_MERCHANT if none else m["merchant"], str(m["count"]), money(m["total"]),
                      "—" if none else str(m["rules"])]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, m)
                if col > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if none:
                    item.setForeground(dim)
                table.setItem(row, col, item)

    def _merchant_double_clicked(self, row, col):
        item = self.merchant_table.item(row, 0)
        m = item.data(Qt.UserRole) if item else None
        if not m:
            return
        if col in (self.M_NAME, self.M_RULES) and m["merchant"]:
            if self.open_merchant:
                self.open_merchant(m["merchant"])
            return
        if not self.show_transactions:
            return
        type_data = self._selected_data(self.type_table)
        cat_data = self._selected_data(self.cat_table)
        sub_data = self._selected_data(self.sub_table)
        where = f"{cat_data['name']} › {sub_data['name']}" if sub_data else cat_data["name"]
        who = html.escape(m["merchant"]) if m["merchant"] else "no merchant"
        self.show_transactions(
            f"<b>{who}</b> in <b>{html.escape(where)}</b>",
            types=[type_data["name"]] if type_data else [], categories=[cat_data["name"]],
            subcategories=[sub_data["name"]] if sub_data else [], merchants=[m["merchant"]])

    # ── Selection handlers ────────────────────────────────────────────────────

    def _on_type_selected(self):
        data = self._selected_data(self.type_table)
        type_id = data["id"] if data else None
        self._reload_cats(type_id)

    def _on_cat_selected(self):
        data = self._selected_data(self.cat_table)
        cat_id = data["id"] if data else None
        self._reload_subs(cat_id)

    def _on_sub_selected(self):
        self._reload_merchants(self._selected_data(self.cat_table), self._selected_data(self.sub_table))

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _selected_data(self, tbl):
        row = tbl.currentRow()
        if row < 0 or not tbl.selectionModel().isRowSelected(row, tbl.rootIndex()):
            return None
        item = tbl.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _selected_multi_data(self, tbl):
        seen = set()
        result = []
        for idx in tbl.selectedIndexes():
            row = idx.row()
            if row in seen:
                continue
            seen.add(row)
            item = tbl.item(row, 0)
            if item:
                d = item.data(Qt.UserRole)
                if d:
                    result.append(d)
        return result

    def _restore_selection(self, tbl, sel, key="id", fallback=True):
        if sel:
            for i in range(tbl.rowCount()):
                item = tbl.item(i, 0)
                if item:
                    d = item.data(Qt.UserRole)
                    if d and d[key] == sel[key]:
                        tbl.setCurrentCell(i, 0)
                        return
        if fallback and tbl.rowCount() > 0:
            tbl.setCurrentCell(0, 0)

    # ── Type actions ──────────────────────────────────────────────────────────

    def _add_type(self):
        name, ok = QInputDialog.getText(self, "Add Type", "Type name (can include emoji):")
        if ok and name.strip():
            if not self.db.add_type(name.strip()):
                QMessageBox.warning(self, "Duplicate", f"'{name}' already exists.")
            else:
                self.on_change()
                self._select_by_name(self.type_table, name.strip())

    def _rename_type(self):
        data = self._selected_data(self.type_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a type first.")
            return
        new, ok = QInputDialog.getText(self, "Rename Type", "New name:", text=data["name"])
        if ok and new.strip() and new.strip() != data["name"]:
            try:
                self.db.rename_type(data["name"], new.strip())
            except ValueError as exc:
                QMessageBox.warning(self, "Rename Type", str(exc))
                return
            self.on_change()

    def _delete_type(self):
        data = self._selected_data(self.type_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a type first.")
            return
        count = self.db.get_transaction_count_for_type(data["id"])
        msg = f"Delete type '{data['name']}'?"
        if count:
            msg += f"\n⚠️ Affects {count} transactions!"
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                self.db.delete_type(data["name"])
            except ValueError as exc:
                QMessageBox.warning(self, "Delete Type", str(exc))
                return
            self.on_change()

    # ── Category actions ──────────────────────────────────────────────────────

    def _add_cat(self):
        type_data = self._selected_data(self.type_table)
        if not type_data:
            QMessageBox.information(self, "Select", "Select a type first.")
            return
        name, ok = QInputDialog.getText(self, "Add Category", f"Name under '{type_data['name']}':")
        if ok and name.strip():
            if not self.db.add_category(name.strip(), type_data["name"]):
                QMessageBox.warning(self, "Duplicate", f"'{name}' already exists.")
            else:
                self.on_change()
                self._select_by_name(self.cat_table, name.strip())

    def _rename_cat(self):
        if self._loans_line():
            return
        data = self._selected_data(self.cat_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        new, ok = QInputDialog.getText(self, "Rename Category", "New name:", text=data["name"])
        if ok and new.strip() and new.strip() != data["name"]:
            target = self.db.get_category_by_name(new.strip(), data["type_id"]) if data["type_id"] else None
            if target and not _confirm_merge(self, "category", data["name"], new.strip(),
                                             "transactions, sub-categories and rules"):
                return
            self.db.rename_category(data["id"], new.strip())
            self.on_change()

    def _delete_cat(self):
        if self._loans_line():
            return
        data = self._selected_data(self.cat_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        count = self.db.get_transaction_count_for_category(data["id"])
        msg = f"Delete category '{data['name']}'?"
        if count:
            msg += f"\n⚠️ Affects {count} transactions!"
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_category(data["id"])
            self.on_change()

    # ── Subcategory actions ───────────────────────────────────────────────────

    def _add_sub(self):
        cat_data = self._selected_data(self.cat_table)
        if not cat_data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        name, ok = QInputDialog.getText(self, "Add Sub-Category", f"Name under '{cat_data['name']}':")
        if ok and name.strip():
            if not self.db.add_subcategory(name.strip(), cat_data["id"]):
                QMessageBox.warning(self, "Duplicate", f"'{name}' already exists here.")
            else:
                self.on_change()
                self._select_by_name(self.sub_table, name.strip())

    def _rename_sub(self):
        data = self._selected_data(self.sub_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a sub-category first.")
            return
        new, ok = QInputDialog.getText(self, "Rename Sub-Category", "New name:", text=data["name"])
        if ok and new.strip() and new.strip() != data["name"]:
            if self.db.get_subcategory_by_name(new.strip(), data["category_id"]) and not _confirm_merge(
                    self, "sub-category", data["name"], new.strip(), "transactions and rules"):
                return
            self.db.rename_subcategory(data["id"], new.strip())
            self.on_change()

    def _reparent_sub(self):
        selected_subs = self._selected_multi_data(self.sub_table)
        if not selected_subs:
            QMessageBox.information(self, "Select", "Select one or more sub-categories first.")
            return

        type_data = self._selected_data(self.type_table)
        type_id = type_data["id"] if type_data else None
        current_cat = self._selected_data(self.cat_table)

        cats = [c["name"] for c in self.db.get_categories(type_id)] if type_id else [
            c["name"] for c in self.db.get_categories()
        ]
        if current_cat:
            cats = [c for c in cats if c != current_cat["name"]]

        if not cats:
            QMessageBox.information(self, "No targets", "No other categories available for this type.")
            return

        n = len(selected_subs)
        desc = f"Move {n} sub-categor{'ies' if n > 1 else 'y'} to:" if n > 1 else f"Move '{selected_subs[0]['name']}' to:"
        dlg = _PickCategoryDialog(cats, desc, parent=self)
        if dlg.exec():
            new_cat = dlg.selected()
            same_type = type_id or (current_cat["type_id"] if current_cat else None)
            cat = self.db.get_category_by_name(new_cat, same_type) if same_type else \
                self.db.get_category_by_name(new_cat)
            if cat:
                for sub in selected_subs:
                    self.db.reparent_subcategory(sub["id"], cat["id"])
                self.on_change()

    def _delete_sub(self):
        data = self._selected_data(self.sub_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a sub-category first.")
            return
        count = self.db.get_transaction_count_for_subcategory(data["id"])
        msg = f"Delete '{data['name']}'?"
        if count:
            msg += f"\n⚠️ Affects {count} transactions!"
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_subcategory(data["id"])
            self.on_change()

    def _set_cat_icon(self):
        data = self._selected_data(self.cat_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        dlg = IconPickerDialog(data["icon"], f"Icon for <b>{html.escape(data['name'])}</b>",
                               "Its sub-categories show it too, unless they have their own.", self)
        if dlg.exec():
            self.db.set_category_icon(data["id"], dlg.icon)
            self.on_change()

    def _set_sub_icon(self):
        data = self._selected_data(self.sub_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a sub-category first.")
            return
        cat = self._selected_data(self.cat_table)
        hint = (f"No Icon: it shows its category's ({cat['icon']})." if cat and cat["icon"]
                else "No Icon: it shows its category's, if that has one.")
        dlg = IconPickerDialog(data["icon"], f"Icon for <b>{html.escape(data['name'])}</b>", hint, self)
        if dlg.exec():
            self.db.set_subcategory_icon(data["id"], dlg.icon)
            self.on_change()

    def _loans_line(self):
        """Transfer › Loans is what the Loans window reads: kept, with its name."""
        from daftarche.db import CAT_LOANS
        cat = self._selected_data(self.cat_table)
        loans = self.db.loans_category()
        if cat and loans and cat["id"] == loans["id"] and cat["name"] == CAT_LOANS:
            QMessageBox.information(self, "Loans",
                                    f"Transfer › {CAT_LOANS} holds the loans (View → Loans): it can't be "
                                    "renamed or deleted. Its sub-categories can.")
            return True
        return False


# RuleEditDialog — one rule: the bank text it looks for, the merchant it sets, and the category
# when the text says enough (else you choose it: the transaction waits in To review)
class RuleEditDialog(QDialog):
    """Add or edit a rule. ``merchant``: the one it is added for; ``existing``: a rule from
    ``db.get_rules`` (edited). After OK, ``values()`` gives what to save."""

    def __init__(self, db, merchant=None, existing=None, parent=None):
        super().__init__(parent)
        from daftarche.db import CAT_INTERNAL_TRANSFER, CAT_EXTERNAL_TRANSFER, UNCATEGORIZED_CAT
        self.db = db
        self.existing = existing
        self._internal, self._external, self._uncat = CAT_INTERNAL_TRANSFER, CAT_EXTERNAL_TRANSFER, UNCATEGORIZED_CAT
        self._texts = {}  # (type, account) → the transactions' (name, memo): what "Matches" counts
        self.setWindowTitle("Edit Rule" if existing else "Add Rule")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self.f_merchant = SingleSelectCombo()
        self.f_merchant.allow_typing("Pick a merchant, or type a new one")
        self.f_merchant.addItems(db.get_merchants())
        self.f_merchant.setCurrentText((existing or {}).get("merchant") or merchant or "")
        self.f_merchant.lineEdit().setPlaceholderText("The shop or person it sets (e.g. Amazon)")
        form.addRow("Merchant:", self.f_merchant)

        self.f_type = SingleSelectCombo()
        types = [t["name"] for t in db.get_types()]
        self.f_type.addItems(types)
        if existing:  # an old rule with no type stays without one until a type is chosen
            self.f_type.setCurrentIndex(self.f_type.findText(existing.get("type") or ""))
        else:
            self.f_type.setCurrentIndex(max(self.f_type.findText("Expense"), 0))
        form.addRow("Type:", self.f_type)
        self.f_cat = SingleSelectCombo()
        self.f_sub = SingleSelectCombo()
        form.addRow("Category:", self.f_cat)
        form.addRow("Sub-Category:", self.f_sub)
        self.cat_hint = QLabel()
        self.cat_hint.setProperty("class", "dim-label")
        self.cat_hint.setWordWrap(True)
        form.addRow(self.cat_hint)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        form.addRow(line)
        self.f_account = SingleSelectCombo()
        self.f_account.addItem("All")
        for a in db.get_accounts(active_only=True):
            self.f_account.addItem(a["name"])
        account = (existing or {}).get("account_name")
        if account and self.f_account.findText(account) < 0:
            self.f_account.addItem(account)  # a closed account
        self.f_account.setCurrentText(account or "All")
        form.addRow("Account:", self.f_account)
        self.f_name = QLineEdit((existing or {}).get("name") or "")
        self.f_name.setPlaceholderText("Words in the bank's name for it (e.g. AMZN MKTP)")
        form.addRow("Name:", self.f_name)
        self.f_memo = QLineEdit((existing or {}).get("memorandum") or "")
        self.f_memo.setPlaceholderText("Words in the memo (optional)")
        form.addRow("Memo:", self.f_memo)
        hint = QLabel("Whole words, any letter case; | joins words that must all appear (e.g. amazon|ca). "
                      "When several rules match, the one that matched the most text wins.")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        form.addRow(hint)
        self.matches = QLabel()
        self.matches.setWordWrap(True)
        form.addRow(self.matches)
        self.apply_box = QFrame()
        box = QVBoxLayout(self.apply_box)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.apply_title = QLabel()
        box.addWidget(self.apply_title)
        self.rb_none = QRadioButton("No — only new imports")
        self.rb_missing = QRadioButton()
        self.rb_all = QRadioButton()
        self.apply_group = QButtonGroup(self)
        for rb in (self.rb_none, self.rb_missing, self.rb_all):
            self.apply_group.addButton(rb)
            box.addWidget(rb)
        self.rb_missing.setChecked(True)
        self._apply_chosen = False  # until you pick one, "those missing …" when there are any
        self.apply_group.buttonClicked.connect(lambda _: setattr(self, "_apply_chosen", True))
        self.apply_note = QLabel()
        self.apply_note.setProperty("class", "dim-label")
        self.apply_note.setWordWrap(True)
        box.addWidget(self.apply_note)
        self.apply_box.hide()
        self._apply_rows = {}  # type → db.rule_apply_rows: what "Also set …" can change
        self._claimed = ([], [])  # (the transactions missing something, all of them) this rule would take
        layout.addLayout(form)
        layout.addWidget(self.apply_box)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.f_type.currentTextChanged.connect(lambda _: (self._fill_cats(), self._count()))
        self.f_cat.currentTextChanged.connect(lambda _: (self._fill_subs(), self._count()))
        self.f_account.currentTextChanged.connect(lambda _: self._count())
        self.f_name.textChanged.connect(lambda _: self._count())
        self.f_memo.textChanged.connect(lambda _: self._count())
        self._fill_cats((existing or {}).get("category_id"), (existing or {}).get("subcategory_id"))
        self._count()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit(True)

    def _fit(self, shown=False):
        """Tall enough for the wrapped hints (adjustSize alone leaves the form short of them)."""
        if shown or self.isVisible():
            self.adjustSize()
            height = self.layout().totalHeightForWidth(self.width())
            if height > self.height():
                self.resize(self.width(), height)

    # ── category ──────────────────────────────────────────────────────────────
    def _is_transfer(self):
        return "Transfer" in self.f_type.currentText()

    def _fill_cats(self, cat_id=None, sub_id=None):
        """Income and expense: you choose (To review) or a category. Transfer: External Transfer
        (matched with the other side later) or another of its categories, such as Loans."""
        type_name = self.f_type.currentText()
        type_id = self.db.get_type_id(type_name)
        self.f_cat.blockSignals(True)
        self.f_cat.clear()
        cats = self.db.get_categories(type_id) if type_id else []
        if self._is_transfer():
            ext = next((c for c in cats if c["name"] == self._external), None)
            if ext:
                self.f_cat.addItem(ext["name"], ext["id"])
            for c in cats:
                if c["name"] not in (self._internal, self._external):
                    self.f_cat.addItem(c["name"], c["id"])
        else:
            self.f_cat.addItem(YOU_CHOOSE, None)
            for c in cats:
                if c["name"] != self._uncat:
                    self.f_cat.addItem(c["name"], c["id"])
        idx = self.f_cat.findData(cat_id) if cat_id is not None else -1
        if cat_id is not None and idx < 0 and cat_id != self.db.get_uncategorized_ids()[0]:
            cat = self.db.get_category_by_id(cat_id)  # one not offered here (Internal Transfer): kept
            if cat and cat["type_id"] == type_id:
                self.f_cat.addItem(cat["name"], cat["id"])
                idx = self.f_cat.count() - 1
        from daftarche.icons import set_category_icons
        set_category_icons(self.f_cat, self.db, type_name)
        self.f_cat.setCurrentIndex(max(idx, 0))
        self.f_cat.blockSignals(False)
        self._fill_subs(sub_id)

    def _cat_id(self):
        """The chosen category's id (None: you choose). By its text: the boxes can be typed in."""
        idx = self.f_cat.findText(self.f_cat.currentText())
        return self.f_cat.itemData(idx) if idx >= 0 else self.f_cat.currentData()

    def _fill_subs(self, sub_id=None):
        from daftarche.widgets import add_subcategory_items
        cat_id = self._cat_id()
        name = self.f_cat.currentText()
        self.f_sub.clear()
        fixed = cat_id is None or name in (self._external, self._internal)  # nothing to choose there
        if not fixed:
            add_subcategory_items(self.f_sub, self.db, cat_id)
            if sub_id is not None:
                sub = self.db.get_subcategory_by_id(sub_id)
                if sub and sub["category_id"] == cat_id:
                    self.f_sub.setCurrentText(sub["name"])
        self.f_sub.setEnabled(not fixed)
        if cat_id is None:
            self.cat_hint.setText("Only the merchant is set: you choose the category of each of its transactions "
                                  "(they wait in To review). For shops that sell many things, like Amazon.")
        elif name == self._external:
            self.cat_hint.setText("Transfer rules work on e-transfers: those it matches are money to or from "
                                  "this person (External Transfer), matched later with the other side if there is one.")
        elif self._is_transfer():
            self.cat_hint.setText(f"Transfer rules work on e-transfers: those it matches go to {name}" +
                                  (" (View → Loans), with the person as merchant." if name == "Loans" else "."))
        else:
            self.cat_hint.setText("")
        self.cat_hint.setVisible(bool(self.cat_hint.text()))
        self._fit()

    # ── what it matches ───────────────────────────────────────────────────────
    def _account(self):
        acc = self.f_account.currentText()
        return None if acc == "All" else acc

    def _count(self):
        self._count_matches()
        self._count_apply()
        self._fit()

    def _count_matches(self):
        from daftarche.db import rule_match_length
        name, memo = self.f_name.text().strip(), self.f_memo.text().strip()
        if not name and not memo:
            self.matches.setText("")
            return
        key = (self.f_type.currentText(), self._account())
        if key not in self._texts:
            self._texts[key] = self.db.get_rule_texts(*key)
        hits = [n or m or "" for n, m in self._texts[key]
                if rule_match_length(n, name) is not None and rule_match_length(m, memo) is not None]
        if not hits:
            self.matches.setText("Matches none of your transactions yet.")
            return
        examples = list(dict.fromkeys(h for h in hits if h))[:3]
        self.matches.setText(f"Matches {len(hits)} of your transactions" +
                             (f", e.g. {', '.join(examples)}" if examples else "") + ".")

    def _count_apply(self):
        """"Also set … on them": the transactions this rule would take from the rules there are
        (it is the newest, so it wins a tie, as in lookup_mapping). Income and expense rules only."""
        from daftarche.db import rule_match_length
        type_name = self.f_type.currentText()
        name, memo = self.f_name.text().strip(), self.f_memo.text().strip()
        self._claimed = ([], [])
        if (name or memo) and ("Expense" in type_name or "Income" in type_name):
            if type_name not in self._apply_rows:
                self._apply_rows[type_name] = self.db.rule_apply_rows(type_name, (self.existing or {}).get("id"))
            account = self._account()
            acc = self.db.get_account_by_name(account) if account else None
            acc_id = acc["id"] if acc else (-1 if account else None)
            merchant_only = self._cat_id() is None
            for row in self._apply_rows[type_name]:
                if acc_id is not None and row["account_id"] != acc_id:
                    continue
                name_len, memo_len = rule_match_length(row["name"], name), rule_match_length(row["memo"], memo)
                if name_len is None or memo_len is None:
                    continue
                if row["best"] is not None and (name_len + memo_len, acc_id is not None) < row["best"][:2]:
                    continue  # a more specific rule there keeps it
                self._claimed[1].append(row["id"])
                if not row["merchant"] or (row["uncategorized"] and not merchant_only):
                    self._claimed[0].append(row["id"])
        missing, everything = (len(x) for x in self._claimed)
        self.apply_box.setVisible(everything > 0)
        if not everything:
            return
        merchant_only = self._cat_id() is None
        self.apply_title.setText("Also set this merchant on them:" if merchant_only else
                                 "Also set this merchant and category on them:")
        self.rb_missing.setText(f"Those with no merchant ({missing})" if merchant_only else
                                f"Those missing a merchant or category ({missing})")
        self.rb_all.setText(f"All {everything}, even those with another merchant" if merchant_only else
                            f"All {everything}, even those already categorized")
        self.rb_missing.setEnabled(missing > 0)
        if not self._apply_chosen or (self.rb_missing.isChecked() and not missing):
            (self.rb_missing if missing else self.rb_none).setChecked(True)
        self.apply_note.setText("Split transactions, and those a more specific rule matches, are left alone.")

    def to_apply(self):
        """After OK: (transaction ids, everything) for "Also set … on them", or None."""
        if self.apply_box.isHidden() or self.rb_none.isChecked():
            return None
        if self.rb_all.isChecked():
            return self._claimed[1], True
        return (self._claimed[0], False) if self._claimed[0] else None

    # ── OK ────────────────────────────────────────────────────────────────────
    def _validate(self):
        merchant = " ".join(self.f_merchant.currentText().split())
        if not merchant:
            QMessageBox.warning(self, "Rule", "Write the merchant this rule sets.")
            return
        if not self.f_name.text().strip() and not self.f_memo.text().strip():
            QMessageBox.warning(self, "Rule", "Write the words to look for: in the name, the memo or both.")
            return
        if self.db.get_type_id(self.f_type.currentText()) is None:
            QMessageBox.warning(self, "Rule", "Choose the rule's type.")
            return
        v = self.values()
        other = self.db.get_rule_id(v["type_name"], v["account_name"], v["name"], v["memo"])
        if other is not None and other != (self.existing or {}).get("id"):
            row = self.db.conn.execute("SELECT merchant FROM import_mappings WHERE id=?", (other,)).fetchone()
            owner = (row["merchant"] if row else None) or NO_MERCHANT
            if QMessageBox.question(
                    self, "Rule",
                    f"There is already a {v['type_name'].lower()} rule for this text and account "
                    f"(merchant: {owner}).\n\nReplace it with this one?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        self.accept()

    def values(self):
        """{type_name, account_name, name, memo, category_id, subcategory_id, merchant}: what to save.
        You choose: Uncategorized (the merchant only); External Transfer: its Unmatched line; an
        edited rule in the same fixed category keeps its line. subcategory_id None: the category's
        Uncategorized line, made by save_rule (nothing is written before OK)."""
        from daftarche.db import SUB_UNMATCHED, UNCATEGORIZED_SUB
        cat_id = self._cat_id()
        name = self.f_cat.currentText()
        old = self.existing or {}
        if cat_id is None:
            cat_id, sub_id = self.db.get_uncategorized_ids()
        elif name in (self._external, self._internal):
            if old.get("category_id") == cat_id and old.get("subcategory_id"):
                sub_id = old["subcategory_id"]
            else:
                sub = self.db.get_subcategory_by_name(SUB_UNMATCHED, cat_id)
                sub_id = sub["id"] if sub else None
        else:
            sub_name = self.f_sub.currentText() or UNCATEGORIZED_SUB
            sub = self.db.get_subcategory_by_name(sub_name, cat_id)
            sub_id = sub["id"] if sub else None
        return {"type_name": self.f_type.currentText(), "account_name": self._account(),
                "name": self.f_name.text().strip() or None, "memo": self.f_memo.text().strip() or None,
                "category_id": cat_id, "subcategory_id": sub_id,
                "merchant": self._merchant()}

    def _merchant(self):
        """The typed merchant; one already used, in another letter case, keeps its spelling."""
        typed = " ".join(self.f_merchant.currentText().split())
        names = self.db.get_merchants()
        if typed in names:
            return typed
        return next((m for m in names if m.casefold() == typed.casefold()), typed)


def save_rule(db, values, existing=None, apply=None):
    """Save what a RuleEditDialog gave (``existing``: the rule it edited) and, with ``apply``
    (its ``to_apply()``), give those transactions its merchant and category, all in one go.
    Returns (the merchant, how many transactions changed)."""
    v = dict(values)
    applied = 0
    with db.transaction():
        if v["subcategory_id"] is None:
            v["subcategory_id"] = db.uncategorized_subcategory(v["category_id"])["id"]
        if existing:
            db.delete_rule_and_save(existing["id"], v["type_name"], v["account_name"], v["name"], v["memo"],
                                    v["subcategory_id"], v["category_id"], v["merchant"])
        else:
            db.save_mapping(v["type_name"], v["account_name"], v["name"], v["memo"],
                            subcategory_id=v["subcategory_id"], category_id=v["category_id"],
                            merchant=v["merchant"])
        if apply:
            ids, everything = apply
            applied = db.apply_rule_to_transactions(ids, v["merchant"], v["category_id"], v["subcategory_id"],
                                                    everything=everything)
    return v["merchant"], applied


class _PickCategoryDialog(QDialog):
    def __init__(self, cats, desc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move Sub-Category")
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(desc))
        self.combo = SingleSelectCombo()
        self.combo.set_items(cats, include_all=False)
        layout.addWidget(self.combo)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected(self):
        return self.combo.currentText()


# TagsPanel
class TagsPanel(QWidget):
    COL_NAME, COL_TX = range(2)

    def __init__(self, db, on_change):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Tag", "# Tx"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(lambda r, c: self.rename())
        _apply_selection_palette(self.table)
        layout.addWidget(self.table, 1)

        btn_panel = QVBoxLayout()
        btn_panel.setSpacing(8)
        for label, slot in [
            ("＋ Add", self.add),
            ("✏️  Rename", self.rename),
            ("🗑️  Delete", self.delete),
        ]:
            btn = QPushButton(label)
            if "Delete" in label:
                btn.setProperty("class", "danger")
            elif "Add" not in label:
                btn.setProperty("class", "secondary")
            btn.clicked.connect(slot)
            btn_panel.addWidget(btn)
        btn_panel.addStretch()
        layout.addLayout(btn_panel)

    def refresh(self):
        self.table.setRowCount(0)
        for tag in self.db.get_tags():
            count = self.db.get_transaction_count_for_tag(tag["id"])
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(tag["name"])
            name_item.setData(Qt.UserRole, tag["id"])
            self.table.setItem(row, self.COL_NAME, name_item)
            cnt = QTableWidgetItem(str(count))
            cnt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COL_TX, cnt)

    def _selected(self):
        rows = self.table.selectedItems()
        if not rows:
            return None, None
        row = rows[0].row()
        item = self.table.item(row, self.COL_NAME)
        return item.data(Qt.UserRole), item.text()

    def add(self):
        name, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and name.strip():
            if not self.db.add_tag(name.strip()):
                QMessageBox.warning(self, "Duplicate", f"'{name}' already exists.")
            else:
                self.on_change()

    def rename(self):
        tag_id, old_name = self._selected()
        if tag_id is None:
            QMessageBox.information(self, "Select", "Select a tag first.")
            return
        new_name, ok = QInputDialog.getText(self, "Rename Tag", "New name:", text=old_name)
        if ok and new_name.strip() and new_name.strip() != old_name:
            if not self.db.rename_tag(tag_id, new_name.strip()):
                QMessageBox.warning(self, "Duplicate", f"'{new_name}' already exists.")
            else:
                self.on_change()

    def delete(self):
        tag_id, name = self._selected()
        if tag_id is None:
            QMessageBox.information(self, "Select", "Select a tag first.")
            return
        count = self.db.get_transaction_count_for_tag(tag_id)
        msg = f"Delete tag '{name}'?"
        if count:
            msg += f"\n\n⚠️ It will be removed from {count} transaction(s)."
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_tag(tag_id)
            self.on_change()


# MerchantsPanel — the shops and people (left) and the rules that recognise each one (right)
class MerchantsPanel(QWidget):
    COL_NAME, COL_TX, COL_RULES, COL_TOTAL = range(4)
    R_TEXT, R_SETS, R_TYPE, R_ACCOUNT = range(4)

    def __init__(self, db, on_change, show_transactions=None, notify=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.show_transactions = show_transactions  # (merchant, "" = none) → Transactions, from the window
        self.notify = notify or (lambda text: None)  # (text) → a line at the bottom of Manage
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 8)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.find = QLineEdit()
        self.find.setPlaceholderText("🔍  Find a merchant")
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._filter)
        left.addWidget(self.find)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Merchant", "Tx", "Rules", "Net Spent"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        h.setMinimumSectionSize(40)
        for col, width in ((self.COL_TX, 62), (self.COL_RULES, 72)):  # the headers' padding made them wide
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            h.resizeSection(col, width)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(self.COL_NAME, Qt.AscendingOrder)  # A to Z until a header is clicked
        self.table.cellDoubleClicked.connect(lambda r, c: self.open_transactions())
        self.table.itemSelectionChanged.connect(self._show_rules)
        _apply_selection_palette(self.table)
        left.addWidget(self.table, 1)
        row, self._merchant_btns = _icon_buttons([
            ("✏️", "Rename / Merge", self.rename),
            ("🏷️", "Set Category… (its rules and transactions)", self.set_category),
            ("📋", "Its Transactions", self.open_transactions),
            ("🗑️", "Delete Merchant", self.delete)])
        left.addLayout(row)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMinimumWidth(510)
        lw.setMaximumWidth(560)
        layout.addWidget(lw, 4)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        layout.addWidget(sep)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.rules_title = QLabel()
        right.addWidget(self.rules_title)
        self.rules = QTableWidget(0, 4)
        self.rules.setHorizontalHeaderLabels(["Bank text", "Sets", "Type", "Account"])
        h = self.rules.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.R_TEXT, QHeaderView.Stretch)
        h.setSectionResizeMode(self.R_SETS, QHeaderView.Stretch)
        self.rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.rules.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rules.verticalHeader().setVisible(False)
        self.rules.setAlternatingRowColors(True)
        self.rules.cellDoubleClicked.connect(lambda r, c: self.edit_rule())
        _apply_selection_palette(self.rules)
        right.addWidget(self.rules, 1)
        self.rules_hint = QLabel()
        self.rules_hint.setProperty("class", "dim-label")
        self.rules_hint.setWordWrap(True)
        right.addWidget(self.rules_hint)
        row, buttons = _icon_buttons([
            ("＋", "Add Rule", self.add_rule),
            ("✏️", "Edit Rule", self.edit_rule),
            ("🏪", "Set Merchant… (the selected rules)", self.set_rules_merchant),
            ("🗑️", "Delete Rule", self.delete_rules)])
        self.btn_set_merchant = buttons[2]
        right.addLayout(row)
        layout.addLayout(right, 7)

    # ── the merchants ─────────────────────────────────────────────────────────
    def refresh(self):
        selected = self._selected()
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        rows = list(self.db.get_merchant_overview())
        n_tx, n_rules = self.db.get_no_merchant_counts()
        if n_tx or n_rules:
            rows.append({"merchant": "", "count": n_tx, "rules": n_rules, "total": None, "rule_targets": set(),
                         "types": {}})
        dim = QBrush(QColor(get_settings().get("text_dim") or "#999"))
        for m in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            none = not m["merchant"]
            items = [_SortItem(NO_MERCHANT if none else m["merchant"], m["merchant"].casefold(), none),
                     _SortItem(str(m["count"]), m["count"], none), _SortItem(str(m["rules"]), m["rules"], none),
                     _SortItem("—" if none else _money(m["total"]), m["total"] or 0, none)]
            items[0].setData(Qt.UserRole, m)
            for c, item in enumerate(items):
                if c != self.COL_NAME:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if none:
                    item.setForeground(dim)
                    item.setToolTip("Transactions and rules with no merchant: give the rules one "
                                    "(select them on the right, then 🏪)")
                self.table.setItem(r, c, item)
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        if selected:
            self.select(selected["merchant"])
        self._filter(self.find.text())
        self._show_rules()

    def _filter(self, text):
        text = text.strip().casefold()
        for r in range(self.table.rowCount()):
            self.table.setRowHidden(r, bool(text) and text not in self.table.item(r, 0).text().casefold())

    def _selected(self):
        r = self.table.currentRow()
        if r < 0 or not self.table.selectionModel().isRowSelected(r, self.table.rootIndex()):
            return None
        item = self.table.item(r, 0)
        return item.data(Qt.UserRole) if item else None

    def select(self, name):
        """Select a merchant ("" = the no-merchant line)."""
        for r in range(self.table.rowCount()):
            m = self.table.item(r, 0).data(Qt.UserRole)
            if m and m["merchant"] == name:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                return

    _select = select  # the name the window used before

    def _need(self, real=True):
        m = self._selected()
        if not m:
            QMessageBox.information(self, "Merchants", "Select a merchant first.")
        elif real and not m["merchant"]:
            QMessageBox.information(self, "Merchants", "Select a merchant: this line holds what has none.")
            return None
        return m

    def open_transactions(self):
        m = self._need(real=False)
        if m and self.show_transactions:
            self.show_transactions(m["merchant"])

    def rename(self):
        m = self._need()
        if not m:
            return
        new, ok = QInputDialog.getText(self, "Rename Merchant", f"New name for '{m['merchant']}':",
                                       text=m["merchant"])
        new = " ".join((new or "").split())
        if not ok or not new or new == m["merchant"]:
            return
        existing = next((x for x in self.db.get_merchants() if x.casefold() == new.casefold() and x != m["merchant"]),
                        None)
        if existing and not _confirm_merge(self, "merchant", m["merchant"], existing, "transactions and rules"):
            return
        name = self.db.rename_merchant(m["merchant"], new)
        self.on_change()
        self.select(name)

    def delete(self):
        m = self._need()
        if not m:
            return
        if QMessageBox.question(
                self, "Delete Merchant",
                f"Take '{m['merchant']}' off its {m['count']} transaction(s) and {m['rules']} rule(s)?\n\n"
                "The transactions stay, without a merchant. Rules that only set this merchant are "
                "deleted; the others stay, under (no merchant).",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_merchant(m["merchant"])
            self.on_change()

    def set_category(self):
        m = self._need()
        if not m:
            return
        dlg = MerchantCategoryDialog(self.db, m, self)
        if dlg.exec():
            self.on_change()
            self.select(m["merchant"])

    # ── its rules ─────────────────────────────────────────────────────────────
    def _show_rules(self):
        m = self._selected()
        self.rules.setRowCount(0)
        none = m is not None and not m["merchant"]
        self.btn_set_merchant.setVisible(none)
        if m is None:
            self.rules_title.setText("Rules")
            self.rules_hint.setText("Select a merchant to see the rules that recognise it in the bank's text.")
            return
        if none:
            self.rules_title.setText("Rules with <b>no merchant</b>")
            self.rules_hint.setText("Every rule should set a merchant. Select these rules (⌘/Shift-click for "
                                    "several) and give them one with 🏪; their transactions keep theirs.")
            rules = self.db.get_rules(no_merchant=True)
        else:
            self.rules_title.setText(f"Rules for <b>{html.escape(m['merchant'])}</b>")
            self.rules_hint.setText("A rule recognises the bank's text and sets this merchant; when the text says "
                                    "enough, a category too, otherwise you choose it (To review). When several "
                                    "match, the one that matched the most text wins.")
            rules = self.db.get_rules(m["merchant"])
        for rule in rules:
            r = self.rules.rowCount()
            self.rules.insertRow(r)
            for c, text in enumerate((rule_text(rule), rule_sets(rule), rule["type"] or "—",
                                      rule["account_name"] or "All")):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, rule)
                if c == self.R_TEXT:
                    item.setToolTip(text)
                self.rules.setItem(r, c, item)

    def _selected_rules(self):
        rows = sorted({i.row() for i in self.rules.selectedIndexes()})
        return [self.rules.item(r, 0).data(Qt.UserRole) for r in rows]

    def add_rule(self):
        m = self._selected()
        dlg = RuleEditDialog(self.db, merchant=m["merchant"] if m else None, parent=self)
        if dlg.exec():
            name, applied = save_rule(self.db, dlg.values(), apply=dlg.to_apply())
            self.on_change()
            self.select(name)
            self._tell_applied(applied)

    def edit_rule(self):
        chosen = self._selected_rules()
        if not chosen:
            QMessageBox.information(self, "Rules", "Select a rule first.")
            return
        if len(chosen) > 1:
            QMessageBox.information(self, "Rules", "Select one rule to edit.")
            return
        dlg = RuleEditDialog(self.db, existing=chosen[0], parent=self)
        if dlg.exec():
            name, applied = save_rule(self.db, dlg.values(), existing=chosen[0], apply=dlg.to_apply())
            self.on_change()
            self.select(name)
            self._tell_applied(applied)

    def _tell_applied(self, n):
        if n:
            self.notify(f"✅ Rule saved and set on {n} transaction{'s' if n != 1 else ''}.")

    def delete_rules(self):
        chosen = self._selected_rules()
        if not chosen:
            QMessageBox.information(self, "Rules", "Select a rule first.")
            return
        n = len(chosen)
        if QMessageBox.question(self, "Delete", f"Delete {n} rule{'s' if n > 1 else ''}? The transactions stay "
                                "as they are; only new imports are affected.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            for rule in chosen:
                self.db.delete_rule(rule["id"])
            self.on_change()

    def set_rules_merchant(self):
        chosen = self._selected_rules()
        if not chosen:
            QMessageBox.information(self, "Rules", "Select the rules to give a merchant first.")
            return
        n = len(chosen)
        names = self.db.get_merchants()
        name, ok = QInputDialog.getItem(self, "Set Merchant", f"The merchant of {n} rule{'s' if n > 1 else ''}:",
                                        names, -1, True)
        if not ok or not " ".join((name or "").split()):
            return
        name = self.db.set_rules_merchant([r["id"] for r in chosen], name)
        self.on_change()
        self.select("" if self.db.get_no_merchant_counts() != (0, 0) else name)


def _money(value):
    from daftarche.widgets import money
    return money(value)


class _SortItem(QTableWidgetItem):
    """A cell sorted by ``key`` (a number sorts as a number); ``last``: the (no merchant) line,
    kept at the bottom whichever way the column is sorted."""

    def __init__(self, text, key, last=False):
        super().__init__(text)
        self._key = key
        self._last = last

    def __lt__(self, other):
        mine, theirs = self._last, getattr(other, "_last", False)
        if mine or theirs:
            table = self.tableWidget()
            descending = table is not None and table.horizontalHeader().sortIndicatorOrder() == Qt.DescendingOrder
            if mine and theirs:
                return False
            return descending if mine else not descending
        try:
            return self._key < other._key
        except (AttributeError, TypeError):
            return super().__lt__(other)


class _NumberItem(QTableWidgetItem):
    """A number cell that sorts as a number."""

    def __init__(self, value, money=False):
        from daftarche.widgets import money as fmt
        super().__init__(fmt(value) if money else str(value))
        self._value = value

    def __lt__(self, other):
        return self._value < getattr(other, "_value", 0)


class MerchantCategoryDialog(QDialog):
    """Set a merchant's category: for its rules (new imports), its transactions with no
    category, or all its transactions (split ones are left alone)."""

    def __init__(self, db, merchant, parent=None):
        super().__init__(parent)
        from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB
        from daftarche.widgets import add_subcategory_items
        self.db = db
        self.m = merchant
        self._uncat = UNCATEGORIZED_CAT
        self._uncat_sub = UNCATEGORIZED_SUB
        self._add_subs = add_subcategory_items
        self.setWindowTitle("Set Category")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        title = QLabel(f"Set the category for <b>{html.escape(merchant['merchant'])}</b>")
        layout.addWidget(title)
        form = QFormLayout()
        self.f_type = SingleSelectCombo()
        types = merchant["types"] or {}
        names = [t["name"] for t in db.get_types() if "Expense" in t["name"] or "Income" in t["name"]]
        names.sort(key=lambda t: (-types.get(t, 0), "Expense" not in t))
        for t in names:
            self.f_type.addItem(t)
        self.f_type.currentTextChanged.connect(self._fill)
        self.f_cat = SingleSelectCombo()
        self.f_cat.currentTextChanged.connect(self._fill_subs)
        self.f_sub = SingleSelectCombo()
        form.addRow("Type:", self.f_type)
        form.addRow("Category:", self.f_cat)
        form.addRow("Sub-Category:", self.f_sub)
        layout.addLayout(form)
        layout.addWidget(QLabel("Apply to:"))
        self.chk_rules = QCheckBox()
        self.chk_rules.setChecked(True)
        self.chk_uncat = QCheckBox()
        self.chk_uncat.setChecked(True)
        self.chk_all = QCheckBox()
        self.chk_all.toggled.connect(self._enable_checks)
        for chk in (self.chk_rules, self.chk_uncat, self.chk_all):
            layout.addWidget(chk)
        note = QLabel(f"Choosing {UNCATEGORIZED_CAT} makes its rules only set the merchant. Split transactions "
                      "are left as they are.")
        note.setProperty("class", "dim-label")
        note.setWordWrap(True)
        layout.addWidget(note)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self._fill(self.f_type.currentText())

    def _enable_checks(self, *_):
        """Uncategorized only ever sets the merchant: it never takes a category off a transaction."""
        uncat = self.f_cat.currentText() == self._uncat
        if not uncat and not self.chk_all.isEnabled():
            self.chk_uncat.setChecked(True)  # back from Uncategorized: the usual choice again
        if uncat:
            self.chk_all.setChecked(False)
        self.chk_all.setEnabled(not uncat)
        self.chk_uncat.setEnabled(not uncat and not self.chk_all.isChecked())
        if uncat:
            self.chk_uncat.setChecked(False)

    def _type_id(self):
        return self.db.get_type_id(self.f_type.currentText())

    def _counts(self, type_name):
        type_id = self.db.get_type_id(type_name)
        uncat_cat, _ = self.db.get_uncategorized_ids()
        q = """SELECT COUNT(*) FROM transactions t WHERE t.merchant = ? AND t.type_id = ?
               AND NOT EXISTS (SELECT 1 FROM transaction_splits sp WHERE sp.transaction_id = t.id)"""
        all_n = self.db.conn.execute(q, (self.m["merchant"], type_id)).fetchone()[0]
        uncat_n = self.db.conn.execute(q + " AND (t.category_id IS NULL OR t.category_id = ?)",
                                       (self.m["merchant"], type_id, uncat_cat)).fetchone()[0]
        rules_n = self.db.conn.execute("SELECT COUNT(*) FROM import_mappings WHERE merchant = ? AND type_id = ?",
                                       (self.m["merchant"], type_id)).fetchone()[0]
        return rules_n, uncat_n, all_n

    def _fill(self, type_name):
        cats = [c["name"] for c in self.db.get_categories(self.db.get_type_id(type_name))]
        self.f_cat.blockSignals(True)
        self.f_cat.clear()
        self.f_cat.addItems([self._uncat] + [c for c in cats if c != self._uncat])
        from daftarche.icons import set_category_icons
        set_category_icons(self.f_cat, self.db, type_name)
        current = sorted(self.m["rule_targets"])
        if len(current) == 1 and current[0] != "(merchant only)":
            idx = self.f_cat.findText(current[0].split(" › ")[0])
            if idx >= 0:
                self.f_cat.setCurrentIndex(idx)
        self.f_cat.blockSignals(False)
        self._fill_subs(self.f_cat.currentText())
        rules_n, uncat_n, all_n = self._counts(type_name)
        self.chk_rules.setText(f"its rules ({rules_n}): what new imports get")
        self.chk_uncat.setText(f"its {type_name.lower()} transactions with no category ({uncat_n})")
        self.chk_all.setText(f"all its {type_name.lower()} transactions ({all_n}), even categorized")

    def _fill_subs(self, cat_name):
        self.f_sub.clear()
        cat = self.db.get_category_by_name(cat_name, type_id=self._type_id()) if cat_name else None
        if cat and cat_name != self._uncat:
            self._add_subs(self.f_sub, self.db, cat["id"])
        else:
            self.f_sub.addItem(self._uncat_sub)
        self.f_sub.setEnabled(cat_name != self._uncat)
        self._enable_checks()

    def _ok(self):
        type_name = self.f_type.currentText()
        cat_name = self.f_cat.currentText()
        if cat_name == self._uncat:
            cat_id, sub_id = self.db.get_uncategorized_ids()
        else:
            cat = self.db.get_category_by_name(cat_name, type_id=self._type_id())
            if cat is None:
                QMessageBox.warning(self, "Set Category", f"'{cat_name}' is not a {type_name} category.")
                return
            sub = self.f_sub.currentText()
            sub_row = self.db.uncategorized_subcategory(cat["id"]) if sub == self._uncat_sub else \
                self.db.get_subcategory_by_name(sub, cat["id"])
            if sub_row is None:
                QMessageBox.warning(self, "Set Category", f"'{sub}' is not a sub-category of {cat_name}.")
                return
            cat_id, sub_id = cat["id"], sub_row["id"]
        self.result = self.db.set_merchant_category(
            self.m["merchant"], type_name, cat_id, sub_id, rules=self.chk_rules.isChecked(),
            uncategorized=self.chk_uncat.isChecked(), all_transactions=self.chk_all.isChecked())
        self.accept()
