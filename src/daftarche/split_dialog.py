"""Split a transaction: one bank row in parts, each with its own category, amount and note.

The parts must add up to the transaction's amount ("Left: $0.00" before OK). Charts and totals
then count each part in its own category. "Join Again" removes the split.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget, QFrame,
)

from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB, round2
from daftarche.style import get_settings
from daftarche.widgets import SingleSelectCombo, SymbolButton, add_subcategory_items, confirm_category, money


def _amount(text):
    try:
        return round2(float(text.replace(",", "").replace("$", "").strip()))
    except ValueError:
        return None


class SplitDialog(QDialog):
    """``parts``: the current ones [{category, subcategory, amount, note}] or none. After OK,
    ``result_parts`` is [(category_id, subcategory_id, amount, note)] (empty: join again)."""

    def __init__(self, db, type_name, total, parts=(), category=None, subcategory=None, about="", parent=None):
        super().__init__(parent)
        self.db = db
        self.type_name = type_name
        self.total = round2(total or 0)
        self.result_parts = None
        self._rows = []  # (category, sub, amount, note, remove)
        self._first_auto = True  # the first amount follows the others until typed in
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Split Transaction")
        self.setMinimumSize(760, 380)
        type_id = db.get_type_id(type_name) if type_name else None
        names = [c["name"] for c in (db.get_categories(type_id) if type_id else db.get_categories())]
        self._categories = [UNCATEGORIZED_CAT] + [n for n in names if n != UNCATEGORIZED_CAT]

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        top = QLabel(f"{about}<br>Split <b>{money(self.total)}</b> into parts, each in its own category."
                     if about else f"Split <b>{money(self.total)}</b> into parts, each in its own category.")
        top.setWordWrap(True)
        layout.addWidget(top)
        host = QWidget()
        outer = QVBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        self._grid = QGridLayout()
        outer.addLayout(self._grid)
        outer.addStretch(1)  # the parts stay at the top
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        for col, title in enumerate(("Category", "Sub-Category", "Amount", "Note")):
            head = QLabel(title)
            head.setProperty("class", "dim-label")
            self._grid.addWidget(head, 0, col)
        self._grid.setColumnStretch(0, 3)
        self._grid.setColumnStretch(1, 3)
        self._grid.setColumnStretch(3, 3)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(host)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        add = QPushButton("＋ Add Part")
        add.setProperty("class", "secondary")
        add.clicked.connect(lambda: self._add_row())
        self.left = QLabel()
        self.left.setStyleSheet("font-weight: bold;")
        row.addWidget(add)
        row.addStretch(1)
        row.addWidget(self.left)
        layout.addLayout(row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = btns.button(QDialogButtonBox.Ok)
        self.join = btns.addButton("Join Again", QDialogButtonBox.DestructiveRole)
        self.join.setToolTip("No more parts: the whole amount in one category again")
        self.join.setVisible(bool(parts))
        self.join.clicked.connect(self._join)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        if parts:
            self._first_auto = False
            for p in parts:
                self._add_row(p["category"], p["subcategory"], p["amount"], p.get("note") or "")
        else:  # start from the whole amount in its category, and an empty second part
            self._add_row(category, subcategory, self.total)
            self._add_row()
        self._update_left()

    # ── rows ──────────────────────────────────────────────────────────────────
    def _add_row(self, category=None, subcategory=None, amount=None, note=""):
        cat = SingleSelectCombo()
        cat.allow_typing()
        cat.addItems(self._categories)
        cat.setCurrentText(category or "")
        cat.lineEdit().setPlaceholderText(UNCATEGORIZED_CAT)
        sub = SingleSelectCombo()
        sub.allow_typing()
        self._fill_subs(cat, sub)
        if subcategory:
            sub.setCurrentText(subcategory)
        cat.currentTextChanged.connect(lambda _t, c=cat, s=sub: self._fill_subs(c, s))
        if amount is None:  # a new part takes what is left
            amount = self.total - self._sum() if self._rows else self.total
        amt = QLineEdit(f"{amount:.2f}" if amount else "")
        amt.setAlignment(Qt.AlignRight)
        amt.setPlaceholderText("0.00")
        amt.setMaximumWidth(130)
        amt.textEdited.connect(lambda _t, a=amt: self._amount_edited(a))
        note_edit = QLineEdit(note)
        note_edit.setPlaceholderText("What it was")
        remove = SymbolButton("close", size=28)
        remove.setToolTip("Remove this part")
        r = self._grid.rowCount()
        entry = (cat, sub, amt, note_edit, remove)
        remove.clicked.connect(lambda _=False, e=entry: self._remove_row(e))
        for col, w in enumerate(entry):
            self._grid.addWidget(w, r, col)
        self._rows.append(entry)
        self._update_left()

    def _fill_subs(self, cat, sub):
        name = cat.currentText().strip()
        found = self.db.get_category_by_name(name, type_name=self.type_name) if name else None
        sub.blockSignals(True)
        sub.clear()
        if found and found["name"] != UNCATEGORIZED_CAT:
            add_subcategory_items(sub, self.db, found["id"])
        else:
            sub.addItem(UNCATEGORIZED_SUB)
        sub.setCurrentIndex(0)
        sub.blockSignals(False)

    def _remove_row(self, entry):
        if len(self._rows) <= 1:
            return
        self._rows.remove(entry)
        for w in entry:
            self._grid.removeWidget(w)
            w.hide()
            w.deleteLater()
        if self._first_auto:
            self._amount_edited(None)  # the first part takes back what was removed
        self._update_left()

    def _sum(self, skip_first=False):
        rows = self._rows[1:] if skip_first else self._rows
        return round2(sum(_amount(r[2].text()) or 0 for r in rows))

    def _amount_edited(self, edited):
        if self._rows and edited is self._rows[0][2]:  # whichever part is first now
            self._first_auto = False
        elif self._first_auto and self._rows:  # the first part keeps the rest
            self._rows[0][2].setText(f"{self.total - self._sum(skip_first=True):.2f}")
        self._update_left()

    def _update_left(self):
        left = round2(self.total - self._sum())
        s = get_settings()
        texts = [r[2].text().strip() for r in self._rows]
        bad = any(t and _amount(t) is None for t in texts)
        empty = any(not _amount(t) for t in texts if not (t and _amount(t) is None))
        done = abs(left) < 0.005 and not bad
        self.left.setText("Not a number in Amount" if bad else f"Left: {money(left)}")
        self.left.setStyleSheet(f"font-weight: bold; color: {s.get('income') if done else s.get('expense')};")
        self.ok.setEnabled(done and not empty and len(self._rows) >= 2)
        self.ok.setToolTip("" if self.ok.isEnabled() else
                           "Every part needs an amount, and the parts must add up (Left: $0.00)")

    # ── OK ────────────────────────────────────────────────────────────────────
    def _join(self):
        self.result_parts = []
        self.accept()

    def _accept(self):
        parts = []
        for cat, sub, amt, note, _ in self._rows:
            amount = _amount(amt.text())
            if not amount:
                QMessageBox.warning(self, "Split", "Every part needs an amount (remove empty parts with ×).")
                return
            names = confirm_category(self, self.db, self.type_name, cat.currentText(), sub.currentText())
            if not names:
                return
            c = self.db.get_category_by_name(names[0], type_name=self.type_name)
            s = self.db.get_subcategory_by_name(names[1], c["id"])
            parts.append((c["id"], s["id"] if s else None, amount, note.text().strip() or None))
        self.result_parts = parts
        self.accept()
