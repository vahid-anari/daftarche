import html

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QInputDialog,
    QColorDialog, QCheckBox, QFormLayout, QLineEdit,
    QDialogButtonBox, QFrame, QSizePolicy, QAbstractScrollArea, QRadioButton, QButtonGroup, QSplitter, QMenu,
)
from PySide6.QtCore import QByteArray, QItemSelectionModel, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPalette

from daftarche.style import get_settings
from daftarche.widgets import AccountsCombo, SingleSelectCombo, accounts_label
from daftarche.icons import IconPickerDialog, blank_icon, emoji_icon, suggest_icon
from daftarche.logos import LogoDialog, icon_size, logo_icon
from daftarche.tx_list import SHOW_KEY, TransactionList
from daftarche.past_categories import category_label, entry_icon


NO_MERCHANT = "(no merchant)"
GEOMETRY_KEY = "manage_geometry"  # Manage's size and place
FILLED_KEY = "manage_filled_screen"  # it filled the screen once, the first time transactions were shown
YOU_CHOOSE = "— you choose (To review)"
TOTAL_TIP = "All its money, all dates (a split transaction's parts each in their own)"


def _compact(table):
    """A list only as wide as its text (the room beside it goes to its transactions)."""
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
    table.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # in a narrow window


def _dim():
    return QBrush(QColor(get_settings().get("text_dim") or "#999"))


def spent_brush(spent):
    """The colour of a Total by what it means: money spent red, money in (or back) green, 0 dim.
    ``spent``: expenses minus income."""
    spent = round(spent or 0, 2)
    if not spent:
        return _dim()
    return QBrush(QColor(get_settings().get("expense" if spent > 0 else "income") or
                         ("#e74c3c" if spent > 0 else "#2ecc71")))


def kind_sign(type_name):
    """+1 for an expense, -1 for income, 0 for a transfer: what an amount of that type adds to
    "spent" (expenses minus income)."""
    type_name = type_name or ""
    return 1 if "Expense" in type_name else -1 if "Income" in type_name else 0


NO_CATEGORY = "(no category)"
NO_SUB = "(no sub-category)"


def _placeholder(data):
    """The line of a list that holds what has none ("(no category)", "(no sub-category)"): not a
    real category or sub-category, so it is not renamed, moved or deleted."""
    return isinstance(data, dict) and bool(data.get("placeholder"))


def _shown_name(data):
    return data["label"] if _placeholder(data) else data["name"]


def _total_item(total, type_name):
    """A Total in the lists of Categories: red spent, green money in, 0 dim; for a transfer "—"
    (money moved both ways: a sum would say nothing)."""
    from daftarche.widgets import money
    sign = kind_sign(type_name)
    right = Qt.AlignRight | Qt.AlignVCenter
    if not sign:
        item = QTableWidgetItem("—")
        item.setTextAlignment(right)
        item.setForeground(_dim())
        item.setToolTip("Transfers move money both ways: no total")
        return item
    item = _number_item(total, money(total), align=right)
    item.setForeground(spent_brush(sign * total))
    return item


def _number_item(value, text=None, align=Qt.AlignCenter):
    """A count (or, with ``text``, an amount) in a list: 0 is written, in the dim colour, so the
    numbers that are not 0 stand out."""
    item = QTableWidgetItem(str(value) if text is None else text)
    item.setTextAlignment(align)
    if not value:
        item.setForeground(_dim())
    return item


def _icon_buttons(items, stretch=True, size=(50, 34)):
    """A row of small buttons: (emoji, tooltip, slot). The emoji are drawn as pictures (as the
    category icons are): as text, they were taller than the button's line and got cut off. ＋
    stays a plain sign, in the theme's colour."""
    row = QHBoxLayout()
    row.setSpacing(6)
    buttons = []
    for label, tip, slot in items:
        btn = QPushButton(label if label == "＋" else "")
        if label != "＋":
            btn.setIcon(emoji_icon(label))
            btn.setIconSize(QSize(20, 20))
        btn.setFixedHeight(size[1])
        btn.setFixedWidth(size[0])
        if size[0] < 50:
            btn.setStyleSheet("padding: 0px;")  # small: the style's padding left no room for ＋
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        if "🗑" in label:
            btn.setProperty("class", "danger")
        elif label != "＋":
            btn.setProperty("class", "secondary")
        btn.clicked.connect(slot)
        row.addWidget(btn)
        buttons.append(btn)
    if stretch:
        row.addStretch()
    return row, buttons


def _head(title, items):
    """A list's title line: its name (a QLabel, or text) and its buttons at the right, so they
    stay at the top of a tall list. Returns (the row, the buttons)."""
    row = QHBoxLayout()
    row.setSpacing(6)
    if not isinstance(title, QWidget):
        title = QLabel(title)
        title.setProperty("class", "dim-label")
    row.addWidget(title, 1)
    buttons_row, buttons = _icon_buttons(items, stretch=False, size=(42, 30))
    row.addLayout(buttons_row)
    return row, buttons


def _list_box(head, table):
    """A list's title line and the list, as wide as the list: its buttons stay at its top right
    corner however wide the room beside it is (Show transactions off, the line dragged)."""
    box = QWidget()
    col = QVBoxLayout(box)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(8)
    col.addLayout(head)
    col.addWidget(table, 1)
    box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)
    return box


def _exec_menu(menu, where):
    menu.exec(where)


def _list_menu(table, items):
    """A right-click menu on a list with the commands of its buttons. ``items``: a list, or a
    function giving one, of (text, slot, needs_row) and None for a line; those that need a row
    are left out when the click is not on one. A click on a row selects it first (one that is
    already selected keeps the others selected with it)."""
    table.setContextMenuPolicy(Qt.CustomContextMenu)

    def show(pos):
        index = table.indexAt(pos)
        if index.isValid() and not table.selectionModel().isRowSelected(index.row(), table.rootIndex()):
            table.selectRow(index.row())
        entries = []
        for item in (items() if callable(items) else items):
            if item is None or not (item[2] and not index.isValid()):
                entries.append(item)
        while entries and entries[0] is None:
            entries.pop(0)
        while entries and entries[-1] is None:
            entries.pop()
        if not entries:
            return
        menu = QMenu(table)
        last = None
        for item in entries:
            if item is None:
                if last is not None:
                    menu.addSeparator()
            else:
                menu.addAction(item[0]).triggered.connect(lambda _=False, slot=item[1]: slot())
            last = item
        _exec_menu(menu, table.viewport().mapToGlobal(pos))
        menu.deleteLater()
    table.customContextMenuRequested.connect(show)
    table._list_menu = show  # for the tests


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
        from daftarche.icons import use_logos
        use_logos(db)
        self._build()
        self.refresh()
        saved = get_settings().get(GEOMETRY_KEY)
        if saved:
            self.restoreGeometry(QByteArray.fromHex(saved.encode()))
        self.finished.connect(self._save_geometry)

    def _line_panels(self):
        return (self.accounts_panel, self.cats_panel, self.merchants_panel, self.tags_panel)

    def _save_geometry(self, *_):
        """Its size and place, so it opens where you left it."""
        get_settings().set(GEOMETRY_KEY, bytes(self.saveGeometry().toHex()).decode())

    def _show_lines(self, shown):
        """"Show transactions" (beside the tabs) ticked or not: every tab shows them or not; the
        first time, the window fills the screen, so the lists keep their room."""
        get_settings().set(SHOW_KEY, shown)
        for panel in self._line_panels():
            panel.set_show_lines(shown)
        if shown and not get_settings().get(FILLED_KEY):
            get_settings().set(FILLED_KEY, True)
            self.showMaximized()

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
        corner = QWidget()
        corner_row = QHBoxLayout(corner)
        corner_row.setContentsMargins(0, 0, 12, 0)
        self.chk_lines = QCheckBox("Show transactions")
        self.chk_lines.setToolTip("Each tab shows the transactions of what is selected in it")
        self.chk_lines.setChecked(bool(get_settings().get(SHOW_KEY)))
        self.chk_lines.toggled.connect(self._show_lines)
        corner_row.addWidget(self.chk_lines)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        layout.addWidget(self.tabs)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 12)

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
        self._own_change = True  # the window's refresh after it need not come back here
        try:
            self.on_change_cb()
        finally:
            self._own_change = False

    def outside_change(self):
        """Something changed in the main window (an import, a category set in Transactions):
        show it here too (no Refresh button to remember)."""
        if not getattr(self, "_own_change", False):
            self.refresh()

    def notify(self, text):
        """A line at the bottom, until the next change (e.g. how many transactions a rule changed)."""
        self.note.setText(text)

    def open_merchant(self, name):
        """The Merchants tab, with this merchant and its rules."""
        self.tabs.setCurrentWidget(self.merchants_panel)
        self.merchants_panel.find.clear()
        self.merchants_panel.select(name)

    def _show_in_window(self, text, panel="cats", **filters):
        if self._show_transactions:
            self._show_transactions(text, panel, **filters)


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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Account", "Account ID", "Type", "Bank ID",
            "Color", "Active", "Dashboard", "Tx"
        ])
        self.table.horizontalHeaderItem(self.COL_TX).setToolTip("Transactions")
        _compact(self.table)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._update_lines)
        _apply_selection_palette(self.table)
        left = QWidget()
        left_col = QVBoxLayout(left)
        left_col.setSpacing(8)
        head, _ = _head("Accounts", [("＋", "Add Account", self.add), ("✏️", "Edit Account", self.edit),
                                     ("🗑️", "Delete Account", self.delete)])
        left_col.addWidget(_list_box(head, self.table), 1, Qt.AlignLeft)
        _list_menu(self.table, [("＋  Add Account…", self.add, False), None,
                                ("✏️  Edit Account…", self.edit, True), None,
                                ("🗑️  Delete Account", self.delete, True)])
        self.lines = TransactionList(self.db, self.on_change, total=False)  # an account's: the four sums
        self.split = _two_rows(left, self.lines, side_by_side=True)
        layout.addWidget(self.split, 1)
        self.set_show_lines(bool(get_settings().get(SHOW_KEY)))

    def showEvent(self, event):
        super().showEvent(event)
        _fit_beside(self.split)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        _fit_beside(self.split)

    def set_show_lines(self, shown):
        """Show or hide the selected account's transactions ("Show transactions")."""
        self.lines.setVisible(shown)
        self._update_lines()

    def _update_lines(self):
        if self.lines.isHidden():
            return
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        item = self.table.item(rows[0].row(), self.COL_NAME) if rows else None
        if item is None:
            self.lines.clear("Select an account to see its transactions")
            return
        self.lines.show_transactions(item.text(), {"account": [item.text()]})

    def refresh(self):
        rows = self.table.selectionModel().selectedRows()
        kept = self.table.item(rows[0].row(), self.COL_NAME).data(Qt.UserRole) if rows else None
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

            self.table.setItem(row, self.COL_TX, _number_item(count))
            if a["id"] == kept:
                self.table.selectRow(row)

        self.table.blockSignals(False)
        _fit_beside(self.split)
        self._update_lines()

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
def _two_rows(top, bottom, side_by_side=False):
    """A list above (or beside) its transactions, and a line between them to drag: it lights
    up under the pointer, with a little room on both sides so the buttons do not touch it."""
    split = QSplitter(Qt.Horizontal if side_by_side else Qt.Vertical)
    split.setChildrenCollapsible(False)
    split.setHandleWidth(7)
    split.addWidget(top)
    split.addWidget(bottom)
    split.setStretchFactor(0, 0)  # a bigger window: the room goes to the transactions
    split.setStretchFactor(1, 1)
    if side_by_side:
        top.layout().setContentsMargins(0, 0, 10, 0)
        bottom.layout().setContentsMargins(8, 0, 0, 0)
    else:
        top.layout().setContentsMargins(0, 0, 0, 10)
        bottom.layout().setContentsMargins(0, 8, 0, 0)
    split.handle(1).setAttribute(Qt.WA_Hover)  # for :hover in the style sheet
    split.handle(1).setToolTip("Drag to give either side more room")
    split.setSizes([top.sizeHint().width(), 2000] if side_by_side else [300, 500])
    return split


def _fit_beside(split):
    """Once its list has its rows: give the list beside the transactions the width it needs
    (the line can still be dragged afterwards)."""
    if getattr(split, "_fitted", False) or not split.isVisible():
        return  # on screen: only then are its columns as wide as their text
    left = split.widget(0)
    table = left.findChild(QTableWidget)
    header = table.horizontalHeader()
    width = sum(max(table.sizeHintForColumn(c), header.sectionSizeHint(c)) for c in range(table.columnCount()))
    width += 2 * table.frameWidth() + table.verticalScrollBar().sizeHint().width() + 24  # its frame, margins
    if split.width() > 600:  # laid out at its real size (the sizes are shares of it)
        width = min(width, split.width() // 2)  # at first at most half: the transactions need room too
        split.setSizes([width, split.width() - width])
        split._fitted = True


class CatsRulesPanel(QWidget):
    """Types, categories, sub-categories, and the merchants whose money goes there."""
    M_NAME, M_TX, M_RULES, M_TOTAL = range(4)

    def __init__(self, db, on_change, open_merchant=None, show_transactions=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.open_merchant = open_merchant  # (name) → Merchants tab
        self.show_transactions = show_transactions  # (text, **filters) → the main window
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        lists = QWidget()  # the four lists side by side; under them (when ticked), the transactions
        lists_row = QHBoxLayout(lists)
        lists_row.setContentsMargins(0, 0, 0, 0)
        lists_row.setSpacing(4)

        self.type_table, type_col, type_w = self._make_table_col(
            "Type", ["Name", "Tx", "Cats", "Total"], {1: "Transactions", 2: "Categories", 3: TOTAL_TIP},
            [("＋", self._add_type), ("✏️", self._rename_type), ("🗑️", self._delete_type)], "Type")
        self.type_table.itemSelectionChanged.connect(self._on_type_selected)
        self.type_table.cellDoubleClicked.connect(lambda r, c: self._rename_type())
        _list_menu(self.type_table, [("＋  Add Type…", self._add_type, False), None,
                                     ("✏️  Rename Type…", self._rename_type, True), None,
                                     ("🗑️  Delete Type", self._delete_type, True)])
        lists_row.addWidget(type_w)
        lists_row.addWidget(self._vline())

        self.cat_table, cat_col, cat_w = self._make_table_col(
            "Category", ["Name", "Tx", "Subs", "Total"], {1: "Transactions", 2: "Sub-categories", 3: TOTAL_TIP},
            [("＋", self._add_cat), ("✏️", self._rename_cat), ("🗑️", self._delete_cat)], "Category")
        self.cat_table.itemSelectionChanged.connect(self._on_cat_selected)
        self.cat_table.cellDoubleClicked.connect(lambda r, c: self._rename_cat())
        # a click on the category (again): its merchants, all sub-categories together
        self.cat_table.cellClicked.connect(lambda r, c: self.sub_table.clearSelection())
        _list_menu(self.cat_table, [("＋  Add Category…", self._add_cat, False), None,
                                    ("✏️  Edit Category…", self._rename_cat, True), None,
                                    ("🗑️  Delete Category", self._delete_cat, True)])
        lists_row.addWidget(cat_w)
        lists_row.addWidget(self._vline())

        self.sub_table, sub_col, sub_w = self._make_table_col(
            "Sub-Category", ["Name", "Tx", "M", "R", "Total"],
            {1: "Transactions", 2: "Merchants with transactions here", 3: "Rules that send money here", 4: TOTAL_TIP},
            [("＋", self._add_sub), ("✏️", self._rename_sub), ("🔀", self._reparent_sub), ("🗑️", self._delete_sub)],
            "Sub-Category")
        self.sub_table.itemSelectionChanged.connect(self._on_sub_selected)
        self.sub_table.cellDoubleClicked.connect(lambda r, c: self._rename_sub())
        self.sub_table.setSelectionMode(QTableWidget.ExtendedSelection)
        _list_menu(self.sub_table, [("＋  Add Sub-Category…", self._add_sub, False), None,
                                    ("✏️  Edit Sub-Category…", self._rename_sub, True),
                                    ("🔀  Move to Another Category…", self._reparent_sub, True), None,
                                    ("🗑️  Delete Sub-Category", self._delete_sub, True)])
        lists_row.addWidget(sub_w)
        lists_row.addWidget(self._vline())

        self.merchant_table, m_col, m_w = self._make_table_col(
            "Merchants", ["Merchant", "Tx", "R", "Total"],
            {1: "Transactions", 2: "Its rules that send money here", 3: "The money of its transactions here"})
        self.merchant_title = m_col.itemAt(0).widget()
        self.merchant_table.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)  # as wide as its text
        self.merchant_table.cellDoubleClicked.connect(self._merchant_double_clicked)
        self.merchant_table.itemSelectionChanged.connect(self._update_lines)
        _list_menu(self.merchant_table, self._merchant_menu)
        hint = QLabel("Double-click a merchant for its rules, its numbers for those transactions. "
                      "R: its rules that send money here.")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        m_col.removeWidget(self.merchant_table)
        self.merchant_title.setWordWrap(True)
        m_col.addWidget(self.merchant_table, 1, Qt.AlignLeft)
        m_col.addWidget(hint)
        m_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lists_row.addWidget(m_w, 1)
        self._lists = lists
        top = lists
        # the transactions under all the lists, across the whole width; the line between them drags
        self.lines = TransactionList(self.db, self.on_change)
        self.lines.btn_all.clicked.connect(self.merchant_table.clearSelection)
        self.split = _two_rows(top, self.lines)
        outer.addWidget(self.split, 1)
        self.set_show_lines(bool(get_settings().get(SHOW_KEY)))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_table_col(self, title, header, tips=None, buttons=None, what=""):
        """A list in its column: its title (with ``buttons``, (emoji, slot), at the right), then
        the list. Returns (the list, the column, its widget)."""
        col = QVBoxLayout()
        col.setSpacing(6)
        col.setContentsMargins(0, 0, 0, 0)

        if buttons:
            col.addLayout(self._make_btns(title, buttons, what))
        else:
            lbl = QLabel(title)
            lbl.setProperty("class", "dim-label")
            col.addWidget(lbl)

        n_cols = len(header)
        tbl = QTableWidget(0, n_cols)
        tbl.setHorizontalHeaderLabels(header)
        for index, tip in (tips or {}).items():  # the short headers in words
            tbl.horizontalHeaderItem(index).setToolTip(tip)
        self._add_scrollbar_gap(tbl, gap=8, scrollbar_width=12)
        h = tbl.horizontalHeader()
        h.setStretchLastSection(False)

        for i in range(n_cols):
            h.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        tbl.verticalHeader().setVisible(False)
        tbl.setIconSize(icon_size(tbl))  # as tall as its text: it follows the font size
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setSelectionMode(QTableWidget.SingleSelection)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)

        tbl.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        tbl.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)  # as wide as its text: scrolls only down
        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        _apply_selection_palette(tbl)
        col.addWidget(tbl, 1, Qt.AlignLeft)  # as wide as its text, even under a wider row of buttons

        w = QWidget()
        w.setLayout(col)
        w.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

        return tbl, col, w

    def _make_btns(self, title, pairs, what):
        """A list's title line with its small buttons, with tooltips."""
        edit = f"Rename {what}" if what == "Type" else f"Edit {what} (name and icon)"
        tips = {"＋": f"Add {what}", "✏️": edit, "🔀": "Move to Another Category", "🗑️": f"Delete {what}"}
        return _head(title, [(label, tips.get(label, ""), slot) for label, slot in pairs])[0]

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

        totals = self.db.line_totals("type_id")
        for t in self.db.get_types():
            tx = self.db.get_transaction_count_for_type(t["id"])
            cats = self.db.get_category_count_for_type(t["id"])

            row = self.type_table.rowCount()
            self.type_table.insertRow(row)
            for col, val in enumerate([t["name"], str(tx), str(cats)]):
                item = QTableWidgetItem(val) if col == 0 else _number_item(int(val))
                item.setData(Qt.UserRole, t)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.type_table.setItem(row, col, item)
            item = _total_item(totals.get(t["id"], 0), t["name"])
            item.setData(Qt.UserRole, t)
            self.type_table.setItem(row, 3, item)

        self.type_table.blockSignals(False)
        self._restore_selection(self.type_table, sel_type, key="id")

        selected_type = self._selected_data(self.type_table)
        type_id = selected_type["id"] if selected_type else None
        self._reload_cats(type_id, sel_cat, sel_sub)

    def _reload_cats(self, type_id=None, sel_cat=None, sel_sub=None):
        self.cat_table.blockSignals(True)
        self.cat_table.setRowCount(0)

        cats = self.db.get_categories(type_id) if type_id else []
        kind = self._selected_data(self.type_table)
        kind = kind["name"] if kind else ""
        totals = self.db.line_totals("category_id") if cats else {}
        for c in cats:
            tx = self.db.get_transaction_count_for_category(c["id"])
            subs = self.db.get_subcategory_count_for_category(c["id"])

            row = self.cat_table.rowCount()
            self.cat_table.insertRow(row)
            for col, val in enumerate([c["name"], str(tx), str(subs)]):
                item = QTableWidgetItem(val) if col == 0 else _number_item(int(val))
                item.setData(Qt.UserRole, c)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                elif c["icon"] or any(x["icon"] for x in cats):  # none: a space, in line with the others
                    item.setIcon(emoji_icon(c["icon"]) if c["icon"] else blank_icon())
                self.cat_table.setItem(row, col, item)
            item = _total_item(totals.get(c["id"], 0), kind)
            item.setData(Qt.UserRole, c)
            self.cat_table.setItem(row, 3, item)
        none = self.db.no_category(type_id) if type_id else None
        if none and (none["count"] or none["rules"]):  # what has no category yet (To review), last
            data = {**dict(none["category"]), "placeholder": True, "label": NO_CATEGORY}
            row = self.cat_table.rowCount()
            self.cat_table.insertRow(row)
            items = [QTableWidgetItem(NO_CATEGORY), _number_item(none["count"]), QTableWidgetItem(""),
                     _total_item(none["total"], kind)]
            items[0].setForeground(_dim())
            items[0].setToolTip("Transactions of this type with no category yet (To review): select it to see them, "
                                "right-click them below to give them one")
            if any(x["icon"] for x in cats):
                items[0].setIcon(blank_icon())
            for col, item in enumerate(items):
                item.setData(Qt.UserRole, data)
                if col in (1, 2):
                    item.setTextAlignment(Qt.AlignCenter)
                self.cat_table.setItem(row, col, item)

        self.cat_table.blockSignals(False)
        self._restore_selection(self.cat_table, sel_cat, key="id")

        selected_cat = self._selected_data(self.cat_table)
        cat_id = selected_cat["id"] if selected_cat else None
        self._reload_subs(cat_id, sel_sub)

    def _reload_subs(self, cat_id=None, sel_sub=None):
        self.sub_table.blockSignals(True)
        self.sub_table.setRowCount(0)

        from daftarche.db import UNCATEGORIZED_SUB
        cat = self._selected_data(self.cat_table)
        subs = self.db.get_subcategories(cat_id) if cat_id and not _placeholder(cat) else []
        # its "Uncategorized" (a category chosen, no sub-category): "(no sub-category)", last, and
        # only when something is in it (an empty one is made again when needed)
        subs = sorted(subs, key=lambda x: x["name"] == UNCATEGORIZED_SUB)
        kind = self._selected_data(self.type_table)
        kind = kind["name"] if kind else ""
        totals = self.db.line_totals("subcategory_id") if subs else {}
        for s in subs:
            tx = self.db.get_transaction_count_for_subcategory(s["id"])
            merchants = self.db.get_merchant_count_for_subcategory(s["id"])
            rules = self.db.get_rule_count_for_subcategory(s["id"])
            none = s["name"] == UNCATEGORIZED_SUB
            if none and not tx and not rules:
                continue
            data = {**dict(s), "placeholder": True, "label": NO_SUB} if none else s

            row = self.sub_table.rowCount()
            self.sub_table.insertRow(row)
            for col, val in enumerate([NO_SUB if none else s["name"], str(tx), str(merchants), str(rules)]):
                item = QTableWidgetItem(val) if col == 0 else _number_item(int(val))
                item.setData(Qt.UserRole, data)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                elif s["icon"] or any(x["icon"] for x in subs):  # its own; none: a space, in line
                    item.setIcon(emoji_icon(s["icon"]) if s["icon"] else blank_icon())
                if col == 0 and none:
                    item.setForeground(_dim())
                    item.setToolTip("Transactions with this category and no sub-category: nothing is missing")
                self.sub_table.setItem(row, col, item)
            item = _total_item(totals.get(s["id"], 0), kind)
            item.setData(Qt.UserRole, data)
            self.sub_table.setItem(row, 4, item)

        self.sub_table.blockSignals(False)
        # nothing chosen: the merchants of the whole category; a click narrows them to one sub-category
        self._restore_selection(self.sub_table, sel_sub, key="id", fallback=False)
        self._on_sub_selected()

    def _reload_merchants(self, cat_data=None, sub_data=None):
        kept = self._selected_data(self.merchant_table)
        self.merchant_table.blockSignals(True)
        try:
            self._fill_merchants(cat_data, sub_data)
            if kept:
                for row in range(self.merchant_table.rowCount()):
                    m = self.merchant_table.item(row, 0).data(Qt.UserRole)
                    if m["merchant"] == kept["merchant"]:
                        self.merchant_table.selectRow(row)
                        break
        finally:
            self.merchant_table.blockSignals(False)
        for table in (self.type_table, self.cat_table, self.sub_table, self.merchant_table):
            table.setMinimumWidth(table.sizeHint().width())  # never narrower than its text: no side scrolling
        self._lists.layout().invalidate()
        self._lists.layout().activate()
        self._lists.setMinimumWidth(self._lists.layout().minimumSize().width())  # the window keeps room for them
        self._update_lines()

    # ── the transactions under the merchants ─────────────────────────────────
    def set_show_lines(self, shown):
        """Show or hide them ("Show transactions", beside Manage's tabs)."""
        self.lines.setVisible(shown)
        self._update_lines()

    def _update_lines(self):
        if self.lines.isHidden():
            return
        cat = self._selected_data(self.cat_table)
        sub = self._selected_data(self.sub_table)
        m = self._selected_data(self.merchant_table)
        self.lines.btn_all.setVisible(m is not None)
        if not cat:
            self.lines.clear()
            return
        kind = self._selected_data(self.type_table)
        where = f"{_shown_name(cat)} › {_shown_name(sub)}" if sub else _shown_name(cat)
        who = (m["merchant"] or NO_MERCHANT) + " in " if m else ""
        filters = {"type": [kind["name"]] if kind else [], "category": [cat["name"]],
                   "subcategory": [sub["name"]] if sub else [], "merchant": [m["merchant"]] if m else []}
        self.lines.show_transactions(who + where, filters, hidden=("type", "category") + (("merchant",) if m else ())
                                     + (("subcategory",) if sub else ()))

    def _fill_merchants(self, cat_data=None, sub_data=None):
        from daftarche.widgets import money
        table = self.merchant_table
        table.setRowCount(0)
        if not cat_data:
            self.merchant_title.setText("Merchants")
            return
        where = sub_data or cat_data
        self.merchant_title.setText(f"Merchants in {_shown_name(where)}" +
                                    ("" if sub_data or _placeholder(cat_data) else "  (all its sub-categories)"))
        dim = QBrush(QColor(get_settings().get("text_dim") or "#999"))
        kind = self._selected_data(self.type_table)
        sign = kind_sign(kind["name"] if kind else "")
        type_id = kind["id"] if kind and _placeholder(cat_data) else None  # Uncategorized has every type's
        logos = {name.casefold(): image for name, image in self.db.get_logos().items()}
        table.setIconSize(icon_size(table))
        for m in self.db.get_merchants_in(cat_data["id"], sub_data["id"] if sub_data else None, type_id):
            row = table.rowCount()
            table.insertRow(row)
            none = not m["merchant"]
            right = Qt.AlignRight | Qt.AlignVCenter
            items = [QTableWidgetItem(NO_MERCHANT if none else m["merchant"]),
                     _number_item(m["count"], align=right), _number_item(m["rules"], align=right),
                     _number_item(m["total"], money(m["total"]), align=right)]
            items[-1].setForeground(spent_brush(sign * m["total"]))  # spent red, money in green
            if logos:
                image = logos.get(m["merchant"].casefold()) if m["merchant"] else None
                items[0].setIcon(logo_icon(image) if image else blank_icon())
            for col, item in enumerate(items):
                item.setData(Qt.UserRole, m)
                if none:
                    item.setForeground(dim)
                table.setItem(row, col, item)

    def _merchant_menu(self):
        """Right-click on a merchant: its rules (Merchants tab) or its transactions here."""
        row = self.merchant_table.currentRow()
        item = self.merchant_table.item(row, 0) if row >= 0 else None
        m = item.data(Qt.UserRole) if item else None
        items = [("📋  Its Transactions Here", lambda: self._merchant_double_clicked(row, self.M_TX), True)]
        if m and m["merchant"] and self.open_merchant:
            items.insert(0, ("🏪  Its Rules (Merchants Tab)", lambda: self._merchant_double_clicked(row, self.M_NAME),
                             True))
        return items

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
        dlg = IconPickerDialog("", f"New category under <b>{html.escape(type_data['name'])}</b>",
                               "Shown beside its name in the lists and the transactions.", self,
                               name="", suggest=suggest_icon, title="Add Category", logos=self.db.get_logos())
        if not dlg.exec():
            return
        if not self.db.add_category(dlg.name, type_data["name"]):
            QMessageBox.warning(self, "Duplicate", f"'{dlg.name}' already exists.")
            return
        if dlg.icon:
            self.db.set_category_icon(self.db.get_category_by_name(dlg.name, type_name=type_data["name"])["id"],
                                      dlg.icon)
        self.on_change()
        self._select_by_name(self.cat_table, dlg.name)

    def _not_a_real_one(self, data, what):
        """True (and says so) for the "(no category)" / "(no sub-category)" line."""
        if not _placeholder(data):
            return False
        QMessageBox.information(self, what, f"{_shown_name(data)} holds the transactions that have none: it is "
                                "not one to change. Give them one: select them below, right-click.")
        return True

    def _rename_cat(self):
        """✏️: the category's name and icon, in one window (Transfer › Loans keeps its name)."""
        data = self._selected_data(self.cat_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        if self._not_a_real_one(data, "Category"):
            return
        from daftarche.db import CAT_LOANS
        loans = self.db.loans_category()
        locked = bool(loans and data["id"] == loans["id"] and data["name"] == CAT_LOANS)
        dlg = IconPickerDialog(data["icon"], "Category", "Shown beside its name in the lists and the transactions."
                               + (" The Loans window reads this name: it is kept." if locked else ""), self,
                               name=data["name"], suggest=suggest_icon, name_locked=locked, title="Edit Category",
                               logos=self.db.get_logos())
        if not dlg.exec():
            return
        cat_id = data["id"]
        with self.db.transaction():
            if dlg.name != data["name"]:
                target = self.db.get_category_by_name(dlg.name, data["type_id"]) if data["type_id"] else None
                if target and not _confirm_merge(self, "category", data["name"], dlg.name,
                                                 "transactions, sub-categories and rules"):
                    return
                self.db.rename_category(cat_id, dlg.name)
                cat_id = target["id"] if target else cat_id
            if dlg.icon != (data["icon"] or ""):
                self.db.set_category_icon(cat_id, dlg.icon)
        self.on_change()
        self._select_by_name(self.cat_table, dlg.name)

    def _delete_cat(self):
        if self._loans_line():
            return
        data = self._selected_data(self.cat_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        if self._not_a_real_one(data, "Category"):
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
        if self._not_a_real_one(cat_data, "Sub-Category"):
            return
        dlg = IconPickerDialog("", f"New sub-category of <b>{html.escape(cat_data['name'])}</b>",
                               self._sub_icon_hint(cat_data), self, name="",
                               suggest=self._sub_suggestion(cat_data), title="Add Sub-Category",
                               logos=self.db.get_logos())
        if not dlg.exec():
            return
        if not self.db.add_subcategory(dlg.name, cat_data["id"]):
            QMessageBox.warning(self, "Duplicate", f"'{dlg.name}' already exists here.")
            return
        if dlg.icon:
            self.db.set_subcategory_icon(self.db.get_subcategory_by_name(dlg.name, cat_data["id"])["id"], dlg.icon)
        self.on_change()
        self._select_by_name(self.sub_table, dlg.name)

    @staticmethod
    def _sub_icon_hint(cat):
        return "Its own icon, beside its name. No Icon: a space (its category's is beside it already)."

    @staticmethod
    def _sub_suggestion(cat):
        """An icon from the name, unless it is the category's (beside it already)."""
        def suggest(name):
            offer = suggest_icon(name)
            return "" if cat and offer == cat["icon"] else offer
        return suggest

    def _rename_sub(self):
        data = self._selected_data(self.sub_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a sub-category first.")
            return
        if self._not_a_real_one(data, "Sub-Category"):
            return
        cat = self._selected_data(self.cat_table)
        dlg = IconPickerDialog(data["icon"], "Sub-category", self._sub_icon_hint(cat), self, name=data["name"],
                               suggest=self._sub_suggestion(cat), title="Edit Sub-Category",
                               logos=self.db.get_logos())
        if not dlg.exec():
            return
        sub_id = data["id"]
        with self.db.transaction():
            if dlg.name != data["name"]:
                target = self.db.get_subcategory_by_name(dlg.name, data["category_id"])
                if target and not _confirm_merge(self, "sub-category", data["name"], dlg.name,
                                                 "transactions and rules"):
                    return
                self.db.rename_subcategory(sub_id, dlg.name)
                sub_id = target["id"] if target else sub_id
            if dlg.icon != (data["icon"] or ""):
                self.db.set_subcategory_icon(sub_id, dlg.icon)
        self.on_change()
        self._select_by_name(self.sub_table, dlg.name)

    def _reparent_sub(self):
        selected_subs = self._selected_multi_data(self.sub_table)
        if not selected_subs:
            QMessageBox.information(self, "Select", "Select one or more sub-categories first.")
            return
        if any(_placeholder(x) for x in selected_subs) and self._not_a_real_one(
                next(x for x in selected_subs if _placeholder(x)), "Sub-Category"):
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
        if self._not_a_real_one(data, "Sub-Category"):
            return
        count = self.db.get_transaction_count_for_subcategory(data["id"])
        msg = f"Delete '{data['name']}'?"
        if count:
            msg += f"\n⚠️ Affects {count} transactions!"
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.db.delete_subcategory(data["id"])
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
        self.f_account = AccountsCombo([a["name"] for a in db.get_accounts(active_only=True)],
                                       (existing or {}).get("accounts") or ())
        self.f_account.setToolTip("The accounts whose statements this rule reads: tick one or several. "
                                  "None ticked: all accounts, also those added later.")
        form.addRow("Accounts:", self.f_account)
        self.f_name = QLineEdit((existing or {}).get("name") or "")
        self.f_name.setPlaceholderText("Words in the bank's name for it (e.g. AMZN MKTP)")
        form.addRow("Name:", self.f_name)
        self.f_memo = QLineEdit((existing or {}).get("memorandum") or "")
        self.f_memo.setPlaceholderText("Words in the memo (optional)")
        form.addRow("Memo:", self.f_memo)
        hint = QLabel("Whole words, any letter case; | joins words that must all appear (e.g. amazon|ca). "
                      "When several rules match, the one that matched the most text wins, then the one "
                      "for fewer accounts.")
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
        self.f_account.selectionChanged.connect(lambda _: self._count())
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
        """The rule's account names ([]: all accounts)."""
        return self.f_account.accounts()

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
        key = (self.f_type.currentText(), tuple(self._account()))
        if key not in self._texts:
            self._texts[key] = self.db.get_rule_texts(key[0], list(key[1]))
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
        from daftarche.db import rule_match_length, rule_rank
        type_name = self.f_type.currentText()
        name, memo = self.f_name.text().strip(), self.f_memo.text().strip()
        self._claimed = ([], [])
        if (name or memo) and ("Expense" in type_name or "Income" in type_name):
            if type_name not in self._apply_rows:
                self._apply_rows[type_name] = self.db.rule_apply_rows(type_name, (self.existing or {}).get("id"))
            accounts = self.db.account_id_set(self._account())
            merchant_only = self._cat_id() is None
            for row in self._apply_rows[type_name]:
                if accounts and row["account_id"] not in accounts:
                    continue
                name_len, memo_len = rule_match_length(row["name"], name), rule_match_length(row["memo"], memo)
                if name_len is None or memo_len is None:
                    continue
                if row["best"] is not None and rule_rank(name_len + memo_len, accounts, 0)[:3] < row["best"][:3]:
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
                    f"There is already a {v['type_name'].lower()} rule for this text and these accounts "
                    f"(merchant: {owner}).\n\nReplace it with this one?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        self.accept()

    def values(self):
        """{type_name, account_name (a list of names; []: all accounts), name, memo, category_id,
        subcategory_id, merchant}: what to save.
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Tag", "Tx"])
        self.table.horizontalHeaderItem(self.COL_TX).setToolTip("Transactions")
        _compact(self.table)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(lambda r, c: self.rename())
        self.table.itemSelectionChanged.connect(self._update_lines)
        _apply_selection_palette(self.table)
        left = QWidget()
        left_col = QVBoxLayout(left)
        left_col.setSpacing(8)
        head, _ = _head("Tags", [("＋", "Add Tag", self.add), ("✏️", "Rename Tag", self.rename),
                                 ("🗑️", "Delete Tag", self.delete)])
        left_col.addWidget(_list_box(head, self.table), 1, Qt.AlignLeft)
        _list_menu(self.table, [("＋  Add Tag…", self.add, False), None,
                                ("✏️  Rename Tag…", self.rename, True), None,
                                ("🗑️  Delete Tag", self.delete, True)])
        self.lines = TransactionList(self.db, self.on_change)
        self.split = _two_rows(left, self.lines, side_by_side=True)
        layout.addWidget(self.split, 1)
        self.set_show_lines(bool(get_settings().get(SHOW_KEY)))

    def showEvent(self, event):
        super().showEvent(event)
        _fit_beside(self.split)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        _fit_beside(self.split)

    def set_show_lines(self, shown):
        """Show or hide the selected tag's transactions ("Show transactions")."""
        self.lines.setVisible(shown)
        self._update_lines()

    def _update_lines(self):
        if self.lines.isHidden():
            return
        tag_id, name = self._selected()
        if tag_id is None:
            self.lines.clear("Select a tag to see its transactions")
            return
        self.lines.show_transactions(name, {"tags": [name]})

    def refresh(self):
        kept, _ = self._selected()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for tag in self.db.get_tags():
            count = self.db.get_transaction_count_for_tag(tag["id"])
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(tag["name"])
            name_item.setData(Qt.UserRole, tag["id"])
            self.table.setItem(row, self.COL_NAME, name_item)
            self.table.setItem(row, self.COL_TX, _number_item(count))
            if tag["id"] == kept:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        _fit_beside(self.split)
        self._update_lines()

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
    COL_FLAG, COL_NAME, COL_TX, COL_RULES, COL_TOTAL = range(5)
    FLAG_KEY = "merchants_flagged"
    """Settings: the merchants ticked 🚩 to look at again (while tidying up; kept on this computer)."""
    R_TEXT, R_SETS, R_TYPE, R_ACCOUNT, R_TX = range(5)
    U_NAME, U_TYPE, U_TX, U_TOTAL = range(4)

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
        find_row, self._merchant_btns = _head(self.find, [
            ("✏️", "Rename / Merge", self.rename),
            ("🏷️", "Set Category… (its rules and transactions)", self.set_category),
            ("📋", "Its Transactions", self.open_transactions),
            ("🗑️", "Delete Merchant", self.delete),
            ("🚩", "Only those ticked 🚩 (to look at again)", self._only_flagged_changed)])
        self.btn_only_flagged = self._merchant_btns[-1]
        self.btn_only_flagged.setCheckable(True)
        left.addLayout(find_row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["🚩", "Merchant", "Tx", "R", "Total"])
        for col, tip in ((self.COL_FLAG, "To look at again: tick a merchant, untick it when done "
                                         "(kept on this computer; a click here puts the ticked first)"),
                         (self.COL_TX, "Transactions"), (self.COL_RULES, "Its rules"),
                         (self.COL_TOTAL, "Spent minus income (money back counts against it); transfers left out")):
            self.table.horizontalHeaderItem(col).setToolTip(tip)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_NAME, QHeaderView.Fixed)  # as wide as the names: _fit_width
        h.setMinimumSectionSize(40)
        for col, width in ((self.COL_FLAG, 44), (self.COL_TX, 62), (self.COL_RULES, 72)):  # padding made them wide
            h.setSectionResizeMode(col, QHeaderView.Fixed)
            h.resizeSection(col, width)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(self.COL_NAME, Qt.AscendingOrder)  # A to Z until a header is clicked
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.itemSelectionChanged.connect(self._show_rules)
        self.table.cellClicked.connect(lambda r, c: self._show_all())  # the merchant again: all of its
        self.table.itemChanged.connect(self._flag_changed)
        _apply_selection_palette(self.table)
        left.addWidget(self.table, 1)
        # the sums of the merchants shown, always in sight under their columns
        self.totals = QTableWidget(1, 5)
        self.totals.horizontalHeader().hide()
        self.totals.verticalHeader().hide()
        self.totals.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.totals.setSelectionMode(QAbstractItemView.NoSelection)
        self.totals.setFocusPolicy(Qt.NoFocus)
        self.totals.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.totals.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.totals.setFixedHeight(self.totals.verticalHeader().defaultSectionSize() + 2 * self.totals.frameWidth())
        self.totals.setToolTip("The merchants shown (all, or those you looked for) added up")
        h.sectionResized.connect(lambda col, _old, new: self.totals.setColumnWidth(col, new))
        left.addWidget(self.totals)
        _list_menu(self.table, lambda: [(("🚩  Done (Untick)" if self._is_flagged() else "🚩  Look at Again"),
                                          self._toggle_flag, True), ("🖼️  Logo…", self.set_logo, True), None,
                                        ("✏️  Rename / Merge…", self.rename, True),
                                ("🏷️  Set Category…", self.set_category, True),
                                ("📋  Its Transactions", self.open_transactions, True), None,
                                        ("🗑️  Delete Merchant", self.delete, True)])
        lw = QWidget()
        lw.setLayout(left)
        self._left = lw  # as wide as its list (_fit_width): a bigger window widens the rules and transactions
        layout.addWidget(lw)
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        layout.addWidget(sep)

        right = QVBoxLayout()
        right.setSpacing(8)
        top = QWidget()
        top_col = QVBoxLayout(top)
        top_col.setContentsMargins(0, 0, 0, 0)
        top_col.setSpacing(8)
        lists = QHBoxLayout()  # its rules, and beside them the categories it was given
        lists.setSpacing(18)
        rules_col = QVBoxLayout()
        rules_col.setSpacing(8)
        self.rules_title = QLabel()
        rules_head, buttons = _head(self.rules_title, [
            ("＋", "Add Rule", self.add_rule),
            ("✏️", "Edit Rule", self.edit_rule),
            ("🏪", "Set Merchant… (the selected rules)", self.set_rules_merchant),
            ("🗑️", "Delete Rule", self.delete_rules)])
        self.btn_set_merchant = buttons[2]
        rules_col.addLayout(rules_head)
        self.rules = QTableWidget(0, 5)
        self.rules.setHorizontalHeaderLabels(["Bank text", "Sets", "Type", "Accounts", "Tx"])
        self.rules.horizontalHeaderItem(self.R_TX).setToolTip(
            "The transactions it recognises and wins now (select it to see them); 0: no use any more?")
        h = self.rules.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.rules.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.rules.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)  # as wide as its text, first
        self.rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rules.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.rules.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rules.verticalHeader().setVisible(False)
        self.rules.setAlternatingRowColors(True)
        self.rules.cellDoubleClicked.connect(lambda r, c: self.edit_rule())
        self.rules.itemSelectionChanged.connect(lambda: self._one_filter(self.used, self.rules))
        _apply_selection_palette(self.rules)
        rules_col.addWidget(self.rules, 1)
        lists.addLayout(rules_col)
        self.used_host = QWidget()
        used_col = QVBoxLayout(self.used_host)
        used_col.setContentsMargins(0, 0, 0, 0)
        used_col.setSpacing(8)
        self.used_title = QLabel("Used in")
        self.used_title.setMinimumHeight(30)  # as tall as the rules' title line with its buttons
        self.used_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.used_title.setToolTip("The categories its transactions have; click one to see only those below")
        used_col.addWidget(self.used_title)
        self.used = QTableWidget(0, 4)
        self.used.setHorizontalHeaderLabels(["Category", "Type", "Tx", "Total"])
        for col, tip in ((self.U_TX, "Transactions"), (self.U_TOTAL, "Their amounts added up")):
            self.used.horizontalHeaderItem(col).setToolTip(tip)
        _compact(self.used)
        self.used.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)  # the rules first; it scrolls if need be
        self.used.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.used.setSelectionMode(QAbstractItemView.SingleSelection)
        self.used.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.used.verticalHeader().setVisible(False)
        self.used.setAlternatingRowColors(True)
        self.used.itemSelectionChanged.connect(lambda: self._one_filter(self.rules, self.used))
        _apply_selection_palette(self.used)
        used_col.addWidget(self.used, 1)
        lists.addWidget(self.used_host)
        lists.addStretch(1)
        top_col.addLayout(lists, 1)
        self.rules_count = QLabel()  # its transactions and its rules, compared
        self.rules_count.setWordWrap(True)
        top_col.addWidget(self.rules_count)
        self.rules_hint = QLabel()  # under the lists, the whole width: few lines
        self.rules_hint.setProperty("class", "dim-label")
        self.rules_hint.setWordWrap(True)
        top_col.addWidget(self.rules_hint)
        _list_menu(self.rules, self._rules_menu)
        self.lines = TransactionList(self.db, self.on_change)
        self.lines.btn_all.setToolTip("Every category again")
        self.lines.btn_all.clicked.connect(self._show_all)
        self.split = _two_rows(top, self.lines)
        right.addWidget(self.split, 1)
        layout.addLayout(right, 7)
        self.set_show_lines(bool(get_settings().get(SHOW_KEY)))

    def showEvent(self, event):
        super().showEvent(event)
        self._update_totals()  # the fonts are final now: the Total column fits the sum

    # ── its transactions, under its rules ─────────────────────────────────────
    def set_show_lines(self, shown):
        """Show or hide them ("Show transactions", beside Manage's tabs)."""
        self.lines.setVisible(shown)
        self._update_lines()

    def _update_lines(self):
        if self.lines.isHidden():
            return
        m = self._selected()
        used = self._selected_used()
        rules = self._selected_rules()
        self.lines.btn_all.setVisible(used is not None or bool(rules))
        if m is None:
            self.lines.clear()
            return
        if rules:  # what these rules recognise now, whatever merchant it has: the Merchant column shows it
            which = (f"rule {rule_text(rules[0])}" if len(rules) == 1 else f"{len(rules)} rules")
            self.lines.show_transactions(f"{m['merchant'] or NO_MERCHANT} · {which}",
                                         {"ids": self.db.rule_transaction_ids(r["id"] for r in rules)})
            return
        if used is None:
            self.lines.show_transactions(m["merchant"] or NO_MERCHANT, {"merchant": [m["merchant"]]},
                                         hidden=("merchant",))
            return
        self.lines.show_transactions(
            f"{m['merchant']} in {category_label(used['category'], used['subcategory'])}",
            {"merchant": [m["merchant"]], "type": [used["type"]], "category": [used["category"]],
             "subcategory": [used["subcategory"]] if used["subcategory"] else []},
            hidden=("merchant", "type", "category", "subcategory"))

    def _one_filter(self, other, chosen):
        """A rule or a line of Used in narrows the transactions below: one of them at a time."""
        if chosen.selectionModel().hasSelection():
            other.blockSignals(True)
            other.clearSelection()
            other.blockSignals(False)
        self._update_lines()

    def _show_all(self):
        """Show All, or a click on the merchant again: all its transactions."""
        if not (self.rules.selectionModel().hasSelection() or self.used.selectionModel().hasSelection()):
            return
        for table in (self.rules, self.used):
            table.blockSignals(True)
            table.clearSelection()
            table.blockSignals(False)
        self._update_lines()

    # ── the categories it was given ──────────────────────────────────────────
    def _selected_used(self):
        rows = self.used.selectionModel().selectedRows()
        return self.used.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None

    def _fill_used(self, m):
        """Its categories, of each of its types (most transactions first). The one selected stays
        selected while it is still there."""
        kept = self._selected_used()
        key = (lambda e: (e["type"], e["category_id"], e["subcategory_id"]))
        self.used.blockSignals(True)
        self.used.setRowCount(0)
        entries = []
        if m and m["merchant"]:
            for kind in sorted(m.get("types") or {}, key=lambda k: -m["types"][k]):
                for e in self.db.merchant_categories(m["merchant"], kind):
                    entries.append({**e, "type": kind})
        entries.sort(key=lambda e: -e["count"])
        icons = self.db.get_icons()
        reselect = None
        for e in entries:
            r = self.used.rowCount()
            self.used.insertRow(r)
            name = QTableWidgetItem(category_label(e["category"], e["subcategory"]))
            icon = entry_icon(icons, e)
            if icon:
                name.setIcon(emoji_icon(icon))
            name.setData(Qt.UserRole, e)
            self.used.setItem(r, self.U_NAME, name)
            self.used.setItem(r, self.U_TYPE, QTableWidgetItem(e["type"]))
            self.used.setItem(r, self.U_TX, _number_item(e["count"], align=Qt.AlignRight | Qt.AlignVCenter))
            total = _number_item(round(e["total"], 2), _money(e["total"]), Qt.AlignRight | Qt.AlignVCenter)
            total.setForeground(spent_brush(kind_sign(e["type"]) * e["total"]))  # income green, as money in
            self.used.setItem(r, self.U_TOTAL, total)
            if kept and key(e) == key(kept):
                reselect = r
        self.used.setColumnHidden(self.U_TYPE, len({e["type"] for e in entries}) < 2)  # one type: says nothing
        if reselect is not None:
            self.used.selectRow(reselect)
        self.used.blockSignals(False)
        self.used_host.setVisible(bool(entries))

    # ── the merchants ─────────────────────────────────────────────────────────
    def refresh(self):
        selected = self._selected()
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        rows = list(self.db.get_merchant_overview())
        n_tx, n_rules = self.db.get_no_merchant_counts()
        if n_tx or n_rules:
            rows.append({"merchant": "", "count": n_tx, "rules": n_rules, "total": self.db.get_no_merchant_total(),
                         "rule_targets": set(), "types": {}})
        dim = QBrush(QColor(get_settings().get("text_dim") or "#999"))
        flagged = self._flagged()
        logos = {name.casefold(): image for name, image in self.db.get_logos().items()}
        self.table.setIconSize(icon_size(self.table))
        for m in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            none = not m["merchant"]
            ticked = not none and m["merchant"] in flagged
            flag = _SortItem("", (0 if ticked else 1, m["merchant"].casefold()), none)
            if none:
                flag.setFlags(flag.flags() & ~Qt.ItemIsUserCheckable)  # the line of what has no merchant
            else:
                flag.setCheckState(Qt.Checked if ticked else Qt.Unchecked)
                flag.setToolTip("Look at it again (untick when done)")
            items = [flag, _SortItem(NO_MERCHANT if none else m["merchant"], m["merchant"].casefold(), none),
                     _SortItem(str(m["count"]), m["count"], none), _SortItem(str(m["rules"]), m["rules"], none),
                     _SortItem(_money(m["total"]), m["total"] or 0, none)]
            items[self.COL_NAME].setData(Qt.UserRole, m)
            if logos:  # its logo, or a space: the names stay in line
                image = logos.get(m["merchant"].casefold()) if m["merchant"] else None
                items[self.COL_NAME].setIcon(logo_icon(image) if image else blank_icon())
            flag.setData(Qt.UserRole, m)
            if not none:
                items[self.COL_NAME].setToolTip(m["merchant"])  # whole, when the column cuts it
            for c, item in enumerate(items):
                if c == self.COL_FLAG:
                    self.table.setItem(r, c, item)
                    continue
                if c != self.COL_NAME:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if c == self.COL_TOTAL:
                        item.setForeground(spent_brush(m["total"]))  # spent red, money in green
                    elif not round(m[("count", "rules", "total")[c - self.COL_TX]] or 0, 2):
                        item.setForeground(_dim())  # 0: written, quietly
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

    def _filter(self, text=None):
        text = (self.find.text() if text is None else text).strip().casefold()
        only = self.btn_only_flagged.isChecked()
        flagged = self._flagged()
        for r in range(self.table.rowCount()):
            m = self.table.item(r, self.COL_NAME).data(Qt.UserRole)
            self.table.setRowHidden(r, (bool(text) and text not in self.table.item(r, self.COL_NAME).text().casefold())
                                    or (only and m["merchant"] not in flagged))
        self._update_totals()

    # ── 🚩 to look at again ───────────────────────────────────────────────────
    def _flagged(self):
        return set(get_settings().get(self.FLAG_KEY) or [])

    def _set_flagged(self, names):
        get_settings().set(self.FLAG_KEY, sorted(names, key=str.casefold))

    def _is_flagged(self):
        m = self._selected()
        return bool(m and m["merchant"] in self._flagged())

    def _flag_changed(self, item):
        if item.column() != self.COL_FLAG:
            return
        m = item.data(Qt.UserRole)
        if not m or not m["merchant"]:
            return
        names = self._flagged()
        (names.add if item.checkState() == Qt.Checked else names.discard)(m["merchant"])
        self._set_flagged(names)
        item._key = (0 if m["merchant"] in names else 1, m["merchant"].casefold())
        if self.btn_only_flagged.isChecked():
            self._filter()
        else:
            self._update_totals()

    def _toggle_flag(self):
        """Right-click: tick or untick the selected merchant."""
        r = self.table.currentRow()
        item = self.table.item(r, self.COL_FLAG) if r >= 0 else None
        if item is not None and item.flags() & Qt.ItemIsUserCheckable:
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _only_flagged_changed(self):
        self._filter()

    def _rename_flag(self, old, new):
        """A ticked merchant renamed (or merged) stays ticked under its new name."""
        names = self._flagged()
        if old in names:
            names.discard(old)
            names.add(new)
            self._set_flagged(names)

    def _update_totals(self):
        """The line under the merchants: how many are shown, and their numbers added up."""
        shown = [self.table.item(r, self.COL_NAME).data(Qt.UserRole) for r in range(self.table.rowCount())
                 if not self.table.isRowHidden(r)]
        named = sum(1 for m in shown if m["merchant"])
        sums = (sum(m["count"] for m in shown), sum(m["rules"] for m in shown),
                sum(m["total"] or 0 for m in shown))
        n_flagged = sum(1 for m in shown if m["merchant"] in self._flagged())
        texts = [str(n_flagged) if n_flagged else "", f"{named} merchant{'s' if named != 1 else ''}", str(sums[0]),
                 str(sums[1]), _money(sums[2])]
        bold = QFont(self.table.font())  # the list's font, as the style sheet made it
        bold.setBold(True)
        for c, text in enumerate(texts):
            item = QTableWidgetItem(text)
            item.setFont(bold)
            if c == self.COL_FLAG:
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip("Ticked 🚩, among those shown")
            elif c != self.COL_NAME:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if c == self.COL_TOTAL:
                item.setForeground(spent_brush(sums[2]))
            self.totals.setItem(0, c, item)
        header = self.table.horizontalHeader()
        needed = QFontMetrics(bold).horizontalAdvance(texts[self.COL_TOTAL]) + 28  # with the cell's padding
        widest = max(self.table.sizeHintForColumn(self.COL_TOTAL), header.sectionSizeHint(self.COL_TOTAL))
        header.setSectionResizeMode(self.COL_TOTAL, QHeaderView.Fixed)
        header.resizeSection(self.COL_TOTAL, int(max(needed, widest)))
        self._fit_width()

    NAME_MAX = 300
    """The widest the Merchant column gets; a longer name ends in "…" (its tooltip has it whole)."""

    def _fit_width(self):
        """The list as wide as its contents: the longest name (all merchants, not only those found,
        so looking for one does not change it; at most NAME_MAX) and the number columns. It
        changes with the merchants, never with the window."""
        header = self.table.horizontalHeader()
        fm = QFontMetrics(self.table.font())
        names = [self.table.item(r, self.COL_NAME).text() for r in range(self.table.rowCount())]
        widest = max((fm.horizontalAdvance(n) for n in names), default=0) + 28  # with the cell's padding
        if self.db.get_logos():
            widest += self.table.iconSize().width() + 6  # the logos before the names
        header.resizeSection(self.COL_NAME, int(min(max(widest, header.sectionSizeHint(self.COL_NAME), 140),
                                                    self.NAME_MAX)))
        columns = range(self.table.columnCount())
        for c in columns:
            self.totals.setColumnWidth(c, header.sectionSize(c))
        table_width = (sum(header.sectionSize(c) for c in columns) + self.table.verticalScrollBar().sizeHint().width()
                       + 2 * self.table.frameWidth())
        margins = self._left.layout().contentsMargins()
        self._left.setFixedWidth(max(table_width, 360) + margins.left() + margins.right())

    def _selected(self):
        r = self.table.currentRow()
        if r < 0 or not self.table.selectionModel().isRowSelected(r, self.table.rootIndex()):
            return None
        item = self.table.item(r, self.COL_NAME)
        return item.data(Qt.UserRole) if item else None

    def select(self, name):
        """Select a merchant ("" = the no-merchant line)."""
        for r in range(self.table.rowCount()):
            m = self.table.item(r, self.COL_NAME).data(Qt.UserRole)
            if m and m["merchant"] == name:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, self.COL_NAME))
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

    def _double_clicked(self, row, col):
        """On the name: Rename / Merge, as in Categories and Tags; on Tx or Total: its
        transactions in Transactions. The line of those with no merchant has no name to change."""
        m = self._selected()
        if col == self.COL_NAME and m and m["merchant"]:
            self.rename()
        elif col in (self.COL_NAME, self.COL_TX, self.COL_TOTAL):
            self.open_transactions()

    def open_transactions(self):
        m = self._need(real=False)
        if m and self.show_transactions:
            self.show_transactions(m["merchant"])

    def set_logo(self):
        """Right-click › Logo…: from the shop's website or a picture file (No Logo: none)."""
        m = self._need()
        if not m:
            return
        name = m["merchant"]
        dlg = LogoDialog(name, self.db.logo_for(name), self.db.logo_source(name), self)
        if not dlg.exec():
            return
        if dlg.image:
            self.db.set_logo(name, dlg.image, dlg.source)
        else:
            self.db.remove_logo(name)
        self.on_change()
        self.select(name)

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
        self._rename_flag(m["merchant"], name)
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
            self._set_flagged(self._flagged() - {m["merchant"]})
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
        if (m or {}).get("merchant") != getattr(self, "_used_of", None):
            self.used.blockSignals(True)
            self.used.clearSelection()  # another merchant: all its transactions
            self.used.blockSignals(False)
        same = (m or {}).get("merchant") == getattr(self, "_used_of", None)
        kept_rules = {r["id"] for r in self._selected_rules()} if same else set()  # after an edit: still those
        self._used_of = (m or {}).get("merchant")
        self._fill_used(m)
        self.rules.blockSignals(True)
        self.rules.setRowCount(0)
        self.rules.blockSignals(False)
        try:
            self._fill_rules(m, kept_rules)
        finally:
            self._update_lines()

    def _fill_rules(self, m, kept=()):
        none = m is not None and not m["merchant"]
        self.btn_set_merchant.setVisible(none)
        self.rules_count.setText("")
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
                                    "match, the one that matched the most text wins, then the one for fewer accounts.")
            rules = self.db.get_rules(m["merchant"])
        if none:  # rules with no merchant: only how many each one wins
            from collections import Counter
            counts = Counter(self.db.rule_winners().values())
        else:
            counts, summary = self.db.merchant_rule_counts(m["merchant"])
            self.rules_count.setText(self._count_text(summary))
        for rule in rules:
            r = self.rules.rowCount()
            self.rules.insertRow(r)
            n = counts.get(rule["id"], 0)
            tx = _number_item(n, align=Qt.AlignRight | Qt.AlignVCenter)
            tx.setData(Qt.UserRole, rule)
            self.rules.setItem(r, self.R_TX, tx)
            for c, text in enumerate((rule_text(rule), rule_sets(rule), rule["type"] or "—",
                                      accounts_label(rule["accounts"]))):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, rule)
                if c == self.R_TEXT:
                    item.setToolTip(text)
                elif c == self.R_ACCOUNT and len(rule["accounts"]) > 1:  # "2 accounts": which
                    item.setToolTip("\n".join(rule["accounts"]))
                self.rules.setItem(r, c, item)
        self.rules.setColumnHidden(self.R_TYPE, len({r["type"] for r in rules}) == 1)  # one type: says nothing
        self.rules.setColumnHidden(self.R_ACCOUNT, bool(rules) and not any(r["accounts"] for r in rules))  # all All
        if kept:
            self.rules.blockSignals(True)
            for r in range(self.rules.rowCount()):
                if self.rules.item(r, 0).data(Qt.UserRole)["id"] in kept:
                    self.rules.selectionModel().select(self.rules.model().index(r, 0),
                                                       QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.rules.blockSignals(False)

    @staticmethod
    def _count_text(c):
        """Its transactions and its rules, compared: which of them the rules give, which they do not."""
        if not c["total"] and not c["elsewhere"]:
            return ""
        parts = [f"{c['from_rules']} of its {c['total']} transaction{'s' if c['total'] != 1 else ''} come from "
                 "these rules"]
        if c["none"]:
            parts.append(f"{c['none']} from no rule (set by hand)")
        if c["other_rule"]:
            parts.append(f"{c['other_rule']} from another merchant's rule")
        if c["elsewhere"]:
            parts.append(f"{c['elsewhere']} more have another merchant now")
        return " · ".join(parts)

    def _rules_menu(self):
        items = [("＋  Add Rule…", self.add_rule, False), None, ("✏️  Edit Rule…", self.edit_rule, True)]
        if not self.btn_set_merchant.isHidden():
            items.append(("🏪  Set Merchant…", self.set_rules_merchant, True))
        return items + [None, ("🗑️  Delete Rules", self.delete_rules, True)]

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
