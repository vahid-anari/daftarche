"""Category icons: an emoji per category (and, if wanted, per sub-category).

The names stay as they are (search, filters and rules use them); the icon is drawn beside them.
"""
import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QStyledItemDelegate, QStyleOptionViewItem,
    QVBoxLayout, QWidget,
)

EMOJI_ROWS = 6  # rows of emoji in sight in the icon window; more scroll (the window stays short)
LOGO_COLUMNS = 6  # logos and pictures across, in the icon window's right-hand column
_CELL_H, _GAP = 42, 4


def _scroll_grid(grid, rows_shown):
    """A grid of buttons in a frameless area that scrolls up and down, ``rows_shown`` high."""
    host = QWidget()
    grid.setContentsMargins(0, 0, 0, 0)
    host.setLayout(grid)
    area = QScrollArea()
    area.setFrameShape(QFrame.NoFrame)
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(host)
    rows = max(1, grid.rowCount())
    area.setFixedHeight(min(rows, rows_shown) * (_CELL_H + _GAP) - _GAP)
    area.setMinimumWidth(host.sizeHint().width() + (area.verticalScrollBar().sizeHint().width() if rows > rows_shown else 0))
    return area


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
    if emoji.startswith("pic:"):  # a picture of its own (category_pictures)
        from daftarche.logos import logo_icon
        number = emoji[4:]
        return logo_icon(_logo_db.picture(int(number)) if _logo_db is not None and number.isdigit() else None)
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


PERSON = "👤"


def merchant_icon(image, person=False):
    """Beside a merchant's name: its logo; 👤 for a person without one; else a space, so the
    names stay in line."""
    if image:
        from daftarche.logos import logo_icon
        return logo_icon(image)
    return emoji_icon(PERSON) if person else blank_icon()


def merchant_icon_for(db):
    """name → its icon (logo, 👤 or a space; None when no merchant has either): for lists of merchants."""
    logos = {name.casefold(): image for name, image in db.get_logos().items()}
    people = db.get_people()
    if not logos and not people:
        return lambda _name: None
    return lambda name: merchant_icon(logos.get((name or "").strip().casefold()),
                                      (name or "").strip().casefold() in people)


def name_icon_for(db, kind):
    """name → its icon (an emoji or a picture; a space for one without; None when none has one), for
    lists of category (``kind`` "cat") or sub-category ("sub") names of any type or category: the
    first icon given to that name."""
    icons = {}
    for (_owner, name), icon in db.get_icons()["cat_name" if kind == "cat" else "sub_name"].items():
        icons.setdefault(name, icon)
    if not icons:
        return lambda _name: None
    return lambda name: emoji_icon(icons[name]) if name in icons else blank_icon()


class _ListIcons(QStyledItemDelegate):
    """Draws an icon beside each name in a combo's list only: a combo one can type in shows its
    current item's icon beside the text typed, and that would be another merchant's."""

    def __init__(self, icon_for, parent=None):
        super().__init__(parent)
        self._icon_for = icon_for

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        icon = self._icon_for(index.data(Qt.DisplayRole))
        if icon is not None:
            option.icon = icon
            option.features |= QStyleOptionViewItem.HasDecoration


def set_merchant_icons(combo, db):
    """Each merchant's logo (or 👤) beside its name in a merchant combo's list (names unchanged)."""
    if db.get_logos() or db.get_people():
        list_icons(combo, merchant_icon_for(db))


def list_icons(combo, icon_for):
    """``icon_for`` (name → QIcon or None) beside the names of a combo: in its list only when one
    can type in it (else the text typed would show the icon of the item chosen before it)."""
    if combo.isEditable():
        combo.setItemDelegate(_ListIcons(icon_for, combo))
        return
    for i in range(combo.count()):
        icon = icon_for(combo.itemText(i))
        if icon is not None:
            combo.setItemIcon(i, icon)


def set_category_icons(combo, db, type_name=None):
    """Put each category's icon beside its name in a category combo (names unchanged)."""
    icons = db.get_icons()["cat_name"]

    def icon_for(name):
        icon = next((ic for (t, n), ic in icons.items() if n == name and (not type_name or type_name in t)), "")
        return emoji_icon(icon)
    list_icons(combo, icon_for)



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
                 name_locked=False, title="Icon", logos=None, db=None):
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

        body = QHBoxLayout()  # emoji on the left; logos and pictures on the right
        body.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(8)
        body.addLayout(left, 1)
        self._db = db
        self._logos = dict(logos if logos is not None else (db.get_logos() if db is not None else {}))
        self._added = []  # pictures added here: taken away again on Cancel
        self._logo_buttons = {}
        self.logo_area = None
        if db is not None or self._logos:
            right = QVBoxLayout()
            right.setSpacing(8)
            head_logos = QLabel("Logos & Pictures")
            head_logos.setProperty("class", "dim-label")
            right.addWidget(head_logos)
            self.find_logo = QLineEdit()
            self.find_logo.setPlaceholderText("🔍  A merchant's logo, by name")
            self.find_logo.setClearButtonEnabled(True)
            self.find_logo.textChanged.connect(lambda _text: self._fill_logos())
            right.addWidget(self.find_logo)
            self._logo_grid = QGridLayout()
            self._logo_grid.setSpacing(_GAP)
            self._logo_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            host = QWidget()
            self._logo_grid.setContentsMargins(0, 0, 0, 0)
            host.setLayout(self._logo_grid)
            self.logo_area = QScrollArea()
            self.logo_area.setFrameShape(QFrame.NoFrame)
            self.logo_area.setWidgetResizable(True)
            self.logo_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.logo_area.setWidget(host)
            self.logo_area.setFixedHeight(EMOJI_ROWS * (_CELL_H + _GAP) - _GAP)  # as tall as the emoji
            self.logo_area.setMinimumWidth(LOGO_COLUMNS * (46 + _GAP)
                                           + self.logo_area.verticalScrollBar().sizeHint().width())
            right.addWidget(self.logo_area)
            if db is not None:  # a picture of its own: not a merchant's logo
                add_row = QHBoxLayout()
                pick = QPushButton("Choose a Picture…")
                pick.setProperty("class", "secondary")
                pick.setToolTip("A picture file as the icon (kept in your data; the phone shows only emoji)")
                pick.clicked.connect(self._choose_picture)
                web = QPushButton("From a Website…")
                web.setProperty("class", "secondary")
                web.setToolTip("A website's icon as the icon, as Get Logo in Edit Merchant")
                web.clicked.connect(self._picture_from_web)
                add_row.addWidget(pick)
                add_row.addWidget(web)
                right.addLayout(add_row)
            right.addStretch()
            body.addLayout(right)
            self._fill_logos()
        head_emoji = QLabel("Emoji")
        head_emoji.setProperty("class", "dim-label")
        left.addWidget(head_emoji)
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
        self.emoji_area = _scroll_grid(grid, EMOJI_ROWS)
        left.addWidget(self.emoji_area)

        self.tip = QLabel()
        self.tip.setProperty("class", "dim-label")
        self.use_tip = QPushButton("Use It")
        self.use_tip.setProperty("class", "secondary")
        self.use_tip.clicked.connect(lambda: self._pick(self._offer))
        tip_row = QHBoxLayout()
        tip_row.addWidget(self.tip, 1)
        tip_row.addWidget(self.use_tip)
        left.addLayout(tip_row)

        self.search = QLineEdit()  # every emoji, by name: no window of the system's (Esc closed this one)
        self.search.setPlaceholderText("🔍  Look for any emoji by name: car, cake, money…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._look_for)
        left.addWidget(self.search)
        self.found = QListWidget()
        self.found.setViewMode(QListView.IconMode)
        self.found.setIconSize(QSize(26, 26))
        self.found.setGridSize(QSize(46, 42))
        self.found.setMovement(QListView.Static)
        self.found.setResizeMode(QListView.Adjust)
        self.found.setFixedHeight(3 * 42 + 8)
        self.found.itemClicked.connect(lambda item: self._pick(item.data(Qt.UserRole)))
        self.found.hide()
        left.addWidget(self.found)
        self.nothing = QLabel("No emoji with that name.")
        self.nothing.setProperty("class", "dim-label")
        self.nothing.hide()
        left.addWidget(self.nothing)

        self.typed = QLineEdit(current or "")  # the usual font size: the icon chosen shows large above
        self.typed.setPlaceholderText("Or paste an emoji")
        self.typed.textChanged.connect(lambda text: self._pick(text.strip(), from_field=True))
        left.addWidget(self.typed)
        left.addStretch()
        layout.addLayout(body)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        none = btns.addButton("No Icon", QDialogButtonBox.ResetRole)
        none.clicked.connect(lambda: self._pick(""))
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        screen = (parent.screen() if parent is not None else None) or QApplication.primaryScreen()
        if screen is not None:  # never taller than the screen above the Dock
            self.setMaximumHeight(screen.availableGeometry().height() - 40)
        self._pick(self.icon)
        self._show_suggestion()
        if self.name_field is not None and not name_locked:
            self.name_field.setFocus()

    _chosen = None  # (its button, the area it is in)

    def showEvent(self, event):
        super().showEvent(event)
        if self._chosen:  # laid out only now: the current icon's row in sight
            btn, area = self._chosen
            QTimer.singleShot(0, lambda: area.ensureWidgetVisible(btn))

    # ── the choice ───────────────────────────────────────────────────────────
    def _pick(self, emoji, from_field=False):
        self.icon = emoji or ""
        shown = "" if self.icon.startswith(("logo:", "pic:")) else self.icon  # a picture is no text for the field
        if not from_field and self.typed.text().strip() != shown:
            self.typed.blockSignals(True)
            self.typed.setText(shown)
            self.typed.blockSignals(False)
        for e, btn in {**self._buttons, **self._logo_buttons}.items():
            chosen = e.casefold() == self.icon.casefold()
            btn.setStyleSheet("border: 2px solid palette(highlight);" if chosen else "")
            if chosen:  # in sight, also when it is in a row further down
                self._chosen = btn, (self.logo_area if e.startswith(("logo:", "pic:")) else self.emoji_area)
                self._chosen[1].ensureWidgetVisible(btn)
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

    # ── logos and pictures ────────────────────────────────────────────────────
    def _fill_logos(self):
        """The pictures added (first) and the merchants' logos whose name has what is in the find
        field, in rows of LOGO_COLUMNS; the one chosen framed."""
        from daftarche.logos import logo_icon
        while self._logo_grid.count():
            item = self._logo_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._logo_buttons = {}
        text = self.find_logo.text().strip().casefold()
        pictures = self._db.get_pictures() if self._db is not None else {}
        entries = [(f"pic:{pid}", name or "A picture", image, True) for pid, (name, image) in pictures.items()
                   if not text or text in (name or "").casefold()]
        entries += [(f"logo:{m}", m, image, False) for m, image in sorted(self._logos.items(), key=lambda x: x[0].casefold())
                    if not text or text in m.casefold()]
        row = 0
        for title, group in (("Yours", [e for e in entries if e[3]]), ("Merchants", [e for e in entries if not e[3]])):
            if not group:
                continue
            if pictures:  # two groups: a line saying which
                label = QLabel(title)
                label.setProperty("class", "dim-label")
                self._logo_grid.addWidget(label, row, 0, 1, LOGO_COLUMNS)
                row += 1
            for i, (key, name, image, own) in enumerate(group):
                btn = QPushButton()
                btn.setIcon(logo_icon(image))
                btn.setIconSize(QSize(28, 28))
                btn.setFixedSize(46, 42)
                btn.setProperty("class", "secondary")
                btn.setToolTip(name + ("  (right-click: Delete Picture)" if own else ""))
                btn.clicked.connect(lambda _=None, k=key: self._pick(k))
                if own:
                    btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    btn.customContextMenuRequested.connect(lambda _pos, k=key, b=btn: self._picture_menu(k, b))
                self._logo_grid.addWidget(btn, row + i // LOGO_COLUMNS, i % LOGO_COLUMNS)
                self._logo_buttons[key] = btn
            row += (len(group) + LOGO_COLUMNS - 1) // LOGO_COLUMNS
        if not entries:
            none = QLabel("No logo with that name." if text else
                          "No logos yet: give a merchant one (Edit Merchant), or add a picture below.")
            none.setProperty("class", "dim-label")
            none.setWordWrap(True)
            self._logo_grid.addWidget(none, 0, 0, 1, LOGO_COLUMNS)
        if hasattr(self, "typed"):  # built: the one chosen framed again
            self._pick(self.icon)

    def _add_picture(self, name, image):
        pid = self._db.add_picture(name, image)
        self._added.append(pid)
        self.find_logo.clear()
        self._fill_logos()
        self._pick(f"pic:{pid}")

    def _choose_picture(self):
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        from daftarche.logos import LogoError, normalise
        path, _ = QFileDialog.getOpenFileName(self, "A Picture for the Icon", "",
                                              "Pictures (*.png *.jpg *.jpeg *.gif *.bmp *.ico *.webp *.svg)")
        if not path:
            return
        try:
            image = normalise(Path(path).read_bytes())
        except (OSError, LogoError, ValueError) as exc:
            QMessageBox.warning(self, "Picture", f"That file cannot be used as a picture:\n{exc}")
            return
        self._add_picture(Path(path).stem, image)

    def _picture_from_web(self):
        from daftarche.logos import LogoDialog
        name = self.name_field.text().strip() if self.name_field is not None else ""
        dlg = LogoDialog(name or "the icon", parent=self)
        dlg.setWindowTitle("A Picture from a Website")
        if dlg.exec() and dlg.image:
            site = LogoDialog._site_of(dlg.source) or name
            self._add_picture(site, dlg.image)

    def _picture_menu(self, key, button):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        delete = menu.addAction("Delete Picture…")
        if menu.exec(button.mapToGlobal(button.rect().bottomLeft())) is not delete:
            return
        pid = int(key[4:])
        uses = self._db.picture_uses(pid)
        more = f"\n\n{uses} categor{'y has' if uses == 1 else 'ies have'} it as the icon: they will have none." \
            if uses else ""
        if QMessageBox.question(self, "Delete Picture", "Delete this picture?" + more,
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._db.delete_picture(pid)
        if self.icon == key:
            self.icon = ""
        self._fill_logos()

    def reject(self):
        """Cancel: the pictures added here are taken away again (no category has them)."""
        if self._db is not None:
            for pid in self._added:
                if not self._db.picture_uses(pid):
                    self._db.delete_picture(pid)
        self._added = []
        super().reject()

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
