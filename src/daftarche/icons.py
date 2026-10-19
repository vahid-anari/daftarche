"""Category icons: an emoji per category (and, if wanted, per sub-category).

The names stay as they are (search, filters and rules use them); the icon is drawn beside them.
"""
import re

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

# the picker's grid: money-related first, then the rest of everyday life
PICKER = [
    "🛒", "🍽️", "☕", "🍔", "🍕", "🥡", "🍺", "🍷",
    "🧾", "💡", "🔥", "💧", "📱", "🌐", "📺", "📦",
    "🏠", "🛋️", "🧹", "🔧", "🪴", "🐾", "👶", "🎓",
    "🚗", "⛽", "🅿️", "🚇", "🚕", "🚲", "✈️", "🏨",
    "💊", "🩺", "🦷", "👓", "💇", "🧴", "🏋️", "🧘",
    "👕", "👟", "🛍️", "💻", "🎮", "📚", "🎬", "🎵",
    "🎁", "🎉", "❤️", "🙏", "🏦", "💳", "💵", "💰",
    "📈", "🧮", "🏛️", "🛡️", "📄", "🔁", "🤝", "❓",
    "👪", "🧺", "🚚", "🎤", "🔄", "🏷️", "⭐", "🌱",
]

# (words in the name, icon): the first match wins, so the more specific come first
_SUGGEST = [
    (("grocery", "groceries", "supermarket", "produce"), "🛒"),
    (("coffee", "cafe", "café", "tim horton", "starbucks"), "☕"),
    (("fast food",), "🍔"),
    (("restaurant", "dining", "eat out", "takeout", "take-out", "food"), "🍽️"),
    (("alcohol", "beer", "bar", "pub"), "🍺"),
    (("wine", "liquor", "lcbo"), "🍷"),
    (("electric", "electricity", "hydro", "power"), "💡"),
    (("gas bill", "heating", "enbridge"), "🔥"),
    (("water",), "💧"),
    (("phone", "mobile", "cell"), "📱"),
    (("internet", "wifi"), "🌐"),
    (("tv", "streaming", "netflix", "subscription", "prime"), "📺"),
    (("repair", "maintenance", "hardware", "tool", "home improvement", "renovation"), "🔧"),
    (("rent", "mortgage", "housing", "home"), "🏠"),
    (("furniture",), "🛋️"),
    (("cleaning", "household"), "🧹"),
    (("pet", "vet"), "🐾"),
    (("child", "children", "kid", "baby", "daycare"), "👶"),
    (("tuition", "school", "education", "course", "university"), "🎓"),
    (("fuel", "gas station", "gasoline", "gas"), "⛽"),
    (("parking",), "🅿️"),
    (("transit", "presto", "subway", "metro", "bus", "buses", "trains", "ttc"), "🚇"),
    (("taxi", "uber", "lyft"), "🚕"),
    (("bike", "bicycle"), "🚲"),
    (("car", "auto", "vehicle", "transport", "transportation"), "🚗"),
    (("flight", "airline", "air"), "✈️"),
    (("hotel", "airbnb", "accommodation", "lodging"), "🏨"),
    (("travel", "trip", "vacation"), "✈️"),
    (("pharmacy", "medicine", "drug"), "💊"),
    (("dental", "dentist"), "🦷"),
    (("glasses", "optical", "eye"), "👓"),
    (("health", "medical", "doctor", "clinic"), "🩺"),
    (("hair", "barber", "salon"), "💇"),
    (("personal care", "cosmetic", "beauty", "toiletries"), "🧴"),
    (("gym", "fitness", "sport"), "🏋️"),
    (("clothes", "clothing", "apparel"), "👕"),
    (("shoe",), "👟"),
    (("electronic", "computer", "software", "tech"), "💻"),
    (("delivery", "takeaway", "doordash", "skip the dishes"), "🥡"),
    (("game",), "🎮"),
    (("book",), "📚"),
    (("movie", "cinema", "entertainment"), "🎬"),
    (("music", "concert"), "🎵"),
    (("gift", "present"), "🎁"),
    (("party", "celebration"), "🎉"),
    (("charity", "donation"), "❤️"),
    (("shopping", "online"), "🛍️"),
    (("insurance",), "🛡️"),
    (("tax",), "🏛️"),
    (("bank", "banking", "service charge", "interest", "atm fee", "transfer fee"), "🏦"),
    (("credit card", "card payment"), "💳"),
    (("salary", "paycheque", "paycheck", "wage", "payroll", "income"), "💵"),
    (("investment", "dividend", "stock", "rrsp", "tfsa"), "📈"),
    (("refund", "rebate", "reimbursement", "cashback", "cash back"), "🔁"),
    (("loan", "debt"), "🤝"),
    (("government", "legal", "immigration", "visa", "passport", "benefit", "ei"), "🏛️"),
    (("family",), "👪"),
    (("laundry",), "🧺"),
    (("moving", "movers"), "🚚"),
    (("conference",), "🎤"),
    (("bonus",), "💰"),
    (("transfer",), "🔄"),
    (("cash", "atm"), "💵"),
    (("saving",), "💰"),
    (("bill", "utility", "utilities"), "🧾"),
    (("shipping", "postage", "parcel", "courier"), "📦"),
]


_ENDINGS = ("", "s", "es", "ies", "y", "ity")  # Pets, Fees, Gifts: not Training (train) or Presentation


def suggest_icon(name):
    """An icon for a category or sub-category name ("" when nothing fits): whole words (with a
    plain plural ending), any case."""
    text = " " + re.sub(r"[^\w]+", " ", (name or "").casefold()) + " "
    for words, icon in _SUGGEST:
        if any(f" {w}{end} " in text for w in words for end in _ENDINGS):
            return icon
    return ""


_qicons = {}


def emoji_icon(emoji):
    """A QIcon drawing ``emoji`` (cached); a null icon for none."""
    if not emoji:
        return QIcon()
    if emoji not in _qicons:
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        font = QFont()
        font.setPixelSize(56)
        p.setFont(font)
        p.drawText(QRect(0, 0, 64, 64), Qt.AlignCenter, emoji)
        p.end()
        _qicons[emoji] = QIcon(pix)
    return _qicons[emoji]


def set_category_icons(combo, db, type_name=None):
    """Put each category's icon beside its name in a category combo (names unchanged)."""
    icons = db.get_icons()["cat_name"]
    for i in range(combo.count()):
        name = combo.itemText(i)
        icon = next((ic for (t, n), ic in icons.items() if n == name and (not type_name or type_name in t)), "")
        combo.setItemIcon(i, emoji_icon(icon))



class IconPickerDialog(QDialog):
    """Pick an emoji from the grid, type any, or No Icon. ``icon``: the choice ("" = none)."""

    def __init__(self, current, about, hint="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Icon")
        self.icon = current or ""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(about))
        if hint:
            h = QLabel(hint)
            h.setProperty("class", "dim-label")
            h.setWordWrap(True)
            layout.addWidget(h)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, emoji in enumerate(PICKER):
            btn = QPushButton(emoji)
            btn.setFixedSize(46, 42)
            btn.setProperty("class", "secondary")
            big = btn.font()
            big.setPixelSize(22)
            btn.setFont(big)
            btn.setToolTip(emoji)
            if emoji == current:
                btn.setStyleSheet("border: 2px solid palette(highlight);")
            btn.clicked.connect(lambda _=None, e=emoji: self._choose(e))
            grid.addWidget(btn, i // 8, i % 8)
        layout.addLayout(grid)
        row = QHBoxLayout()
        self.typed = QLineEdit(current or "")
        self.typed.setPlaceholderText("Or type any emoji (⌃⌘Space opens the emoji picker)")
        self.typed.returnPressed.connect(lambda: self._choose(self.typed.text().strip()))
        use = QPushButton("Use")
        use.setProperty("class", "secondary")
        use.clicked.connect(lambda: self._choose(self.typed.text().strip()))
        row.addWidget(self.typed, 1)
        row.addWidget(use)
        layout.addLayout(row)
        btns = QDialogButtonBox(QDialogButtonBox.Cancel)
        none = btns.addButton("No Icon", QDialogButtonBox.ResetRole)
        none.clicked.connect(lambda: self._choose(""))
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _choose(self, emoji):
        from daftarche.db import clean_icon
        try:
            self.icon = clean_icon(emoji)
        except ValueError as e:
            QMessageBox.warning(self, "Icon", str(e))
            return
        self.accept()

class SuggestIconsDialog(QDialog):
    """Icons for the categories (and clear sub-categories) that have none, from their names:
    each line can be changed or unticked before Save."""

    COL_USE, COL_TYPE, COL_CAT, COL_SUB, COL_ICON = range(5)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Suggest Icons")
        self.setMinimumSize(640, 520)
        layout = QVBoxLayout(self)
        hint = QLabel("Icons for the categories with none, from their names. A sub-category is "
                      "listed only when a different icon fits it better than its category's; "
                      "the others show their category's. Untick a line, or change its icon, "
                      "then Save.")
        hint.setWordWrap(True)
        hint.setProperty("class", "dim-label")
        layout.addWidget(hint)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Type", "Category", "Sub-Category", "Icon"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_SUB, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
                                   | QAbstractItemView.AnyKeyPressed)
        layout.addWidget(self.table, 1)
        self.empty = QLabel("Every category has an icon, or none fits its name.")
        layout.addWidget(self.empty)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.lines = self.suggestions(db)
        for line in self.lines:
            r = self.table.rowCount()
            self.table.insertRow(r)
            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            use.setCheckState(Qt.Checked)
            self.table.setItem(r, self.COL_USE, use)
            for c, text in ((self.COL_TYPE, line["type"]), (self.COL_CAT, line["category"]),
                            (self.COL_SUB, line["sub"] or "—")):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(r, c, item)
            icon_item = QTableWidgetItem(line["icon"])
            big = icon_item.font()
            big.setPixelSize(20)
            icon_item.setFont(big)
            icon_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, self.COL_ICON, icon_item)
        self.empty.setVisible(not self.lines)

    @staticmethod
    def suggestions(db):
        """[{kind: "cat"|"sub", id, type, category, sub, icon}] for what has no icon yet."""
        from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB
        out = []
        for c in db.get_categories():
            if c["name"] == UNCATEGORIZED_CAT or not c["type_name"]:
                continue
            cat_icon = c["icon"] or suggest_icon(c["name"])
            if not c["icon"] and cat_icon:
                out.append({"kind": "cat", "id": c["id"], "type": c["type_name"], "category": c["name"],
                            "sub": "", "icon": cat_icon})
            for s in db.get_subcategories(c["id"]):
                if s["icon"] or s["name"] == UNCATEGORIZED_SUB:
                    continue
                icon = suggest_icon(s["name"])
                if icon and icon != cat_icon:
                    out.append({"kind": "sub", "id": s["id"], "type": c["type_name"], "category": c["name"],
                                "sub": s["name"], "icon": icon})
        return out

    def save(self):
        from daftarche.db import clean_icon
        for r, line in enumerate(self.lines):
            try:
                clean_icon(self.table.item(r, self.COL_ICON).text())
            except ValueError as e:
                where = line["category"] + (f" › {line['sub']}" if line["sub"] else "")
                QMessageBox.warning(self, "Suggest Icons", f"{where}: {e}")
                return
        with self.db.transaction():
            for r, line in enumerate(self.lines):
                if self.table.item(r, self.COL_USE).checkState() != Qt.Checked:
                    continue
                icon = (self.table.item(r, self.COL_ICON).text() or "").strip()
                if not icon:
                    continue
                if line["kind"] == "cat":
                    self.db.set_category_icon(line["id"], icon)
                else:
                    self.db.set_subcategory_icon(line["id"], icon)
        self.accept()
