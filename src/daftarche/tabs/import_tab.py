import re
import os
import html
from datetime import date, timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QAbstractItemView, QHeaderView,
    QMessageBox, QCheckBox, QFileDialog, QDialog, QDialogButtonBox,
    QApplication, QStyledItemDelegate,
    QMenu, QListWidget, QFormLayout
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QBrush, QKeySequence, QShortcut, QAction

from daftarche.style import get_settings
from daftarche.category_dialog import CategoryDialog
from daftarche.tag_picker import TagsDialog
from daftarche.widgets import (
    amount_color_key, money, EditableTableView, ReadOnlyCopyDelegate, SingleSelectCombo,
)
from daftarche.db import (
    CAT_EXTERNAL_TRANSFER,
    CAT_INTERNAL_TRANSFER,
    MONTHS_ORDER,
    SUB_UNMATCHED,
    TRANSFER_MATCHED,
    TRANSFER_UNMATCHED,
    UNCATEGORIZED_CAT,
    UNCATEGORIZED_SUB,
)


# OFX / QFX Parser
def decode_statement(data: bytes) -> str:
    """Text of a QFX/OFX file, decoded with the charset its header names (CIBC: 1252)."""
    head = data[:600].decode("ascii", "replace").upper()
    if re.search(r"ENCODING:\s*UTF-8", head) or b"encoding=\"utf-8\"" in data[:200].lower():
        order = ["utf-8", "cp1252"]
    elif re.search(r"CHARSET:\s*(1252|WINDOWS-1252)", head):
        order = ["cp1252", "utf-8"]
    else:
        order = ["utf-8", "cp1252"]
    for encoding in order:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


_PAYMENT = re.compile(r"\b(PAYMENT|PAIEMENT)\b")


def parse_ofx(content, account_name="", skipped=None):
    """Transactions of a QFX/OFX statement, sorted by date.

    Blocks that cannot be read (no date, an impossible date, an amount that is not a number)
    are left out; with ``skipped`` (a list) each one is added to it as (reason, text).
    """
    results = []
    skipped = [] if skipped is None else skipped
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    ofx_start = re.search(r'<OFX>', content, re.IGNORECASE)
    if ofx_start:
        content = content[ofx_start.start():]

    blocks = re.split(r'<STMTTRN>', content, flags=re.IGNORECASE)[1:]

    def _get_field(block, tag):
        m = re.search(rf'<{tag}>\s*([^<\n]+)', block, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    # credit-card statements are <CCSTMTRS> with <CCACCTFROM> (no ACCTTYPE); the account name
    # is only a fallback for files without them
    is_credit = bool(re.search(r"<CCSTMTRS>|<CCACCTFROM>", content, re.IGNORECASE)) or \
        "credit" in account_name.lower()
    accttype = re.search(r'<ACCTTYPE>([^<\n]+)', content, re.IGNORECASE)
    if accttype and accttype.group(1).strip().upper() in ("CREDITCARD", "CREDITLINE"):
        is_credit = True

    for block in blocks:
        block = re.split(r'</STMTTRN>|<LEDGERBAL>|</BANKTRANLIST>', block,
                         flags=re.IGNORECASE)[0]
        try:
            trntype = _get_field(block, "TRNTYPE").upper()
            dtposted = _get_field(block, "DTPOSTED")
            trnamt = _get_field(block, "TRNAMT")
            fitid = _get_field(block, "FITID") or None
            name = html.unescape(_get_field(block, "NAME"))
            memo = html.unescape(_get_field(block, "MEMO"))

            desc = name if name else memo.strip()

            dtposted = re.sub(r'[\.\[].*', '', dtposted)
            if len(dtposted) < 8:
                skipped.append((f"no date ({dtposted or 'missing'})", desc))
                continue
            try:
                date_str = date(int(dtposted[0:4]), int(dtposted[4:6]), int(dtposted[6:8])).isoformat()
            except ValueError:
                skipped.append((f"impossible date {dtposted[:8]}", desc))
                continue

            try:
                amt = float(trnamt.replace(",", ""))
            except ValueError:
                skipped.append((f"amount '{trnamt}' is not a number", desc))
                continue

            is_payment = bool(_PAYMENT.search(desc.upper()))
            memo_upper = memo.upper()
            is_internal = (
                    trntype in ("XFER", "TRANSFER") or
                    "INTERNET TRANSFER" in memo_upper
            )
            is_etransfer = (
                    "E-TRANSFER" in memo_upper or
                    "ETRANSFER" in memo_upper
            )

            if is_internal or (is_payment and is_credit):
                type_ = "Transfer"
                direction = "debit" if (
                        trntype in ("DEBIT", "SRVCHG", "ATM", "CHECK", "FEE") or amt < 0
                ) else "credit"
            elif amt < 0 or trntype in ("DEBIT", "SRVCHG", "ATM", "CHECK", "FEE"):
                type_ = "Expense"
                direction = "debit"
            else:
                type_ = "Income"
                direction = "credit"

            results.append({
                "date": date_str,
                "type": type_, "amount": abs(amt),
                "description": desc, "memo": memo,
                "name": name or "",
                "memorandum": memo.strip() if memo else "",
                "fitid": fitid,
                "raw": block.strip(),
                "direction": direction,
                "is_etransfer": is_etransfer,
                "source": "ofx",
            })

        except Exception as exc:  # anything else odd in one block: skip it, but say so
            skipped.append((f"unreadable ({exc})", block.strip()[:60]))
            continue

    results.sort(key=lambda r: r["date"])
    return results


def parse_qfx_header(content):
    """Extract account identification info from QFX/OFX header."""

    def _get(tag):
        m = re.search(rf'<{tag}>\s*([^<\n]+)', content, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    dtstart = _get("DTSTART")
    dtend = _get("DTEND")
    dtasof = _get("DTASOF")
    balamt = _get("BALAMT")
    try:
        balamt_f = float(balamt) if balamt else None
    except ValueError:
        balamt_f = None
    return {
        "acctid": _get("ACCTID"),
        "accttype": _get("ACCTTYPE"),
        "bankid": _get("BANKID"),
        "dtstart": dtstart[:8] if dtstart else "",
        "dtend": dtend[:8] if dtend else "",
        "curdef": _get("CURDEF"),
        "balamt": balamt_f,
        "dtasof": dtasof[:8] if dtasof else "",
    }


# Column definitions
PREVIEW_COLS = [
    "Status", "Date", "Type", "Amount", "Merchant",
    "Category", "Sub-Category", "Tags",
    "Name", "Memo", "FITID",
]
COL_STATUS = 0
COL_DATE = 1
COL_TYPE = 2
COL_AMT = 3
COL_MERCHANT = 4
COL_CAT = 5
COL_SUB = 6
COL_TAGS = 7
COL_NAME = 8
COL_MEMO = 9
COL_FITID = 10

OPPOSITE = {"Income": "Expense", "Expense": "Income"}

BANK_NAMES = {"010": "CIBC", "004": "TD", "003": "RBC", "001": "BMO", "002": "Scotiabank", "006": "National",
              "016": "HSBC", "614": "Tangerine", "815": "Desjardins", "030": "Simplii"}


def _fmt_date(d):
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 else (d or "")


class Statement:
    """One QFX/OFX file of an import: its account, its rows, or why it cannot be imported."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.content = None
        self.header = {}
        self.account = None
        self.rows = []
        self.skipped = []
        self.error = None  # why this file is left out (not a statement, unreadable…)

    @property
    def balamt(self):
        return self.header.get("balamt")

    @property
    def curdef(self):
        return self.header.get("curdef") or "CAD"

    def read(self):
        try:
            with open(self.path, "rb") as f:
                self.content = decode_statement(f.read())
        except OSError as exc:
            self.error = f"could not be read ({exc.strerror or exc})"
            return
        if not re.search(r"<OFX>|<STMTTRN>", self.content, re.IGNORECASE):
            self.error = "not a bank statement (QFX/OFX)"
            return
        self.header = parse_qfx_header(self.content)

    def label(self, new_count=None):
        if self.error:
            return f"✗  {self.name}\n{self.error}"
        if not self.account:
            last4 = (self.header.get("acctid") or "")[-4:]
            return f"⚠  {self.name}\naccount …{last4}: choose one"
        if new_count is None:
            return f"✓  {self.name}\n{self.account}"
        return f"✓  {self.name}\n{self.account} · {new_count} new"


def find_rule(db, type_name, account, name, memo):
    """(rule, type, money back) for a transaction from the bank.

    The rule of its own type wins. A credit with only an expense rule (Amazon paying back) is
    money back of that expense: a negative Expense in the same category, and the other way
    round for a debit with only an income rule. (None, type_name, False) when nothing matches.
    """
    rule = db.lookup_mapping(type_name=type_name, account_name=account, name=name or None,
                             memorandum=memo or None)
    if rule or type_name not in OPPOSITE:
        return rule, type_name, False
    other = OPPOSITE[type_name]
    rule = db.lookup_mapping(type_name=other, account_name=account, name=name or None, memorandum=memo or None)
    return (rule, other, True) if rule else (None, type_name, False)


# PreviewModel

def _without_category(rows):
    """Income/expense rows still in the Uncategorized category."""
    return [r for r in rows if not r.get("is_transfer")
            and (not r.get("category") or r["category"]["name"] == UNCATEGORIZED_CAT)]


def _category_only(row):
    """A row with a category but sub-category "Uncategorized" (set on purpose, not a warning)."""
    return (not row.get("is_transfer") and row.get("category") and row.get("subcategory")
            and row["category"]["name"] != UNCATEGORIZED_CAT and row["subcategory"]["name"] == UNCATEGORIZED_SUB)

class PreviewModel(QAbstractTableModel):
    def __init__(self, rows=None):
        super().__init__()
        self._rows = rows or []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(PREVIEW_COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return PREVIEW_COLS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        s = get_settings()

        if role == Qt.DisplayRole:
            if col == COL_STATUS: return row.get("_status", "")
            if col == COL_DATE:   return row.get("date", "")
            if col == COL_TYPE:   return row.get("type", "")
            if col == COL_AMT:
                return money(row.get("amount"))
            if col == COL_MERCHANT:
                return row.get("merchant") or ""
            if col == COL_CAT:
                cat = row.get("category")
                return cat["name"] if cat else UNCATEGORIZED_CAT
            if col == COL_SUB:
                sub = row.get("subcategory")
                return sub["name"] if sub else UNCATEGORIZED_SUB
            if col == COL_TAGS:
                tags = row.get("_tags", [])
                return ", ".join(t["name"] for t in tags) if tags else ""
            if col == COL_NAME:  return row.get("name", "")
            if col == COL_MEMO:
                memo = row.get("memorandum") or row.get("memo") or ""
                return memo.strip()
            if col == COL_FITID: return row.get("fitid", "") or ""
            return ""

        if role == Qt.ForegroundRole:
            status = row.get("_status", "")
            if col == COL_STATUS:
                if "Duplicate" in status: return QBrush(QColor(s.get("text_dim")))
                if "New" in status: return QBrush(QColor(s.get("income")))
            if col in (COL_TYPE, COL_AMT):
                key = amount_color_key(row.get("type", ""), row.get("amount") if col == COL_AMT else 0)
                if key:
                    return QBrush(QColor(s.get(key)))

        if role == Qt.TextAlignmentRole:
            if col in (COL_DATE, COL_AMT):
                return Qt.AlignRight | Qt.AlignVCenter

        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx]

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable


# NullDelegate
class NullDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        return None


# ImportTagPickerDialog
class ImportTagPickerDialog(TagsDialog):
    def __init__(self, db, current_tags=None, parent=None):
        super().__init__(db, [t["name"] for t in (current_tags or [])], "Edit Tags", parent=parent)


# ImportTab
class ImportTab(QWidget):
    def __init__(self, db, on_done_cb):
        super().__init__()
        self.db = db
        self.on_done_cb = on_done_cb
        self.imported_ids = []  # the transactions the last Import added
        self.statements = []  # the files of this import, in the order chosen
        self._index = -1  # the one shown
        self._show_new_only = False
        self._build_ui()

    # the statement on screen: most of the tab works on it
    @property
    def current(self):
        return self.statements[self._index] if 0 <= self._index < len(self.statements) else None

    @property
    def parsed_rows(self):
        return self.current.rows if self.current else []

    @parsed_rows.setter
    def parsed_rows(self, rows):
        if self.current:
            self.current.rows = rows

    @property
    def _current_account(self):
        return self.current.account if self.current else None

    @property
    def _ofx_content(self):
        return self.current.content if self.current else None

    @property
    def _skipped(self):
        return self.current.skipped if self.current else []

    @_skipped.setter
    def _skipped(self, value):
        if self.current:
            self.current.skipped = value

    @property
    def _balamt(self):
        return self.current.balamt if self.current else None

    @property
    def _curdef(self):
        return self.current.curdef if self.current else "CAD"

    def _is_dup(self, fitid, account=None):
        """Already in the database, or in an earlier file of this import for the same account."""
        account = account or self._current_account
        if not fitid or not account:
            return False
        if self.db.fitid_exists(fitid, account):
            return True
        return any(st.account == account and any(r.get("fitid") == fitid for r in st.rows)
                   for st in self.statements[:max(self._index, 0)])

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_browse = QPushButton("📂  Select QFX File...")
        btn_browse.setMinimumWidth(160)
        btn_browse.clicked.connect(self._browse_ofx)

        btn_clear = QPushButton("🧹 Clear")
        btn_clear.setProperty("class", "secondary")
        btn_clear.setMinimumWidth(80)
        btn_clear.clicked.connect(self._clear)

        btn_reapply = QPushButton("🔁  Re-apply Mappings")
        btn_reapply.setProperty("class", "secondary")
        btn_reapply.setMinimumWidth(150)
        btn_reapply.setToolTip("Apply saved category mappings to existing uncategorized transactions")
        btn_reapply.clicked.connect(self._reapply_mappings)

        btn_import = QPushButton("✅  Import New")
        btn_import.setMinimumWidth(130)
        btn_import.clicked.connect(self.import_all)

        for btn in (btn_browse, btn_clear, btn_reapply, btn_import):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── File / account info row ───────────────────────────────────────────
        info_row = QHBoxLayout()
        info_row.setSpacing(6)

        self.btn_choose_account = QPushButton("Choose account…")
        self.btn_choose_account.clicked.connect(self._choose_account)
        self.btn_choose_account.hide()
        self.lbl_file = QLabel("File: —")
        self.lbl_account = QLabel("")
        self.lbl_period = QLabel("")
        self.lbl_balance = QLabel("")

        for lbl in (self.lbl_file, self.lbl_account, self.lbl_period, self.lbl_balance):
            lbl.setProperty("class", "dim-label")

        sep1 = QLabel("|")
        sep1.setProperty("class", "dim-label")
        sep2 = QLabel("|")
        sep2.setProperty("class", "dim-label")
        sep3 = QLabel("|")
        sep3.setProperty("class", "dim-label")

        info_row.addWidget(self.lbl_file)
        info_row.addWidget(sep1)
        info_row.addWidget(self.lbl_account)
        info_row.addWidget(sep2)
        info_row.addWidget(self.lbl_period)
        info_row.addWidget(sep3)
        info_row.addWidget(self.lbl_balance)
        info_row.addWidget(self.btn_choose_account)
        info_row.addStretch()

        # hide separators until populated
        for w in (sep1, sep2, sep3,
                  self.lbl_account, self.lbl_period, self.lbl_balance):
            w.setVisible(False)
        self._info_seps = (sep1, sep2, sep3)

        layout.addLayout(info_row)

        # ── Preview label ─────────────────────────────────────────────────────
        self.preview_lbl = QLabel("Parsed transactions appear here. Tip: you can also drag a QFX file onto the main window.")
        self.preview_lbl.setProperty("class", "dim-label")
        layout.addWidget(self.preview_lbl)

        # ── Table ─────────────────────────────────────────────────────────────
        self.model = PreviewModel()
        self.table = EditableTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegate(NullDelegate(self.table))
        for col in (COL_NAME, COL_MEMO, COL_FITID):
            self.table.setItemDelegateForColumn(col, ReadOnlyCopyDelegate(self.table))
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._on_cell_double_clicked)

        QShortcut(QKeySequence.Copy, self.table, activated=self._copy_selected)

        self.file_list = QListWidget()  # the files of this import (shown when there are several)
        self.file_list.setFixedWidth(300)
        self.file_list.setTextElideMode(Qt.ElideMiddle)
        self.file_list.setSpacing(3)
        self.file_list.currentRowChanged.connect(self._show_statement)
        self.file_list.hide()
        body = QHBoxLayout()
        body.addWidget(self.file_list)
        body.addWidget(self.table, 1)
        layout.addLayout(body, 1)

        # ── Status row ────────────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("class", "dim-label")
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        self.chk_new_only = QCheckBox("Show new only")
        self.chk_new_only.toggled.connect(self._apply_new_filter)
        status_row.addWidget(self.chk_new_only)
        layout.addLayout(status_row)

    # ── File browsing ─────────────────────────────────────────────────────────

    def _browse_ofx(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open QFX/OFX Files (several: ⌘-click)", "",
            "QFX/OFX Files (*.qfx *.ofx);;All Files (*)"
        )
        if paths:
            self.load_files(paths)

    def load_file(self, path):
        self.load_files([path])

    def load_files(self, paths):
        """Read and preview the statements at ``paths`` (chosen or dropped): each file's account
        comes from the file; an unknown one is asked for (or chosen later); files that cannot be
        imported are listed with the reason."""
        self.statements = [Statement(p) for p in paths]
        self._index = -1
        self._chosen = {}  # account number → name chosen in this import (saved when it is imported)
        self._new_accounts = set()  # names typed for new accounts (made when imported)
        for st in self.statements:
            st.read()
            if st.error:
                continue
            acctid = st.header.get("acctid")
            known = self.db.get_account_by_acctid(acctid) if acctid else None
            if known:
                st.account = known["name"]
        unknown = [st for st in self.statements if not st.error and not st.account]
        for n, st in enumerate(unknown, start=1):  # asked in turn (once per account number); Cancel: later
            if st.account:
                continue  # an earlier file had the same account number
            note = f"File {n} of {len(unknown)}: {st.name}" if len(self.statements) > 1 else st.name
            self._identify(st, note)
        for i, st in enumerate(self.statements):
            if st.account:
                self._parse_statement(i)
        self._recheck_duplicates()
        self._refresh_file_list()
        first = next((i for i, st in enumerate(self.statements) if st.account), 0)
        self.file_list.blockSignals(True)
        self.file_list.setCurrentRow(first)
        self.file_list.blockSignals(False)
        self._show_statement(first)

    def _parse_statement(self, i):
        self._index = i
        self.parse()
        st = self.statements[i]
        if not st.rows:
            st.error = "no transactions in it"

    def _recheck_duplicates(self):
        """Duplicate or new, in file order: a row also in an earlier file of the same account is
        a duplicate (after an account is chosen, a later file may now have some)."""
        keep = self._index
        for i, st in enumerate(self.statements):
            if st.account and not st.error:
                self._index = i
                for r in st.rows:
                    r["_status"] = "⏭️ Duplicate" if self._is_dup(r.get("fitid")) else "🆕 New"
        self._index = keep

    def _identify(self, st, note=""):
        """Ask which account ``st`` is for; every file with its account number gets the answer.
        Nothing is saved yet: a new account, and the account number's link, come with the import."""
        h = st.header
        name = self._ask_account(h.get("acctid"), h.get("accttype"), h.get("bankid"), note=note,
                                 period=(h.get("dtstart"), h.get("dtend")), current=st.account)
        if name:
            if getattr(self, "_made_account", False):
                self._new_accounts.add(name)
            self._made_account = False
            for other in self.statements:
                if not other.error and other.header.get("acctid") == h.get("acctid"):
                    other.account = name
            if h.get("acctid"):
                self._chosen[h["acctid"]] = name
        return name

    def _choose_account(self):
        """Choose (or change) the account of the file shown, and of the others with its number."""
        st = self.current
        if not st or st.error or not self._identify(st, st.name):
            return
        shown = self._index
        for i, other in enumerate(self.statements):
            if other.account == st.account and other.header.get("acctid") == st.header.get("acctid"):
                self._parse_statement(i)
        self._recheck_duplicates()
        self._index = shown
        self._refresh_file_list()
        self._show_statement(shown)

    def _refresh_file_list(self):
        self.file_list.blockSignals(True)
        current = self.file_list.currentRow()
        self.file_list.clear()
        for st in self.statements:
            new = sum(1 for r in st.rows if "Duplicate" not in r.get("_status", ""))
            self.file_list.addItem(st.label(new if st.account else None))
        self.file_list.setCurrentRow(max(current, 0) if self.statements else -1)
        self.file_list.setVisible(len(self.statements) > 1)
        self.file_list.blockSignals(False)

    def _show_statement(self, index):
        """Show one file of the import: its account, period, balance and rows."""
        if not 0 <= index < len(self.statements):
            return
        self._index = index
        st = self.current
        s = get_settings()
        self.lbl_file.setText(f"File: {st.name}")
        h = st.header
        for w in (self.lbl_account, self.lbl_period, self.lbl_balance, *self._info_seps):
            w.setVisible(False)
        self.btn_choose_account.setVisible(not st.error)
        self.btn_choose_account.setText("Change account…" if st.account else "Choose account…")
        self.model.set_rows(st.rows)
        if st.error:
            self.lbl_status.setText(f"✗ {st.name}: {st.error}. It is left out.")
            return
        if not st.account:
            self.lbl_status.setText("⚠ This file's account is not known yet: choose it to import this file.")
            return
        acc = self.db.get_account_by_name(st.account)
        color = (acc["color"] if acc and acc["color"] else None) or s.get("accent")
        self.lbl_account.setText(st.account + ("  (new)" if st.account in self._new_accounts else ""))
        self.lbl_account.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.lbl_account.setVisible(True)
        self._info_seps[0].setVisible(True)
        if h.get("dtstart"):
            self.lbl_period.setText(f"Period: {_fmt_date(h['dtstart'])} → {_fmt_date(h.get('dtend'))}")
            self.lbl_period.setVisible(True)
            self._info_seps[1].setVisible(True)
        if st.balamt is not None:
            asof = f"  as of {_fmt_date(h.get('dtasof'))}" if h.get("dtasof") else ""
            self.lbl_balance.setText(f"Balance: {money(st.balamt)} {st.curdef}{asof}")
            self.lbl_balance.setVisible(True)
            self._info_seps[2].setVisible(True)
        self._apply_new_filter(self.chk_new_only.isChecked())
        self._update_status_bar()

    def _suggest_account_name(self, accttype, bankid):
        """A name in the style of the accounts there are (Person-Bank-Type)."""
        names = [a["name"] for a in self.db.get_accounts()]
        people = [n.split("-")[0] for n in names if n.count("-") >= 2]
        person = max(set(people), key=people.count) if people else ""
        bank = BANK_NAMES.get((bankid or "").lstrip("0").rjust(3, "0")) or BANK_NAMES.get(bankid or "")
        if not bank:
            for a in self.db.get_all_account_ids():
                if a["bankid"] == bankid and a["account_name"] and a["account_name"].count("-") >= 2:
                    bank = a["account_name"].split("-")[1]
                    break
        kind = {"CHECKING": "Chequing", "SAVINGS": "Saving", "CREDITLINE": "Credit", "CREDITCARD": "Credit"}.get(
            (accttype or "").upper(), "Credit" if not accttype else accttype.title())
        return "-".join(x for x in (person, bank or "Bank", kind) if x)

    def _ask_account(self, acctid, accttype, bankid, note="", period=(None, None), current=None):
        """Which account a file is for: an existing one, or a new name (made on OK)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Identify Account")
        dlg.setMinimumWidth(540)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        bank = BANK_NAMES.get(bankid or "") or (f"bank {bankid}" if bankid else "a bank")
        kind = {"CHECKING": "chequing", "SAVINGS": "savings", "MONEYMRKT": "money market"}.get(
            (accttype or "").upper(), "credit card")
        when = f" · {_fmt_date(period[0])} – {_fmt_date(period[1])}" if period and period[0] else ""
        info = QLabel((f"<b>{note}</b><br>" if note else "") +
                      f"This file is for an account not seen before:<br>"
                      f"{bank} · {kind} · ending {(acctid or '')[-4:] or '?'}{when}<br><br>"
                      "Pick the account, or type a name for a new one.")
        info.setWordWrap(True)
        layout.addWidget(info)
        names = [a["name"] for a in self.db.get_accounts()]
        combo = SingleSelectCombo()
        combo.allow_typing()
        combo.addItems(names)
        combo.setCurrentText(current or self._suggest_account_name(accttype, bankid))
        new = QLabel("New")
        new.setStyleSheet(f"color: {get_settings().get('income') or '#2ecc71'}; font-weight: bold;")
        policy = new.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        new.setSizePolicy(policy)

        def mark(text):
            new.setVisible(bool(text.strip()) and not any(n.casefold() == text.strip().casefold() for n in names))
        combo.currentTextChanged.connect(mark)
        mark(combo.currentText())
        row = QHBoxLayout()
        row.addWidget(combo, 1)
        row.addWidget(new)
        form = QFormLayout()
        form.addRow("Account:", row)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if not dlg.exec():
            return None
        typed = combo.currentText().strip()
        if not typed:
            return None
        account_name = next((n for n in names if n.casefold() == typed.casefold()), typed)
        self._made_account = account_name not in names  # made when the import is done, not before
        return account_name

    def _clear(self):
        self.statements = []
        self._index = -1
        self._chosen = {}
        self._new_accounts = set()
        self._refresh_file_list()
        self.btn_choose_account.hide()
        self.lbl_file.setText("File: —")
        self.lbl_account.setVisible(False)
        self.lbl_period.setVisible(False)
        self.lbl_balance.setVisible(False)
        for sep in self._info_seps:
            sep.setVisible(False)
        self.model.set_rows([])
        self.lbl_status.setText("")

    def refresh(self):
        pass  # account is auto-detected from file

    # ── Parse ─────────────────────────────────────────────────────────────────

    def parse(self):
        if not self._ofx_content:
            QMessageBox.warning(self, "No file", "Select a QFX/OFX file first.")
            return
        if not self._current_account:
            QMessageBox.warning(self, "No account", "Account could not be determined.")
            return

        account = self._current_account
        skipped = []
        rows = parse_ofx(self._ofx_content, account, skipped=skipped)
        self._skipped = skipped

        if not rows:
            self.parsed_rows = []
            self.model.set_rows([])
            note = f" ({len(skipped)} unreadable)" if skipped else ""
            self.lbl_status.setText(f"⚠️  No transactions found{note}. Check format or file.")
            return

        uncategorized_cat = self.db.get_category_by_name(UNCATEGORIZED_CAT)
        uncategorized_sub = (
            self.db.get_subcategory_by_name(UNCATEGORIZED_SUB, uncategorized_cat["id"])
            if uncategorized_cat else None
        )

        transfer_cat_internal = self.db.get_category_by_name("Internal Transfer")
        transfer_cat_external = self.db.get_category_by_name("External Transfer")
        transfer_sub_unmatched_int = self.db.get_subcategory_by_name(
            "⚠️ Unmatched", transfer_cat_internal["id"]) if transfer_cat_internal else None
        transfer_sub_unmatched_ext = self.db.get_subcategory_by_name(
            "⚠️ Unmatched", transfer_cat_external["id"]) if transfer_cat_external else None

        for r in rows:
            r["subcategory"] = None
            r["category"] = None
            r["merchant"] = None
            r["is_transfer"] = False
            r["_tags"] = []  # tags to assign on import

            name = r.get("name") or r.get("description") or ""
            memorandum = r.get("memorandum") or r.get("memo") or ""

            # Step 1 — Internal transfer
            if r["type"] == "Transfer":
                r["is_transfer"] = True
                r["category"] = transfer_cat_internal
                r["subcategory"] = transfer_sub_unmatched_int
                fitid_t = r.get("fitid")
                r["_status"] = "⏭️ Duplicate" if self._is_dup(fitid_t) else "🆕 New"
                continue

            # Step 2 — E-transfer with a Transfer mapping
            if r.get("is_etransfer"):
                ext_mapping = self.db.lookup_mapping(
                    type_name="Transfer",
                    account_name=account,
                    name=name or None,
                    memorandum=memorandum or None,
                )
                if ext_mapping and ext_mapping["subcategory_id"]:
                    r["type"] = "Transfer"
                    r["is_transfer"] = True
                    r["merchant"] = ext_mapping["merchant"]  # the person
                    r["category"], r["subcategory"] = self._transfer_rule_category(
                        ext_mapping, transfer_cat_external, transfer_sub_unmatched_ext)
                    fitid_t = r.get("fitid")
                    r["_status"] = "⏭️ Duplicate" if self._is_dup(fitid_t) else "🆕 New"
                    continue

            # Step 3 — Normal income/expense mapping (a credit that only an expense rule knows is
            # money back of that expense: a negative Expense)
            mapping, rule_type, back = find_rule(self.db, r["type"], account, name, memorandum)
            if back:
                r["type"], r["amount"] = rule_type, -r["amount"]
            if mapping:
                r["merchant"] = mapping["merchant"]
            if mapping and mapping["subcategory_id"]:
                sub = self.db.get_subcategory_by_id(mapping["subcategory_id"])
                cat = self.db.get_category_by_id(mapping["category_id"]) if mapping["category_id"] else None
                if sub and cat and cat["name"] != UNCATEGORIZED_CAT:
                    r["subcategory"] = sub
                    r["category"] = cat

            if not r["subcategory"]:
                r["subcategory"] = uncategorized_sub
                r["category"] = uncategorized_cat

            # Step 4 — Status
            fitid = r.get("fitid")
            is_dup = self._is_dup(fitid)
            sub = r["subcategory"]

            if is_dup:
                r["_status"] = "⏭️ Duplicate"
            else:
                r["_status"] = "🆕 New"

        self.parsed_rows = rows
        self.model.set_rows(self.parsed_rows)
        self._apply_new_filter(self.chk_new_only.isChecked())
        self._update_status_bar()

    def _transfer_rule_category(self, rule, external, external_unmatched):
        """Where a Transfer rule sends an e-transfer: its own Transfer category (Transfer › Loans:
        money lent or paid back), else External Transfer, unmatched until matched."""
        cat = self.db.get_category_by_id(rule["category_id"]) if rule["category_id"] else None
        sub = self.db.get_subcategory_by_id(rule["subcategory_id"]) if rule["subcategory_id"] else None
        transfer_id = self.db.get_type_id("Transfer")
        if (cat and sub and sub["category_id"] == cat["id"] and cat["type_id"] == transfer_id
                and cat["name"] not in (CAT_INTERNAL_TRANSFER, CAT_EXTERNAL_TRANSFER)):
            return cat, sub
        return external, external_unmatched

    def _update_status_bar(self):
        rows = self.parsed_rows
        dups = sum(1 for r in rows if "Duplicate" in r.get("_status", ""))
        transfers = sum(1 for r in rows if r.get("is_transfer"))
        new_count = len(rows) - dups
        new_rows = [r for r in rows if "Duplicate" not in r.get("_status", "")]
        no_category = len(_without_category(new_rows))
        no_subcategory = sum(1 for r in new_rows if _category_only(r))
        new_transfers = sum(1 for r in new_rows if r.get("is_transfer"))

        parts = [f"{len(rows)} parsed", f"🆕 {new_count} new", f"⏭️ {dups} duplicate"]
        if transfers: parts.append(f"🔄 {transfers} transfers ({new_transfers} new, to be matched)")
        if no_category: parts.append(f"⚠️ {no_category} uncategorized")
        if no_subcategory: parts.append(f"{no_subcategory} without sub-category")
        skipped = getattr(self, "_skipped", [])
        if skipped:
            parts.append(f"⚠️ {len(skipped)} unreadable (left out)")
        self.lbl_status.setText("  |  ".join(parts))
        self.lbl_status.setToolTip("\n".join(f"{why}: {text}" for why, text in skipped))

    # ── Double-click routing ──────────────────────────────────────────────────

    def _on_cell_double_clicked(self, index):
        if not index.isValid():
            return
        col = index.column()
        row_idx = index.row()

        if col in (COL_CAT, COL_SUB):
            self._edit_cat_for_row(row_idx)
        elif col == COL_TAGS:
            self._edit_tags_for_row(row_idx)
        elif col in (COL_NAME, COL_MEMO, COL_FITID):
            self.table.edit(index)
        # Status / Date / Amount — no action

    def _edit_cat_for_row(self, row_idx):
        if not self.model.get_row(row_idx).get("is_transfer"):
            self._edit_categories([row_idx], self.model.get_row(row_idx).get("type", "Expense"))

    def _edit_categories(self, row_indices, row_type):
        """Edit Category / Sub-Category (with the rules) for preview rows; new rules can also
        categorize other uncategorized rows of the preview."""
        rows = [self.model.get_row(i) for i in row_indices]
        first = rows[0]
        if len(rows) == 1:
            about = "  ·  ".join(x for x in (first.get("name") or first.get("memorandum"), self._current_account,
                                             money(first['amount'])) if x)
        else:
            about = f"{len(rows)} transactions"
        names = {(r["category"]["name"] if r.get("category") else None,
                  r["subcategory"]["name"] if r.get("subcategory") else None) for r in rows}
        preset_cat, preset_sub = names.pop() if len(names) == 1 else (None, None)
        candidates = [
            {"key": i, "account": self._current_account, "name": r.get("name") or r.get("description") or "",
             "memo": r.get("memorandum") or r.get("memo") or ""}
            for i, r in enumerate(self.parsed_rows)
            if i not in row_indices and r.get("type") == row_type and "Duplicate" not in r.get("_status", "")
            and _without_category([r])]
        merchants = {(r.get("merchant") or "") for r in rows}
        dlg = CategoryDialog(
            self.db, row_type, self, preset_cat=preset_cat, preset_sub=preset_sub, about=about,
            default_rule=(first.get("name") or "", first.get("memorandum") or "") if len(rows) == 1 else None,
            candidates=candidates,
            preset_merchant=merchants.pop() if len(merchants) == 1 else None,
            merchant_mixed=len(merchants) > 1,
            can_flip=True,
        )
        if not dlg.exec():
            return
        cat = self.db.get_category_by_name(dlg.cat_name, type_name=dlg.row_type)
        sub = self.db.get_subcategory_by_name(dlg.sub_name, cat["id"]) if cat else None
        for i in list(row_indices) + list(dlg.apply_keys):
            row = self.model.get_row(i)
            row["category"] = cat
            row["subcategory"] = sub
            if i in dlg.apply_merchants:
                row["merchant"] = dlg.apply_merchants[i] or row.get("merchant")
            elif dlg.merchant_changed:
                row["merchant"] = dlg.merchant
            if dlg.flipped and i in row_indices and row["type"] != dlg.row_type:  # money back of the other type
                row["type"], row["amount"] = dlg.row_type, -row["amount"]
            if i in row_indices:
                row["_manual"] = True  # chosen by hand: Re-apply leaves it as it is
            self._refresh_status_for_row(i)
        self.model.dataChanged.emit(self.model.index(0, 0),
                                    self.model.index(self.model.rowCount() - 1, len(PREVIEW_COLS) - 1))
        self._update_status_bar()

    def _edit_tags_for_row(self, row_idx):
        row = self.model.get_row(row_idx)
        dlg = ImportTagPickerDialog(self.db, row.get("_tags", []), self)
        if dlg.exec():
            selected_ids = dlg.get_selected_ids()
            all_tags = {t["id"]: t for t in self.db.get_tags()}
            row["_tags"] = [all_tags[tid] for tid in selected_ids if tid in all_tags]
            self.model.dataChanged.emit(
                self.model.index(row_idx, COL_TAGS),
                self.model.index(row_idx, COL_TAGS),
            )

    def _refresh_status_for_row(self, row_idx):
        row = self.model.get_row(row_idx)
        fitid = row.get("fitid")
        is_dup = self._is_dup(fitid)
        row["_status"] = "⏭️ Duplicate" if is_dup else "🆕 New"

    def _emit_row_changed(self, row_idx):
        self.model.dataChanged.emit(
            self.model.index(row_idx, 0),
            self.model.index(row_idx, len(PREVIEW_COLS) - 1),
        )

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        selected = self._get_selected_row_indices()
        if not selected:
            return

        menu = QMenu(self)
        n = len(selected)

        if n == 1:
            row_idx = selected[0]
            menu.addAction(QAction("✏️  Edit Category / Sub-Cat", self,
                                   triggered=lambda: self._edit_cat_for_row(row_idx)))
            menu.addAction(QAction("🏷️  Edit Tags", self,
                                   triggered=lambda: self._edit_tags_for_row(row_idx)))
        else:
            menu.addAction(QAction(f"✏️  Bulk Edit Category / Sub-Cat ({n} rows)", self,
                                   triggered=self._bulk_edit_cat))
            menu.addAction(QAction(f"🏷️  Add Tags ({n} rows)", self,
                                   triggered=self._bulk_add_tags))

        menu.addSeparator()
        menu.addAction(QAction(f"📋  Copy {n} row{'s' if n > 1 else ''}", self,
                               triggered=self._copy_selected))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _get_selected_row_indices(self):
        return sorted(set(idx.row() for idx in self.table.selectedIndexes()))

    def _bulk_edit_cat(self):
        selected = self._get_selected_row_indices()
        non_transfer = [i for i in selected if not self.model.get_row(i).get("is_transfer")]
        if not non_transfer:
            QMessageBox.information(self, "Info", "All selected rows are transfers — category is fixed.")
            return
        types = set(self.model.get_row(i)["type"] for i in non_transfer)
        if len(types) > 1:
            QMessageBox.warning(self, "Mixed Types",
                                "All selected rows must have the same type (Income or Expense).\n"
                                f"You selected: {', '.join(sorted(types))}")
            return
        self._edit_categories(non_transfer, types.pop())

    def _bulk_add_tags(self):
        selected = self._get_selected_row_indices()
        if not selected:
            return
        dlg = ImportTagPickerDialog(self.db, parent=self)
        if dlg.exec():
            new_ids = set(dlg.get_selected_ids())
            if not new_ids:
                return
            all_tags = {t["id"]: t for t in self.db.get_tags()}
            for row_idx in selected:
                row = self.model.get_row(row_idx)
                existing_ids = {t["id"] for t in row.get("_tags", [])}
                merged_ids = existing_ids | new_ids
                row["_tags"] = [all_tags[tid] for tid in merged_ids if tid in all_tags]
            self.model.dataChanged.emit(
                self.model.index(selected[0], COL_TAGS),
                self.model.index(selected[-1], COL_TAGS),
            )

    # ── Copy ─────────────────────────────────────────────────────────────────

    def _copy_selected(self):
        selected = self._get_selected_row_indices()
        if not selected:
            return
        lines = ["\t".join(PREVIEW_COLS)]
        for row_idx in selected:
            row = self.model.get_row(row_idx)
            cat = row.get("category")
            sub = row.get("subcategory")
            tags = row.get("_tags", [])
            memo = (row.get("memorandum") or row.get("memo") or "").strip()
            values = [
                row.get("_status", ""),
                row.get("date", ""),
                row.get("type", ""),
                money(row.get("amount")),
                row.get("merchant") or "",
                cat["name"] if cat else "",
                sub["name"] if sub else "",
                ", ".join(t["name"] for t in tags),
                row.get("name", ""),
                memo,
                row.get("fitid", "") or "",
            ]
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))

    # ── Re-apply mappings ─────────────────────────────────────────────────────

    def _reapply_mappings(self):
        if not self.parsed_rows:
            QMessageBox.warning(self, "Nothing", "Parse a statement first.")
            return

        account = self._current_account
        uncat_cat_id, uncat_sub_id = self.db.get_uncategorized_ids()

        transfer_ext = self.db.get_category_by_name(CAT_EXTERNAL_TRANSFER)
        transfer_unmatched = self.db.get_subcategory_by_name(SUB_UNMATCHED, transfer_ext["id"]) if transfer_ext else None
        updated = 0
        for i, r in enumerate(self.parsed_rows):
            if r.get("_manual"):
                continue
            internal = r.get("category") and r["category"]["name"] == CAT_INTERNAL_TRANSFER
            if r.get("is_etransfer") and not internal:  # as when parsing: a Transfer rule makes it a transfer, to its person
                rule = self.db.lookup_mapping(type_name="Transfer", account_name=account,
                                              name=(r.get("name") or r.get("description") or None),
                                              memorandum=(r.get("memorandum") or r.get("memo") or None))
                if rule and rule["subcategory_id"]:
                    before = (r["type"], r.get("merchant"), r.get("category"), r.get("subcategory"))
                    r["type"], r["is_transfer"], r["amount"] = "Transfer", True, abs(r["amount"])
                    r["merchant"] = rule["merchant"] or r.get("merchant")
                    r["category"], r["subcategory"] = self._transfer_rule_category(rule, transfer_ext,
                                                                                   transfer_unmatched)
                    if (r["type"], r.get("merchant"), r.get("category"), r.get("subcategory")) != before:
                        self._refresh_status_for_row(i)
                        updated += 1
                    continue
            if r.get("is_transfer"):
                continue
            sub = r.get("subcategory")
            if sub and sub["id"] != uncat_sub_id:
                continue

            name = r.get("name") or r.get("description") or ""
            memorandum = r.get("memorandum") or r.get("memo") or ""
            # its type as the bank gave it, so a rule added since can still make it money back
            bank_type = r["type"] if r.get("amount", 0) >= 0 else OPPOSITE.get(r["type"], r["type"])
            mapping, rule_type, back = find_rule(self.db, bank_type, account, name, memorandum)
            if not mapping:
                continue
            before = (r["type"], r["amount"], r.get("merchant"), r.get("category"), r.get("subcategory"))
            r["type"], r["amount"] = rule_type, -abs(r["amount"]) if back else abs(r["amount"])
            r["merchant"] = mapping["merchant"] or r.get("merchant")
            new_sub = self.db.get_subcategory_by_id(mapping["subcategory_id"]) if mapping["subcategory_id"] else None
            new_cat = self.db.get_category_by_id(mapping["category_id"]) if mapping["category_id"] else None
            if new_sub and new_cat and new_cat["name"] != UNCATEGORIZED_CAT:
                r["subcategory"] = new_sub
                r["category"] = new_cat
            if (r["type"], r["amount"], r.get("merchant"), r.get("category"), r.get("subcategory")) != before:
                self._refresh_status_for_row(i)
                updated += 1

        if updated:
            self.model.dataChanged.emit(
                self.model.index(0, 0),
                self.model.index(len(self.parsed_rows) - 1, len(PREVIEW_COLS) - 1),
            )
        QMessageBox.information(
            self, "Re-apply Mappings",
            f"✅ Updated {updated} row{'s' if updated != 1 else ''} in preview."
        )

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_new_filter(self, checked):
        self._show_new_only = checked
        for i in range(self.model.rowCount()):
            row = self.model.get_row(i)
            is_dup = "Duplicate" in row.get("_status", "")
            self.table.setRowHidden(i, checked and is_dup)

    # ── Import ────────────────────────────────────────────────────────────────

    def _ready(self):
        """The files that can be imported: a known account and rows."""
        return [st for st in self.statements if st.account and not st.error and st.rows]

    def import_all(self):
        """Import every file that is ready, all of them or none; then the balances, matched transfers."""
        ready = self._ready()
        if not ready:
            QMessageBox.warning(self, "Nothing", "Choose a statement first (or the account of the one chosen).")
            return
        left_out = [st for st in self.statements if st not in ready]
        new_rows = [r for st in ready for r in st.rows if "Duplicate" not in r.get("_status", "")]
        uncategorized = _without_category(new_rows)
        if uncategorized or left_out:
            parts = []
            if left_out:
                parts.append("Left out: " + ", ".join(
                    f"{st.name} ({st.error or 'no account chosen'})" for st in left_out) + ".")
            if uncategorized:
                n = len(uncategorized)
                parts.append(f"{n} transaction{'s have' if n != 1 else ' has'} no category: "
                             f"{'they wait' if n != 1 else 'it waits'} in To review (⇧⌘R).")
            box = QMessageBox(QMessageBox.Question, "Import", "\n\n".join(parts) + "\n\nImport?", parent=self)
            import_btn = box.addButton("Import", QMessageBox.AcceptRole)
            box.addButton("Go Back", QMessageBox.RejectRole)
            box.setDefaultButton(import_btn)
            box.exec()
            if box.clickedButton() is not import_btn:
                return

        imported = skipped_dup = 0
        imported_ids = []
        had = {st.account: self._tx_count(st.account) for st in ready}
        try:
            with self.db.transaction():
                for st in ready:  # new accounts, and the account numbers chosen here, come with it
                    self.db.get_or_create_account(st.account)
                    acctid = st.header.get("acctid")
                    if acctid and self._chosen.get(acctid) == st.account:
                        self.db.save_account_id(acctid, st.account, st.header.get("accttype"),
                                                st.header.get("bankid"))
                for st in ready:
                    n, dups, ids = self._import_statement(st)
                    imported += n
                    skipped_dup += dups
                    imported_ids += ids
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed",
                                 f"Nothing was imported.\n\n{type(exc).__name__}: {exc}")
            return

        matched = 0
        if imported and any("Transfer" in (r.get("type") or "") for st in ready for r in st.rows):
            try:
                matched = self.db.match_unmatched_transfers()  # both sides may have come in together
            except Exception as exc:  # the import itself is done
                QMessageBox.warning(self, "Match Transfers", f"Matching transfers failed: {exc}\n"
                                                             "Use Match Transfers in Transactions later.")
            merged = getattr(self.db, "last_merged", {}) or {}
            imported_ids = list(dict.fromkeys(merged.get(i, i) for i in imported_ids))  # the pair, not the gone half

        files = f" from {len(ready)} files" if len(ready) > 1 else ""
        msg = f"✅ Imported {imported} transaction{'s' if imported != 1 else ''}{files}."
        if skipped_dup:
            msg += f"<br>⏭️ {skipped_dup} duplicate{'s' if skipped_dup != 1 else ''} skipped."
        if matched:
            msg += f"<br>🔄 Matched {matched} transfer pair{'s' if matched != 1 else ''}."
        checks = self._balance_checks(ready) if imported else []
        if checks:
            msg += "<br><br><table cellspacing='6'><tr><th align='left'>Account</th><th>Bank</th>" \
                   "<th>Calculated</th><th></th></tr>"
            for account, bank, calc, diff, _st in checks:
                ok = abs(diff) < 0.02
                msg += (f"<tr><td>{html.escape(account)}</td><td align='right'>{money(bank)}</td>"
                        f"<td align='right'>{money(calc)}</td>"
                        f"<td>{'✅' if ok else '⚠️ off by ' + money(abs(diff))}</td></tr>")
            msg += "</table>"
        box = QMessageBox(QMessageBox.Information, "Import complete", msg, parent=self)
        box.setTextFormat(Qt.RichText)
        box.exec()

        for account, bank, calc, diff, st in checks:  # a new account starts with money already in it
            if abs(diff) >= 0.02 and account in self._new_accounts and not had.get(account):
                first = min((r["date"] for s2 in ready if s2.account == account for r in s2.rows), default=None)
                self._offer_starting_balance(st, diff, imported_ids, first)

        self.imported_ids = imported_ids
        if imported > 0:
            self.on_done_cb()

        self._clear()

    def _tx_count(self, account):
        acc = self.db.get_account_by_name(account)
        return self.db.get_transaction_count_for_account(acc["id"]) if acc else 0

    def _balance_checks(self, ready):
        """(account, bank balance, calculated, difference, statement) per account, from its newest file."""
        newest = {}
        for st in ready:
            if st.balamt is None:
                continue
            key = st.header.get("dtasof") or st.header.get("dtend") or ""
            if st.account not in newest or key >= newest[st.account][0]:
                newest[st.account] = (key, st)
        balances = self.db.get_latest_account_balances()
        out = []
        for account, (_key, st) in newest.items():
            acc = self.db.get_account_by_name(account)
            calc = balances.get(acc["id"]) if acc else None
            if calc is not None:
                out.append((account, st.balamt, calc, round(st.balamt - calc, 2), st))
        return out

    def _offer_starting_balance(self, st, diff, imported_ids, first):
        """A new account's first statement rarely starts from zero: offer the difference as an
        External Transfer the day before its first transaction in any file (your way of recording it)."""
        if not first:
            return
        day = date.fromisoformat(first) - timedelta(days=1)
        box = QMessageBox(QMessageBox.Question, "Starting Balance",
                          f"{st.account} is off by {money(abs(diff))}: probably the money it had before "
                          f"this statement.\n\nAdd {money(abs(diff))} as its starting balance "
                          f"(an {'incoming' if diff > 0 else 'outgoing'} External Transfer on {day})?",
                          parent=self)
        add = box.addButton("Add Starting Balance", QMessageBox.AcceptRole)
        box.addButton("Not Now", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not add:
            return
        with self.db.transaction():
            cat_id, sub_id = self.db.get_transfer_cat_sub(description="Starting balance", matched=True)
            tx_id = self.db.add_transaction(
                day.year, MONTHS_ORDER[day.month - 1], day.day, "Transfer",
                None if diff > 0 else st.account, abs(diff), sub_id, cat_id,
                name="Starting balance", to_account_name=st.account if diff > 0 else None,
                transfer_status=TRANSFER_MATCHED)  # nothing to match it with: not left as unmatched
        imported_ids.append(tx_id)

    def _import_statement(self, st):
        """Add one file's new rows (inside the import's transaction); (added, duplicates, ids)."""
        account = st.account
        added = dups = 0
        ids = []
        for r in st.rows:
            fitid = r.get("fitid") or None
            if fitid and self.db.fitid_exists(fitid, account):  # also catches an earlier file of this import
                dups += 1
                continue
            type_str = r.get("type", "Expense")
            _dp = date.fromisoformat(r["date"])
            tx_name = r.get("name") or None
            tx_memo = r.get("memorandum") or r.get("memo") or None
            if "Transfer" in type_str:
                direction = r.get("direction", "debit")
                from_acc = account if direction == "debit" else None
                to_acc = None if direction == "debit" else account
                if r.get("category") and r.get("subcategory"):  # as shown in the preview
                    cat_id, sub_id = r["category"]["id"], r["subcategory"]["id"]
                else:
                    cat_id, sub_id = self.db.get_transfer_cat_sub(
                        description=tx_name or tx_memo or "", from_account=from_acc or "",
                        to_account=to_acc or "", matched=False)
                tx_id = self.db.add_transaction(
                    _dp.year, MONTHS_ORDER[_dp.month - 1], _dp.day, type_str,
                    from_acc, r["amount"], sub_id, cat_id, name=tx_name, memorandum=tx_memo,
                    to_account_name=to_acc, transfer_status=TRANSFER_UNMATCHED, fitid=fitid,
                    merchant=r.get("merchant"))  # a rule's Transfer › Loans row: the person
            else:
                uncat_cat, uncat_sub = self.db.get_uncategorized_ids()
                cat, sub = r.get("category"), r.get("subcategory")
                tx_id = self.db.add_transaction(
                    _dp.year, MONTHS_ORDER[_dp.month - 1], _dp.day, type_str,
                    account, r["amount"], sub["id"] if sub else uncat_sub, cat["id"] if cat else uncat_cat,
                    name=tx_name, memorandum=tx_memo, fitid=fitid, merchant=r.get("merchant"))
            ids.append(tx_id)
            tags = r.get("_tags", [])
            if tags and tx_id:
                self.db.set_tags_for_transaction(tx_id, [t["id"] for t in tags])
            added += 1
        return added, dups, ids
