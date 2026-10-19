"""Choosing tags: a list to tick, with a box on top that finds a tag or adds a new one.

A new tag is shown ticked with a green "New" and saved only when the window is accepted.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from daftarche.style import get_settings
from daftarche.widgets import plain_label


class TagChecklist(QWidget):
    def __init__(self, names, checked=(), parent=None):
        super().__init__(parent)
        self._existing = list(names)
        self._checks = {}  # name → checkbox
        self._new = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find a tag, or type a new one")
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._filter)
        self.find.returnPressed.connect(self._enter)
        layout.addWidget(self.find)
        self.add_btn = QPushButton()
        self.add_btn.setProperty("class", "secondary")
        self.add_btn.clicked.connect(self._add_typed)
        self.add_btn.hide()
        layout.addWidget(self.add_btn)
        btn_row = QHBoxLayout()
        for text, state in (("✓ All", True), ("✕ None", False)):
            b = QPushButton(text)
            b.setProperty("class", "secondary")
            b.setFixedHeight(28)
            b.clicked.connect(lambda _=False, st=state: self.set_all(st))
            btn_row.addWidget(b)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        self._list = QVBoxLayout(host)
        self._list.setSpacing(4)
        self._list.setContentsMargins(4, 4, 4, 4)
        self._list.addStretch()
        scroll.setWidget(host)
        scroll.setMinimumHeight(min(len(self._existing) * 28 + 16, 240) if self._existing else 60)
        layout.addWidget(scroll, 1)
        checked = set(checked)
        for name in self._existing:
            self._add_box(name, name in checked)

    def _add_box(self, name, checked, new=False):
        cb = QCheckBox(plain_label(name))
        cb.setChecked(checked)
        row = QHBoxLayout()
        row.addWidget(cb)
        if new:
            mark = QLabel("New")
            mark.setStyleSheet(f"color: {get_settings().get('income') or '#2ecc71'}; font-weight: bold;")
            mark.setToolTip("Not there yet: added when you press Save")
            row.addWidget(mark)
        row.addStretch()
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self._list.insertWidget(self._list.count() - 1, holder)
        self._checks[name] = (cb, holder)

    def _match(self, text):
        return next((n for n in self._checks if n.casefold() == text.casefold()), None)

    def _filter(self, text):
        text = text.strip()
        for name, (_cb, holder) in self._checks.items():
            holder.setVisible(not text or text.casefold() in name.casefold())
        new = bool(text) and self._match(text) is None
        self.add_btn.setText(f"＋ Add “{text}”")
        self.add_btn.setVisible(new)

    def _enter(self):
        text = self.find.text().strip()
        found = self._match(text) if text else None
        if found:
            self._checks[found][0].setChecked(True)  # Enter on a name ticks it
            self.find.clear()
        elif text:
            self._add_typed()

    def _add_typed(self):
        text = " ".join(self.find.text().split())
        if not text or self._match(text):
            return
        self._new.append(text)
        self._add_box(text, True, new=True)
        self.find.clear()

    def set_all(self, checked):
        for cb, _holder in self._checks.values():
            cb.setChecked(checked)

    def selected(self):
        return [name for name, (cb, _h) in self._checks.items() if cb.isChecked()]

    def new_names(self):
        return [n for n in self._new if n in self.selected()]


class TagsDialog(QDialog):
    """Tick tags (or add new ones); new ticked tags are saved when Save is pressed."""

    def __init__(self, db, checked=(), title="Edit Tags", hint=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)
        if hint:
            lbl = QLabel(hint)
            lbl.setProperty("class", "dim-label")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        self.tags = TagChecklist([t["name"] for t in db.get_tags()], checked)
        layout.addWidget(self.tags, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.tags.find.setFocus()

    def _save(self):
        new = self.tags.new_names()
        if new:
            with self.db.transaction():
                for name in new:
                    self.db.add_tag(name)
        self.accept()

    def get_selected(self):
        return self.tags.selected()

    def get_selected_ids(self):
        ids = {t["name"]: t["id"] for t in self.db.get_tags()}
        return [ids[n] for n in self.get_selected() if n in ids]
