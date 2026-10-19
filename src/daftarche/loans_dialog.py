"""View → Loans: money lent to and borrowed from people (Transfer › Loans), one line per person."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from daftarche.db import CAT_LOANS
from daftarche.tabs.manage import _NumberItem, _apply_selection_palette
from daftarche.widgets import SingleSelectCombo, money

NO_PERSON = "(no person)"


def balance_text(balance):
    if not balance:
        return "Settled"
    return f"Owes you {money(balance)}" if balance > 0 else f"You owe {money(-balance)}"


class LoansDialog(QDialog):
    COL_NAME, COL_BAL, COL_OUT, COL_IN, COL_OPEN, COL_LAST = range(6)

    def __init__(self, db, on_change, show_transactions=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.on_change = on_change
        self.show_transactions = show_transactions  # (person) → their loan rows in the main window
        self.setWindowTitle("Loans")
        self.setMinimumSize(1040, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        self.summary = QLabel()
        layout.addWidget(self.summary)

        middle = QVBoxLayout()
        middle.setSpacing(8)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Person", "Balance", "Paid Out", "Received", "Starting", "Last"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(self.COL_NAME, Qt.AscendingOrder)
        self.table.cellDoubleClicked.connect(self._double_clicked)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        _apply_selection_palette(self.table)
        middle.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.btn_open = QPushButton("💵  Starting Balance…")
        self.btn_open.setToolTip("What was owed before your records start")
        self.btn_open.clicked.connect(self.set_opening)
        self.btn_settle = QPushButton("✅  Mark Settled")
        self.btn_settle.clicked.connect(self.toggle_settled)
        self.btn_tx = QPushButton("📋  Transactions")
        self.btn_tx.clicked.connect(self.open_transactions)
        for btn in (self.btn_open, self.btn_settle, self.btn_tx):
            btn.setProperty("class", "secondary")
            buttons.addWidget(btn)
        buttons.addStretch()
        middle.addLayout(buttons)
        layout.addLayout(middle, 1)

        hint = QLabel(f"Paid Out: money that left your accounts (you lent it, or paid a loan back). Received: "
                      f"money that came in. Loan rows are Transfer › {CAT_LOANS}, with the person as merchant: "
                      "right-click income or expense rows in Transactions → Make It a Loan. Mark Settled "
                      "writes off what is left (no transaction is made).")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        bottom = QHBoxLayout()
        refresh = QPushButton("🔄 Refresh")
        refresh.setProperty("class", "secondary")
        refresh.clicked.connect(self.refresh)
        close = QPushButton("Close")
        close.setProperty("class", "secondary")
        close.clicked.connect(self.accept)
        bottom.addWidget(refresh)
        bottom.addStretch()
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.refresh()

    # ── table ────────────────────────────────────────────────────────────────
    def refresh(self):
        selected = self._selected()
        you_owe, owed = self.db.get_loan_totals()
        self.summary.setText(f"<b>You owe {money(you_owe)}</b>   ·   <b>Owed to you {money(owed)}</b>")
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for e in self.db.get_loans():
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = QTableWidgetItem(e["merchant"] or NO_PERSON)
            name.setData(Qt.UserRole, e)
            if e["note"]:
                name.setToolTip(e["note"])
            bal = _NumberItem(e["balance"])
            bal.setText(balance_text(e["balance"]))
            if e["written_off"]:
                off = e["written_off"]
                note = f"{money(abs(off))} {'they owed' if off > 0 else 'you owed'} was written off"
                bal.setText(f"Settled (wrote off {money(abs(off))})" if not e["balance"] else bal.text())
                bal.setToolTip(note)
            opening = _NumberItem(e["opening"])
            opening.setText(balance_text(e["opening"]).replace("Settled", "—"))
            items = [name, bal, _NumberItem(e["paid_out"], money=True), _NumberItem(e["received"], money=True),
                     opening, QTableWidgetItem(e["last"] or "—")]
            for c, item in enumerate(items):
                if c in (self.COL_OUT, self.COL_IN):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        if selected:
            self._select(selected["merchant"])
        self._update_buttons()

    def _selected(self):
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _select(self, merchant):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.UserRole)["merchant"] == merchant:
                self.table.selectRow(r)
                return

    def _update_buttons(self):
        e = self._selected()
        person = bool(e and e["merchant"])
        self.btn_open.setEnabled(person)
        self.btn_settle.setEnabled(person and bool(e["balance"] or e["written_off"]))
        self.btn_settle.setText("↩️  Undo Settled" if person and e["written_off"] and not e["balance"]
                                else "✅  Mark Settled")
        self.btn_tx.setEnabled(e is not None)

    def _double_clicked(self, row, col):
        self.table.selectRow(row)
        if col == self.COL_OPEN and self._selected()["merchant"]:
            self.set_opening()
        else:
            self.open_transactions()

    # ── actions ──────────────────────────────────────────────────────────────
    def open_transactions(self):
        e = self._selected()
        if e is not None and self.show_transactions:
            self.show_transactions(e["merchant"])

    def set_opening(self):
        e = self._selected()
        if not e or not e["merchant"]:
            return
        dlg = StartingBalanceDialog(e, self)
        if dlg.exec():
            self.db.set_loan_opening(e["merchant"], dlg.value, dlg.note or None)
            self._changed(e["merchant"])

    def toggle_settled(self):
        e = self._selected()
        if not e or not e["merchant"]:
            return
        if e["written_off"] and not e["balance"]:
            self.db.unsettle_loan(e["merchant"])
        else:
            if QMessageBox.question(
                    self, "Mark Settled",
                    f"{e['merchant']}: {balance_text(e['balance'])}.\n\nMark it settled? What is left is written "
                    "off; no transaction is made. Undo Settled brings it back.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.db.settle_loan(e["merchant"])
        self._changed(e["merchant"])

    def _changed(self, merchant):
        self.refresh()
        self._select(merchant)
        if self.on_change:
            self.on_change()


class StartingBalanceDialog(QDialog):
    """What was owed before your records start: who owed whom, and how much."""

    THEY_OWED, I_OWED = "They owed me", "I owed them"

    def __init__(self, loan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Starting Balance")
        self.setMinimumWidth(420)
        self.value, self.note = 0.0, ""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Before your records, with <b>{loan['merchant']}</b>:"))
        form = QFormLayout()
        self.f_who = SingleSelectCombo()
        self.f_who.addItems([self.I_OWED, self.THEY_OWED])
        self.f_who.setCurrentIndex(1 if loan["opening"] > 0 else 0)
        self.f_amount = QLineEdit(f"{abs(loan['opening']):.2f}" if loan["opening"] else "")
        self.f_amount.setPlaceholderText("0.00")
        self.f_note = QLineEdit(loan["note"] or "")
        self.f_note.setPlaceholderText("e.g. lent me $939.22 in 2016")
        form.addRow("Who:", self.f_who)
        form.addRow("Amount:", self.f_amount)
        form.addRow("Note:", self.f_note)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _ok(self):
        text = self.f_amount.text().replace("$", "").replace(",", "").strip() or "0"
        try:
            amount = abs(float(text))
        except ValueError:
            QMessageBox.warning(self, "Starting Balance", "Write the amount as a number, e.g. 939.22.")
            return
        self.value = amount if self.f_who.currentText() == self.THEY_OWED else -amount
        self.note = self.f_note.text().strip()
        self.accept()
