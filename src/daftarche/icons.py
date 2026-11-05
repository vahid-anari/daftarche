"""Category icons: an emoji per category (and, if wanted, per sub-category).

The names stay as they are (search, filters and rules use them); the icon is drawn beside them.
"""
import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStyledItemDelegate,
    QStyleOptionViewItem, QVBoxLayout, QWidget,
)

EMOJI_ROWS = 6  # rows of emoji in sight in the icon window; more scroll (the window stays short)
LOGO_COLUMNS = 6  # logos and pictures across, in the icon window's right-hand column
_CELL_H, _GAP = 42, 4


_CELL_W = 46


class _FlowArea(QScrollArea):
    """Buttons in lines that go on to the next line when there is no room, in a frameless area
    that scrolls up and down: as wide as ``columns`` and ``rows`` high at first, and growing with
    the window (more in a line, and more lines in sight) instead of spreading them apart."""

    def __init__(self, columns, rows, grow=True):
        super().__init__()
        from daftarche.widgets import FlowLayout

        class Flow(FlowLayout):  # its height is that for the width it has (not for one button a line)
            def minimumSize(self):
                return QSize(_CELL_W, 0)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        self.flow = Flow(host, spacing=_GAP, line_spacing=_GAP)
        self.setWidget(host)
        bar = self.verticalScrollBar().sizeHint().width()
        self._hint = QSize(columns * (_CELL_W + _GAP) - _GAP + bar, rows * (_CELL_H + _GAP) - _GAP)
        self.setMinimumSize(self._hint)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding if grow else QSizePolicy.Fixed)

    def sizeHint(self):
        return self._hint

    def add(self, widget):
        self.flow.addWidget(widget)

    def clear(self):
        while self.flow.count():
            item = self.flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.widget().updateGeometry()


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
        if db is not None:  # its pictures and logos are drawn from this database
            use_logos(db)
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
            self.yours_head = QLabel("Yours")
            self.yours_head.setProperty("class", "dim-label")
            right.addWidget(self.yours_head)
            self.yours_area = _FlowArea(LOGO_COLUMNS, 1, grow=False)  # pictures of your own, the first
            right.addWidget(self.yours_area)
            self.merchants_head = QLabel("Merchants")
            self.merchants_head.setProperty("class", "dim-label")
            right.addWidget(self.merchants_head)
            self.logo_area = _FlowArea(LOGO_COLUMNS, EMOJI_ROWS - 2)
            right.addWidget(self.logo_area, 1)
            self.none_logos = QLabel()
            self.none_logos.setProperty("class", "dim-label")
            self.none_logos.setWordWrap(True)
            right.addWidget(self.none_logos)
            if db is not None:  # a picture of its own: not a merchant's logo
                web = QHBoxLayout()
                web.addWidget(QLabel("Website:"))
                self.site = QLineEdit()
                self.site.setPlaceholderText("its icon as a picture, e.g. example.com")
                self.site.returnPressed.connect(self._picture_from_web)
                web.addWidget(self.site, 1)
                self.btn_site = QPushButton("Get")
                self.btn_site.setProperty("class", "secondary")
                self.btn_site.setToolTip("The website's icon, as a picture of your own (as Get Logo in Edit Merchant)")
                self.btn_site.clicked.connect(self._picture_from_web)
                web.addWidget(self.btn_site)
                right.addLayout(web)
                pick = QPushButton("Choose a Picture…")
                pick.setProperty("class", "secondary")
                pick.setToolTip("A picture file as the icon (kept in your data; the phone shows only emoji)")
                pick.clicked.connect(self._choose_picture)
                right.addWidget(pick)
                self._web_job = None
                self._web_poll = QTimer(self)
                self._web_poll.setInterval(100)
                self._web_poll.timeout.connect(self._web_collect)
            body.addLayout(right, 1)
            self._fill_logos()
        head_emoji = QLabel("Emoji")
        head_emoji.setProperty("class", "dim-label")
        left.addWidget(head_emoji)
        self.emoji_area = _FlowArea(8, EMOJI_ROWS)
        for emoji in PICKER:
            btn = QPushButton()  # drawn as a picture: as text, the emoji were cut off
            btn.setIcon(emoji_icon(emoji))
            btn.setIconSize(QSize(26, 26))
            btn.setFixedSize(_CELL_W, _CELL_H)
            btn.setProperty("class", "secondary")
            btn.setToolTip(emoji)
            btn.clicked.connect(lambda _=None, e=emoji: self._pick(e))
            self.emoji_area.add(btn)
            self._buttons[emoji] = btn
        left.addWidget(self.emoji_area, 1)

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
        layout.addLayout(body, 1)

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
        """The pictures added (Yours) and the merchants' logos whose name has what is in the find
        field; the one chosen framed."""
        from daftarche.logos import logo_icon
        self.yours_area.clear()
        self.logo_area.clear()
        self._logo_buttons = {}
        text = self.find_logo.text().strip().casefold()
        pictures = self._db.get_pictures() if self._db is not None else {}
        yours = [(f"pic:{pid}", name or "A picture", image) for pid, (name, image) in pictures.items()
                 if not text or text in (name or "").casefold()]
        theirs = [(f"logo:{m}", m, image) for m, image in sorted(self._logos.items(), key=lambda x: x[0].casefold())
                  if not text or text in m.casefold()]
        for area, group, own in ((self.yours_area, yours, True), (self.logo_area, theirs, False)):
            for key, name, image in group:
                btn = QPushButton()
                btn.setIcon(logo_icon(image))
                btn.setIconSize(QSize(28, 28))
                btn.setFixedSize(_CELL_W, _CELL_H)
                btn.setProperty("class", "secondary")
                btn.setToolTip(name + ("  (right-click: Delete Picture)" if own else ""))
                btn.clicked.connect(lambda _=None, k=key: self._pick(k))
                if own:
                    btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    btn.customContextMenuRequested.connect(lambda _pos, k=key, b=btn: self._picture_menu(k, b))
                area.add(btn)
                self._logo_buttons[key] = btn
        for widget in (self.yours_head, self.yours_area):
            widget.setVisible(bool(yours))
        self.merchants_head.setVisible(bool(theirs) and bool(yours))
        self.none_logos.setText("" if theirs or yours else (
            "No logo with that name." if text else
            "No logos yet: give a merchant one (Edit Merchant), or add a picture below."))
        self.none_logos.setVisible(not theirs and not yours)
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
        """Website: Get — its icon, got in the background (pressed again: Cancel), as a picture of
        your own."""
        import threading

        from daftarche.logos import fetch_within
        if self._web_job is not None:  # Cancel
            self._web_stop()
            return
        site = self.site.text().strip()
        if not site:
            return
        state = {"done": False}

        def work():
            try:
                state["result"] = fetch_within(site)
            except Exception as exc:  # LogoError, no connection
                state["error"] = exc
            state["done"] = True
        self._web_job = (site, state)
        threading.Thread(target=work, daemon=True).start()
        self.btn_site.setText("Cancel")
        self._web_poll.start()

    def _web_stop(self):
        self._web_job = None
        self._web_poll.stop()
        self.btn_site.setText("Get")

    def _web_collect(self):
        from daftarche.logos import LogoError, LogoDialog
        if self._web_job is None or not self._web_job[1]["done"]:
            return
        site, state = self._web_job
        self._web_stop()
        if "error" in state:
            error = state["error"]
            QMessageBox.warning(self, "Picture", str(error) if isinstance(error, LogoError) else
                                f"No icon found at {site}: the site did not answer in time, or there is no connection.")
            return
        image, source = state["result"]
        self._add_picture(LogoDialog._site_of(source) or site, image)
        self.site.clear()

    def web_busy(self):
        """A website's icon is being got (for tests)."""
        return getattr(self, "_web_job", None) is not None

    def done(self, result):
        if getattr(self, "_web_poll", None) is not None:
            self._web_stop()
        super().done(result)

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
