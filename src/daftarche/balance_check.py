"""View → Balance Check: the Dashboard's Total Balance built up again from the transactions, a
line at a time, each with where in Daftarche to compare it (the Merchants' Total, the Loans
window), then each account's own sums. If the two totals differ, something is in no balance."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from daftarche.db import CAT_INTERNAL_TRANSFER, CAT_LOANS
from daftarche.style import get_settings
from daftarche.widgets import money


def _colour(value):
    key = "income" if value > 0 else "expense" if value < 0 else "text_dim"
    return QBrush(QColor(get_settings().get(key) or "#999"))


def lines(b):
    """The steps from the transactions to the balance: [(what, amount or None, where to compare)].
    ``b``: db.balance_breakdown(). The amounts are what each adds to the balance."""
    out = [("Income − expenses, all of them", -b["spent"],
            f"Manage › Merchants, the line under the list (nothing searched): Total {money(b['merchants_total'])}")]
    if b["no_account"]:
        out.append(("…less income and expenses with no account", -b["no_account"], "in no account's balance"))
    if b["no_date"]:
        out.append(("…less income and expenses with no date", -b["no_date"], "in no month's balance"))
    for category, t in b["transfers"].items():
        loans = category == CAT_LOANS
        where = "the Loans window: Received / Paid Out" if loans else \
            "transfers with only one of your accounts (money from or to outside)"
        if category == CAT_INTERNAL_TRANSFER:
            where = "one side only: View › Unmatched Transfers… (their other side not found)"
        if t["in"]:
            out.append((f"Transfer › {category}: in", t["in"], where))
        if t["out"]:
            out.append((f"Transfer › {category}: out", -t["out"], where))
    if b["between"]:
        out.append(("Moved between your accounts", None, f"{money(b['between'])}: out of one, into another (adds 0)"))
    if b["undated_transfers"]:
        out.append((f"Transfers with no date ({b['undated_transfers']})", None, "in no balance"))
    return out


class BalanceCheckDialog(QDialog):
    COL_WHAT, COL_AMOUNT, COL_WHERE = range(3)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Balance Check")
        self.db = db
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        intro = QLabel("The Total Balance of the Dashboard, built up again from your transactions. Each line "
                       "says where in Daftarche to compare it.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.steps = self._table(["", "Adds", "Compare with"])
        layout.addWidget(self.steps, 3)
        self.verdict = QLabel()
        self.verdict.setWordWrap(True)
        layout.addWidget(self.verdict)
        head = QLabel("Each account")
        head.setProperty("class", "dim-label")
        layout.addWidget(head)
        self.accounts = self._table(["Account", "Income", "Expenses", "Transfers in", "Transfers out", "Balance"])
        layout.addWidget(self.accounts, 2)
        note = QLabel("An account's Balance is its income − expenses + transfers in − out, from its first "
                      "transaction (the starting money is an incoming transfer). Compare it with the bank.")
        note.setProperty("class", "dim-label")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        refresh = QPushButton("🔄  Refresh")
        refresh.setProperty("class", "secondary")
        refresh.clicked.connect(self.refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(refresh)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()
        self.resize(self.sizeHint().width(), 640)

    @staticmethod
    def _table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setAlternatingRowColors(True)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        t.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)  # the window as wide as its text
        return t

    @staticmethod
    def _amount(value, bold=False):
        item = QTableWidgetItem("" if value is None else money(value))
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if value is not None:
            item.setForeground(_colour(value))
        if bold:
            f = item.font()
            f.setBold(True)
            item.setFont(f)
        return item

    def _add(self, table, cells):
        r = table.rowCount()
        table.insertRow(r)
        for c, cell in enumerate(cells):
            table.setItem(r, c, cell if isinstance(cell, QTableWidgetItem) else QTableWidgetItem(cell))

    def refresh(self):
        b = self.db.balance_breakdown()
        self.breakdown = b
        self.steps.setRowCount(0)
        for what, amount, where in lines(b):
            self._add(self.steps, [what, self._amount(amount), where])
        total = QTableWidgetItem("= Balance of all accounts")
        f = total.font()
        f.setBold(True)
        total.setFont(f)
        self._add(self.steps, [total, self._amount(b["computed"], bold=True), ""])
        self._add(self.steps, ["Total Balance on the Dashboard", self._amount(b["balance"], bold=True),
                               "all accounts, also those hidden from the Dashboard"])
        diff = round(b["computed"] - b["balance"], 2)
        ok = abs(diff) < 0.005
        colour = get_settings().get("income" if ok else "expense")
        self.verdict.setText(f"<b style='color:{colour}'>✓ They agree.</b>" if ok else
                             f"<b style='color:{colour}'>✗ They differ by {money(diff)}.</b> Something is "
                             "counted in one and not the other: please report it.")
        self.accounts.setRowCount(0)
        for a in sorted(b["accounts"].values(), key=lambda a: a["name"].casefold()):
            self._add(self.accounts, [a["name"], self._amount(a["income"]), self._amount(-a["expense"]),
                                      self._amount(a["in"]), self._amount(-a["out"]), self._amount(a["balance"], True)])
