"""The transactions beside or under a list in Manage (Accounts, Categories, Merchants, Tags): the
Transactions table itself, without its filter bar, so it works exactly as there (right-click,
double-click, Delete, ⌘C…). Its columns are those Transactions shows."""

from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QPushButton, QVBoxLayout, QWidget

from daftarche.db import TRANSFER_LOAN
from daftarche.style import get_settings
from daftarche.tabs.transactions import COLUMN_KEYS, TransactionsTab, cell_text
from daftarche.widgets import money

SHOW_KEY = "manage_show_transactions"  # the "Show transactions" tick beside Manage's tabs


class _ManageTransactions(TransactionsTab):
    """The Transactions table, its filters set by Manage (``show``) instead of by its filter bar,
    which is hidden. Edits made in it are saved and reported as in Transactions."""

    _shown = None  # the filters of what Manage selected; None: nothing selected, so no rows
    _hidden = frozenset()  # columns that would show one value for every row

    def __init__(self, db, on_change, total=True):
        self._total = total  # one Total (Categories, Merchants, Tags) or Income / Expense / Net (Accounts)
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
        # columns sized by _fit_columns from every row's text: Qt's own ResizeToContents lays out
        # every cell, too slow for a click on a list
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.lbl_income.parentWidget().layout().setSpacing(14)  # the sums' line: it fits a narrow column

    def show(self, filters, hidden=()):
        """``filters``: lists of names, as Transactions' boxes hold them: type, account, category,
        subcategory, merchant ("" for none), tags; and ``ids``: only these transactions. None:
        nothing to show."""
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
                "search_fields": self._search_fields, "ids": f.get("ids")}

    def _update_review_button(self):
        self.btn_review.hide()  # Transactions' own: it sets the filters of the bar hidden here

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
        self._fit_columns()

    def _fit_columns(self):
        """Each shown column as wide as its widest text in any row (none cut with "…"): the text
        of every row is measured with the font, and only the widest cell is laid out as Qt does
        (its icon, margins)."""
        table, model = self.table, self.model
        header = table.horizontalHeader()
        measure = table.fontMetrics().horizontalAdvance
        rows = model._rows
        grid = 1 if table.showGrid() else 0
        for col in range(model.columnCount()):
            if table.isColumnHidden(col):
                continue
            widest, at, seen = -1, None, set()
            for i, row in enumerate(rows):
                text = cell_text(row, col)
                if text not in seen:
                    seen.add(text)
                    width = measure(text)
                    if width > widest:
                        widest, at = width, i
            width = header.sectionSizeHint(col)
            if at is not None:
                width = max(width, table.sizeHintForIndex(model.index(at, col)).width() + grid)
            header.resizeSection(col, width)

    def _update_summary(self):
        """``total``: one Total, as the lists of Manage count it: expenses minus income (money back
        counts against them), transfers left out; red when money was spent, green when more came
        in, plain at 0. Else as in Transactions, without the sums that say nothing here: those that
        are 0, and Net when it is only the income or only the expenses."""
        super()._update_summary()
        rows = self._current_rows
        if rows and all(r.get("transfer_status") == TRANSFER_LOAN for r in rows):
            self._loans_summary(rows)
            return
        for label in (self.lbl_income, self.lbl_expense, self.lbl_transfer, self.lbl_net):
            label.setToolTip("")  # what the loans' line set
        self.lbl_transfer.setStyleSheet("")
        if self._total:
            spent = round(sum(r.get("shown_amount", r["amount"]) * (1 if "Expense" in r["type"] else -1)
                              for r in rows if r["type"] and ("Expense" in r["type"] or "Income" in r["type"])), 2)
            counted = any(r["type"] and ("Expense" in r["type"] or "Income" in r["type"]) for r in rows)
            self.lbl_net.setText(f"Total: {money(spent)}")
            self.lbl_net.setToolTip("Spent minus income (money back counts against it); transfers left out")
            colour = get_settings().get("expense" if spent > 0 else "income") if spent else ""
            self.lbl_net.setStyleSheet(f"color: {colour};" if colour else "")
            self.lbl_net.setVisible(counted)
            self.lbl_income.hide()
            self.lbl_expense.hide()
            self.lbl_transfer.setVisible(not counted and bool(rows))
            return
        income = any(r["type"] and "Income" in r["type"] for r in rows)
        expense = any(r["type"] and "Expense" in r["type"] for r in rows)
        self.lbl_income.setVisible(income)
        self.lbl_expense.setVisible(expense)
        self.lbl_net.setVisible(income and expense)
        self.lbl_transfer.setVisible(any(r["type"] and "Transfer" in r["type"] for r in rows))

    def _loans_summary(self, rows):
        """Only loan rows: what went out and came in, and what the people shown owe now, as the
        Loans window counts it (their starting balances and what was marked settled too)."""
        out = round(sum(r["amount"] or 0 for r in rows if r["account_id"] and not r["to_account_id"]), 2)
        came = round(sum(r["amount"] or 0 for r in rows if r["to_account_id"] and not r["account_id"]), 2)
        people = {(r.get("merchant") or "").strip().casefold() for r in rows}
        balances = [e["balance"] for e in self.db.get_loans() if e["merchant"].casefold() in people]
        owed = round(sum(b for b in balances if b > 0), 2)
        owe = round(-sum(b for b in balances if b < 0), 2)
        s = get_settings()
        self.lbl_income.setText(f"Out: {money(out)}")
        self.lbl_income.setStyleSheet("")
        self.lbl_income.setVisible(bool(out))
        self.lbl_expense.setText(f"In: {money(came)}")
        self.lbl_expense.setStyleSheet("")
        self.lbl_expense.setVisible(bool(came))
        self.lbl_net.setText(f"They owe you: {money(owed)}")
        self.lbl_net.setStyleSheet(f"color: {s.get('income')};")
        self.lbl_net.setVisible(bool(owed))
        self.lbl_transfer.setText(f"You owe: {money(owe)}")
        self.lbl_transfer.setStyleSheet(f"color: {s.get('expense')};")
        self.lbl_transfer.setVisible(bool(owe))
        tip = ("As the Loans window counts it: money out − money in, with the starting balance and "
               "what was marked settled")
        for label in (self.lbl_net, self.lbl_transfer):
            label.setToolTip(tip)
        self.lbl_income.setToolTip("Money that left your accounts: lent, or a loan paid back")
        self.lbl_expense.setToolTip("Money that came in: borrowed, or paid back to you")
        if not owed and not owe and balances:
            self.lbl_net.setText("Settled")
            self.lbl_net.setStyleSheet("")
            self.lbl_net.setVisible(True)

    def _apply_column_visibility(self):
        super()._apply_column_visibility()
        for key in self._hidden:
            self.table.setColumnHidden(COLUMN_KEYS.index(key), True)


class TransactionList(QWidget):
    """A title (and Show All, for Categories) above the transactions Manage shows.
    ``on_change()``: after an edit made here (Manage refreshes, and the main window)."""

    def __init__(self, db, on_change, parent=None, total=True):
        super().__init__(parent)
        self._total = total
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
            self.tx = _ManageTransactions(self._db, self._on_change, total=self._total)
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
