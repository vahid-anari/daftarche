import calendar
from datetime import date as _date, timedelta as _td

from PySide6.QtWidgets import (
    QToolButton, QListWidget, QListWidgetItem, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
    QApplication, QSizePolicy, QLabel, QGridLayout,
    QLineEdit, QComboBox, QStyledItemDelegate, QTableView, QMessageBox, QCompleter, QLayout,
    QDialog, QStackedWidget, QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QPoint, QDate, QObject, QEvent, QTimer, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QPolygon, QPen
from daftarche.style import get_settings, build_stylesheet, popup_list_stylesheet
from daftarche.db import MONTHS_ORDER, MONTH_NUM, UNCATEGORIZED_CAT, UNCATEGORIZED_SUB

# Global date range bounds — pickers never go outside this window
PICKER_MIN_YEAR, PICKER_MIN_MONTH = 2023, "August"
PICKER_MAX_YEAR, PICKER_MAX_MONTH = 2035, "December"
PICKER_MIN_DAY, PICKER_MAX_DAY = 1, 31


# Helpers
def _repolish(widget):
    """Force Qt to re-evaluate QSS property selectors after setProperty()."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _show_popup(btn, popup):
    """Position and show a popup below (or above if no room) btn."""
    popup.adjustSize()
    pos = btn.mapToGlobal(QPoint(0, btn.height()))
    screen = QApplication.primaryScreen().availableGeometry()
    ph = popup.sizeHint().height()
    if pos.y() + ph > screen.bottom():
        pos = btn.mapToGlobal(QPoint(0, -ph))
    popup.move(pos)
    popup.show()
    popup.raise_()


def _setup_combo_editing(combo):
    """
    Make combo behave as a read-only styled dropdown (macOS-safe).
    Sets editable mode so the painted ▼ triangle stays visible, but
    locks the line edit so the user can't type. All visual styling
    is handled by the QComboBox[class="single-combo"] QSS rule.
    """
    if combo.isEditable():
        return
    combo.setEditable(True)
    le = combo.lineEdit()
    le.setReadOnly(True)
    le.setTextMargins(0, 0, 0, 0)
    le.setStyleSheet(
        "QLineEdit { selection-background-color: transparent; "
        "selection-color: inherit; padding: 0; margin: 0; }")

    def _deselect():
        le.blockSignals(True)
        le.deselect()
        le.blockSignals(False)

    le.selectionChanged.connect(_deselect)
    combo._deselect = _deselect

    class _ClickFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.MouseButtonRelease:
                combo.showPopup()
                return True
            return False

    combo._click_filter = _ClickFilter(combo)
    le.installEventFilter(combo._click_filter)
    combo.installEventFilter(combo._click_filter)


def fit_combo_column(table, col, combo, padding=100):
    """Set column width to fit the widest combo item text."""
    fm = combo.fontMetrics()
    max_w = 0
    for i in range(combo.count()):
        w = fm.horizontalAdvance(combo.itemText(i))
        max_w = max(max_w, w)
    table.setColumnWidth(col, max_w + padding)



def plain_label(text):
    """A name for a checkbox or button label: Qt reads "&" there as a shortcut marker
    ("Food & Drink" showed as "Food _Drink"), so it is doubled to show as itself."""
    return (text or "").replace("&", "&&")


def money(value, decimals=2):
    """$1,234.50, or -$30.00 for money back (a refund is a negative expense)."""
    if value is None:
        return ""
    return f"-${-value:,.{decimals}f}" if round(value, decimals) < 0 else f"${abs(value):,.{decimals}f}"


def amount_color_key(type_name, amount):
    """The theme colour for an amount: income green and expense red, the other way round when
    the money went back (a refund shows green, money returned from an income red)."""
    type_name = type_name or ""
    back = (amount or 0) < 0
    if "Income" in type_name:
        return "expense" if back else "income"
    if "Expense" in type_name:
        return "income" if back else "expense"
    if "Transfer" in type_name:
        return "transfer"
    return None


def add_subcategory_items(combo, db, category_id):
    """A category's sub-categories into ``combo``, with "Uncategorized" first: picking only the
    category is enough, and the sub-category can be set later."""
    from daftarche.icons import blank_icon, emoji_icon, list_icons
    names = [s["name"] for s in db.get_subcategories(category_id)]
    combo.addItem(UNCATEGORIZED_SUB)
    combo.addItems([n for n in names if n != UNCATEGORIZED_SUB])
    icons = {n: icon for (cid, n), icon in db.get_icons()["sub_name"].items() if cid == category_id}
    # its own icon; a space for one without (in line with those that have one)
    list_icons(combo, lambda n: (emoji_icon(icons[n]) if n in icons else blank_icon()) if icons else None)


def _same_name(names, typed):
    """The existing name written differently ("pets" for "Pets"), else ``typed``."""
    return next((n for n in names if n.casefold() == typed.casefold()), typed)


def confirm_category(parent, db, type_name, cat_name, sub_name):
    """Check a typed category and sub-category; a new one is added after asking.

    Returns ``(category, sub-category)`` as they are now named in the database (an empty
    sub-category means Uncategorized), or None when the user goes back to fix the names.
    """
    cat_name, sub_name = (cat_name or "").strip(), (sub_name or "").strip() or UNCATEGORIZED_SUB
    if not cat_name and type_name and ("Income" in type_name or "Expense" in type_name):
        cat_name = UNCATEGORIZED_CAT  # chosen later: it waits in To review
    if not cat_name:
        QMessageBox.warning(parent, "Category", "Choose a category.")
        return None
    type_id = db.get_type_id(type_name) if type_name else None
    if cat_name.casefold() == UNCATEGORIZED_CAT.casefold():
        cat = db.get_category_by_name(UNCATEGORIZED_CAT)
    else:
        own = db.get_categories(type_id) if type_id else db.get_categories()
        cat_name = _same_name([c["name"] for c in own], cat_name)
        cat = next((c for c in own if c["name"] == cat_name), None)
    if cat:
        cat_name = cat["name"]
        sub_name = _same_name([x["name"] for x in db.get_subcategories(cat["id"])] + [UNCATEGORIZED_SUB], sub_name)
    new_sub = sub_name != UNCATEGORIZED_SUB and not (cat and db.get_subcategory_by_name(sub_name, cat["id"]))

    if not cat or new_sub:
        if not cat:
            kind = f" to {type_name}" if type_name else ""
            text = f"Add the category \"{cat_name}\"{kind}"
            text += f", with the sub-category \"{sub_name}\"?" if new_sub else "?"
        else:
            text = f"Add the sub-category \"{sub_name}\" to \"{cat_name}\"?"
        box = QMessageBox(QMessageBox.Question, "New Category" if not cat else "New Sub-Category", text,
                          parent=parent)
        add = box.addButton("Add", QMessageBox.AcceptRole)
        box.addButton("Go Back", QMessageBox.RejectRole)
        box.setDefaultButton(add)
        box.exec()
        if box.clickedButton() is not add:
            return None

    with db.transaction():
        if not cat:
            db.add_category(cat_name, type_name)
            cat = db.get_category_by_name(cat_name, type_name=type_name)
        if sub_name == UNCATEGORIZED_SUB:
            db.uncategorized_subcategory(cat["id"])
        elif new_sub:
            db.add_subcategory(sub_name, cat["id"])
    return cat_name, sub_name

class ReadOnlyCopyDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setStyleSheet("QLineEdit {padding: 0; margin: 0; }")
        editor.setReadOnly(True)
        editor.setFrame(False)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data() or "")
        editor.selectAll()  # select all text when editor opens

    def setModelData(self, editor, model, index):
        pass


class EditableTableView(QTableView):
    def mouseDoubleClickEvent(self, event):
        idx = self.indexAt(event.pos())
        if idx.isValid():
            self.doubleClicked.emit(idx)
        else:
            super().mouseDoubleClickEvent(event)


# StatCard  — reusable account balance card with a colored left border
class AccountCard(QFrame):
    """Reusable account balance card with a colored left border."""

    def __init__(self, name, balance=0.0, color="#7c6af7", min_size=(155, 78), parent=None):
        super().__init__(parent)
        self.setMinimumSize(*min_size)
        self._color = color
        self._build(name)
        self.refresh_style()
        self.update_balance(balance)

    def _build(self, name):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(2)

        self._name_lbl = QLabel(name)
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setProperty("class", "stat-label")
        self._name_lbl.setStyleSheet(f"color: {self._color};")

        self._bal_lbl = QLabel("$0.00", alignment=Qt.AlignVCenter | Qt.AlignRight)
        self._bal_lbl.setProperty("class", "stat-value")

        layout.addWidget(self._name_lbl)
        layout.addWidget(self._bal_lbl)

    def update_balance(self, balance):
        s = get_settings()
        bal_color = s.get("income") if balance >= 0 else s.get("expense")
        self._bal_lbl.setText(f"${balance:,.2f}")
        self._bal_lbl.setStyleSheet(f"color: {bal_color};")

    def refresh_style(self):
        self.setProperty("class", "stat-card")
        self.setStyleSheet(f"QFrame[class='stat-card'] {{ border-left: 3px solid {self._color}; }}")
        self._name_lbl.setStyleSheet(f"color: {self._color};")


# SummaryCard  — dashboard period summary card with a colored top border
#               used in: dashboard stat row (Income / Expense / Net / Tx count)
class SummaryCard(QFrame):
    """Dashboard summary card with a colored top border."""

    def __init__(self, label, color, parent=None):
        super().__init__(parent)
        self._color = color
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build(label)
        self.refresh_style()

    def _build(self, label):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setProperty("class", "summary-label")

        self._val = QLabel("—", alignment=Qt.AlignVCenter | Qt.AlignRight)
        self._val.setProperty("class", "summary-value")
        self._val.setStyleSheet(f"color: {self._color};")

        layout.addWidget(self._lbl)
        layout.addWidget(self._val)

    def set_value(self, text, color=None):
        if color is not None:
            self._color = color
        self._val.setText(text)
        self._val.setStyleSheet(f"color: {self._color};")
        self.setStyleSheet(f"QFrame[class='summary-card'] {{ border-top: 3px solid {self._color}; }}")

    def refresh_style(self):
        self.setProperty("class", "summary-card")
        self.setStyleSheet(f"QFrame[class='summary-card'] {{ border-top: 3px solid {self._color}; }}")


# CheckComboBox  — multi-select dropdown with checkboxes
class _ToggleListWidget(QListWidget):
    """QListWidget where clicking anywhere on a row (text or checkbox) toggles it."""

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if item and item.flags() & Qt.ItemIsUserCheckable:
            new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
            item.setCheckState(new_state)
        else:
            super().mousePressEvent(event)


class CheckComboBox(QToolButton):
    """Multi-select dropdown with checkboxes. All/None at top.
    Pass searchable=True to show a search box inside the popup.
    """
    selectionChanged = Signal(list)

    def __init__(self, placeholder="All", searchable=False, parent=None, allow_new=False):
        super().__init__(parent)
        self._placeholder = placeholder
        self._allow_new = allow_new  # Enter in the search box adds what was typed (e.g. a new tag)
        self.new_items = []
        searchable = searchable or allow_new
        self._items = []
        self._checked = set()
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(32)
        self.setProperty("class", "check-combo")

        self._popup = QFrame(self, Qt.Popup | Qt.FramelessWindowHint)  # owned: deleted with self
        self._popup.setProperty("class", "picker-popup")
        self._popup.setMinimumWidth(200)

        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(6, 6, 6, 6)
        popup_layout.setSpacing(4)

        # ── Optional search box ───────────────────────────────────────────────
        self._search = None
        if searchable:
            self._search = QLineEdit()
            self._search.setPlaceholderText("🔍  Search...")
            self._search.setClearButtonEnabled(True)
            self._search.textChanged.connect(self._filter_list)
            if allow_new:
                self._search.setPlaceholderText("🔍  Find, or type a new one + Enter")
                self._search.returnPressed.connect(self._add_typed)
            popup_layout.addWidget(self._search)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        self._btn_all = QPushButton("All")
        self._btn_none = QPushButton("None")
        for btn in (self._btn_all, self._btn_none):
            btn.setFixedHeight(26)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_all.clicked.connect(self._select_all)
        self._btn_none.clicked.connect(self._select_none)
        btn_col.addWidget(self._btn_all)
        btn_col.addWidget(self._btn_none)
        popup_layout.addLayout(btn_col)

        self._list = _ToggleListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemChanged.connect(self._on_item_changed)
        popup_layout.addWidget(self._list)

        self._update_display()

    def refresh_style(self):
        _repolish(self)
        _repolish(self._popup)

    icon_for = None  # () → (text → QIcon or None): the icons beside the items (a category's, a logo)

    def populate(self, items, keep_selection=True):
        old = set(self._checked) if keep_selection else set()
        self._items = list(items)
        self._list.blockSignals(True)
        self._list.clear()
        icon_for = self.icon_for() if self.icon_for else None
        for text in self._items:
            li = QListWidgetItem(text)
            icon = icon_for(text) if icon_for else None
            if icon is not None:
                li.setIcon(icon)
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked if text in old else Qt.Unchecked)
            self._list.addItem(li)
        self._list.blockSignals(False)
        self._checked = {t for t in old if t in self._items}
        self._update_display()

    def get_selected(self):
        return list(self._checked)

    def set_selected(self, values):
        self._checked = set(values) & set(self._items)
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            li = self._list.item(i)
            li.setCheckState(Qt.Checked if (li.data(Qt.UserRole) or li.text()) in self._checked else Qt.Unchecked)
        self._list.blockSignals(False)
        self._update_display()

    def clear_selection(self):
        self._checked.clear()
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Unchecked)
        self._list.blockSignals(False)
        self._update_display()

    def mousePressEvent(self, event):
        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._popup.setStyleSheet(build_stylesheet())
            if self._search:
                self._search.clear()
                self._search.setFocus()
            _repolish(self)
            _repolish(self._popup)
            self._list.setFixedHeight(self._list_height())
            fm = self.fontMetrics()
            max_w = max(
                (fm.horizontalAdvance(self._list.item(i).text()) for i in range(self._list.count())),
                default=0
            )
            self._popup.setFixedWidth(max(max_w + 80, self.width() + 60, 200))
            _show_popup(self, self._popup)

    ROWS_SHOWN = 15

    def _list_height(self):
        """As tall as its rows (their real height: the font size and the icons decide it), up to
        ROWS_SHOWN, and no taller than the room on the screen below or above the button."""
        n = max(self._list.count(), 1)
        row = max(self._list.sizeHintForRow(0) if self._list.count() else 0, self.fontMetrics().height() + 8)
        frame = 2 * self._list.frameWidth() + 4
        want = min(n, self.ROWS_SHOWN) * row + frame
        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        top = self.mapToGlobal(QPoint(0, 0)).y()
        room = max(screen.bottom() - (top + self.height()), top - screen.top())  # where _show_popup puts it
        lay = self._popup.layout()  # what is above the list: the search box, All, None, the margins
        m = lay.contentsMargins()
        others = (m.top() + m.bottom() + self._btn_all.height() + self._btn_none.height() + 3 * lay.spacing()
                  + (self._search.sizeHint().height() + lay.spacing() if self._search else 0))
        return max(row + frame, min(want, room - others - 8))

    def _filter_list(self, text):
        """Show only items matching the search text."""
        text = text.lower().strip()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _add_typed(self):
        """Enter: tick the typed name, adding it when it is new (saved by the caller)."""
        text = " ".join(self._search.text().split())
        if not text:
            return
        found = next((t for t in self._items if t.casefold() == text.casefold()), None)
        if found is None:
            found = text
            self._items.append(text)
            self.new_items.append(text)
            li = QListWidgetItem(f"{text}  (new)")
            li.setData(Qt.UserRole, text)
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Unchecked)
            self._list.addItem(li)
        self._search.clear()
        self.set_selected(self.get_selected() + [found])
        self.selectionChanged.emit(self.get_selected())

    def _on_item_changed(self, item):
        name = item.data(Qt.UserRole) or item.text()
        if item.checkState() == Qt.Checked:
            self._checked.add(name)
        else:
            self._checked.discard(name)
        self._update_display()
        self.selectionChanged.emit(self.get_selected())

    def _select_all(self):
        self._checked = set(self._items)
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Checked)
        self._list.blockSignals(False)
        self._update_display()
        self.selectionChanged.emit(self.get_selected())

    def _select_none(self):
        self._checked.clear()
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Unchecked)
        self._list.blockSignals(False)
        self._update_display()
        self.selectionChanged.emit(self.get_selected())

    def _update_display(self):
        n, total = len(self._checked), len(self._items)
        if n == 0:  # nothing ticked: its placeholder ("All" for a filter, "No tags" for a transaction's tags)
            self.setText(f"{self._placeholder}  ▼")
        elif n == total:
            self.setText("All  ▼")
        elif n == 1:
            self.setText(f"{plain_label(next(iter(self._checked)))}  ▼")  # "Coffee & Snacks", not "Coffee _Snacks"
        else:
            self.setText(f"{n} selected  ▼")
        # what is ticked, in full (a narrow box shows only "2 …")
        self.setToolTip("\n".join(sorted(self._checked, key=str.casefold)) if 1 < n < total else "")


# StepSpinBox  — custom spin box with visible ▲▼ buttons (macOS-safe)
class AccountsCombo(CheckComboBox):
    """The accounts of a rule: tick one or several; none ticked is all accounts ("All"), also
    those added later. Ticking every one is those accounts only. ``accounts``: the names to
    offer; ``selected``: those ticked (a closed account among them is offered too)."""

    def __init__(self, accounts, selected=(), parent=None):
        super().__init__(placeholder="All", parent=parent)
        self.populate(list(accounts) + [a for a in selected if a not in accounts], keep_selection=False)
        self.set_selected(selected)

    def accounts(self):
        """The ticked names, in the list's order; [] for all accounts."""
        chosen = set(self.get_selected())
        return [a for a in self._items if a in chosen]

    def _update_display(self):
        names = self.accounts() if hasattr(self, "_items") else []
        self.setText(f"{accounts_label(names)}  ▼")
        self.setToolTip("\n".join(names) if len(names) > 1 else "")

    def set_accounts(self, names):
        self.set_selected(names or [])
        self.selectionChanged.emit(self.get_selected())


def accounts_label(names):
    """A rule's accounts in a list: "All", the one name, else how many (bank account names are
    long; the tooltip has them all)."""
    if not names:
        return "All"
    return names[0] if len(names) == 1 else f"{len(names)} accounts"


class StepSpinBox(QWidget):
    valueChanged = Signal(float)

    def __init__(self, value=0.0, min_val=-999999.0, max_val=9999999.0,
                 step=100.0, decimals=2, parent=None):
        super().__init__(parent)
        self._value = float(value)
        self._min = float(min_val)
        self._max = float(max_val)
        self._step = float(step)
        self._decimals = decimals
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._edit = QLineEdit()
        self._edit.setText(self._fmt(self._value))
        self._edit.setAlignment(Qt.AlignRight)
        self._edit.setMinimumHeight(32)
        self._edit.editingFinished.connect(self._on_edit)

        btn_up = QPushButton("▲")
        btn_dn = QPushButton("▼")
        for b in (btn_up, btn_dn):
            b.setFixedSize(15, 15)
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("class", "spin-btn")
        btn_up.clicked.connect(self._step_up)
        btn_dn.clicked.connect(self._step_down)

        btn_col = QVBoxLayout()
        btn_col.setContentsMargins(2, 0, 0, 0)
        btn_col.setSpacing(2)
        btn_col.addWidget(btn_up)
        btn_col.addWidget(btn_dn)

        layout.addWidget(self._edit)
        layout.addLayout(btn_col)

        self._btn_up = btn_up
        self._btn_dn = btn_dn

    def _fmt(self, v):
        return f"{v:.{self._decimals}f}"

    def _on_edit(self):
        try:
            v = float(self._edit.text().replace(",", ""))
            self._set(v)
        except ValueError:
            self._edit.setText(self._fmt(self._value))

    def _step_up(self):
        self._set(self._value + self._step)

    def _step_down(self):
        self._set(self._value - self._step)

    def _set(self, v):
        v = max(self._min, min(self._max, v))
        if v != self._value:
            self._value = v
            self._edit.setText(self._fmt(v))
            self.valueChanged.emit(v)

    # ── Public API (matches QDoubleSpinBox interface used in charts.py) ───────
    def value(self):
        return self._value

    def setValue(self, v):
        self._set(float(v))

    def setRange(self, a, b):
        self._min = float(a)
        self._max = float(b)

    def setEnabled(self, on):
        super().setEnabled(on)
        self._edit.setEnabled(on)
        self._btn_up.setEnabled(on)
        self._btn_dn.setEnabled(on)


# SymbolButton  — QPushButton with a QPainter-drawn symbol (macOS-safe)
#                Shapes: "up", "down", "close"
class SymbolButton(QPushButton):
    """Small button that paints its symbol with QPainter — no font/emoji needed."""

    def __init__(self, shape, size=28, parent=None):
        super().__init__(parent)
        assert shape in ("up", "down", "close"), f"Unknown shape: {shape}"
        self._shape = shape
        self._hovered = False
        self.setFixedSize(size, size)
        self.setProperty("class", "secondary")
        self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        s = get_settings()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        color = QColor("#ffffff") if self._hovered else QColor(s.get("text"))
        p.setPen(Qt.NoPen)
        p.setBrush(color)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        if self._shape == "up":
            tri = QPolygon([QPoint(cx, cy - 5), QPoint(cx - 5, cy + 3), QPoint(cx + 5, cy + 3)])
            p.drawPolygon(tri)
        elif self._shape == "down":
            tri = QPolygon([QPoint(cx, cy + 5), QPoint(cx - 5, cy - 3), QPoint(cx + 5, cy - 3)])
            p.drawPolygon(tri)
        elif self._shape == "close":
            pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            d = 5
            p.drawLine(cx - d, cy - d, cx + d, cy + d)
            p.drawLine(cx + d, cy - d, cx - d, cy + d)

        p.end()


# SingleSelectCombo  — QComboBox with a painted ▼ triangle, auto-sizing,
#                      and a selectionChanged signal (macOS-safe)
class SingleSelectCombo(QComboBox):
    selectionChanged = Signal(str)

    def __init__(self, placeholder="All", parent=None):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setProperty("class", "single-combo")
        self.setMaxVisibleItems(15)
        _setup_combo_editing(self)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContentsOnFirstShow)
        self.currentTextChanged.connect(self._emit_change)
        self._item_added = False
        self._after_add()

    def paintEvent(self, event):
        super().paintEvent(event)
        s = get_settings()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(s.get("text"))
        color.setAlpha(200)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        cx = self.width() - 13
        cy = self.height() // 2
        tri = QPolygon([QPoint(cx - 5, cy - 2), QPoint(cx + 5, cy - 2), QPoint(cx, cy + 4)])
        p.drawPolygon(tri)
        p.end()
        if self._item_added:
            self._after_add()

    def _emit_change(self, text):
        self.selectionChanged.emit(text or self._placeholder)

    def set_items(self, items, include_all=True, selected=None, emit=True):
        self.blockSignals(True)
        self.clear()
        values = list(items or [])
        if include_all:
            self.addItem("All")
        for v in values:
            self.addItem(str(v))
        idx = self.findText(selected) if selected else -1
        self.setCurrentIndex(idx if idx >= 0 else 0)
        self.blockSignals(False)
        if emit:
            self.selectionChanged.emit(self.current_text())

    def current_text(self):
        t = self.currentText().strip()
        return t if t else "All"

    def allow_typing(self, hint="Pick from the list, or type a new name"):
        """Unlock the text: a name can be typed as well as picked (the ▼ still opens the list)."""
        le = self.lineEdit()
        le.setReadOnly(False)
        le.removeEventFilter(self._click_filter)
        le.selectionChanged.disconnect(self._deselect)
        le.setStyleSheet("QLineEdit { padding: 0; margin: 0; }")
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setToolTip(hint)
        completer = self.completer()  # suggestions while typing: names containing the text
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.popup().setStyleSheet(popup_list_stylesheet())  # a top-level list: not themed by the window

        class _SelectOnFocus(QObject):  # clicking in selects the name, so typing replaces it
            def eventFilter(self_, obj, event):
                if event.type() == QEvent.FocusIn:
                    QTimer.singleShot(0, le, le.selectAll)
                return False

        self._select_on_focus = _SelectOnFocus(le)
        le.installEventFilter(self._select_on_focus)
        self.installEventFilter(self._select_on_focus)  # focus often arrives at the combo itself

    def addItem(self, text, userData=None):
        if userData is not None:
            super().addItem(text, userData)
        else:
            super().addItem(text)
        self._item_added = True

    def addItems(self, texts):
        super().addItems(texts)
        self._item_added = True

    def _after_add(self):
        fm = self.fontMetrics()
        max_w = max(
            (fm.horizontalAdvance(self.itemText(i)) for i in range(self.count())),
            default=0
        )
        self.setMinimumWidth(max_w + 80)
        self._item_added = False


# DatePicker  — unified picker: mode="month" (nav+OK) or mode="day" (nav+grid)
#               Signal: dateChanged(year: int, month_name: str, day: int)
#               day is always 1 for mode="month"
class DatePicker(QFrame):
    dateChanged = Signal(int, str, int)  # year, month_name, day (day=1 for month mode)

    def __init__(self, mode="day", parent=None):
        super().__init__(parent)
        assert mode in ("day", "month"), f"Unknown mode: {mode!r}"
        self._mode = mode
        now = QDate.currentDate()
        self._year = now.year()
        self._month = MONTHS_ORDER[now.month() - 1]
        self._day = now.day()
        self._vy, self._vm = self._year, self._month  # month shown in the popup while browsing
        self._min = None
        self._max = None
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Trigger button ────────────────────────────────────────────────────
        self._btn = QToolButton()
        self._btn.setProperty("class", "picker-combo")
        self._btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._btn.setFixedHeight(32)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.clicked.connect(self._show)
        layout.addWidget(self._btn)

        # ── Popup ─────────────────────────────────────────────────────────────
        self._popup = QFrame(self, Qt.Popup | Qt.FramelessWindowHint)  # owned: deleted with self
        self._popup.setProperty("class", "picker-popup")
        self._pl = QVBoxLayout(self._popup)
        self._pl.setContentsMargins(8, 8, 8, 8)
        self._pl.setSpacing(6)

        # ── Nav row: ◀  [Month combo]  [Year spinbox]  ▶ ─────────────────────
        nav = QHBoxLayout()
        nav.setSpacing(4)

        self._btn_prev = QPushButton("◀")
        self._btn_prev.setProperty("class", "nav-btn")
        self._btn_prev.clicked.connect(self._prev_month)

        self._month_combo = SingleSelectCombo()
        for m in MONTHS_ORDER:
            self._month_combo.addItem(m)
        idx = self._month_combo.findText(self._month)
        if idx >= 0:
            self._month_combo.setCurrentIndex(idx)
        self._month_combo.currentTextChanged.connect(self._on_nav_month_changed)

        self._year_spin = StepSpinBox(
            value=self._year,
            min_val=PICKER_MIN_YEAR,
            max_val=PICKER_MAX_YEAR,
            step=1, decimals=0,
        )
        self._year_spin.setFixedWidth(90)
        self._year_spin.valueChanged.connect(self._on_nav_year_changed)

        self._btn_next = QPushButton("▶")
        self._btn_next.setProperty("class", "nav-btn")
        self._btn_next.clicked.connect(self._next_month)

        nav.addWidget(self._btn_prev)
        nav.addWidget(self._month_combo, 2)
        nav.addWidget(self._year_spin, 1)
        nav.addWidget(self._btn_next)
        self._pl.addLayout(nav)

        if self._mode == "month":
            # ── OK button ─────────────────────────────────────────────────────
            btn_ok = QPushButton("OK")
            btn_ok.setProperty("class", "nav-btn")
            btn_ok.clicked.connect(self._confirm_month)
            self._pl.addWidget(btn_ok)
        else:
            # ── Day-of-week header ────────────────────────────────────────────
            s = get_settings()
            dow_row = QHBoxLayout()
            dow_row.setSpacing(2)
            dow_row.setContentsMargins(0, 0, 0, 0)
            for d in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]:
                lbl = QLabel(d)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setFixedWidth(32)
                lbl.setStyleSheet(f"color: {s.get('text_dim')}; font-size: 10pt;")
                dow_row.addWidget(lbl)
            self._pl.addLayout(dow_row)

            # ── Day grid ──────────────────────────────────────────────────────
            self._grid_widget = QWidget()
            self._grid_layout = QGridLayout(self._grid_widget)
            self._grid_layout.setSpacing(2)
            self._grid_layout.setContentsMargins(0, 0, 0, 0)
            self._pl.addWidget(self._grid_widget)

        self._update_btn()

    # ── Nav actions ───────────────────────────────────────────────────────────

    def _prev_month(self):
        mn = MONTH_NUM.get(self._vm, 1)
        if mn == 1:
            if self._vy <= PICKER_MIN_YEAR: return
            self._vy -= 1
            self._vm = MONTHS_ORDER[11]
        else:
            self._vm = MONTHS_ORDER[mn - 2]
        self._sync_nav()
        if self._mode == "day":
            self._rebuild_grid()

    def _next_month(self):
        mn = MONTH_NUM.get(self._vm, 1)
        if mn == 12:
            if self._vy >= PICKER_MAX_YEAR: return
            self._vy += 1
            self._vm = MONTHS_ORDER[0]
        else:
            self._vm = MONTHS_ORDER[mn]
        self._sync_nav()
        if self._mode == "day":
            self._rebuild_grid()

    def _on_nav_month_changed(self, month_name):
        if month_name and month_name in MONTHS_ORDER:
            self._vm = month_name
            if self._mode == "day":
                self._rebuild_grid()

    def _on_nav_year_changed(self, value):
        self._vy = int(value)
        if self._mode == "day":
            self._rebuild_grid()

    def _sync_nav(self):
        self._month_combo.blockSignals(True)
        self._year_spin._edit.blockSignals(True)
        idx = self._month_combo.findText(self._vm)
        if idx >= 0:
            self._month_combo.setCurrentIndex(idx)
        self._year_spin._value = self._vy
        self._year_spin._edit.setText(str(self._vy))
        self._month_combo.blockSignals(False)
        self._year_spin._edit.blockSignals(False)

    def _confirm_month(self):
        """Month mode: OK button pressed — the shown month becomes the date; emit and close."""
        self._commit(self._vy, self._vm, 1)

    # ── Day grid (mode="day" only) ────────────────────────────────────────────

    def _clear_grid(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _rebuild_grid(self):
        self._clear_grid()
        mn = MONTH_NUM.get(self._vm, 1)
        first_wd = QDate(self._vy, mn, 1).dayOfWeek() - 1
        days_in_month = calendar.monthrange(self._vy, mn)[1]
        today = QDate.currentDate()

        prev_mn = mn - 1 if mn > 1 else 12
        prev_yr = self._vy if mn > 1 else self._vy - 1
        prev_days = calendar.monthrange(prev_yr, prev_mn)[1]
        next_mn = mn + 1 if mn < 12 else 1
        next_yr = self._vy if mn < 12 else self._vy + 1

        for i in range(42):
            day_num = i - first_wd + 1
            b = QPushButton()
            b.setProperty("class", "picker-btn")
            # b.setFixedSize(32, 28)

            if day_num < 1:
                actual_day = prev_days + day_num
                b.setText(str(actual_day))
                b.setProperty("state", "overflow")
                b.clicked.connect(lambda _, d=actual_day, y=prev_yr, m=prev_mn: self._pick_overflow(y, m, d))
            elif day_num > days_in_month:
                actual_day = day_num - days_in_month
                b.setText(str(actual_day))
                b.setProperty("state", "overflow")
                b.clicked.connect(lambda _, d=actual_day, y=next_yr, m=next_mn: self._pick_overflow(y, m, d))
            else:
                b.setText(str(day_num))
                disabled = False
                if self._min:
                    if (self._vy, mn, day_num) < (self._min[0], MONTH_NUM.get(self._min[1], 1), self._min[2]):
                        disabled = True
                if self._max:
                    if (self._vy, mn, day_num) > (self._max[0], MONTH_NUM.get(self._max[1], 12), self._max[2]):
                        disabled = True

                is_today = (self._vy == today.year() and mn == today.month() and day_num == today.day())
                is_sel = (self._vy, self._vm, day_num) == (self._year, self._month, self._day)

                b.setEnabled(not disabled)
                if is_sel:
                    b.setProperty("state", "selected")
                elif is_today and not disabled:
                    b.setProperty("state", "today")
                else:
                    b.setProperty("state", "normal")
                b.clicked.connect(lambda _, d=day_num: self._pick_day(d))

            self._grid_layout.addWidget(b, i // 7, i % 7)
            _repolish(b)

        self._popup.adjustSize()

    def _pick_day(self, day):
        self._commit(self._vy, self._vm, day)

    def _pick_overflow(self, year, month_num, day):
        """A grey day of the previous or next month: pick it like any other day."""
        self._commit(year, MONTHS_ORDER[month_num - 1], day)

    def _commit(self, year, month, day):
        self._year, self._month, self._day = year, month, day
        self._update_btn()
        self._popup.hide()
        self.dateChanged.emit(year, month, day if self._mode == "day" else 1)

    # ── Show ──────────────────────────────────────────────────────────────────

    def _show(self):
        self._popup.setStyleSheet(build_stylesheet())
        self._vy, self._vm = self._year, self._month  # open on the chosen date
        self._sync_nav()
        if self._mode == "day":
            self._rebuild_grid()
        self._popup.adjustSize()
        _show_popup(self._btn, self._popup)

    def _refresh_styles(self):
        _repolish(self._btn)
        _repolish(self._popup)

    def _update_btn(self):
        if self._mode == "month":
            self._btn.setText(f"{self._month[:3]} {self._year}  ▼")
        else:
            self._btn.setText(f"{self._month[:3]} {self._day}, {self._year}  ▼")

    # ── Public API ────────────────────────────────────────────────────────────
    def get_year(self):
        return self._year

    def get_month(self):
        return self._month

    def get_day(self):
        return self._day if self._mode == "day" else 1

    def set_date(self, year, month, day=1):
        self._year = self._vy = year
        self._month = self._vm = month
        if self._mode == "day":
            mn = MONTH_NUM.get(month, 1)
            self._day = min(day, calendar.monthrange(year, mn)[1])
        self._update_btn()

    def set_min_date(self, year, month, day=1):
        self._min = (year, month, day)

    def set_max_date(self, year, month, day=31):
        self._max = (year, month, day)


# DateRangeWidget  — unified From→To range: mode="month" or mode="day"
#                    Signal: rangeChanged(fy, fm, fd, ty, tm, td)
#                    fd/td are always 1/last-day for month mode
class DateRangeWidget(QWidget):
    rangeChanged = Signal(int, str, int, int, str, int)

    def __init__(self, mode="day", config_key="range_date", parent=None):
        super().__init__(parent)
        self._mode = mode
        self._config_key = config_key
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lbl_from = QLabel("From:")
        lbl_from.setProperty("class", "range-label")
        layout.addWidget(lbl_from)

        self.from_p = DatePicker(mode=self._mode)
        self.from_p.dateChanged.connect(self._on_from_changed)
        layout.addWidget(self.from_p)

        lbl_to = QLabel("To:")
        lbl_to.setProperty("class", "range-label")
        layout.addWidget(lbl_to)

        self.to_p = DatePicker(mode=self._mode)
        self.to_p.dateChanged.connect(self._on_to_changed)
        layout.addWidget(self.to_p)

        self.from_p.set_min_date(PICKER_MIN_YEAR, PICKER_MIN_MONTH, PICKER_MIN_DAY)
        self.from_p.set_max_date(PICKER_MAX_YEAR, PICKER_MAX_MONTH, PICKER_MAX_DAY)
        self.to_p.set_min_date(PICKER_MIN_YEAR, PICKER_MIN_MONTH, PICKER_MIN_DAY)
        self.to_p.set_max_date(PICKER_MAX_YEAR, PICKER_MAX_MONTH, PICKER_MAX_DAY)

        saved = get_settings().get(self._config_key)
        if saved and isinstance(saved, dict):
            fy = saved.get("from_year", PICKER_MIN_YEAR)
            fm = saved.get("from_month", PICKER_MIN_MONTH)
            fd = saved.get("from_day", PICKER_MIN_DAY)
            ty = saved.get("to_year", PICKER_MAX_YEAR)
            tm = saved.get("to_month", PICKER_MAX_MONTH)
            td = saved.get("to_day", PICKER_MAX_DAY)
            self.from_p.set_date(fy, fm, fd)
            self.to_p.set_date(ty, tm, td)
            self.to_p.set_min_date(fy, fm, fd)

    def refresh_style(self):
        self.from_p._refresh_styles()
        self.to_p._refresh_styles()

    def _on_from_changed(self, year, month, day):
        self.to_p.set_min_date(year, month, day)
        ty, tm, td = self.to_p.get_year(), self.to_p.get_month(), self.to_p.get_day()
        if (ty, MONTH_NUM.get(tm, 0), td) < (year, MONTH_NUM.get(month, 0), day):
            self.to_p.set_date(year, month, day)
        self._save()
        self.rangeChanged.emit(year, month, day,
                               self.to_p.get_year(), self.to_p.get_month(), self.to_p.get_day())

    def _on_to_changed(self, year, month, day):
        fy, fm, fd = self.from_p.get_year(), self.from_p.get_month(), self.from_p.get_day()
        if (year, MONTH_NUM.get(month, 0), day) < (fy, MONTH_NUM.get(fm, 0), fd):
            self.from_p.set_date(year, month, day)  # From moves back along with To
        self._save()
        self.rangeChanged.emit(self.from_p.get_year(), self.from_p.get_month(), self.from_p.get_day(),
                               year, month, day)

    def get_range(self):
        return (self.from_p.get_year(), self.from_p.get_month(), self.from_p.get_day(),
                self.to_p.get_year(), self.to_p.get_month(), self.to_p.get_day())

    def _save(self):
        fy, fm, fd, ty, tm, td = self.get_range()
        get_settings().set(self._config_key, {
            "from_year": fy, "from_month": fm, "from_day": fd,
            "to_year": ty, "to_month": tm, "to_day": td,
        })


# Aliases for backward compatibility
MonthYearPicker = lambda *a, **kw: DatePicker(mode="month", *a, **kw)
MonthRangeWidget = lambda *a, **kw: DateRangeWidget(mode="month", *a, **kw)


# PeriodSelectorWidget  — unified preset buttons + optional custom range picker
#
#   mode="month"  presets: This Month / Last Month / 3 Months / 6 Months /
#                          This Year / Custom  →  shows MonthRangeWidget
#   mode="day"    presets: Today / Yesterday / Last 7 Days / Last 30 Days /
#                          Last 3 Months / Custom  →  shows DateRangeWidget
#
#   Signal: rangeChanged(from_date: date, to_date: date)
#           Both modes emit standard Python date objects, so callers are
#           mode-agnostic — they just receive (from_date, to_date).
#
#   Usage:
#       sel = PeriodSelectorWidget(mode="month", config_key="period_dashboard")
#       sel.rangeChanged.connect(lambda f, t: self.refresh(f, t))
#       from_date, to_date = sel.get_range()   # always returns (date, date)
class PeriodSelectorWidget(QWidget):
    """Preset period buttons + collapsible custom range picker.

    Parameters
    ----------
    mode : "month" | "day"
        Controls which presets are shown and which picker appears for Custom.
    config_key : str
        Passed through to the inner range widget so custom selection persists.
    """

    rangeChanged = Signal(object, object)  # from_date, to_date
    chosen = Signal()  # just before rangeChanged when the person chose (a button, ◀ ▶, Custom's window)

    # ── Preset definitions ────────────────────────────────────────────────────
    _MONTH_PRESETS = ["All", "This Month", "Last Month", "3 Months", "6 Months", "This Year", "Custom"]
    _DAY_PRESETS = ["All", "Today", "Yesterday", "Last 7 Days", "Last 30 Days", "Last 3 Months", "Custom"]

    def __init__(self, mode="month", config_key="period_selector",
                 inline=True, parent=None):
        super().__init__(parent)
        assert mode in ("month", "day"), f"Unknown mode: {mode!r}"
        self._mode = mode
        self._config_key = config_key
        self._inline = inline
        self._active_idx = 0  # index of the currently selected preset
        self._preset_btns = []
        self._build()
        # Restore last-used preset index from settings
        saved_idx = get_settings().get(f"{config_key}_preset_idx")
        if isinstance(saved_idx, int):
            self._select_preset(saved_idx, emit=False)
        else:
            self._select_preset(0, emit=False)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)

        presets = self._MONTH_PRESETS if self._mode == "month" else self._DAY_PRESETS
        custom_idx = len(presets) - 1
        for i, label in enumerate(presets):
            if i == custom_idx:  # ◀ Custom ▶: the arrows step a chosen month or year
                self._step_back = self._arrow("◀", -1)
                btn_row.addWidget(self._step_back)
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("class", "period-preset-btn")
            btn.setFocusPolicy(Qt.NoFocus)
            if i == custom_idx:
                btn.clicked.connect(self._open_custom)
            else:
                btn.clicked.connect(lambda _, idx=i: self._choose(idx))
            btn_row.addWidget(btn)
            self._preset_btns.append(btn)
        self._step_on = self._arrow("▶", 1)
        btn_row.addWidget(self._step_on)

        # From – to lives in the Custom window now; this one keeps the days chosen there
        self._range_widget = DateRangeWidget(mode=self._mode, config_key=self._config_key, parent=self)
        self._range_widget.setVisible(False)
        self._custom = self._load_custom()  # {"mode": "month" | "year" | "range", "start": date}

        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def _choose(self, idx):
        self.chosen.emit()
        self._select_preset(idx)

    def _arrow(self, text, step):
        btn = QPushButton(text)
        btn.setProperty("class", "nav-btn")
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedWidth(30)
        btn.setToolTip("The month before" if step < 0 else "The month after")
        btn.clicked.connect(lambda: self._step(step))
        btn.setVisible(False)
        return btn

    # ── Custom: a month, a year, or From – to ────────────────────────────────
    data_months = None
    """A function giving {"2026-09", …}, the months with transactions (set by the tab); without it
    every month can be chosen."""

    def _custom_idx(self):
        return len(self._MONTH_PRESETS if self._mode == "month" else self._DAY_PRESETS) - 1

    def _load_custom(self):
        saved = get_settings().get(f"{self._config_key}_custom")
        if isinstance(saved, dict) and saved.get("mode") in ("month", "year"):
            try:
                return {"mode": saved["mode"], "start": _date.fromisoformat(saved["start"])}
            except (KeyError, TypeError, ValueError):
                pass
        return {"mode": "range"}

    def _save_custom(self):
        c = self._custom
        get_settings().set(f"{self._config_key}_custom",
                           {"mode": c["mode"], "start": c["start"].isoformat()} if c["mode"] != "range" else
                           {"mode": "range"})

    def _custom_bounds(self, custom):
        """(first day, last day) of a chosen month or year (the last no later than today)."""
        start = custom["start"]
        if custom["mode"] == "month":
            end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
        else:
            end = start.replace(month=12, day=31)
        return start, min(end, _date.today())

    def _months(self):
        try:
            return set(self.data_months()) or None if self.data_months else None
        except Exception:  # noqa: BLE001 — a closed database: every month can be chosen
            return None  # (and no transactions yet: no limit either)

    def _stepped(self, n):
        c = self._custom
        if c["mode"] == "month":
            i = c["start"].year * 12 + c["start"].month - 1 + n
            start = _date(i // 12, i % 12 + 1, 1)
        else:
            start = _date(c["start"].year + n, 1, 1)
        return {"mode": c["mode"], "start": start}

    def _has_room(self, custom):
        """A month or year to step to: not after today, not before the first transaction."""
        if custom["start"] > _date.today():
            return False
        months = self._months()
        if not months:
            return custom["start"].year >= PICKER_MIN_YEAR
        first = min(months)
        key = custom["start"].strftime("%Y-%m")
        return key >= first if custom["mode"] == "month" else custom["start"].year >= int(first[:4])

    def _step(self, n):
        stepped = self._stepped(n)
        if self._has_room(stepped):
            self._custom = stepped
            self._save_custom()
            self._choose(self._custom_idx())

    def _open_custom(self):
        """Custom: the window to choose in (the button stays as it was until a choice)."""
        btn = self._preset_btns[-1]
        btn.setChecked(self._active_idx == self._custom_idx())
        dialog = PeriodDialog(self._mode, self._custom if self._active_idx == self._custom_idx() else None,
                              self._range_widget.get_range(), self._months(), parent=self.window())
        try:
            accepted = dialog.exec() == QDialog.Accepted and dialog.choice
            choice = dialog.choice
        finally:
            dialog.deleteLater()  # not kept, with its pickers, after each Custom
        if not accepted:
            return
        mode, value = choice
        if mode == "range":
            self._set_pickers(*value)
            self._range_widget._save()
            self._custom = {"mode": "range"}
        else:
            self._custom = {"mode": mode, "start": value}
        self._save_custom()
        self._choose(self._custom_idx())

    def _custom_label(self):
        c = self._custom
        if c["mode"] == "month":
            return f"{c['start'].strftime('%b %Y')}  ▾"
        if c["mode"] == "year":
            return f"{c['start'].year}  ▾"
        fy, fm, fd, ty, tm, td = self._range_widget.get_range()
        if self._mode == "month":
            return f"{fm[:3]} {fy} – {tm[:3]} {ty}  ▾"
        return f"{fm[:3]} {fd}, {fy} – {tm[:3]} {td}, {ty}  ▾"

    def update_arrows(self):
        """◀ ▶ anew (new transactions, or a new month since): the tabs call it when they refresh."""
        self._show_custom(self._active_idx == self._custom_idx())

    def _show_custom(self, on):
        btn = self._preset_btns[-1]
        btn.setText(self._custom_label() if on else "Custom")
        steps = on and self._custom["mode"] in ("month", "year")
        for arrow, n in ((self._step_back, -1), (self._step_on, 1)):
            arrow.setVisible(steps)
            if steps:
                arrow.setEnabled(self._has_room(self._stepped(n)))
                arrow.setToolTip(f"The {self._custom['mode']} {'before' if n < 0 else 'after'}")

    # ── Preset selection ──────────────────────────────────────────────────────
    def _select_preset(self, idx, emit=True, persist=True):
        self._active_idx = idx
        presets = self._MONTH_PRESETS if self._mode == "month" else self._DAY_PRESETS
        is_custom = (idx == len(presets) - 1)

        for i, btn in enumerate(self._preset_btns):
            btn.setChecked(i == idx)
            _repolish(btn)
        self._show_custom(is_custom)

        if persist:
            get_settings().set(f"{self._config_key}_preset_idx", idx)

        if emit:
            from_d, to_d = self._compute_preset_range(idx)
            self.rangeChanged.emit(from_d, to_d)

    def _compute_preset_range(self, idx):
        """Return (from_date, to_date) for a non-custom preset index."""
        today = _date.today()

        if self._mode == "month":
            if idx == 0:  # All
                return None, None
            elif idx == 1:  # This Month
                f = today.replace(day=1)
                t = today
            elif idx == 2:  # Last Month
                first_this = today.replace(day=1)
                last_last = first_this - _td(days=1)
                f = last_last.replace(day=1)
                t = last_last
            elif idx == 3:  # 3 Months
                f = _month_back(today, 2)
                t = today
            elif idx == 4:  # 6 Months
                f = _month_back(today, 5)
                t = today
            elif idx == 5:  # This Year
                f = today.replace(month=1, day=1)
                t = today
            else:
                f = t = today
        else:  # day mode
            if idx == 0:  # All
                return None, None
            if idx == 1:  # Today
                f = t = today
            elif idx == 2:  # Yesterday
                f = t = today - _td(days=1)
            elif idx == 3:  # Last 7 Days
                f = today - _td(days=6)
                t = today
            elif idx == 4:  # Last 30 Days
                f = today - _td(days=29)
                t = today
            elif idx == 5:  # Last 3 Months
                f = _month_back(today, 2)
                t = today
            else:
                f = t = today

        return f, t

    # ── Range widget callbacks ────────────────────────────────────────────────
    def _on_range_changed(self, fy, fm, fd, ty, tm, td):
        """Convert DateRangeWidget signal to date objects."""
        from_d = _date(fy, MONTH_NUM.get(fm, 1), fd)
        if self._mode == "month":
            last_day = calendar.monthrange(ty, MONTH_NUM.get(tm, 1))[1]
            to_d = min(_date(ty, MONTH_NUM.get(tm, 1), last_day), _date.today())
        else:
            to_d = _date(ty, MONTH_NUM.get(tm, 1), td)
        self.rangeChanged.emit(min(from_d, to_d), to_d)

    # ── Public API ────────────────────────────────────────────────────────────
    def get_range(self):
        """Return (from_date, to_date) as Python date objects."""
        presets = self._MONTH_PRESETS if self._mode == "month" else self._DAY_PRESETS
        is_custom = (self._active_idx == len(presets) - 1)

        if is_custom and self._custom["mode"] != "range":
            return self._custom_bounds(self._custom)
        if is_custom:
            fy, fm, fd, ty, tm, td = self._range_widget.get_range()
            from_d = _date(fy, MONTH_NUM.get(fm, 1), fd)
            if self._mode == "month":
                last_day = calendar.monthrange(ty, MONTH_NUM.get(tm, 1))[1]
                to_d = min(_date(ty, MONTH_NUM.get(tm, 1), last_day), _date.today())
            else:
                to_d = _date(ty, MONTH_NUM.get(tm, 1), td)
            return min(from_d, to_d), to_d

        return self._compute_preset_range(self._active_idx)

    def set_custom_range(self, from_date, to_date, emit=False):
        """Custom, from ``from_date`` to ``to_date`` (dates): e.g. the months a chart showed. For
        the moment only: your saved choice stays (see state/restore)."""
        self._set_pickers(from_date.year, MONTHS_ORDER[from_date.month - 1], from_date.day,
                          to_date.year, MONTHS_ORDER[to_date.month - 1], to_date.day)
        self._custom = {"mode": "range"}
        presets = self._MONTH_PRESETS if self._mode == "month" else self._DAY_PRESETS
        self._select_preset(len(presets) - 1, emit=emit, persist=False)

    def _set_pickers(self, fy, fm, fd, ty, tm, td):
        rw = self._range_widget
        rw.to_p.set_min_date(PICKER_MIN_YEAR, PICKER_MIN_MONTH, PICKER_MIN_DAY)
        rw.from_p.set_date(fy, fm, fd)
        rw.to_p.set_date(ty, tm, td)
        rw.to_p.set_min_date(fy, fm, fd)

    def state(self):
        """What is chosen now (preset, custom dates, a chosen month or year), to put back with restore()."""
        return self._active_idx, self._range_widget.get_range(), dict(self._custom)

    def restore(self, state):
        idx, rng, *custom = state
        self._set_pickers(*rng)
        if custom:
            self._custom = dict(custom[0])
        self._select_preset(idx, emit=False, persist=False)

    def refresh_style(self):
        for btn in (*self._preset_btns, self._step_back, self._step_on):
            _repolish(btn)
        self._range_widget.refresh_style()
        self.update_arrows()


class PeriodDialog(QDialog):
    """Custom: a month (a year's months, ◀ ▶ for the year), a year, or From – to. A month or year
    is chosen with one click; From – to with Show. ``choice``: ("month", first day),
    ("year", 1 January) or ("range", (fy, fm, fd, ty, tm, td)); None when cancelled."""

    def __init__(self, mode, custom, rng, months=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose a Period")
        self.setStyleSheet(build_stylesheet())
        self.choice = None
        self._months = months  # None: any month
        today = _date.today()
        self._first_year = int(min(months)[:4]) if months else PICKER_MIN_YEAR
        chosen = custom if custom and custom.get("mode") in ("month", "year") else None
        self._chosen = chosen
        self._year = min(max((chosen["start"].year if chosen else today.year), self._first_year), today.year)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(12)
        title = QLabel("Choose a period")
        title.setStyleSheet("font-weight: bold; font-size: 15px;")
        root.addWidget(title)

        seg = QHBoxLayout()
        seg.setSpacing(4)
        self._segments = QButtonGroup(self)
        self._pages = QStackedWidget()
        for i, (name, key) in enumerate((("Month", "month"), ("Year", "year"), ("From – to", "range"))):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setProperty("class", "period-preset-btn")
            b.setFocusPolicy(Qt.NoFocus)
            b.setAutoDefault(False)
            self._segments.addButton(b, i)
            seg.addWidget(b)
        self._segments.idClicked.connect(self._pages.setCurrentIndex)
        root.addLayout(seg)

        # Month
        month_page = QWidget()
        mv = QVBoxLayout(month_page)
        mv.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self._prev = QPushButton("◀")
        self._next = QPushButton("▶")
        self._year_label = QLabel()
        self._year_label.setAlignment(Qt.AlignCenter)
        self._year_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        for b in (self._prev, self._next):
            b.setAutoDefault(False)
            b.setProperty("class", "nav-btn")
            b.setFocusPolicy(Qt.NoFocus)
        self._prev.clicked.connect(lambda: self._show_year(self._year - 1))
        self._next.clicked.connect(lambda: self._show_year(self._year + 1))
        nav.addWidget(self._prev)
        nav.addWidget(self._year_label, 1)
        nav.addWidget(self._next)
        mv.addLayout(nav)
        grid = QGridLayout()
        grid.setSpacing(6)
        self._month_btns = []
        for m in range(1, 13):
            b = QPushButton(MONTHS_ORDER[m - 1][:3])
            b.setAutoDefault(False)  # Return does not pick a month by itself
            b.setProperty("class", "picker-btn")
            b.setMinimumSize(64, 34)
            b.clicked.connect(lambda _, m=m: self._pick("month", _date(self._year, m, 1)))
            grid.addWidget(b, (m - 1) // 4, (m - 1) % 4)
            self._month_btns.append(b)
        mv.addLayout(grid)
        self._pages.addWidget(month_page)

        # Year
        year_page = QWidget()
        yg = QGridLayout(year_page)
        yg.setContentsMargins(0, 0, 0, 0)
        yg.setSpacing(6)
        years = {int(k[:4]) for k in months} if months else None
        for i, y in enumerate(range(today.year, self._first_year - 1, -1)):
            b = QPushButton(str(y))
            b.setAutoDefault(False)
            b.setProperty("class", "picker-btn")
            b.setMinimumSize(64, 34)
            on = bool(chosen) and chosen["mode"] == "year" and chosen["start"].year == y
            b.setProperty("state", "selected" if on else "normal")
            b.setEnabled(years is None or y in years)
            b.clicked.connect(lambda _, y=y: self._pick("year", _date(y, 1, 1)))
            yg.addWidget(b, i // 4, i % 4)
        yg.setRowStretch(yg.rowCount(), 1)
        self._pages.addWidget(year_page)

        # From – to
        range_page = QWidget()
        rv = QVBoxLayout(range_page)
        rv.setContentsMargins(0, 0, 0, 0)
        self._range = DateRangeWidget(mode=mode, config_key="period_dialog_range")
        fy, fm, fd, ty, tm, td = rng
        self._range.to_p.set_min_date(PICKER_MIN_YEAR, PICKER_MIN_MONTH, PICKER_MIN_DAY)
        self._range.from_p.set_date(fy, fm, fd)
        self._range.to_p.set_date(ty, tm, td)
        self._range.to_p.set_min_date(fy, fm, fd)
        rv.addWidget(self._range)
        show = QPushButton("Show")
        show.setDefault(True)
        show.clicked.connect(lambda: self._pick("range", self._range.get_range()))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(show)
        rv.addLayout(row)
        rv.addStretch(1)
        self._pages.addWidget(range_page)
        root.addWidget(self._pages)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        cancel_row.addWidget(cancel)
        root.addLayout(cancel_row)

        start = {"month": 0, "year": 1}.get(custom.get("mode") if custom else "month", 2)
        self._segments.button(start).setChecked(True)
        self._pages.setCurrentIndex(start)
        self._show_year(self._year)
        for b in self.findChildren(QPushButton):
            _repolish(b)

    def _show_year(self, year):
        today = _date.today()
        self._year = year
        self._year_label.setText(str(year))
        self._prev.setEnabled(year > self._first_year)
        self._next.setEnabled(year < today.year)
        for m, b in enumerate(self._month_btns, 1):
            key = f"{year}-{m:02d}"
            on = bool(self._chosen) and self._chosen["mode"] == "month" and \
                (self._chosen["start"].year, self._chosen["start"].month) == (year, m)
            b.setProperty("state", "selected" if on else "normal")
            b.setEnabled((self._months is None or key in self._months) and (year, m) <= (today.year, today.month))
            _repolish(b)

    def _pick(self, mode, value):
        self.choice = (mode, value)
        self.accept()


def _month_back(today, months):
    """Return a date approx `months` months before today (same day, clamped)."""
    m = today.month - months
    y = today.year
    while m < 1:
        m += 12
        y -= 1
    last = calendar.monthrange(y, m)[1]
    return today.replace(year=y, month=m, day=min(today.day, last))


class FlowLayout(QLayout):
    """Widgets in a line that goes on to the next line when there is no room (as words do),
    each line at the right when ``right`` (the sums under a table): nothing is cut off."""

    def __init__(self, parent=None, spacing=28, line_spacing=4, right=False):
        super().__init__(parent)
        self._items = []
        self._spacing, self._line_spacing, self._right = spacing, line_spacing, right
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), move=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect, move=True)

    def sizeHint(self):
        shown = [i for i in self._items if not i.isEmpty()]
        w = sum(i.sizeHint().width() for i in shown) + self._spacing * max(0, len(shown) - 1)
        h = max((i.sizeHint().height() for i in shown), default=0)
        m = self.contentsMargins()
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        widest = max((i.minimumSize().width() for i in self._items if not i.isEmpty()), default=0)
        m = self.contentsMargins()
        return QSize(widest + m.left() + m.right(), self.heightForWidth(widest + m.left() + m.right()))

    def _place(self, rect, move):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        lines, line, used = [], [], 0
        for item in (i for i in self._items if not i.isEmpty()):
            w = item.sizeHint().width()
            if line and used + self._spacing + w > area.width():
                lines.append((line, used))
                line, used = [], 0
            used += (self._spacing if line else 0) + w
            line.append(item)
        if line:
            lines.append((line, used))
        y = area.y()
        for items, used in lines:
            h = max(i.sizeHint().height() for i in items)
            x = area.x() + (max(0, area.width() - used) if self._right else 0)
            for item in items:
                size = item.sizeHint()
                if move:
                    item.setGeometry(QRect(QPoint(x, y + (h - size.height()) // 2), size))
                x += size.width() + self._spacing
            y += h + self._line_spacing
        return (y - self._line_spacing - area.y() if lines else 0) + m.top() + m.bottom()
