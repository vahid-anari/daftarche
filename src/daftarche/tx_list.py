"""The list of transactions under a list in Manage (Categories, Merchants): read-only, newest
first, sortable, a split transaction as its part there (✂). Double-click opens it in Transactions."""

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from daftarche.style import get_settings
from daftarche.widgets import amount_color_key, money

SHOW_KEY = "manage_show_transactions"  # the "Show transactions" tick, shared by the Manage tabs
SPLIT_MARK = "✂ "  # before the amount of a split transaction's part


def line_filters(line):
    """(text, filters) that show a line in Transactions: that day's transactions of its merchant
    there (so this one, mostly), for the window's show_matching."""
    where = f"{line['category']} › {line['subcategory']}" if line["subcategory"] else (line["category"] or "")
    who = html.escape(line["merchant"]) if line["merchant"] else "no merchant"
    return (f"<b>{who}</b> on {line['date']} in <b>{html.escape(where)}</b>",
            {"types": [line["type"]] if line["type"] else [],
             "categories": [line["category"]] if line["category"] else [],
             "subcategories": [line["subcategory"]] if line["subcategory"] else [],
             "merchants": [line["merchant"]], "from_day": line["date"], "to_day": line["date"]})


def net_spent(lines):
    """Expenses minus income (transfers left out), as the Merchants list adds them up."""
    return sum((line["amount"] or 0) * (1 if "Expense" in (line["type"] or "") else -1)
               for line in lines if "Expense" in (line["type"] or "") or "Income" in (line["type"] or ""))


class _SortItem(QTableWidgetItem):
    """Sorts by the value it was given (an amount as a number), not by its text."""

    def __init__(self, text, key):
        super().__init__(text)
        self._key = key

    def __lt__(self, other):
        if isinstance(other, _SortItem):
            return self._key < other._key
        return super().__lt__(other)


class TransactionList(QWidget):
    """``columns``: some of "date", "account", "merchant", "category", "subcategory", "amount".
    ``open_line(line)``: what a double-click does. Fill it with ``set_lines(lines, title)``."""

    COLUMN_TITLES = {"date": "Date", "account": "Account", "merchant": "Merchant", "category": "Category",
                     "subcategory": "Sub-Category", "amount": "Amount"}

    def __init__(self, columns=("date", "merchant", "subcategory", "amount"), open_line=None, parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.open_line = open_line
        self.lines = []
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

        self.table = QTableWidget(0, len(self.columns))
        self.table.setHorizontalHeaderLabels([self.COLUMN_TITLES[c] for c in self.columns])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)
        hint = QLabel("Double-click a transaction to open it in Transactions; "
                      + ("the bank's text shows" if "account" in self.columns else "the account and the bank's "
                         "text show") + " when you hold the pointer over it.")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def set_lines(self, lines, title, hide=(), total=None, total_label=""):
        """Show these lines (from db.get_lines), with ``title`` and their count and total above
        (``total``: another sum, e.g. net spent, named by ``total_label``); ``hide``: columns not
        needed now (the merchant, when they are all one merchant's)."""
        self.lines = list(lines)
        shown = [c for c in self.columns if c not in hide]
        wide = next((c for c in ("merchant", "account", "subcategory", "category") if c in shown), None)
        header = self.table.horizontalHeader()
        for col, c in enumerate(self.columns):
            self.table.setColumnHidden(col, c in hide)
            header.setSectionResizeMode(col, QHeaderView.Stretch if c == wide else QHeaderView.ResizeToContents)
        if total is None:
            total = sum(line["amount"] or 0 for line in self.lines)
        n = len(self.lines)
        self.title.setText(f"{title} — {n} transaction{'s' if n != 1 else ''}"
                           + (f" · {money(total)}{' ' + total_label if total_label else ''}" if n else ""))
        table = self.table
        table.setSortingEnabled(False)
        table.setRowCount(0)
        table.setRowCount(n)
        settings = get_settings()
        for row, line in enumerate(self.lines):
            tip = "\n".join(x for x in (line.get("account"), line.get("name"), line.get("memorandum"),
                                        line.get("note"), "Part of a split transaction" if line["part"] else None)
                             if x)
            color_key = amount_color_key(line.get("type"), line["amount"])
            for col, c in enumerate(self.columns):
                if c == "amount":
                    item = _SortItem((SPLIT_MARK if line["part"] else "") + money(line["amount"]), line["amount"] or 0)
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if color_key:
                        item.setForeground(QBrush(QColor(settings.get(color_key))))
                elif c == "date":
                    item = _SortItem(line["date"] or "", (line["date"] or "", line["id"], line["part"]))
                else:
                    text = line.get(c) or ("—" if c == "subcategory" else "")
                    item = _SortItem(text, text.casefold())
                item.setData(Qt.UserRole, row)
                if tip:
                    item.setToolTip(tip)
                table.setItem(row, col, item)
        table.setSortingEnabled(True)
        if "date" in self.columns:
            table.sortItems(self.columns.index("date"), Qt.DescendingOrder)

    def clear(self, title="Transactions"):
        self.set_lines([], title)
        self.title.setText(title)

    def _double_clicked(self, row, _col):
        item = self.table.item(row, 0)
        if item is not None and self.open_line:
            self.open_line(self.lines[item.data(Qt.UserRole)])
