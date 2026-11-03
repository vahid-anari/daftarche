"""Category icons: an emoji per category (and, if wanted, per sub-category).

The names stay as they are (search, filters and rules use them); the icon is drawn beside them.
"""
import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
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


_logo_db = None


def use_logos(db):
    """Where the logos come from when an icon is "logo:<merchant>" (the database open now)."""
    global _logo_db
    _logo_db = db


def emoji_icon(emoji):
    """A QIcon drawing ``emoji`` (cached), or a merchant's logo for "logo:<merchant>"; a null
    icon for none."""
    if not emoji:
        return QIcon()
    if emoji.startswith("logo:"):
        from daftarche.logos import logo_icon
        return logo_icon(_logo_db.logo_for(emoji[5:]) if _logo_db is not None else None)
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


_blank = None


def blank_icon():
    """An empty picture as big as an icon: a name without one stays in line with those that have one."""
    global _blank
    if _blank is None:
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        _blank = QIcon(pix)
    return _blank


def set_category_icons(combo, db, type_name=None):
    """Put each category's icon beside its name in a category combo (names unchanged)."""
    icons = db.get_icons()["cat_name"]
    for i in range(combo.count()):
        name = combo.itemText(i)
        icon = next((ic for (t, n), ic in icons.items() if n == name and (not type_name or type_name in t)), "")
        combo.setItemIcon(i, emoji_icon(icon))



# ── every emoji, to look for by name (the grid has only the common ones) ──────
_EMOJI_RANGES = ((0x1F300, 0x1F5FF), (0x1F600, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F900, 0x1F9FF),
                 (0x1FA70, 0x1FAFF))
_EMOJI_BMP = "☕☀☁☂☔⚡⛄⛅⚽⚾⛳⛵⛺⛽✈✉✏✂❤⭐⌚⌛☎♻⚓⚠⚙⚖⚛✅❌❓❗➕⏰⏳☘♨⛪⛲⛱⛷⛸⛹⛰⛩⛔✋✌✍✨❄"
"""Emoji below U+1F300 (most of that block are plain symbols, drawn as text)."""
_ALIASES = {
    "🚗": "car", "🚙": "car suv", "🏎️": "car race", "🚓": "car", "🚕": "car", "💵": "money cash",
    "💰": "money", "💸": "money", "🪙": "money", "💴": "money cash", "💶": "money cash", "💷": "money cash",
    "🏠": "house", "🏡": "house", "📱": "phone cell", "☎️": "phone", "🍽️": "food dinner restaurant",
    "🛒": "grocery shopping", "🎂": "birthday", "❤️": "heart love", "✈️": "plane flight travel",
    "☕": "coffee", "⭐": "star", "⛽": "gas fuel", "✂️": "scissors haircut", "✏️": "pencil",
}
_all_emoji = None


def all_emoji():
    """[(emoji, the words to find it by)] from Python's Unicode names, plus a few everyday words."""
    global _all_emoji
    if _all_emoji is None:
        import unicodedata
        extra = {}
        for words, icon in _SUGGEST:
            extra.setdefault(icon, []).extend(words)
        for icon, words in _ALIASES.items():
            extra.setdefault(icon, []).append(words)
        chars = [ch + "\ufe0f" for ch in _EMOJI_BMP]
        for start, end in _EMOJI_RANGES:
            for cp in range(start, end + 1):
                if 0x1F3FB <= cp <= 0x1F3FF:
                    continue  # skin tones: they go after another emoji
                chars.append(chr(cp))
        out = []
        for emoji in chars:
            name = unicodedata.name(emoji[0], "")
            if name:
                words = [name.lower()] + extra.get(emoji, []) + extra.get(emoji.rstrip("\ufe0f"), []) + \
                        extra.get(emoji + "\ufe0f", [])
                out.append((emoji, " ".join(words)))
        _all_emoji = out
    return _all_emoji


def search_emoji(text, limit=96):
    """The emoji whose names have all the words of ``text`` ("car" → 🚗 🚓 🏎️ …), the closest
    first: a whole word before part of one."""
    words = text.lower().split()
    if not words:
        return []
    found = [(e, k) for e, k in all_emoji() if all(w in k for w in words)]
    found.sort(key=lambda ek: 0 if all(re.search(rf"\b{re.escape(w)}\b", ek[1]) for w in words) else 1)
    return [e for e, _ in found[:limit]]


class IconPickerDialog(QDialog):
    """A category's (or sub-category's) name and icon in one window. ``name``: the name to edit
    ("" for a new one; None: no name field, the icon only). Pick an emoji in the grid, look for
    any other by name, paste one, or No Icon; OK keeps both. After OK: ``name`` and ``icon`` ("" = none).
    ``suggest``: name → an icon that suits it (suggest_icon), offered while there is none.
    ``name_locked``: the name is shown but cannot change (Transfer › Loans)."""

    def __init__(self, current, about, hint="", parent=None, suggested="", name=None, suggest=None,
                 name_locked=False, title="Icon", logos=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.icon = current or ""
        self.name = name
        self._suggest = suggest or (lambda _name: suggested or "")
        self._buttons = {}
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(14)
        self.preview = QLabel()  # the icon chosen, large
        self.preview.setFixedSize(56, 56)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("border: 1px dashed palette(mid); border-radius: 10px;")
        self.preview.setToolTip("The icon chosen (an empty frame: none)")
        top.addWidget(self.preview)
        head = QVBoxLayout()
        head.setSpacing(6)
        head.addWidget(QLabel(about))
        self.name_field = None
        if name is not None:
            self.name_field = QLineEdit(name)
            self.name_field.setPlaceholderText("Name")
            self.name_field.setReadOnly(name_locked)
            if name_locked:
                self.name_field.setToolTip("This name is kept: the Loans window reads it.")
            self.name_field.textChanged.connect(lambda _: self._show_suggestion())
            head.addWidget(self.name_field)
        if hint:
            h = QLabel(hint)
            h.setProperty("class", "dim-label")
            h.setWordWrap(True)
            head.addWidget(h)
        top.addLayout(head, 1)
        layout.addLayout(top)

        self._logo_buttons = {}
        if logos:  # the merchants' logos saved (Manage › Merchants › Logo…): one can be the icon
            from daftarche.logos import logo_icon
            head_logos = QLabel("Logos")
            head_logos.setProperty("class", "dim-label")
            layout.addWidget(head_logos)
            logo_grid = QGridLayout()
            logo_grid.setSpacing(4)
            for i, (merchant, data) in enumerate(logos.items()):
                btn = QPushButton()
                btn.setIcon(logo_icon(data))
                btn.setIconSize(QSize(28, 28))
                btn.setFixedSize(46, 42)
                btn.setProperty("class", "secondary")
                btn.setToolTip(merchant)
                btn.clicked.connect(lambda _=None, m=merchant: self._pick("logo:" + m))
                logo_grid.addWidget(btn, i // 8, i % 8)
                self._logo_buttons["logo:" + merchant] = btn
            layout.addLayout(logo_grid)
            head_emoji = QLabel("Emoji")
            head_emoji.setProperty("class", "dim-label")
            layout.addWidget(head_emoji)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, emoji in enumerate(PICKER):
            btn = QPushButton()  # drawn as a picture: as text, the emoji were cut off
            btn.setIcon(emoji_icon(emoji))
            btn.setIconSize(QSize(26, 26))
            btn.setFixedSize(46, 42)
            btn.setProperty("class", "secondary")
            btn.setToolTip(emoji)
            btn.clicked.connect(lambda _=None, e=emoji: self._pick(e))
            grid.addWidget(btn, i // 8, i % 8)
            self._buttons[emoji] = btn
        layout.addLayout(grid)

        self.tip = QLabel()
        self.tip.setProperty("class", "dim-label")
        self.use_tip = QPushButton("Use It")
        self.use_tip.setProperty("class", "secondary")
        self.use_tip.clicked.connect(lambda: self._pick(self._offer))
        tip_row = QHBoxLayout()
        tip_row.addWidget(self.tip, 1)
        tip_row.addWidget(self.use_tip)
        layout.addLayout(tip_row)

        self.search = QLineEdit()  # every emoji, by name: no window of the system's (Esc closed this one)
        self.search.setPlaceholderText("🔍  Look for any emoji by name: car, cake, money…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._look_for)
        layout.addWidget(self.search)
        self.found = QListWidget()
        self.found.setViewMode(QListView.IconMode)
        self.found.setIconSize(QSize(26, 26))
        self.found.setGridSize(QSize(46, 42))
        self.found.setMovement(QListView.Static)
        self.found.setResizeMode(QListView.Adjust)
        self.found.setFixedHeight(3 * 42 + 8)
        self.found.itemClicked.connect(lambda item: self._pick(item.data(Qt.UserRole)))
        self.found.hide()
        layout.addWidget(self.found)
        self.nothing = QLabel("No emoji with that name.")
        self.nothing.setProperty("class", "dim-label")
        self.nothing.hide()
        layout.addWidget(self.nothing)

        row = QHBoxLayout()
        self.typed = QLineEdit(current or "")
        self.typed.setPlaceholderText("Or paste an emoji")
        self.typed.setStyleSheet("font-size: 22px; padding: 4px 8px;")  # an emoji is taller than a line of text
        self.typed.setMinimumHeight(44)
        self.typed.textChanged.connect(lambda text: self._pick(text.strip(), from_field=True))
        row.addWidget(self.typed, 1)
        layout.addLayout(row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        none = btns.addButton("No Icon", QDialogButtonBox.ResetRole)
        none.clicked.connect(lambda: self._pick(""))
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self._pick(self.icon)
        self._show_suggestion()
        if self.name_field is not None and not name_locked:
            self.name_field.setFocus()

    # ── the choice ───────────────────────────────────────────────────────────
    def _pick(self, emoji, from_field=False):
        self.icon = emoji or ""
        shown = "" if self.icon.startswith("logo:") else self.icon  # a logo is no text for the field
        if not from_field and self.typed.text().strip() != shown:
            self.typed.blockSignals(True)
            self.typed.setText(shown)
            self.typed.blockSignals(False)
        for e, btn in {**self._buttons, **self._logo_buttons}.items():
            btn.setStyleSheet("border: 2px solid palette(highlight);" if e.casefold() == self.icon.casefold() else "")
        if self.icon:
            self.preview.setPixmap(emoji_icon(self.icon).pixmap(QSize(48, 48)))
            self.preview.setText("")
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("")
        self._show_suggestion()

    def _show_suggestion(self):
        name = self.name_field.text() if self.name_field is not None else ""
        self._offer = "" if self.icon else (self._suggest(name) or "")
        self.tip.setText(f"Suggested from its name: {self._offer}" if self._offer else "")
        self.tip.setVisible(bool(self._offer))
        self.use_tip.setVisible(bool(self._offer))

    def _look_for(self, text):
        self.found.clear()
        for emoji in search_emoji(text):
            item = QListWidgetItem(emoji_icon(emoji), "")
            item.setData(Qt.UserRole, emoji)
            item.setToolTip(emoji)
            item.setSizeHint(QSize(44, 40))
            self.found.addItem(item)
        looking = bool(text.strip())
        self.found.setVisible(looking and self.found.count() > 0)
        self.nothing.setVisible(looking and self.found.count() == 0)

    def _accept(self):
        from daftarche.db import clean_icon
        if self.name_field is not None:
            self.name = " ".join(self.name_field.text().split())
            if not self.name:
                QMessageBox.warning(self, self.windowTitle(), "Write a name.")
                return
        try:
            self.icon = clean_icon(self.icon)
        except ValueError as e:
            QMessageBox.warning(self, self.windowTitle(), str(e))
            return
        self.accept()
