from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QInputDialog,
    QColorDialog, QCheckBox, QFormLayout, QLineEdit,
    QDialogButtonBox, QFrame, QSizePolicy, QAbstractScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush, QPalette

from daftarche.style import get_settings
from daftarche.widgets import SingleSelectCombo


def _apply_selection_palette(widget):
    s = get_settings()
    hi = QColor(s.get("accent"))
    hi.setAlpha(90)
    pal = widget.palette()
    pal.setColor(QPalette.Highlight, hi)
    pal.setColor(QPalette.HighlightedText, QColor(s.get("text")))
    widget.setPalette(pal)


# ManageDialog
class ManageDialog(QDialog):
    def __init__(self, db, on_change_cb, parent=None):
        super().__init__(parent)
        self.db = db
        self.on_change_cb = on_change_cb
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
        self.cats_panel = CatsRulesPanel(self.db, self._changed)
        self.tags_panel = TagsPanel(self.db, self._changed)

        self.tabs.addTab(self.accounts_panel, "🏦  Accounts")
        self.tabs.addTab(self.cats_panel, "🏷️  Categories && Rules")
        self.tabs.addTab(self.tags_panel, "🔖  Tags")

        layout.addWidget(self.tabs)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 12)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.setProperty("class", "secondary")
        btn_refresh.setMinimumWidth(90)
        btn_refresh.clicked.connect(self.refresh)
        btn_row.addWidget(btn_refresh)

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
        self.tags_panel.refresh()

    def _changed(self):
        self.refresh()
        self.on_change_cb()


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

        self.f_name.setPlaceholderText("e.g. Vahid-CIBC-Checking")
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
    def __init__(self, db, on_change):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self._build()

    def _build(self):
        lists_row = QHBoxLayout(self)
        lists_row.setContentsMargins(10, 10, 10, 10)
        lists_row.setSpacing(4)

        self.type_table, type_col, type_w = self._make_table_col("Type", ["Name", "Tx", "Rules", "Cats"])
        self.type_table.itemSelectionChanged.connect(self._on_type_selected)
        self.type_table.cellDoubleClicked.connect(lambda r, c: self._rename_type())
        type_col.addLayout(self._make_btns([
            ("＋", self._add_type),
            ("✏️", self._rename_type),
            ("🗑️", self._delete_type),
        ]))
        lists_row.addWidget(type_w)
        lists_row.addWidget(self._vline())

        self.cat_table, cat_col, cat_w = self._make_table_col("Category", ["Name", "Tx", "Rules", "Subs"])
        self.cat_table.itemSelectionChanged.connect(self._on_cat_selected)
        self.cat_table.cellDoubleClicked.connect(lambda r, c: self._rename_cat())
        cat_col.addLayout(self._make_btns([
            ("＋", self._add_cat),
            ("✏️", self._rename_cat),
            ("🗑️", self._delete_cat),
        ]))
        lists_row.addWidget(cat_w)
        lists_row.addWidget(self._vline())

        self.sub_table, sub_col, sub_w = self._make_table_col("Sub-Category", ["Name", "Tx", "Rules"])
        self.sub_table.itemSelectionChanged.connect(self._on_sub_selected)
        self.sub_table.cellDoubleClicked.connect(lambda r, c: self._rename_sub())
        self.sub_table.setSelectionMode(QTableWidget.ExtendedSelection)
        sub_col.addLayout(self._make_btns([
            ("＋", self._add_sub),
            ("✏️", self._rename_sub),
            ("🔀", self._reparent_sub),
            ("🗑️", self._delete_sub),
        ]))
        lists_row.addWidget(sub_w)
        lists_row.addWidget(self._vline())

        self.map_table, map_col, map_w = self._make_table_col("Rules", ["Account", "Name", "Memo"])
        self.map_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.map_table.cellDoubleClicked.connect(lambda r, c: self._edit_map())
        map_col.addLayout(self._make_btns([
            ("＋", self._add_map),
            ("✏️", self._edit_map),
            ("🗑️", self._delete_map),
        ]))
        lists_row.addWidget(map_w, 1)

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

    def _make_btns(self, pairs):
        row = QHBoxLayout()
        row.setSpacing(6)
        for label, slot in pairs:
            btn = QPushButton(label)
            btn.setFixedHeight(34)
            btn.setFixedWidth(58)
            if "🗑" in label:
                btn.setProperty("class", "danger")
            elif "＋" not in label:
                btn.setProperty("class", "secondary")
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch()
        return row

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
            maps = self.db.get_rule_count_for_type(t["id"])
            cats = self.db.get_category_count_for_type(t["id"])

            row = self.type_table.rowCount()
            self.type_table.insertRow(row)
            for col, val in enumerate([t["name"], str(tx), str(maps), str(cats)]):
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
            maps = self.db.get_rule_count_for_category(c["id"])
            subs = self.db.get_subcategory_count_for_category(c["id"])

            row = self.cat_table.rowCount()
            self.cat_table.insertRow(row)
            for col, val in enumerate([c["name"], str(tx), str(maps), str(subs)]):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, c)
                if col > 0:
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

        subs = self.db.get_subcategories(cat_id) if cat_id else []

        for s in subs:
            tx = self.db.get_transaction_count_for_subcategory(s["id"])
            maps = self.db.get_rule_count_for_subcategory(s["id"])

            row = self.sub_table.rowCount()
            self.sub_table.insertRow(row)
            for col, val in enumerate([s["name"], str(tx), str(maps)]):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, s)
                if col > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.sub_table.setItem(row, col, item)

        self.sub_table.blockSignals(False)
        self._restore_selection(self.sub_table, sel_sub, key="id")
        self._on_sub_selected()

    def _reload_maps(self, type_id=None, cat_id=None, sub_id=None):
        self.map_table.setRowCount(0)
        if sub_id is None:
            return

        for row_idx, m in enumerate(self.db.get_rules_for_subcategory(sub_id)):
            self.map_table.insertRow(row_idx)
            for col_idx, val in enumerate([
                m["account_name"] or "All",
                m["name"] or "—",
                m["memorandum"] or "—",
            ]):
                item = QTableWidgetItem(val)
                item.setData(Qt.UserRole, dict(m))
                self.map_table.setItem(row_idx, col_idx, item)

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
        type_data = self._selected_data(self.type_table)
        cat_data = self._selected_data(self.cat_table)
        sub_data = self._selected_data(self.sub_table)
        self._reload_maps(
            type_id=type_data["id"] if type_data else None,
            cat_id=cat_data["id"] if cat_data else None,
            sub_id=sub_data["id"] if sub_data else None,
        )

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _selected_data(self, tbl):
        row = tbl.currentRow()
        if row < 0:
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

    def _selected_map_data(self):
        row = self.map_table.currentRow()
        if row < 0:
            return None
        item = self.map_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _restore_selection(self, tbl, sel, key="id"):
        if sel:
            for i in range(tbl.rowCount()):
                item = tbl.item(i, 0)
                if item:
                    d = item.data(Qt.UserRole)
                    if d and d[key] == sel[key]:
                        tbl.setCurrentCell(i, 0)
                        return
        if tbl.rowCount() > 0:
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
            self.db.rename_type(data["name"], new.strip())
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
            self.db.delete_type(data["name"])
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
        data = self._selected_data(self.cat_table)
        if not data:
            QMessageBox.information(self, "Select", "Select a category first.")
            return
        new, ok = QInputDialog.getText(self, "Rename Category", "New name:", text=data["name"])
        if ok and new.strip() and new.strip() != data["name"]:
            self.db.rename_category(data["name"], new.strip())
            self.on_change()

    def _delete_cat(self):
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
            cat = self.db.get_category_by_name(new_cat)
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

    # ── Rules actions ─────────────────────────────────────────────────────────

    def _get_context(self):
        return (
            self._selected_data(self.type_table),
            self._selected_data(self.cat_table),
            self._selected_data(self.sub_table),
        )

    def _add_map(self):
        type_data, cat_data, sub_data = self._get_context()
        if not sub_data:
            QMessageBox.information(self, "Select", "Select a sub-category first.")
            return
        dlg = RuleEditDialog(self.db, type_data, cat_data, sub_data, parent=self)
        if dlg.exec():
            acc_name, name, memo = dlg.get_values()
            try:
                self.db.save_mapping(
                    type_name=type_data["name"] if type_data else None,
                    account_name=acc_name,
                    name=name or None,
                    memorandum=memo or None,
                    subcategory_id=sub_data["id"],
                    category_id=cat_data["id"] if cat_data else None,
                )
                self.on_change()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _edit_map(self):
        type_data, cat_data, sub_data = self._get_context()
        map_data = self._selected_map_data()
        if not map_data:
            QMessageBox.information(self, "Select", "Select a rule first.")
            return
        dlg = RuleEditDialog(self.db, type_data, cat_data, sub_data, existing=map_data, parent=self)
        if not dlg.exec():
            return
        acc_name, name, memo = dlg.get_values()
        try:
            self.db.delete_rule_and_save(
                rule_id=map_data["id"],
                type_name=type_data["name"] if type_data else None,
                account_name=acc_name,
                name=name or None,
                memorandum=memo or None,
                subcategory_id=sub_data["id"],
                category_id=cat_data["id"] if cat_data else None,
            )
            self.on_change()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _delete_map(self):
        rows = list(set(i.row() for i in self.map_table.selectedItems()))
        if not rows:
            QMessageBox.information(self, "Select", "Select a rule first.")
            return
        msg = f"Delete {len(rows)} rule{'s' if len(rows) > 1 else ''}?"
        if QMessageBox.question(self, "Delete", msg, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for row in rows:
                item = self.map_table.item(row, 0)
                if item:
                    map_data = item.data(Qt.UserRole)
                    self.db.delete_rule(map_data["id"])
            self.on_change()


# RuleEditDialog
class RuleEditDialog(QDialog):
    def __init__(self, db, type_data, cat_data, sub_data, existing=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.existing = existing

        self.setWindowTitle("Edit Rule" if existing else "Add Rule")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        if type_data and cat_data and sub_data:
            ctx = QLabel(f"{type_data['name']}  →  {cat_data['name']}  →  {sub_data['name']}")
            ctx.setProperty("class", "dim-label")
            layout.addWidget(ctx)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(10)

        self.combo_account = SingleSelectCombo()
        self.combo_account.addItem("All")
        for a in db.get_accounts(active_only=True):
            self.combo_account.addItem(a["name"])
        if existing and existing["account_name"]:
            idx = self.combo_account.findText(existing["account_name"])
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)
        else:
            self.combo_account.setCurrentIndex(0)
        form.addRow("Account:", self.combo_account)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Transaction name (optional)")
        if existing:
            self.edit_name.setText(existing["name"] or "")
        form.addRow("Name:", self.edit_name)

        hint_name = QLabel("Use | to require multiple terms  (e.g. amazon|ca)")
        hint_name.setProperty("class", "dim-label")
        form.addRow("", hint_name)

        self.edit_memo = QLineEdit()
        self.edit_memo.setPlaceholderText("Memo (optional)")
        if existing:
            self.edit_memo.setText(existing["memorandum"] or "")
        form.addRow("Memo:", self.edit_memo)

        hint_memo = QLabel("Use | to require multiple terms  (e.g. ref|invoice)")
        hint_memo.setProperty("class", "dim-label")
        form.addRow("", hint_memo)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _validate(self):
        name = self.edit_name.text().strip()
        memo = self.edit_memo.text().strip()
        if not name and not memo:
            QMessageBox.warning(self, "Required", "Enter at least a Name or Memo.")
            return
        self.accept()

    def get_values(self):
        acc = self.combo_account.currentText()
        return (
            acc if acc != "All" else None,
            self.edit_name.text().strip() or None,
            self.edit_memo.text().strip() or None,
        )


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
