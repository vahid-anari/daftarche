"""The Charts tab's detail panel: what is inside the category (or sub-category) under the mouse.

The Charts tab fills it (``show_rows``) as the mouse moves over its list and its chart; a click
on the chart, or the Pin button, keeps what it shows until unpinned (Pin again, or Esc).
Double-clicking a line asks for those transactions in the Transactions tab (``openRequested``).
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from daftarche.style import get_settings

HINT = "Hover a category to see what's inside; click the chart (or Pin) to keep it."


class DetailPanel(QFrame):
    openRequested = Signal(dict)
    """Filters for the Transactions tab (``types``, ``accounts``, ``categories``, ``subcategories``)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cat_panel")
        self.setFixedWidth(330)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.pinned = False
        self.key = None  # what is shown now (the tab's own key): no reload while it stays the same

        self.title = QLabel()
        self.title.setWordWrap(True)
        self.pin = QPushButton("Pin")
        self.pin.setCheckable(True)
        self.pin.setToolTip("Keep this here while the mouse moves on (Esc to let go)")
        self.pin.toggled.connect(self._pin_toggled)
        self.pin.setEnabled(False)
        head = QHBoxLayout()
        head.addWidget(self.title, 1)
        head.addWidget(self.pin, 0, Qt.AlignTop)

        self.hint = QLabel(HINT)
        self.hint.setWordWrap(True)
        self.hint.setProperty("class", "dim-label")

        self.table = QTableWidget(0, 3)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setWordWrap(True)  # a long name takes two lines instead of "PIZZA ..."
        self.table.setTextElideMode(Qt.ElideNone)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setStyleSheet("QTableWidget { background: transparent; border: none; }"
                                 "QTableWidget::item { padding: 2px 4px; }")
        self.table.cellDoubleClicked.connect(self._open_row)
        header.sectionResized.connect(lambda *_: self.table.resizeRowsToContents())  # wrapped names
        self.table.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addLayout(head)
        layout.addWidget(self.hint)
        layout.addWidget(self.table, 1)
        self.clear()

    # ── content ───────────────────────────────────────────────────────────────

    def clear(self):
        """Back to the hint (e.g. after the range or type changed)."""
        self.set_pinned(False)
        self.key = None
        self.title.setText("<b>Details</b>")
        self.table.setRowCount(0)
        self.table.hide()
        self.hint.show()
        self.pin.setEnabled(False)

    def show_rows(self, key, title, rows, filters=None):
        """``rows``: (first column, label, amount, filters for a double-click or None)."""
        if self.pinned:
            return
        self.key = key
        self.title.setText(title)
        s = get_settings()
        dim, text = QColor(s.get("text_dim") or "#888"), QColor(s.get("text"))
        self.table.setRowCount(0)
        for first, label, amount, row_filters in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = (QTableWidgetItem(first), QTableWidgetItem(label), QTableWidgetItem(f"${amount:,.2f}"))
            cells[0].setForeground(dim)
            cells[1].setForeground(text)
            cells[1].setToolTip(label)
            cells[2].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cells[0].setData(Qt.UserRole, row_filters or filters)
            for c, item in enumerate(cells):
                self.table.setItem(r, c, item)
        if not rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            none = QTableWidgetItem("Nothing in this period.")
            none.setForeground(dim)
            self.table.setItem(r, 1, none)
        self.hint.hide()
        self.table.show()
        self.table.resizeRowsToContents()
        QTimer.singleShot(0, self.table.resizeRowsToContents)  # again once the columns have their widths
        self.pin.setEnabled(True)

    # ── pinning ───────────────────────────────────────────────────────────────

    def set_pinned(self, pinned):
        pinned = bool(pinned) and self.key is not None
        if self.pin.isChecked() != pinned:
            self.pin.setChecked(pinned)  # calls _pin_toggled
        else:
            self._pin_toggled(pinned)

    def toggle_pinned(self):
        self.set_pinned(not self.pinned)

    def _pin_toggled(self, checked):
        self.pinned = bool(checked) and self.key is not None
        self.pin.setText("Pinned" if self.pinned else "Pin")
        f = self.pin.font()
        f.setWeight(QFont.Bold if self.pinned else QFont.Normal)
        self.pin.setFont(f)

    def _open_row(self, row, _column):
        item = self.table.item(row, 0)
        filters = item.data(Qt.UserRole) if item else None
        if filters:
            self.openRequested.emit(dict(filters))
