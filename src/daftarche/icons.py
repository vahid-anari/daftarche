"""Category icons: an emoji per category (and, if wanted, per sub-category).

The names stay as they are (search, filters and rules use them); the icon is drawn beside them.
"""
import re

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
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
    """Pick an emoji from the grid, type any, or No Icon. ``icon``: the choice ("" = none).
    ``suggested``: one from the name (suggest_icon), ready to use when there is none yet."""

    def __init__(self, current, about, hint="", parent=None, suggested=""):
        super().__init__(parent)
        self.setWindowTitle("Icon")
        self.icon = current or ""
        offer = "" if current else (suggested or "")
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
            if emoji == (current or offer):
                btn.setStyleSheet("border: 2px solid palette(highlight);")
            btn.clicked.connect(lambda _=None, e=emoji: self._choose(e))
            grid.addWidget(btn, i // 8, i % 8)
        layout.addLayout(grid)
        if offer:
            tip = QLabel(f"Suggested from its name: {offer}  — press Use (or Return) to take it.")
            tip.setProperty("class", "dim-label")
            layout.addWidget(tip)
        row = QHBoxLayout()
        self.typed = QLineEdit(current or offer)
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
