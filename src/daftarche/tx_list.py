"""The transactions beside or under a list in Manage (Accounts, Categories, Merchants, Tags): the
Transactions table itself, without its filter bar, so it works exactly as there (right-click,
double-click, Delete, ⌘C…). Its columns are those Transactions shows."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from daftarche.tabs.transactions import COLUMN_KEYS, TransactionsTab

SHOW_KEY = "manage_show_transactions"  # the "Show transactions" tick beside Manage's tabs


class _ManageTransactions(TransactionsTab):
    """The Transactions table, its filters set by Manage (``show``) instead of by its filter bar,
    which is hidden. Edits made in it are saved and reported as in Transactions."""

    _shown = None  # the filters of what Manage selected; None: nothing selected, so no rows
    _hidden = frozenset()  # columns that would show one value for every row

    def __init__(self, db, on_change):
        super().__init__(db, on_change)
        layout = self.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        for i in range(layout.count()):  # the toolbar, period and filter rows
            row = layout.itemAt(i).layout()
            if row is not None:
                for j in range(row.count()):
                    if row.itemAt(j).widget() is not None:
                        row.itemAt(j).widget().hide()
        self.nav_bar.hide()
        self._period._select_preset(0, emit=False, persist=False)  # all dates; Transactions' own stays
        # columns as wide as the first rows' text, not all of them: a click on a list stays quick
        self.table.horizontalHeader().setResizeContentsPrecision(60)
        self.lbl_income.parentWidget().layout().setSpacing(14)  # the sums' line: it fits a narrow column

    def show(self, filters, hidden=()):
        """``filters``: lists of names, as Transactions' boxes hold them: type, account, category,
        subcategory, merchant ("" for none), tags. None: nothing to show."""
        self._shown = filters
        self._hidden = frozenset(hidden)
        self._apply_column_visibility()
        self._apply_filters()

    # ── Transactions' own machinery, fed by Manage ────────────────────────────
    def _get_filters(self):
        f = self._shown or {}
        return {"from_day": None, "to_day": None, "type": f.get("type", []), "account": f.get("account", []),
                "category": f.get("category", []), "subcategory": f.get("subcategory", []),
                "merchant": f.get("merchant", []), "tags": f.get("tags", []), "search": "",
                "search_fields": self._search_fields, "ids": None}

    def refresh(self):
        self._apply_filters()

    def _apply_filters(self):
        if self._shown is None:
            self._current_rows = []
            self.model.set_rows([])
            self._update_rows_info()
            self._update_summary()
            return
        super()._apply_filters()

    def _update_summary(self):
        """As in Transactions, without the sums that say nothing here: those that are 0, and Net
        when it is only the income or only the expenses."""
        super()._update_summary()
        rows = self._current_rows
        income = any(r["type"] and "Income" in r["type"] for r in rows)
        expense = any(r["type"] and "Expense" in r["type"] for r in rows)
        self.lbl_income.setVisible(income)
        self.lbl_expense.setVisible(expense)
        self.lbl_net.setVisible(income and expense)
        self.lbl_transfer.setVisible(any(r["type"] and "Transfer" in r["type"] for r in rows))

    def _apply_column_visibility(self):
        super()._apply_column_visibility()
        for key in self._hidden:
            self.table.setColumnHidden(COLUMN_KEYS.index(key), True)


class TransactionList(QWidget):
    """A title (and Show All, for Categories) above the transactions Manage shows.
    ``on_change()``: after an edit made here (Manage refreshes, and the main window)."""

    def __init__(self, db, on_change, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel("Transactions")
        self.title.setProperty("class", "dim-label")
        self.title.setWordWrap(True)
        head.addWidget(self.title, 1)
        self.btn_all = QPushButton("Show All")
        self.btn_all.setProperty("class", "secondary")
        self.btn_all.setToolTip("Every merchant again")
        self.btn_all.hide()
        head.addWidget(self.btn_all)
        layout.addLayout(head)
        self._db, self._on_change = db, on_change
        self.tx = None  # made the first time transactions are shown: Manage opens quickly
        hint = QLabel("Works as in Transactions: right-click a row (or several) to edit, split or tag them, "
                      "double-click a cell to change it. The columns are those Transactions shows.")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _table(self):
        if self.tx is None:
            self.tx = _ManageTransactions(self._db, self._on_change)
            self.layout().insertWidget(1, self.tx, 1)
        return self.tx

    @property
    def table(self):
        return self._table().table

    def show_transactions(self, title, filters, hidden=()):
        """Show the transactions matching ``filters`` (see _ManageTransactions.show)."""
        self.title.setText(title)
        self._table().show(filters, hidden)

    def clear(self, title="Transactions"):
        self.title.setText(title)
        if self.tx is not None:
            self.tx.show(None)
