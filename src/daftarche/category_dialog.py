"""Edit Category / Sub-Category: pick or type the names, and edit the rules of that sub-category.

Used by the Transactions tab and the Import tab. Nothing is saved before OK: a new category or
sub-category (marked "New") is created then, together with the rule changes. Rules added here
can also be applied to other uncategorized transactions (the caller's ``candidates``).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB, rule_match_length
from daftarche.style import get_settings
from daftarche.widgets import SingleSelectCombo, SymbolButton, add_subcategory_items

ALL_ACCOUNTS = "All"


def _match(names, typed):
    """The existing name for ``typed`` (any letter case), or None."""
    typed = typed.strip().casefold()
    return next((n for n in names if n.casefold() == typed), None)


def _rule_matches(rule, account, name, memo):
    """Would ``rule`` (account, name, memo) categorize this transaction?"""
    r_account, r_name, r_memo = rule
    if r_account and r_account != account:
        return False
    return rule_match_length(name, r_name) is not None and rule_match_length(memo, r_memo) is not None


def _typing_combo():
    combo = SingleSelectCombo()
    combo.allow_typing()
    return combo


class CategoryDialog(QDialog):
    """``about``: the line on top. ``default_rule``: (name, memo) for the new-rule row.
    ``candidates``: [{"key", "account", "name", "memo"}] other uncategorized transactions;
    after OK, ``apply_keys`` holds those the new rules categorize (when the box was ticked)."""

    def __init__(self, db, row_type, parent=None, preset_cat=None, preset_sub=None, about="",
                 default_rule=None, candidates=()):
        super().__init__(parent)
        self.db = db
        self.row_type = row_type
        self.cat_name = ""
        self.sub_name = ""
        self.apply_keys = []
        self._default_rule = default_rule or ("", "")
        self._candidates = list(candidates)
        self._rules = {}  # (category, sub-category) → rule entries, kept while switching names
        self._shown_key = None
        self._rule_rows = []  # widgets of the shown entries: (entry, account, name, memo)
        self._accounts = [a["name"] for a in db.get_accounts(active_only=True)]
        type_id = db.get_type_id(row_type) if row_type else None
        self._categories = [c["name"] for c in (db.get_categories(type_id) if type_id else db.get_categories())]
        if preset_cat and preset_cat not in self._categories:
            self._categories.insert(0, preset_cat)  # e.g. Uncategorized, which has no type
        # gone as soon as it closes: a closed one lingering until quit crashed Python's shutdown
        # (its results are plain attributes, still readable after exec returns)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Edit Category / Sub-Category")
        self.setMinimumSize(780, 580)
        self._build(about)
        self.f_category.setCurrentText(preset_cat or "")
        self._fill_subcats()
        if preset_sub:
            self.f_subcat.setCurrentText(preset_sub)
        self._names_changed()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self, about):
        green = get_settings().get("income") or "#2ecc71"
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        if about:
            top = QLabel(about)
            top.setProperty("class", "dim-label")
            top.setWordWrap(True)
            layout.addWidget(top)

        form = QFormLayout()
        form.setSpacing(10)
        self.f_category = _typing_combo()
        self.f_category.addItems(self._categories)
        self.f_subcat = _typing_combo()
        self.new_cat = QLabel("New")
        self.new_sub = QLabel("New")
        for label in (self.new_cat, self.new_sub):
            label.setStyleSheet(f"color: {green}; font-weight: bold;")
            label.setToolTip("Not there yet: added when you press OK")
            policy = label.sizePolicy()
            policy.setRetainSizeWhenHidden(True)  # the boxes keep their width
            label.setSizePolicy(policy)
        for title, combo, new in (("Category:", self.f_category, self.new_cat),
                                  ("Sub-Category:", self.f_subcat, self.new_sub)):
            row = QHBoxLayout()
            row.addWidget(combo, 1)
            row.addWidget(new)
            new.setFixedWidth(new.sizeHint().width() + 8)
            form.addRow(title, row)
        layout.addLayout(form)
        self.f_category.currentTextChanged.connect(self._category_changed)
        self.f_subcat.currentTextChanged.connect(lambda _: self._names_changed())

        self.rules_box = QFrame()
        rules = QVBoxLayout(self.rules_box)
        rules.setContentsMargins(0, 4, 0, 0)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        rules.addWidget(line)
        self.rules_title = QLabel()
        self.rules_title.setStyleSheet("font-weight: bold;")
        rules.addWidget(self.rules_title)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setColumnStretch(1, 3)
        self._grid.setColumnStretch(2, 2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._grid_host)
        scroll.setMinimumHeight(190)
        rules.addWidget(scroll, 1)

        new_row = QHBoxLayout()
        self.new_account = self._account_combo(None)
        self.new_name = QLineEdit(self._default_rule[0] or "")
        self.new_name.setPlaceholderText("Name")
        self.new_memo = QLineEdit(self._default_rule[1] or "")
        self.new_memo.setPlaceholderText("Memo")
        add = QPushButton("Add")
        add.setToolTip("Add this rule (edit the name or memo first: whole words that always appear)")
        add.clicked.connect(self._add_rule)
        new_row.addWidget(self.new_account)
        new_row.addWidget(self.new_name, 3)
        new_row.addWidget(self.new_memo, 2)
        for field in (self.new_name, self.new_memo):
            field.setCursorPosition(0)
        new_row.addWidget(add)
        rules.addLayout(new_row)
        hint = QLabel("A rule matches whole words, any letter case; | joins words that must all appear "
                      "(e.g. amazon|ca).")
        hint.setProperty("class", "dim-label")
        hint.setWordWrap(True)
        rules.addWidget(hint)
        self.chk_apply = QCheckBox()
        self.chk_apply.setChecked(True)
        rules.addWidget(self.chk_apply)
        layout.addWidget(self.rules_box, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _account_combo(self, current):
        combo = SingleSelectCombo()
        combo.addItem(ALL_ACCOUNTS)
        combo.addItems(self._accounts)
        if current and current not in self._accounts:
            combo.addItem(current)  # a closed account
        combo.setCurrentIndex(max(combo.findText(current or ALL_ACCOUNTS), 0))
        return combo

    # ── names ─────────────────────────────────────────────────────────────────

    def _names(self):
        """(category, sub-category) as they are or will be named, and whether each is new."""
        typed_cat = self.f_category.currentText().strip()
        cat_name = _match(self._categories, typed_cat) or typed_cat
        cat = self.db.get_category_by_name(cat_name, type_name=self.row_type) if cat_name in self._categories else None
        typed_sub = self.f_subcat.currentText().strip() or UNCATEGORIZED_SUB
        subs = [s["name"] for s in self.db.get_subcategories(cat["id"])] if cat else []
        sub_name = _match(subs + [UNCATEGORIZED_SUB], typed_sub) or typed_sub
        return cat, cat_name, sub_name, (sub_name != UNCATEGORIZED_SUB and sub_name not in subs)

    def _category_changed(self, _text):
        self._fill_subcats()
        self._names_changed()

    def _fill_subcats(self):
        cat, *_ = self._names()
        self.f_subcat.blockSignals(True)
        self.f_subcat.clear()
        if cat:
            add_subcategory_items(self.f_subcat, self.db, cat["id"])
        else:
            self.f_subcat.addItem(UNCATEGORIZED_SUB)
        self.f_subcat.setCurrentIndex(0)
        self.f_subcat.blockSignals(False)

    def _names_changed(self):
        cat, cat_name, sub_name, new_sub = self._names()
        self.new_cat.setVisible(bool(cat_name) and cat is None)
        self.new_sub.setVisible(new_sub)
        self._show_rules(cat, cat_name, sub_name)

    # ── rules ─────────────────────────────────────────────────────────────────

    def _entries_for(self, key, cat, sub_name):
        if key not in self._rules:
            entries = []
            sub = self.db.get_subcategory_by_name(sub_name, cat["id"]) if cat else None
            type_id = self.db.get_type_id(self.row_type) if self.row_type else None
            for r in (self.db.get_rules_for_subcategory(sub["id"]) if sub else []):
                if r["type_id"] == type_id:
                    values = (r["account_name"], r["name"] or "", r["memorandum"] or "")
                    entries.append({"id": r["id"], "orig": values, "values": values, "deleted": False})
            self._rules[key] = entries
        return self._rules[key]

    def _keep_shown_edits(self):
        for entry, account, name, memo in self._rule_rows:
            acc = account.currentText()
            entry["values"] = (None if acc == ALL_ACCOUNTS else acc, name.text().strip(), memo.text().strip())

    def _show_rules(self, cat, cat_name, sub_name):
        self._keep_shown_edits()
        has_rules = bool(cat_name) and cat_name.casefold() != UNCATEGORIZED_CAT.casefold()
        self.rules_box.setVisible(has_rules)
        key = (cat_name, sub_name)
        self._shown_key = key if has_rules else None
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget:  # hidden now (deleteLater waits until the dialog closes); keep the parent:
                widget.hide()  # a parentless combo crashed Python's shutdown
                widget.deleteLater()
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        self._rule_rows = []
        if not has_rules:
            return
        self.rules_title.setText(f"Rules for {cat_name} › {sub_name}")
        entries = [e for e in self._entries_for(key, cat, sub_name) if not e["deleted"]]
        for col, title in enumerate(("Account", "Name", "Memo") if entries else ()):
            head = QLabel(title)
            head.setProperty("class", "dim-label")
            self._grid.addWidget(head, 0, col)
        row = 1
        for entry in entries:
            account_v, name_v, memo_v = entry["values"]
            account = self._account_combo(account_v)
            name, memo = QLineEdit(name_v), QLineEdit(memo_v)
            name.setCursorPosition(0)
            memo.setCursorPosition(0)
            remove = SymbolButton("close", size=30)
            remove.setToolTip("Remove this rule")
            remove.clicked.connect(lambda _=False, e=entry: self._remove_rule(e))
            for col, w in enumerate((account, name, memo, remove)):
                self._grid.addWidget(w, row, col)
            self._rule_rows.append((entry, account, name, memo))
            row += 1
        if row == 1:
            none = QLabel("No rules yet.")
            none.setProperty("class", "dim-label")
            self._grid.addWidget(none, 1, 0, 1, 3)
        self._grid.setRowStretch(row + 1, 1)
        self._update_apply_box()

    def _refresh_rules(self):
        cat, cat_name, sub_name, _ = self._names()
        self._show_rules(cat, cat_name, sub_name)

    def _remove_rule(self, entry):
        self._keep_shown_edits()
        entry["deleted"] = True
        self._rule_rows = [r for r in self._rule_rows if r[0] is not entry]
        self._refresh_rules()

    def _add_rule(self):
        name, memo = self.new_name.text().strip(), self.new_memo.text().strip()
        if not name and not memo:
            return  # a blank row is no rule
        acc = self.new_account.currentText()
        self._keep_shown_edits()
        values = (None if acc == ALL_ACCOUNTS else acc, name, memo)
        self._rules.setdefault(self._shown_key, []).append(
            {"id": None, "orig": None, "values": values, "deleted": False})
        self.new_account.setCurrentText(ALL_ACCOUNTS)
        self.new_name.clear()
        self.new_memo.clear()
        self._refresh_rules()

    def _new_rules(self, key):
        return [e["values"] for e in self._rules.get(key, []) if e["id"] is None and not e["deleted"]]

    def _update_apply_box(self):
        rules = self._new_rules(self._shown_key)
        hits = [c["key"] for c in self._candidates
                if any(_rule_matches(r, c["account"], c["name"], c["memo"]) for r in rules)]
        self.chk_apply.setVisible(bool(hits))
        n = len(hits)
        self.chk_apply.setText(f"Also apply the new rule{'s' if len(rules) > 1 else ''} to {n} matching "
                               f"uncategorized transaction{'s' if n != 1 else ''}")

    # ── OK ────────────────────────────────────────────────────────────────────

    def _accept(self):
        self._keep_shown_edits()
        cat, cat_name, sub_name, new_sub = self._names()
        if not cat_name:
            QMessageBox.warning(self, "Category", "Choose or type a category.")
            return
        for key, entries in self._rules.items():
            for e in entries:
                if not e["deleted"] and not (e["values"][1] or e["values"][2]):
                    QMessageBox.warning(self, "Rule", f"A rule of {key[0]} › {key[1]} has no name and no memo. "
                                                      "Write one, or remove the rule with ×.")
                    return
        new_rule_ids = []
        with self.db.transaction():
            if cat is None:
                self.db.add_category(cat_name, self.row_type)
                cat = self.db.get_category_by_name(cat_name, type_name=self.row_type)
            if sub_name == UNCATEGORIZED_SUB:
                self.db.uncategorized_subcategory(cat["id"])
            elif new_sub:
                self.db.add_subcategory(sub_name, cat["id"])
            for key, entries in self._rules.items():
                key_cat = cat if key == (cat_name, sub_name) else \
                    self.db.get_category_by_name(key[0], type_name=self.row_type)
                key_sub = self.db.get_subcategory_by_name(key[1], key_cat["id"]) if key_cat else None
                if not key_sub:
                    continue  # names tried on the way and left: nothing to keep
                for e in entries:
                    account, name, memo = e["values"]
                    if e["deleted"]:
                        if e["id"]:
                            self.db.delete_rule(e["id"])
                    elif e["id"] is None:
                        self.db.save_mapping(self.row_type, account, name or None, memo or None,
                                             subcategory_id=key_sub["id"], category_id=key_cat["id"])
                        if key == (cat_name, sub_name):
                            new_rule_ids.append(self.db.get_rule_id(self.row_type, account, name, memo))
                    elif e["values"] != e["orig"]:
                        self.db.delete_rule_and_save(e["id"], self.row_type, account, name or None, memo or None,
                                                     key_sub["id"], key_cat["id"])
        if new_rule_ids and not self.chk_apply.isHidden() and self.chk_apply.isChecked():
            for c in self._candidates:  # the saved rules decide: a more specific older rule still wins
                rule = self.db.lookup_mapping(self.row_type, c["account"], c["name"] or None, c["memo"] or None)
                if rule and rule["id"] in new_rule_ids:
                    self.apply_keys.append(c["key"])
        self.cat_name, self.sub_name = cat_name, sub_name
        self.accept()
