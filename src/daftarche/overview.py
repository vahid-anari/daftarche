"""View → Uncategorized… and View → Unmatched Transfers…: what still needs attention, all time.

Both are a short summary over a tree; double-clicking a line asks the window to show those
transactions (``show_transactions`` gets type, account, category and sub-category filters).
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout,
)

from daftarche.db import SUB_UNMATCHED, UNCATEGORIZED_CAT, UNCATEGORIZED_SUB, round2

ShowTransactions = Callable[..., None]


def _money(value):
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def _summary(parts):
    """'<b>Expense</b> 5 · $192.40     <b>Income</b> …' (spaces kept in rich text)."""
    return "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;".join(f"<b>{name}</b>&nbsp; {c} · {_money(t)}" for name, (c, t) in parts)


class _OverviewDialog(QDialog):
    """Summary line, a tree (label, count, total), a close button; filters behind every line."""

    def __init__(self, title, show_transactions: ShowTransactions, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 440)
        self._show_transactions = show_transactions
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["", "Count", "Total"])
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(80)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self._open)
        self.hint = QLabel("Double-click a line to see its transactions.")
        self.hint.setProperty("class", "dim")
        self.buttons = QHBoxLayout()
        self.buttons.addWidget(self.hint, 1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        self.buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.tree, 1)
        layout.addLayout(self.buttons)

    def _line(self, parent, label, count, total, filters):
        item = QTreeWidgetItem(parent, [label, str(count), _money(total)])
        for col in (1, 2):
            item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
        item.setData(0, Qt.UserRole, filters)
        return item

    def _open(self, item, _column=0):
        filters = item.data(0, Qt.UserRole)
        if filters:
            self.accept()
            self._show_transactions(**filters)


class UncategorizedDialog(_OverviewDialog):
    """Income/expense rows without a category, or with a category but no sub-category."""

    def __init__(self, db, show_transactions: ShowTransactions, parent=None):
        super().__init__("Uncategorized", show_transactions, parent)
        self.db = db
        self.refresh()

    def refresh(self):
        self.tree.clear()
        rows = self.db.get_uncategorized_overview()
        totals = {"Expense": (0, 0.0), "Income": (0, 0.0)}
        for kind in ("Expense", "Income"):  # tree: expenses (most of the work) first
            mine = [r for r in rows if r["kind"] == kind]
            count = sum(r["count"] for r in mine)
            totals[kind] = (count, round2(sum(r["total"] for r in mine)))
            if not mine:
                continue
            top = self._line(self.tree, kind, *totals[kind], {"types": sorted({r["type"] for r in mine})})
            for r in mine:
                fully = r["category"] == UNCATEGORIZED_CAT
                label = UNCATEGORIZED_CAT if fully else f"{r['category']} › {UNCATEGORIZED_SUB}"
                filters = {"types": [r["type"]], "categories": [r["category"]]}
                if not fully:
                    filters["subcategories"] = [UNCATEGORIZED_SUB]
                self._line(top, label, r["count"], r["total"], filters)
            top.setExpanded(True)
        if not rows:
            self.summary.setText("Every income and expense transaction has a category and a sub-category.")
        else:
            self.summary.setText(_summary(totals.items()))


class UnmatchedTransfersDialog(_OverviewDialog):
    """Transfers whose other side has not been found, per account; Match Transfers runs here too."""

    def __init__(self, db, show_transactions: ShowTransactions, on_change: Callable[[], None] = lambda: None,
                 parent=None):
        super().__init__("Unmatched Transfers", show_transactions, parent)
        self.db = db
        self._on_change = on_change
        match = QPushButton("Match Transfers")
        match.clicked.connect(self._match)
        self.buttons.insertWidget(1, match)
        self.refresh()

    def refresh(self):
        self.tree.clear()
        rows = self.db.get_unmatched_transfer_overview()
        directions = {}
        for r in rows:
            c, t = directions.get(r["direction"], (0, 0.0))
            directions[r["direction"]] = (c + r["count"], round2(t + r["total"]))
        for account in dict.fromkeys(r["account"] for r in rows):
            mine = [r for r in rows if r["account"] == account]
            types = sorted({r["type"] for r in mine})
            top = self._line(self.tree, account or "(no account)", sum(r["count"] for r in mine),
                             round2(sum(r["total"] for r in mine)),
                             {"types": types, "accounts": [account], "subcategories": [SUB_UNMATCHED]})
            for r in mine:
                self._line(top, f"{r['direction']} · {r['category'] or 'no category'}", r["count"], r["total"],
                           {"types": [r["type"]], "accounts": [account], "categories": [r["category"]],
                            "subcategories": [SUB_UNMATCHED]})
            top.setExpanded(True)
        if not rows:
            self.summary.setText("Every transfer has found its other side.")
        else:
            self.summary.setText(_summary(sorted(directions.items(), reverse=True)))

    def _match(self):
        matched = self.db.match_unmatched_transfers()
        self._on_change()
        self.refresh()
        self.hint.setText(f"Matched {matched} transfer{'s' if matched != 1 else ''}.")
