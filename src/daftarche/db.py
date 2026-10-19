import sqlite3
from contextlib import contextmanager
from functools import wraps
import pandas as pd
import re
from datetime import date as _date
import calendar
from decimal import Decimal, ROUND_HALF_UP
from daftarche.style import TAB20_COLORS

TRANSFER_MATCHED = "matched"
TRANSFER_UNMATCHED = "unmatched"

UNCATEGORIZED_CAT = "Uncategorized"
UNCATEGORIZED_SUB = "Uncategorized"

CAT_INTERNAL_TRANSFER = "Internal Transfer"
CAT_EXTERNAL_TRANSFER = "External Transfer"
SUB_MATCHED = "✅ Matched"
SUB_UNMATCHED = "⚠️ Unmatched"


def round2(value):
    """Round to 2 decimal places using standard rounding (0.5 rounds up)."""
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


MONTHS_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS_ORDER)}


def rule_match_length(value, pattern):
    """How much of a rule pattern matches ``value``: the total length of its ``|``-separated
    terms when every term appears as whole words (case-insensitive), 0 for an empty pattern
    (matches anything), None when it does not match."""
    if not pattern or not pattern.strip():
        return 0
    terms = [t.strip() for t in pattern.split("|") if t.strip()]
    for term in terms:
        words = r"\s+".join(re.escape(w) for w in term.split())
        if not re.search(rf"(?<!\w){words}(?!\w)", value or "", re.IGNORECASE):
            return None
    return sum(len(" ".join(t.split())) for t in terms)


def _ymd_to_date_str(year, month, day):
    """Convert year (int), month (name str), day (int) -> 'YYYY-MM-DD'."""
    mn = MONTH_NUM.get(month, 1)
    return f"{int(year):04d}-{mn:02d}-{int(day):02d}"


def _date_str_to_parts(date_str):
    """Convert 'YYYY-MM-DD' -> (year int, month_name str, day int)."""
    if not date_str:
        return None, None, None
    try:
        d = _date.fromisoformat(date_str)
        return d.year, MONTHS_ORDER[d.month - 1], d.day
    except Exception:
        return None, None, None


SCHEMA_VERSION = 3  # 2: transactions.note; 3: merchant (transactions and rules)
"""Database layout version, stored in the file (PRAGMA user_version). Raise it whenever
_migrate learns something new, so an older Daftarche refuses a database it cannot read."""


class NewerDatabaseError(ValueError):
    """The database was written by a newer Daftarche."""


def atomic(method):
    """Run a Database method as one transaction: all its writes are kept, or none."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.transaction():
            return method(self, *args, **kwargs)
    return wrapper


class Database:
    def __init__(self, path):
        self.path = path
        self._tx_depth = 0
        self._data_version = 0  # goes up with every committed change; keys self._cache
        self._cache = {}
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self.conn.close()
            raise NewerDatabaseError(
                f"This database was saved by a newer version of Daftarche (layout {version}; this "
                f"version knows up to {SCHEMA_VERSION}). Update Daftarche to open it.")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._migrate()
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def transaction(self):
        """Group writes: committed together at the end, rolled back together on any error.

        Nested uses (an @atomic method called inside another, or inside an import) join the
        outer transaction, so nothing is committed until the outermost one finishes.
        """
        self._tx_depth += 1
        try:
            yield
        except BaseException:
            self._tx_depth -= 1
            if self._tx_depth == 0:
                self.conn.rollback()
            raise
        self._tx_depth -= 1
        if self._tx_depth == 0:
            self.conn.commit()
            self._data_version += 1

    # ── Schema ────────────────────────────────────────────────────
    def _create_tables(self):
        self.conn.executescript("""
                                CREATE TABLE IF NOT EXISTS types
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    name
                                    TEXT
                                    UNIQUE
                                    NOT
                                    NULL
                                );

                                CREATE TABLE IF NOT EXISTS categories
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    name
                                    TEXT
                                    NOT
                                    NULL,
                                    type_id
                                    INTEGER
                                    REFERENCES
                                    types
                                (
                                    id
                                ),
                                    UNIQUE
                                (
                                    name,
                                    type_id
                                )
                                    );

                                CREATE TABLE IF NOT EXISTS subcategories
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    name
                                    TEXT
                                    NOT
                                    NULL,
                                    category_id
                                    INTEGER
                                    NOT
                                    NULL
                                    REFERENCES
                                    categories
                                (
                                    id
                                ) ON DELETE CASCADE,
                                    UNIQUE
                                (
                                    name,
                                    category_id
                                )
                                    );

                                CREATE TABLE IF NOT EXISTS accounts
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    name
                                    TEXT
                                    UNIQUE
                                    NOT
                                    NULL,
                                    color
                                    TEXT
                                    DEFAULT
                                    '#7c6af7',
                                    active
                                    INTEGER
                                    DEFAULT
                                    1,
                                    visible
                                    INTEGER
                                    DEFAULT
                                    1,
                                    show_in_accounts
                                    INTEGER
                                    DEFAULT
                                    1
                                );

                                CREATE TABLE IF NOT EXISTS transactions
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    date
                                    TEXT
                                    NOT
                                    NULL,
                                    type_id
                                    INTEGER
                                    REFERENCES
                                    types
                                (
                                    id
                                ),
                                    account_id INTEGER REFERENCES accounts
                                (
                                    id
                                ),
                                    to_account_id INTEGER REFERENCES accounts
                                (
                                    id
                                ),
                                    amount REAL NOT NULL,
                                    subcategory_id INTEGER REFERENCES subcategories
                                (
                                    id
                                ),
                                    category_id INTEGER REFERENCES categories
                                (
                                    id
                                ),
                                    name TEXT,
                                    memorandum TEXT,
                                    description TEXT,
                                    fitid TEXT,
                                    transfer_status TEXT DEFAULT NULL,
                                    created_at TEXT DEFAULT
                                (
                                    datetime
                                (
                                    'now'
                                ))
                                    );

                                CREATE TABLE IF NOT EXISTS import_mappings
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    type_id
                                    INTEGER
                                    REFERENCES
                                    types
                                (
                                    id
                                ),
                                    account_id INTEGER REFERENCES accounts
                                (
                                    id
                                ),
                                    name TEXT,
                                    memorandum TEXT,
                                    subcategory_id INTEGER REFERENCES subcategories
                                (
                                    id
                                ) ON DELETE CASCADE,
                                    category_id INTEGER REFERENCES categories
                                (
                                    id
                                ),
                                    UNIQUE
                                (
                                    type_id,
                                    account_id,
                                    name,
                                    memorandum
                                )
                                    );

                                CREATE TABLE IF NOT EXISTS account_ids
                                (
                                    id
                                    INTEGER
                                    PRIMARY
                                    KEY
                                    AUTOINCREMENT,
                                    acctid
                                    TEXT
                                    UNIQUE
                                    NOT
                                    NULL,
                                    accttype
                                    TEXT,
                                    bankid
                                    TEXT,
                                    account_id
                                    INTEGER
                                    REFERENCES
                                    accounts
                                (
                                    id
                                )
                                    );

                                CREATE INDEX IF NOT EXISTS idx_tx_type ON transactions(type_id);
                                CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
                                CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
                                CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(transfer_status);

                                CREATE TABLE IF NOT EXISTS tags
                                (
                                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                                    name TEXT UNIQUE NOT NULL
                                );

                                CREATE TABLE IF NOT EXISTS transaction_tags
                                (
                                    transaction_id INTEGER NOT NULL REFERENCES transactions (id) ON DELETE CASCADE,
                                    tag_id         INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
                                    PRIMARY KEY (transaction_id, tag_id)
                                );

                                CREATE INDEX IF NOT EXISTS idx_tx_tags_tx  ON transaction_tags(transaction_id);
                                CREATE INDEX IF NOT EXISTS idx_tx_tags_tag ON transaction_tags(tag_id);
                                """)
        self.conn.commit()

    def _migrate(self):
        """Seed default types/categories; handle schema upgrades for existing DBs."""
        c = self.conn

        if not c.execute("SELECT 1 FROM types LIMIT 1").fetchone():
            for t in ["Income", "Expense", "Transfer"]:
                c.execute("INSERT OR IGNORE INTO types(name) VALUES(?)", (t,))
            c.commit()

        def add_col_if_missing(table, col, typedef):
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")

        # Migrate old year/month/day/weekday columns to single date column
        tx_cols = [r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()]
        if "year" in tx_cols and "date" not in tx_cols:
            # Add date column
            c.execute("ALTER TABLE transactions ADD COLUMN date TEXT")
            # Populate from existing y/m/d
            month_case = " ".join(f"WHEN '{m}' THEN {i}" for i, m in enumerate(MONTHS_ORDER, 1))
            c.execute(f"""
                UPDATE transactions
                SET date = printf('%04d-%02d-%02d',
                    year,
                    CASE month {month_case} ELSE 1 END,
                    day)
            """)
            c.commit()
            # Remove old columns via table rebuild
            c.executescript("""
                            CREATE TABLE transactions_new
                            (
                                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                                date            TEXT NOT NULL DEFAULT '2026-01-01',
                                type_id         INTEGER REFERENCES types (id),
                                account_id      INTEGER REFERENCES accounts (id),
                                to_account_id   INTEGER REFERENCES accounts (id),
                                amount          REAL NOT NULL DEFAULT 0,
                                subcategory_id  INTEGER REFERENCES subcategories (id),
                                category_id     INTEGER REFERENCES categories (id),
                                name            TEXT,
                                memorandum      TEXT,
                                description     TEXT,
                                fitid           TEXT,
                                transfer_status TEXT          DEFAULT NULL,
                                created_at      TEXT          DEFAULT (datetime('now'))
                            );
                            INSERT INTO transactions_new
                            (id, date, type_id, account_id, to_account_id, amount,
                             subcategory_id, category_id, name, memorandum, description,
                             fitid, transfer_status, created_at)
                            SELECT id, date, type_id, account_id, to_account_id, amount, subcategory_id, category_id, name, memorandum, description, fitid, transfer_status, created_at
                            FROM transactions;
                            DROP TABLE transactions;
                            ALTER TABLE transactions_new RENAME TO transactions;
                            CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
                            CREATE INDEX IF NOT EXISTS idx_tx_type ON transactions(type_id);
                            CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
                            CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
                            CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(transfer_status);
                            """)
            c.commit()
        elif "date" not in tx_cols:
            add_col_if_missing("transactions", "date", "TEXT NOT NULL DEFAULT '2026-01-01'")
        add_col_if_missing("transactions", "note", "TEXT")  # your own words: what it was (layout 2)
        add_col_if_missing("transactions", "merchant", "TEXT")  # the shop or person (layout 3)
        add_col_if_missing("import_mappings", "merchant", "TEXT")  # what a rule sets as merchant (layout 3)

        # Ensure date index exists (safe to run every time)
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)")
        c.commit()

        add_col_if_missing("transactions", "to_account_id", "INTEGER REFERENCES accounts(id)")
        add_col_if_missing("transactions", "description", "TEXT")
        add_col_if_missing("transactions", "type_id", "INTEGER REFERENCES types(id)")
        add_col_if_missing("transactions", "transfer_status", "TEXT DEFAULT NULL")
        add_col_if_missing("transactions", "name", "TEXT")
        add_col_if_missing("transactions", "memorandum", "TEXT")
        add_col_if_missing("transactions", "fitid", "TEXT")
        add_col_if_missing("accounts", "color", "TEXT DEFAULT '#7c6af7'")
        add_col_if_missing("accounts", "active", "INTEGER DEFAULT 1")
        add_col_if_missing("accounts", "visible", "INTEGER DEFAULT 1")
        add_col_if_missing("accounts", "show_in_accounts", "INTEGER DEFAULT 1")

        existing_cols = [r[1] for r in c.execute("PRAGMA table_info(import_mappings)").fetchall()]
        needs_rebuild = "keyword" in existing_cols or "name" not in existing_cols
        if needs_rebuild:
            c.executescript("""
                            CREATE TABLE IF NOT EXISTS import_mappings_new
                            (
                                id
                                INTEGER
                                PRIMARY
                                KEY
                                AUTOINCREMENT,
                                type_id
                                INTEGER
                                REFERENCES
                                types
                            (
                                id
                            ),
                                account_id INTEGER REFERENCES accounts
                            (
                                id
                            ),
                                name TEXT,
                                memorandum TEXT,
                                subcategory_id INTEGER REFERENCES subcategories
                            (
                                id
                            ) ON DELETE CASCADE,
                                category_id INTEGER REFERENCES categories
                            (
                                id
                            ),
                                UNIQUE
                            (
                                type_id,
                                account_id,
                                name,
                                memorandum
                            )
                                );
                            DROP TABLE IF EXISTS import_mappings;
                            ALTER TABLE import_mappings_new RENAME TO import_mappings;
                            """)

        # Migrate categories to UNIQUE(name, type_id) if still using old UNIQUE(name)
        # Check by trying to detect the old single-column unique index
        cat_index_info = c.execute("PRAGMA index_list(categories)").fetchall()
        needs_cat_rebuild = False
        for idx_row in cat_index_info:
            if idx_row[2]:  # unique index
                cols = c.execute(f"PRAGMA index_info('{idx_row[1]}')").fetchall()
                if len(cols) == 1 and cols[0][2] == "name":
                    needs_cat_rebuild = True
                    break
        if needs_cat_rebuild:
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("DROP TABLE IF EXISTS categories_new")
            c.execute("""
                      CREATE TABLE categories_new
                      (
                          id      INTEGER PRIMARY KEY AUTOINCREMENT,
                          name    TEXT NOT NULL,
                          type_id INTEGER REFERENCES types (id),
                          UNIQUE (name, type_id)
                      )
                      """)
            c.execute("""
                      INSERT INTO categories_new (id, name, type_id)
                      SELECT id, name, type_id
                      FROM categories
                      """)
            c.execute("DROP TABLE categories")
            c.execute("ALTER TABLE categories_new RENAME TO categories")
            c.commit()
            c.execute("PRAGMA foreign_keys = ON")

        # Tags tables — ensure indices exist for older DBs
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_tags_tx  ON transaction_tags(transaction_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tx_tags_tag ON transaction_tags(tag_id)")
        for column in ("to_account_id", "subcategory_id", "fitid", "merchant"):
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_tx_{column} ON transactions({column})")

        self._dedupe_rules()
        c.commit()
        self._seed_uncategorized()
        self._seed_transfer_categories()

    def _dedupe_rules(self):
        """One rule per (type, account, name, memo): SQLite's UNIQUE never compares empty (NULL)
        fields, so saving a rule again used to add a copy. Keep the newest (the one meant last)."""
        c = self.conn
        c.execute("UPDATE import_mappings SET name=NULL WHERE TRIM(name)=''")
        c.execute("UPDATE import_mappings SET memorandum=NULL WHERE TRIM(memorandum)=''")
        c.execute("""DELETE FROM import_mappings WHERE id NOT IN (
                         SELECT MAX(id) FROM import_mappings
                         GROUP BY type_id, IFNULL(account_id, -1), IFNULL(name, ''), IFNULL(memorandum, ''))""")
        c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_mapping_key ON import_mappings
                         (type_id, IFNULL(account_id, -1), IFNULL(name, ''), IFNULL(memorandum, ''))""")

    def _seed_transfer_categories(self):
        for cat_name in [CAT_INTERNAL_TRANSFER, CAT_EXTERNAL_TRANSFER]:
            if not self.get_category_by_name(cat_name):
                self.add_category(cat_name, "Transfer")
            cat = self.get_category_by_name(cat_name)
            if cat:
                for sub_name in [SUB_MATCHED, SUB_UNMATCHED]:
                    if not self.get_subcategory_by_name(sub_name, cat["id"]):
                        self.add_subcategory(sub_name, cat["id"])

    def _seed_uncategorized(self):
        if not self.get_category_by_name(UNCATEGORIZED_CAT):
            self.add_category(UNCATEGORIZED_CAT, None)
        cat = self.get_category_by_name(UNCATEGORIZED_CAT)
        if cat and not self.get_subcategory_by_name(UNCATEGORIZED_SUB, cat["id"]):
            self.add_subcategory(UNCATEGORIZED_SUB, cat["id"])

    def get_uncategorized_ids(self):
        cat = self.get_category_by_name(UNCATEGORIZED_CAT)
        if not cat:
            self._seed_uncategorized()
            cat = self.get_category_by_name(UNCATEGORIZED_CAT)
        sub = self.get_subcategory_by_name(UNCATEGORIZED_SUB, cat["id"])
        return cat["id"], sub["id"] if sub else None

    def get_transfer_cat_sub(self, description="", matched=False,
                             from_account="", to_account=""):
        BANK_KEYWORDS = ["CIBC", "TD", "RBC", "BMO", "SCOTIABANK", "TANGERINE",
                         "SIMPLII", "DESJARDINS", "NATIONAL", "HSBC", "ATB"]

        def _bank(name):
            name_upper = (name or "").upper()
            for kw in BANK_KEYWORDS:
                if kw in name_upper:
                    return kw
            return None

        def _person(name):
            return (name or "").split("-")[0].strip().upper()

        is_internal = False

        if "INTERNET TRANSFER" in (description or "").upper():
            is_internal = True

        if not is_internal and from_account and to_account:
            b1, b2 = _bank(from_account), _bank(to_account)
            p1, p2 = _person(from_account), _person(to_account)
            if b1 and b1 == b2 and p1 and p1 == p2:
                is_internal = True

        cat_name = CAT_INTERNAL_TRANSFER if is_internal else CAT_EXTERNAL_TRANSFER
        sub_name = SUB_MATCHED if matched else SUB_UNMATCHED

        cat = self.get_category_by_name(cat_name)
        if not cat:
            self._seed_transfer_categories()
            cat = self.get_category_by_name(cat_name)

        sub = self.get_subcategory_by_name(sub_name, cat["id"])
        if not sub:
            self.add_subcategory(sub_name, cat["id"])
            sub = self.get_subcategory_by_name(sub_name, cat["id"])

        return cat["id"], sub["id"] if sub else None

    # ── Types ─────────────────────────────────────────────────────
    def get_types(self):
        return self.conn.execute("SELECT * FROM types ORDER BY id").fetchall()

    def get_type_by_name(self, name):
        return self.conn.execute("SELECT * FROM types WHERE name=?", (name,)).fetchone()

    def get_type_id(self, name):
        row = self.get_type_by_name(name)
        return row["id"] if row else None

    @atomic
    def add_type(self, name):
        try:
            self.conn.execute("INSERT INTO types(name) VALUES(?)", (name,))
            return True
        except sqlite3.IntegrityError:
            return False

    @atomic
    def rename_type(self, old_name, new_name):
        """Raises ValueError when another type already has ``new_name``."""
        if self.get_type_by_name(new_name):
            raise ValueError(f"A type named '{new_name}' already exists.")
        self.conn.execute("UPDATE types SET name=? WHERE name=?", (new_name, old_name))

    @atomic
    def delete_type(self, name):
        """Raises ValueError while transactions, categories or rules still use the type."""
        type_id = self.get_type_id(name)
        uses = {
            ("transaction", "transactions"): self.get_transaction_count_for_type(type_id),
            ("category", "categories"): self.get_category_count_for_type(type_id),
            ("rule", "rules"): self.conn.execute("SELECT COUNT(*) FROM import_mappings WHERE type_id=?",
                                                 (type_id,)).fetchone()[0],
        }
        used = [f"{n} {one if n == 1 else many}" for (one, many), n in uses.items() if n]
        if used:
            raise ValueError(f"'{name}' is still used by {', '.join(used)}. "
                             "Move or delete them first.")
        self.conn.execute("DELETE FROM types WHERE name=?", (name,))

    # ── Categories ────────────────────────────────────────────────
    def get_categories(self, type_id=None):
        if type_id:
            return self.conn.execute(
                "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.type_id=? ORDER BY c.name",
                (type_id,)).fetchall()
        return self.conn.execute(
            "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id ORDER BY c.name"
        ).fetchall()

    def get_category_by_name(self, name, type_id=None, type_name=None):
        """The category ``name``. With ``type_id``: only that type's. With ``type_name``: that
        type's if there is one, else one without a type (Uncategorized), else any — the same
        name can exist under several types (e.g. "Other" under Income and under Expense)."""
        if type_id is not None:
            return self.conn.execute(
                "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.name=? AND c.type_id=?",
                (name, type_id)).fetchone()
        preferred = self.get_type_id(type_name) if type_name else None
        return self.conn.execute(
            "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.name=? "
            "ORDER BY (c.type_id IS ?) DESC, (c.type_id IS NULL) DESC, c.id LIMIT 1",
            (name, preferred)).fetchone()

    def get_category_by_id(self, id_):
        return self.conn.execute(
            "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.id=?",
            (id_,)).fetchone()

    @atomic
    def add_category(self, name, type_name=None):
        try:
            type_id = self.get_type_id(type_name) if type_name else None
            self.conn.execute("INSERT INTO categories(name, type_id) VALUES(?,?)", (name, type_id))
            return True
        except sqlite3.IntegrityError:
            return False  # already exists under same type

    @atomic
    def rename_category(self, cat_id, new_name):
        """Rename a category; when its type already has ``new_name``, merge into that one:
        transactions, sub-categories (same-named ones merged too) and rules all move."""
        old = self.get_category_by_id(cat_id)
        if not old:
            return
        target = self.get_category_by_name(new_name, old["type_id"]) if old["type_id"] is not None else \
            self.conn.execute("SELECT * FROM categories WHERE name=? AND type_id IS NULL", (new_name,)).fetchone()
        if not target or target["id"] == old["id"]:
            self.conn.execute("UPDATE categories SET name=? WHERE id=?", (new_name, old["id"]))
            return
        for sub in self.get_subcategories(old["id"]):
            twin = self.get_subcategory_by_name(sub["name"], target["id"])
            if twin:
                self._move_subcategory_contents(sub["id"], twin["id"], target["id"])
                self.conn.execute("DELETE FROM subcategories WHERE id=?", (sub["id"],))
            else:
                self.conn.execute("UPDATE subcategories SET category_id=? WHERE id=?", (target["id"], sub["id"]))
        self.conn.execute("UPDATE transactions SET category_id=? WHERE category_id=?", (target["id"], old["id"]))
        self.conn.execute("UPDATE import_mappings SET category_id=? WHERE category_id=?", (target["id"], old["id"]))
        self.conn.execute("DELETE FROM categories WHERE id=?", (old["id"],))

    def _move_subcategory_contents(self, from_sub_id, to_sub_id, to_cat_id):
        """Transactions and rules of one sub-category over to another (part of a merge)."""
        self.conn.execute("UPDATE transactions SET subcategory_id=?, category_id=? WHERE subcategory_id=?",
                          (to_sub_id, to_cat_id, from_sub_id))
        self.conn.execute("UPDATE import_mappings SET subcategory_id=?, category_id=? WHERE subcategory_id=?",
                          (to_sub_id, to_cat_id, from_sub_id))

    @atomic
    def delete_category(self, cat_id):
        uncat_cat_id, uncat_sub_id = self.get_uncategorized_ids()
        self.conn.execute("""
                          UPDATE transactions
                          SET category_id=?,
                              subcategory_id=?
                          WHERE category_id = ?
                          """, (uncat_cat_id, uncat_sub_id, cat_id))
        self.conn.execute("DELETE FROM import_mappings WHERE category_id=?", (cat_id,))
        self.conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))

    # ── Subcategories ─────────────────────────────────────────────
    def get_subcategories(self, category_id=None):
        if category_id:
            return self.conn.execute(
                "SELECT s.*, c.name as cat_name FROM subcategories s JOIN categories c ON s.category_id=c.id WHERE s.category_id=? ORDER BY s.name",
                (category_id,)).fetchall()
        return self.conn.execute(
            "SELECT s.*, c.name as cat_name FROM subcategories s JOIN categories c ON s.category_id=c.id ORDER BY c.name, s.name"
        ).fetchall()

    def get_subcategory_by_name(self, name, category_id):
        return self.conn.execute(
            "SELECT * FROM subcategories WHERE name=? AND category_id=?", (name, category_id)
        ).fetchone()

    def get_subcategory_by_id(self, id_):
        return self.conn.execute(
            "SELECT s.*, c.name as cat_name FROM subcategories s JOIN categories c ON s.category_id=c.id WHERE s.id=?",
            (id_,)).fetchone()

    @atomic
    def add_subcategory(self, name, category_id):
        try:
            self.conn.execute("INSERT INTO subcategories(name, category_id) VALUES(?,?)", (name, category_id))
            return True
        except sqlite3.IntegrityError:
            return False

    @atomic
    def rename_subcategory(self, subcat_id, new_name, new_category_id=None):
        old = self.get_subcategory_by_id(subcat_id)
        if not old:
            return
        target_cat_id = new_category_id if new_category_id else old["category_id"]
        existing = self.get_subcategory_by_name(new_name, target_cat_id)
        if existing and existing["id"] != subcat_id:
            self._move_subcategory_contents(subcat_id, existing["id"], target_cat_id)
            self.conn.execute("DELETE FROM subcategories WHERE id=?", (subcat_id,))
        else:
            self.conn.execute(
                "UPDATE subcategories SET name=?, category_id=? WHERE id=?",
                (new_name, target_cat_id, subcat_id))
            self.conn.execute("UPDATE transactions SET category_id=? WHERE subcategory_id=?",
                              (target_cat_id, subcat_id))
            self.conn.execute("UPDATE import_mappings SET category_id=? WHERE subcategory_id=?",
                              (target_cat_id, subcat_id))

    @atomic
    def reparent_subcategory(self, subcat_id, new_category_id):
        old = self.get_subcategory_by_id(subcat_id)
        if not old:
            return

        existing = self.get_subcategory_by_name(old["name"], new_category_id)

        if existing:
            self.conn.execute(
                "UPDATE transactions SET subcategory_id=?, category_id=? WHERE subcategory_id=?",
                (existing["id"], new_category_id, subcat_id))
            self.conn.execute(
                "UPDATE import_mappings SET subcategory_id=?, category_id=? WHERE subcategory_id=?",
                (existing["id"], new_category_id, subcat_id))
            self.conn.execute("DELETE FROM subcategories WHERE id=?", (subcat_id,))
        else:
            self.conn.execute(
                "UPDATE subcategories SET category_id=? WHERE id=?",
                (new_category_id, subcat_id))
            self.conn.execute(
                "UPDATE transactions SET category_id=? WHERE subcategory_id=?",
                (new_category_id, subcat_id))
            self.conn.execute(
                "UPDATE import_mappings SET category_id=? WHERE subcategory_id=?",
                (new_category_id, subcat_id))


    @atomic
    def delete_subcategory(self, subcat_id):
        uncat_cat_id, uncat_sub_id = self.get_uncategorized_ids()
        self.conn.execute("""
                          UPDATE transactions
                          SET category_id=?,
                              subcategory_id=?
                          WHERE subcategory_id = ?
                          """, (uncat_cat_id, uncat_sub_id, subcat_id))
        self.conn.execute("DELETE FROM subcategories WHERE id=?", (subcat_id,))

    # ── Accounts ──────────────────────────────────────────────────
    def get_accounts(self, active_only=False, visible_only=False):
        q = "SELECT * FROM accounts"
        conds = []
        if active_only:  conds.append("active=1")
        if visible_only: conds.append("visible=1")
        if conds: q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY name"
        return self.conn.execute(q).fetchall()

    def get_account_monthly_inout(self, account_id, type_filter, account_field="account_id"):
        q = f"""
            SELECT strftime('%Y', t.date) AS year,
                   strftime('%m', t.date) AS month_num,
                   SUM(t.amount) as total
            FROM transactions t
            LEFT JOIN types ty ON t.type_id = ty.id
            WHERE t.{account_field} = ?
              AND ty.name LIKE ?
            GROUP BY year, month_num
        """
        rows = self.conn.execute(q, (account_id, f"%{type_filter}%")).fetchall()
        result = {}
        for r in rows:
            y = int(r["year"])
            m = MONTHS_ORDER[int(r["month_num"]) - 1]
            result[(y, m)] = r["total"] or 0
        return result

    def get_account_monthly_transfer_net(self, account_id):
        """Transfer In minus Transfer Out per month for one account."""
        t_out = self.get_account_monthly_inout(account_id, "Transfer", "account_id")
        t_in = self.get_account_monthly_inout(account_id, "Transfer", "to_account_id")
        all_periods = set(t_out.keys()) | set(t_in.keys())
        return {
            p: round2(t_in.get(p, 0) - t_out.get(p, 0))
            for p in all_periods
        }

    def get_account_by_name(self, name):
        return self.conn.execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()

    @atomic
    def get_or_create_account(self, name):
        row = self.conn.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()
        if row:
            return row["id"]
        used = [r["color"] for r in self.conn.execute("SELECT color FROM accounts").fetchall()]
        color = next((c for c in TAB20_COLORS if c not in used), TAB20_COLORS[0])
        cur = self.conn.execute("INSERT INTO accounts(name, color) VALUES(?,?)", (name, color))
        return cur.lastrowid

    @atomic
    def update_account(self, account_id, **kwargs):
        sets = ", ".join(f"{k}=?" for k in kwargs)
        self.conn.execute(f"UPDATE accounts SET {sets} WHERE id=?",
                          list(kwargs.values()) + [account_id])

    @atomic
    def rename_account(self, old_name, new_name):
        existing = self.get_account_by_name(new_name)
        old = self.get_account_by_name(old_name)
        if not old:
            return
        if existing and existing["id"] != old["id"]:
            new_id, old_id = existing["id"], old["id"]
            self.conn.execute("UPDATE transactions SET account_id=? WHERE account_id=?", (new_id, old_id))
            self.conn.execute("UPDATE transactions SET to_account_id=? WHERE to_account_id=?", (new_id, old_id))
            self.conn.execute("UPDATE account_ids SET account_id=? WHERE account_id=?", (new_id, old_id))
            # the merged-into account's own rule wins where both have the same one
            self.conn.execute("UPDATE OR IGNORE import_mappings SET account_id=? WHERE account_id=?", (new_id, old_id))
            self.conn.execute("DELETE FROM import_mappings WHERE account_id=?", (old_id,))
            self.conn.execute("DELETE FROM accounts WHERE id=?", (old_id,))
        else:
            self.conn.execute("UPDATE accounts SET name=? WHERE name=?", (new_name, old_name))

    @atomic
    def delete_account(self, account_id):
        self.conn.execute("UPDATE transactions SET account_id=NULL WHERE account_id=?", (account_id,))
        self.conn.execute("UPDATE transactions SET to_account_id=NULL WHERE to_account_id=?", (account_id,))
        self.conn.execute("UPDATE import_mappings SET account_id=NULL WHERE account_id=?", (account_id,))
        self.conn.execute("DELETE FROM account_ids WHERE account_id=?", (account_id,))
        self.conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))

    # ── Transactions ──────────────────────────────────────────────
    def get_transactions(self, filters=None):
        q = """
            SELECT t.id,
                   t.date,
                   ty.name  as type,
                   a.name   as account,
                   a.color  as account_color,
                   ta.name  as to_account,
                   ta.color as to_account_color,
                   t.amount,
                   s.name   as subcategory,
                   c.name   as category,
                   t.name,
                   t.memorandum,
                   t.note,
                   t.merchant,
                   t.description,
                   t.fitid,
                   t.transfer_status,
                   t.account_id,
                   t.to_account_id,
                   t.subcategory_id,
                   t.category_id,
                   t.type_id
            FROM transactions t
                     LEFT JOIN types ty ON t.type_id = ty.id
                     LEFT JOIN accounts a ON t.account_id = a.id
                     LEFT JOIN accounts ta ON t.to_account_id = ta.id
                     LEFT JOIN subcategories s ON t.subcategory_id = s.id
                     LEFT JOIN categories c ON t.category_id = c.id
            WHERE 1 = 1 \
            """
        params = []
        f = filters or {}

        if f.get("type"):
            q += " AND ty.name IN (" + ",".join("?" * len(f["type"])) + ")"
            params += f["type"]
        if f.get("account"):
            q += " AND (a.name IN (" + ",".join("?" * len(f["account"])) + ") OR ta.name IN (" + ",".join(
                "?" * len(f["account"])) + "))"
            params += f["account"]
            params += f["account"]
        if f.get("category"):
            q += " AND c.name IN (" + ",".join("?" * len(f["category"])) + ")"
            params += f["category"]
        if f.get("subcategory"):
            q += " AND s.name IN (" + ",".join("?" * len(f["subcategory"])) + ")"
            params += f["subcategory"]
        if f.get("merchant"):
            q += " AND t.merchant IN (" + ",".join("?" * len(f["merchant"])) + ")"
            params += f["merchant"]
        if f.get("ids") is not None:  # just these (e.g. those just imported)
            if not f["ids"]:
                return []
            q += " AND t.id IN (" + ",".join("?" * len(f["ids"])) + ")"
            params += list(f["ids"])
        if f.get("tags"):
            ph = ",".join("?" * len(f["tags"]))
            tag_id_rows = self.conn.execute(f"""
                SELECT DISTINCT tt.transaction_id
                FROM transaction_tags tt
                JOIN tags tg ON tg.id = tt.tag_id
                WHERE tg.name IN ({ph})
            """, f["tags"]).fetchall()
            allowed_ids = [r[0] for r in tag_id_rows]
            if not allowed_ids:
                return []
            q += " AND t.id IN (" + ",".join("?" * len(allowed_ids)) + ")"
            params += allowed_ids
        if f.get("transfer_status") == "unmatched":
            q += " AND t.transfer_status = 'unmatched'"
        elif f.get("transfer_status") == "matched":
            q += " AND t.transfer_status = 'matched'"

        if f.get("from_day"):
            q += " AND t.date >= ?"
            params.append(f["from_day"])

        if f.get("to_day"):
            q += " AND t.date <= ?"
            params.append(f["to_day"])

        if f.get("search"):
            kw = f"%{f['search']}%"
            sf = f.get("search_fields") or {}
            # default: name + memo + category + subcategory if no fields specified
            if not any(sf.values()):
                sf = {"name": True, "memo": True, "category": True, "subcategory": True}
            field_clauses = []
            if sf.get("name"):
                field_clauses.append("t.name LIKE ?")
                params.append(kw)
            if sf.get("memo"):
                field_clauses.append("t.memorandum LIKE ?")
                params.append(kw)
            if sf.get("category"):
                field_clauses.append("c.name LIKE ?")
                params.append(kw)
            if sf.get("subcategory"):
                field_clauses.append("s.name LIKE ?")
                params.append(kw)
            if sf.get("tags"):
                field_clauses.append("""t.id IN (
                    SELECT tt2.transaction_id FROM transaction_tags tt2
                    JOIN tags tg2 ON tg2.id = tt2.tag_id
                    WHERE tg2.name LIKE ?)""")
                params.append(kw)
            if sf.get("fitid"):
                field_clauses.append("t.fitid LIKE ?")
                params.append(kw)
            if sf.get("note", True):  # on unless turned off (older settings do not know it)
                field_clauses.append("t.note LIKE ?")
                params.append(kw)
            if sf.get("merchant", True):  # the same
                field_clauses.append("t.merchant LIKE ?")
                params.append(kw)
            if field_clauses:
                q += " AND (" + " OR ".join(field_clauses) + ")"

        q += " ORDER BY t.date DESC, t.id"
        rows = self.conn.execute(q, params).fetchall()

        if not rows:
            return []

        # Second pass — attach tags without blowing up the main query
        ids = [r["id"] for r in rows]
        ph = ",".join("?" * len(ids))
        tag_rows = self.conn.execute(f"""
            SELECT tt.transaction_id, tg.name
            FROM transaction_tags tt
            JOIN tags tg ON tg.id = tt.tag_id
            WHERE tt.transaction_id IN ({ph})
            ORDER BY tg.name
        """, ids).fetchall()

        tag_map = {}
        for tr in tag_rows:
            tag_map.setdefault(tr["transaction_id"], []).append(tr["name"])

        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = ", ".join(tag_map.get(r["id"], []))
            result.append(d)
        return result

    @atomic
    def add_transaction(self, year, month, day, type_name, account_name, amount,
                        subcategory_id, category_id, name=None, memorandum=None,
                        description=None, to_account_name=None, transfer_status=None,
                        fitid=None, merchant=None, note=None):
        """``amount`` is positive, or negative for money back of that type (a refund is a
        negative Expense, in the category it was spent in)."""
        amount = round2(amount)
        type_id = self.get_type_id(type_name)
        account_id = self.get_or_create_account(account_name) if account_name else None
        to_account_id = self.get_or_create_account(to_account_name) if to_account_name else None

        if transfer_status is None and type_name and "Transfer" in type_name:
            if account_id and to_account_id:
                transfer_status = TRANSFER_MATCHED
            else:
                transfer_status = TRANSFER_UNMATCHED

        date_str = _ymd_to_date_str(year, month, day)

        self.conn.execute("""
                          INSERT INTO transactions(date, type_id, account_id, to_account_id,
                                                   amount, subcategory_id, category_id, name, memorandum,
                                                   description, fitid, transfer_status, merchant, note)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                          """, (date_str, type_id, account_id, to_account_id,
                                amount, subcategory_id, category_id, name, memorandum,
                                description, fitid, transfer_status,
                                (merchant or "").strip() or None, (note or "").strip() or None))
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    @atomic
    def update_transaction(self, tx_id, **kwargs):
        # Convert y/m/d -> date if passed separately
        if "year" in kwargs or "month" in kwargs or "day" in kwargs:
            row = self.conn.execute("SELECT date FROM transactions WHERE id=?", (tx_id,)).fetchone()
            old_y, old_m, old_d = _date_str_to_parts(row["date"] if row else None)
            year = kwargs.pop("year", old_y)
            month = kwargs.pop("month", old_m)
            day = kwargs.pop("day", old_d)
            kwargs["date"] = _ymd_to_date_str(year, month, day)
        if "type_name" in kwargs:
            kwargs["type_id"] = self.get_type_id(kwargs.pop("type_name"))
        if "account_name" in kwargs:
            n = kwargs.pop("account_name")
            kwargs["account_id"] = self.get_or_create_account(n) if n else None
        if "to_account_name" in kwargs:
            n = kwargs.pop("to_account_name")
            kwargs["to_account_id"] = self.get_or_create_account(n) if n else None
        if "amount" in kwargs:
            kwargs["amount"] = round2(kwargs["amount"])
        sets = ", ".join(f"{k}=?" for k in kwargs)
        self.conn.execute(f"UPDATE transactions SET {sets} WHERE id=?",
                          list(kwargs.values()) + [tx_id])

    @atomic
    def delete_transaction(self, tx_id):
        self.conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))

    def fitid_exists(self, fitid, account_name):
        """Whether the account already has a transaction with this FITID. A matched transfer
        keeps both sides' FITIDs as "a|b" and counts for both accounts."""
        if not fitid:
            return False
        acc = self.get_account_by_name(account_name)
        if not acc:
            return False
        return self.conn.execute("""
            SELECT 1 FROM transactions
            WHERE (account_id = :acc OR to_account_id = :acc) AND fitid IS NOT NULL
              AND (fitid = :fitid OR instr('|' || fitid || '|', '|' || :fitid || '|') > 0)
            LIMIT 1""", {"acc": acc["id"], "fitid": fitid}).fetchone() is not None

    def get_uncategorized_transactions(self, from_str, to_str):
        uncat_cat_id, _ = self.get_uncategorized_ids()
        return self.conn.execute("""
                                 SELECT t.date,
                                        t.amount,
                                        a.name  as account,
                                        ty.name as type_name,
                                        t.name,
                                        t.memorandum
                                 FROM transactions t
                                          LEFT JOIN accounts a ON t.account_id = a.id
                                          LEFT JOIN types ty ON t.type_id = ty.id
                                 WHERE t.category_id = ?
                                   AND (ty.name LIKE '%Income%' OR ty.name LIKE '%Expense%')
                                   AND t.date BETWEEN ? AND ?
                                 ORDER BY t.date DESC
                                 """, (uncat_cat_id, from_str, to_str)).fetchall()

    def get_unmatched_transfer_transactions(self, from_str, to_str):
        return self.conn.execute("""
                                 SELECT t.date,
                                        t.amount,
                                        a.name  as account,
                                        ta.name as to_account,
                                        t.name,
                                        t.memorandum
                                 FROM transactions t
                                          LEFT JOIN accounts a ON t.account_id = a.id
                                          LEFT JOIN accounts ta ON t.to_account_id = ta.id
                                 WHERE t.transfer_status = 'unmatched'
                                   AND t.date BETWEEN ? AND ?
                                 ORDER BY t.date DESC
                                 """, (from_str, to_str)).fetchall()

    def get_unmatched_transfers(self):
        return self.conn.execute("""
                                 SELECT t.date,
                                        t.amount,
                                        a.name  as account,
                                        ta.name as to_account,
                                        t.memorandum,
                                        t.name
                                 FROM transactions t
                                          LEFT JOIN accounts a ON t.account_id = a.id
                                          LEFT JOIN accounts ta ON t.to_account_id = ta.id
                                 WHERE t.transfer_status = ?
                                 ORDER BY t.date DESC
                                 """, (TRANSFER_UNMATCHED,)).fetchall()

    # ── Account ID Mappings ───────────────────────────────────────
    def get_account_by_acctid(self, acctid):
        return self.conn.execute("""
                                 SELECT a.name, a.id, ai.accttype, ai.bankid
                                 FROM account_ids ai
                                          JOIN accounts a ON ai.account_id = a.id
                                 WHERE ai.acctid = ?
                                 """, (acctid,)).fetchone()

    @atomic
    def save_account_id(self, acctid, account_name, accttype=None, bankid=None):
        acc = self.get_account_by_name(account_name)
        if not acc:
            return False
        self.conn.execute("""
                          INSERT INTO account_ids(acctid, accttype, bankid, account_id)
                          VALUES (?, ?, ?, ?) ON CONFLICT(acctid) DO
                          UPDATE SET
                              account_id = excluded.account_id,
                              accttype = excluded.accttype,
                              bankid = excluded.bankid
                          """, (acctid, accttype, bankid, acc["id"]))
        return True

    def get_all_account_ids(self):
        return self.conn.execute("""
                                 SELECT ai.id, ai.acctid, ai.accttype, ai.bankid, a.name as account_name
                                 FROM account_ids ai
                                          LEFT JOIN accounts a ON ai.account_id = a.id
                                 ORDER BY a.name, ai.acctid
                                 """).fetchall()

    # ── Transfer matching ─────────────────────────────────────────
    @atomic
    def match_unmatched_transfers(self):
        rows = self.conn.execute("""
                                 SELECT t.id,
                                        t.date,
                                        t.amount,
                                        t.account_id,
                                        t.to_account_id,
                                        t.subcategory_id,
                                        t.category_id,
                                        t.fitid,
                                        t.memorandum,
                                        t.name
                                 FROM transactions t
                                 WHERE t.transfer_status = 'unmatched'
                                    OR (
                                     t.transfer_status IS NULL
                                         AND t.type_id IN (SELECT id FROM types WHERE name LIKE '%Transfer%')
                                         AND (
                                         (t.account_id IS NOT NULL AND t.to_account_id IS NULL)
                                             OR
                                         (t.account_id IS NULL AND t.to_account_id IS NOT NULL)
                                         )
                                     )
                                 ORDER BY t.date, t.id
                                 """).fetchall()

        def _transfer_type(memo, name):
            text = ((memo or "") + " " + (name or "")).upper()
            if "E-TRANSFER" in text or "ETRANSFER" in text:
                return "etransfer"
            if "INTERNET TRANSFER" in text:
                return "internet"
            return "other"

        from_rows = [r for r in rows if r["account_id"] is not None and r["to_account_id"] is None]
        to_rows = [r for r in rows if r["to_account_id"] is not None and r["account_id"] is None]

        # every possible pair, closest dates first: a greedy pass over the rows in date order
        # could take an 8-day-apart partner while an exact same-day one existed
        pairs = []
        for r1 in from_rows:
            r1_ttype = _transfer_type(r1["memorandum"], r1["name"])
            for r2 in to_rows:
                if round2(r2["amount"]) != round2(r1["amount"]) or r2["to_account_id"] == r1["account_id"]:
                    continue
                r2_ttype = _transfer_type(r2["memorandum"], r2["name"])
                if r1_ttype != "other" and r2_ttype != "other" and r1_ttype != r2_ttype:
                    continue
                try:
                    diff = abs((_date.fromisoformat(r2["date"]) - _date.fromisoformat(r1["date"])).days)
                except (TypeError, ValueError):
                    continue
                if diff <= 10:
                    pairs.append((diff, r1["date"], r1["id"], r2["id"], r1, r2))
        pairs.sort(key=lambda p: p[:4])

        internal = self.get_category_by_name(CAT_INTERNAL_TRANSFER)
        internal_id = internal["id"] if internal else None
        used = set()
        matched = 0
        self.last_merged = {}  # incoming id → the id of the pair it became (the incoming row is deleted)
        for _, _, _, _, r1, r2 in pairs:
            if r1["id"] in used or r2["id"] in used:
                continue
            acc1_name = self.get_account_name_by_id(r1["account_id"]) or ""
            acc2_name = self.get_account_name_by_id(r2["to_account_id"]) or ""
            text = " ".join(t for t in (r1["name"], r1["memorandum"], r2["name"], r2["memorandum"]) if t)
            cat_id, sub_id = self.get_transfer_cat_sub(
                description=text, from_account=acc1_name, to_account=acc2_name, matched=True)
            if internal_id in (r1["category_id"], r2["category_id"]):  # already known to be internal
                cat_id, sub_id = internal_id, self.get_subcategory_by_name(SUB_MATCHED, internal_id)["id"]

            combined_fitid = "|".join(f for f in [r1["fitid"], r2["fitid"]] if f) or None
            self.conn.execute("""
                              UPDATE transactions
                              SET to_account_id=?,
                                  transfer_status=?,
                                  subcategory_id=?,
                                  category_id=?,
                                  fitid=?,
                                  name=?,
                                  memorandum=?
                              WHERE id = ?
                              """, (r2["to_account_id"], TRANSFER_MATCHED, sub_id, cat_id, combined_fitid,
                                    r1["name"] or r2["name"], r1["memorandum"] or r2["memorandum"], r1["id"]))
            # the incoming side's tags stay with the pair
            self.conn.execute("""INSERT OR IGNORE INTO transaction_tags(transaction_id, tag_id)
                                 SELECT ?, tag_id FROM transaction_tags WHERE transaction_id = ?""",
                              (r1["id"], r2["id"]))
            self.conn.execute("DELETE FROM transactions WHERE id=?", (r2["id"],))
            self.last_merged[r2["id"]] = r1["id"]
            used.update((r1["id"], r2["id"]))
            matched += 1

        return matched

    # ── Cascading filter options ───────────────────────────────────
    def get_filter_options(self, filters=None):
        f = filters or {}

        def _selected(key):
            vals = f.get(key)
            return bool(vals)

        def _add_date_filters(q, params):
            if f.get("from_day"):
                q += " AND t.date >= ?"
                params.append(f["from_day"])
            if f.get("to_day"):
                q += " AND t.date <= ?"
                params.append(f["to_day"])
            return q, params

        def _add_search_filter(q, params):
            search = (f.get("search") or "").strip()
            if search:
                kw = f"%{search}%"
                q += """
                    AND (
                        s.name LIKE ?
                        OR c.name LIKE ?
                        OR a.name LIKE ?
                        OR ta.name LIKE ?
                        OR t.name LIKE ?
                        OR t.memorandum LIKE ?
                        OR t.description LIKE ?
                        OR t.fitid LIKE ?
                        OR t.merchant LIKE ?
                        OR t.note LIKE ?
                    )
                """
                params += [kw] * 10
            return q, params

        def build_base(exclude_key):
            q = """
                SELECT ty.name AS type_name,
                       a.name  AS aname,
                       ta.name AS taname,
                       c.name  AS cname,
                       s.name  AS sname
                FROM transactions t
                         LEFT JOIN types ty ON t.type_id = ty.id
                         LEFT JOIN accounts a ON t.account_id = a.id
                         LEFT JOIN accounts ta ON t.to_account_id = ta.id
                         LEFT JOIN subcategories s ON t.subcategory_id = s.id
                         LEFT JOIN categories c ON t.category_id = c.id
                WHERE 1 = 1 \
                """
            params = []

            q, params = _add_date_filters(q, params)

            if exclude_key != "type" and _selected("type"):
                vals = f["type"]
                ph = ",".join("?" * len(vals))
                q += f" AND ty.name IN ({ph})"
                params += vals

            if exclude_key != "account" and _selected("account"):
                vals = f["account"]
                ph = ",".join("?" * len(vals))
                q += f" AND (a.name IN ({ph}) OR ta.name IN ({ph}))"
                params += vals + vals

            if exclude_key != "category" and _selected("category"):
                vals = f["category"]
                ph = ",".join("?" * len(vals))
                q += f" AND c.name IN ({ph})"
                params += vals

            if exclude_key != "subcategory" and _selected("subcategory"):
                vals = f["subcategory"]
                ph = ",".join("?" * len(vals))
                q += f" AND s.name IN ({ph})"
                params += vals

            q, params = _add_search_filter(q, params)

            return q, params

        result = {}

        for dim in ["type", "account", "category", "subcategory"]:
            q, params = build_base(dim)

            if dim == "account":
                rows = self.conn.execute(
                    f"""
                    SELECT DISTINCT aname AS val FROM ({q}) x WHERE val IS NOT NULL
                    UNION
                    SELECT DISTINCT taname AS val FROM ({q}) x WHERE val IS NOT NULL
                    """,
                    params + params
                ).fetchall()
                result[dim] = sorted({r["val"] for r in rows})

            elif dim == "type":
                rows = self.conn.execute(
                    f"SELECT DISTINCT type_name AS val FROM ({q}) x WHERE val IS NOT NULL ORDER BY val",
                    params
                ).fetchall()
                result[dim] = [r["val"] for r in rows]

            elif dim == "category":
                rows = self.conn.execute(
                    f"SELECT DISTINCT cname AS val FROM ({q}) x WHERE val IS NOT NULL ORDER BY val",
                    params
                ).fetchall()
                result[dim] = [r["val"] for r in rows]

            elif dim == "subcategory":
                rows = self.conn.execute(
                    f"SELECT DISTINCT sname AS val FROM ({q}) x WHERE val IS NOT NULL ORDER BY val",
                    params
                ).fetchall()
                result[dim] = [r["val"] for r in rows]

        return result

    # ── Import Mappings ───────────────────────────────────────────
    @atomic
    def save_mapping(self, type_name, account_name, name=None, memorandum=None,
                     subcategory_id=None, category_id=None, merchant=None):
        """Add a rule, or change the rule with the same type, account, name and memo.

        A rule sets the merchant and the category; one in Uncategorized sets only the merchant
        (the category is then chosen by hand: Amazon, a friend who pays back)."""
        merchant = (merchant or "").strip() or None
        type_id = self.get_type_id(type_name) if type_name else None
        acc = self.get_account_by_name(account_name) if account_name else None
        account_id = acc["id"] if acc else None
        name = (name or "").strip() or None
        memorandum = (memorandum or "").strip() or None
        same = self.conn.execute(
            "SELECT id FROM import_mappings WHERE type_id IS ? AND account_id IS ? AND name IS ? AND memorandum IS ?",
            (type_id, account_id, name, memorandum)).fetchone()
        if same:
            self.conn.execute("UPDATE import_mappings SET subcategory_id=?, category_id=?, merchant=? WHERE id=?",
                              (subcategory_id, category_id, merchant, same["id"]))
        else:
            self.conn.execute(
                "INSERT INTO import_mappings(type_id, account_id, name, memorandum, subcategory_id, category_id, "
                "merchant) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (type_id, account_id, name, memorandum, subcategory_id, category_id, merchant))

    def get_rule_id(self, type_name, account_name, name=None, memorandum=None):
        """The id of the rule with exactly this type, account (None = all), name and memo."""
        type_id = self.get_type_id(type_name) if type_name else None
        acc = self.get_account_by_name(account_name) if account_name else None
        row = self.conn.execute(
            "SELECT id FROM import_mappings WHERE type_id IS ? AND account_id IS ? AND name IS ? AND memorandum IS ?",
            (type_id, acc["id"] if acc else None, (name or "").strip() or None,
             (memorandum or "").strip() or None)).fetchone()
        return row["id"] if row else None

    def get_uncategorized_rows(self, type_name):
        """Transactions of a type with no category (To review). One with a category but no
        sub-category is not missing anything, so a new rule never changes it."""
        return self.conn.execute(
            """SELECT t.id, a.name AS account, t.name, t.memorandum
               FROM transactions t
                    JOIN types ty ON ty.id = t.type_id
                    LEFT JOIN accounts a ON a.id = t.account_id
                    LEFT JOIN categories c ON c.id = t.category_id
               WHERE ty.name = ? AND (t.category_id IS NULL OR c.name = ?)""",
            (type_name, UNCATEGORIZED_CAT)).fetchall()

    def get_merchants(self):
        """Every merchant name in use (transactions and rules), A to Z."""
        rows = self.conn.execute("""
            SELECT merchant FROM transactions WHERE merchant IS NOT NULL AND TRIM(merchant) <> ''
            UNION SELECT merchant FROM import_mappings WHERE merchant IS NOT NULL AND TRIM(merchant) <> ''
        """).fetchall()
        return sorted({r[0] for r in rows}, key=str.casefold)

    def get_categories_for_merchant(self, merchant, type_name):
        """The categories this merchant's transactions of ``type_name`` are in, most used first
        (Uncategorized left out): suggested first when choosing a category."""
        if not (merchant or "").strip():
            return []
        rows = self.conn.execute("""
            SELECT c.name, COUNT(*) AS n FROM transactions t
                 JOIN categories c ON c.id = t.category_id
                 JOIN types ty ON ty.id = t.type_id
            WHERE t.merchant = ? COLLATE NOCASE AND ty.name = ? AND c.name <> ?
            GROUP BY c.name ORDER BY n DESC, c.name""", (merchant.strip(), type_name, UNCATEGORIZED_CAT)).fetchall()
        return [r["name"] for r in rows]

    def get_to_review_count(self):
        """Income and expense transactions with no category (all time): the "To review" list."""
        cat_id, _ = self.get_uncategorized_ids()
        return self.conn.execute("""
            SELECT COUNT(*) FROM transactions t JOIN types ty ON ty.id = t.type_id
            WHERE (t.category_id = ? OR t.category_id IS NULL)
              AND (ty.name LIKE '%Income%' OR ty.name LIKE '%Expense%')""", (cat_id,)).fetchone()[0]

    def lookup_mapping(self, type_name, account_name, name=None, memorandum=None):
        """The rule for a transaction, or None.

        A rule's name and memo patterns are terms separated by ``|``; all of them must appear
        as whole words (case-insensitive), so "Ali" matches "E-TRANSFER ALI" and "ALI MOHAMMAD"
        but not "NATALIE". When several rules match, the most specific wins: the most matched
        text, then a rule for this account over one for all accounts, then the newest rule.
        """
        type_id = self.get_type_id(type_name) if type_name else None
        account_id = None
        if account_name:
            acc = self.get_account_by_name(account_name)
            account_id = acc["id"] if acc else None
        candidates = self.conn.execute(
            "SELECT * FROM import_mappings WHERE type_id = ? AND (account_id = ? OR account_id IS NULL)",
            (type_id, account_id)).fetchall()
        best, best_key = None, None
        for row in candidates:
            name_len = rule_match_length(name, row["name"])
            memo_len = rule_match_length(memorandum, row["memorandum"])
            if name_len is None or memo_len is None:
                continue
            key = (name_len + memo_len, row["account_id"] is not None, row["id"])
            if best_key is None or key > best_key:
                best, best_key = row, key
        return best

    # ── Dashboard / Analytics ─────────────────────────────────────
    @staticmethod
    def _month_range_dates(from_year, from_month, to_year, to_month):
        """Returns (from_date_str, to_date_str) for a month range."""
        from_str = f"{int(from_year):04d}-{MONTH_NUM.get(from_month, 1):02d}-01"
        last_day = calendar.monthrange(int(to_year), MONTH_NUM.get(to_month, 12))[1]
        to_str = f"{int(to_year):04d}-{MONTH_NUM.get(to_month, 12):02d}-{last_day:02d}"
        return from_str, to_str

    def get_dashboard_summary(self, from_year, from_month, to_year, to_month):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        row = self.conn.execute("""
                                SELECT SUM(CASE WHEN ty.name LIKE '%Income%' THEN t.amount ELSE 0 END)  AS income,
                                       SUM(CASE WHEN ty.name LIKE '%Expense%' THEN t.amount ELSE 0 END) AS expense,
                                       COUNT(*)                                                         AS tx_count
                                FROM transactions t
                                         LEFT JOIN types ty ON t.type_id = ty.id
                                WHERE t.date BETWEEN ? AND ?
                                """, (from_str, to_str)).fetchone()

        income = round2(row["income"] or 0)
        expense = round2(row["expense"] or 0)
        return {
            "income": income,
            "expense": expense,
            "net": round2(income - expense),
            "tx_count": row["tx_count"] or 0,
        }

    def uncategorized_subcategory(self, category_id):
        """The "Uncategorized" sub-category of a category (category known, sub-category not yet),
        created the first time it is needed."""
        sub = self.get_subcategory_by_name(UNCATEGORIZED_SUB, category_id)
        if not sub:
            self.add_subcategory(UNCATEGORIZED_SUB, category_id)
            sub = self.get_subcategory_by_name(UNCATEGORIZED_SUB, category_id)
        return sub

    def get_uncategorized_overview(self):
        """All-time Income/Expense transactions without a (sub-)category, grouped.

        Returns rows of {kind: "Income"|"Expense", type, category, count, total}; ``category`` is
        "Uncategorized" for fully uncategorized rows, else the category whose sub-category is
        "Uncategorized".
        """
        rows = self.conn.execute("""
            SELECT CASE WHEN ty.name LIKE '%Income%' THEN 'Income' ELSE 'Expense' END AS kind,
                   ty.name AS type, c.name AS category, COUNT(*) AS count, SUM(t.amount) AS total
            FROM transactions t
            JOIN types ty ON t.type_id = ty.id
            JOIN categories c ON t.category_id = c.id
            LEFT JOIN subcategories s ON t.subcategory_id = s.id
            WHERE (ty.name LIKE '%Income%' OR ty.name LIKE '%Expense%')
              AND (c.name = :uncat OR s.name = :uncat OR t.subcategory_id IS NULL)
            GROUP BY kind, ty.name, c.name
            ORDER BY kind DESC, c.name <> :uncat, c.name
        """, {"uncat": UNCATEGORIZED_SUB}).fetchall()
        return [{**dict(r), "total": round2(r["total"] or 0)} for r in rows]

    def get_unmatched_transfer_overview(self):
        """All-time transfers still waiting for their other side, per account.

        Returns rows of {account, direction: "Outgoing"|"Incoming", type, category, count, total}.
        """
        rows = self.conn.execute("""
            SELECT COALESCE(a.name, ta.name) AS account,
                   CASE WHEN t.account_id IS NOT NULL THEN 'Outgoing' ELSE 'Incoming' END AS direction,
                   ty.name AS type, c.name AS category, COUNT(*) AS count, SUM(t.amount) AS total
            FROM transactions t
            JOIN types ty ON t.type_id = ty.id
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN accounts ta ON t.to_account_id = ta.id
            WHERE ty.name LIKE '%Transfer%'
              AND (t.transfer_status = :unmatched
                   OR (t.transfer_status IS NULL AND (t.account_id IS NULL OR t.to_account_id IS NULL)))
            GROUP BY account, direction, ty.name, c.name
            ORDER BY account, direction DESC, c.name
        """, {"unmatched": TRANSFER_UNMATCHED}).fetchall()
        return [{**dict(r), "total": round2(r["total"] or 0)} for r in rows]

    def get_uncategorized_count(self, from_year, from_month, to_year, to_month):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        cat_id, _ = self.get_uncategorized_ids()
        row = self.conn.execute("""
                                SELECT COUNT(*) AS cnt
                                FROM transactions t
                                         LEFT JOIN types ty ON t.type_id = ty.id
                                WHERE t.date BETWEEN ? AND ?
                                  AND t.category_id = ?
                                  AND (ty.name LIKE '%Income%' OR ty.name LIKE '%Expense%')
                                """, (from_str, to_str, cat_id)).fetchone()
        return row["cnt"] if row else 0

    def get_unmatched_transfer_count(self, from_year, from_month, to_year, to_month):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        row = self.conn.execute("""
                                SELECT COUNT(*) AS cnt
                                FROM transactions t
                                WHERE t.date BETWEEN ? AND ?
                                  AND t.transfer_status = ?
                                """, (from_str, to_str, TRANSFER_UNMATCHED)).fetchone()
        return row["cnt"] if row else 0

    def get_monthly_summary_for_range(self, from_year, from_month, to_year, to_month):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        rows = self.conn.execute("""
                                 SELECT strftime('%Y', t.date) AS year,
                strftime('%m', t.date) AS month_num,
                SUM(CASE WHEN ty.name LIKE '%Income%'  THEN t.amount ELSE 0 END) AS income,
                SUM(CASE WHEN ty.name LIKE '%Expense%' THEN t.amount ELSE 0 END) AS expense
                                 FROM transactions t
                                     LEFT JOIN types ty
                                 ON t.type_id = ty.id
                                 WHERE t.date BETWEEN ?
                                   AND ?
                                   AND (ty.name LIKE '%Income%'
                                    OR ty.name LIKE '%Expense%')
                                 GROUP BY year, month_num
                                 ORDER BY year, month_num
                                 """, (from_str, to_str)).fetchall()

        result = {}
        for r in rows:
            y = int(r["year"])
            m = MONTHS_ORDER[int(r["month_num"]) - 1]
            result[(y, m)] = {
                "income": round2(r["income"] or 0),
                "expense": round2(r["expense"] or 0),
            }
        return result

    def get_category_totals_for_range(self, from_year, from_month, to_year, to_month):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        return self.conn.execute("""
                                 SELECT c.name AS category, ty.name AS type_name, SUM(t.amount) AS total
                                 FROM transactions t
                                          JOIN categories c ON t.category_id = c.id
                                          LEFT JOIN types ty ON t.type_id = ty.id
                                 WHERE t.date BETWEEN ? AND ?
                                   AND (ty.name LIKE '%Income%' OR ty.name LIKE '%Expense%')
                                 GROUP BY c.name, ty.name
                                 HAVING total > 0
                                 ORDER BY total DESC
                                 """, (from_str, to_str)).fetchall()

    def get_latest_account_balances(self, visible_only=False):
        snapshots, _ = self.get_account_monthly_balance()
        if not snapshots:
            return {}
        latest_period = sorted(
            snapshots.keys(),
            key=lambda ym: (ym[0], MONTH_NUM.get(ym[1], 0))
        )[-1]
        balances = snapshots[latest_period]
        if visible_only:
            visible_ids = {a["id"] for a in self.get_accounts(visible_only=True)}
            balances = {aid: bal for aid, bal in balances.items() if aid in visible_ids}
        return {aid: round2(bal) for aid, bal in balances.items()}

    def get_current_total_balance(self):
        return round2(sum(self.get_latest_account_balances().values()))

    def get_monthly_category_totals(self, year_from, month_from, year_to, month_to,
                                    type_filter="Expense",
                                    account_names=None,
                                    category_name=None,
                                    group_by="category"):
        if group_by not in ("category", "subcategory"):
            group_by = "category"

        key_expr = "c.name" if group_by == "category" else "COALESCE(s.name, '(No Sub-Category)')"
        from_str, to_str = self._month_range_dates(year_from, month_from, year_to, month_to)

        q = f"""
            SELECT strftime('%Y', t.date) AS year,
                   strftime('%m', t.date) AS month_num,
                   {key_expr} AS k, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN subcategories s ON t.subcategory_id = s.id
            LEFT JOIN types ty ON t.type_id = ty.id
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN accounts ta ON t.to_account_id = ta.id
            WHERE ty.name LIKE ?
              AND t.date BETWEEN ? AND ?
        """
        params = [f"%{type_filter}%", from_str, to_str]

        if account_names:
            placeholders = ",".join("?" * len(account_names))
            q += f" AND (a.name IN ({placeholders}) OR ta.name IN ({placeholders}))"
            params += account_names + account_names

        if category_name:
            q += " AND c.name = ?"
            params.append(category_name)

        q += f" GROUP BY year, month_num, {key_expr}"

        rows = self.conn.execute(q, params).fetchall()
        result = {}
        for r in rows:
            y = int(r["year"])
            m = MONTHS_ORDER[int(r["month_num"]) - 1]
            key = (y, m)
            if key not in result:
                result[key] = {}
            result[key][r["k"]] = r["total"] or 0
        return result

    def get_period_totals_by_group(self, from_year, from_month, to_year, to_month,
                                   type_filter, account_names=None,
                                   category_name=None, group_by="category"):
        if group_by not in ("category", "subcategory"):
            group_by = "category"

        key_expr = "c.name" if group_by == "category" else "COALESCE(s.name, '(No Sub-Category)')"
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)

        q = f"""
            SELECT {key_expr} AS k, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            LEFT JOIN subcategories s ON t.subcategory_id = s.id
            LEFT JOIN types ty ON t.type_id = ty.id
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN accounts ta ON t.to_account_id = ta.id
            WHERE ty.name LIKE ?
              AND t.date BETWEEN ? AND ?
        """
        params = [f"%{type_filter}%", from_str, to_str]

        if account_names:
            ph = ",".join("?" * len(account_names))
            q += f" AND (a.name IN ({ph}) OR ta.name IN ({ph}))"
            params += account_names + account_names

        if category_name:
            q += " AND c.name = ?"
            params.append(category_name)

        q += f" GROUP BY {key_expr} HAVING ROUND(total, 2) <> 0 ORDER BY total DESC"  # negative: money back
        rows = self.conn.execute(q, params).fetchall()
        return {r["k"]: round2(r["total"] or 0) for r in rows if r["k"]}

    def get_account_monthly_balance(self):
        """Running balance per account at the end of every month, starting from 0.

        Every month from the first transaction to the last has an entry (a month without
        transactions repeats the balances before it). One pass over the transactions, and
        cached until the next change to the database: three tabs ask for it on each refresh.
        """
        cached = self._cache.get("monthly_balance")
        if cached and cached[0] == self._data_version:
            return cached[1]
        rows = self.conn.execute("""
            SELECT t.date, t.account_id, t.to_account_id, t.amount, ty.name AS type_name
            FROM transactions t LEFT JOIN types ty ON t.type_id = ty.id
            WHERE t.date IS NOT NULL
            ORDER BY t.date
        """).fetchall()
        accounts = {a["id"]: a["name"] for a in self.get_accounts()}
        running = {aid: 0.0 for aid in accounts}
        snapshots = {}

        def close_months(until):  # snapshot every month before ``until`` (year, month_num)
            nonlocal current
            while current is not None and current < until:
                y, mn = current
                snapshots[(y, MONTHS_ORDER[mn - 1])] = {aid: round2(bal) for aid, bal in running.items()}
                current = (y + 1, 1) if mn == 12 else (y, mn + 1)

        current = None
        for r in rows:
            month = (int(r["date"][:4]), int(r["date"][5:7]))
            if current is None:
                current = month
            close_months(month)
            type_name = r["type_name"] or ""
            aid, taid, total = r["account_id"], r["to_account_id"], r["amount"] or 0
            if "Income" in type_name:
                if aid: running[aid] = running.get(aid, 0) + total
            elif "Expense" in type_name:
                if aid: running[aid] = running.get(aid, 0) - total
            elif "Transfer" in type_name:
                if aid: running[aid] = running.get(aid, 0) - total
                if taid: running[taid] = running.get(taid, 0) + total
        if current is not None:
            last = current
            close_months((last[0] + 1, 1) if last[1] == 12 else (last[0], last[1] + 1))

        self._cache["monthly_balance"] = (self._data_version, (snapshots, accounts))
        return snapshots, accounts

    def get_categories_in_month_range(self, from_year, from_month, to_year, to_month,
                                      type_filter, account_names=None):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        q = """
            SELECT c.name
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            LEFT JOIN types ty ON t.type_id = ty.id
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN accounts ta ON t.to_account_id = ta.id
            WHERE ty.name LIKE ?
              AND t.date BETWEEN ? AND ?
        """
        params = [f"%{type_filter}%", from_str, to_str]

        if account_names:
            ph = ",".join("?" * len(account_names))
            q += f" AND (a.name IN ({ph}) OR ta.name IN ({ph}))"
            params += account_names + account_names

        q += " GROUP BY c.name HAVING ROUND(SUM(t.amount), 2) <> 0 ORDER BY c.name"
        rows = self.conn.execute(q, params).fetchall()
        return [r["name"] for r in rows]

    def get_data_date_range(self):
        row = self.conn.execute("""
                                SELECT MIN(date) as min_date, MAX(date) as max_date
                                FROM transactions
                                """).fetchone()
        today = _date.today()
        if not row or not row["min_date"]:
            return today, today
        return _date.fromisoformat(row["min_date"]), _date.fromisoformat(row["max_date"])

    # ── Export from xlsx ──────────────────────────────────────────
    def export_to_xlsx(self, path, filters=None, rows=None):
        """Write transactions to an Excel file: ``rows`` as given (e.g. the table's rows in
        their on-screen order), or those matching ``filters``."""
        rows = self.get_transactions(filters) if rows is None else rows
        data = []
        for r in rows:
            y, m, d = _date_str_to_parts(r["date"])
            data.append({
                "Date": r["date"],
                "Year": y, "Month": m, "Day": d,
                "Type": r["type"],
                "Account": r["account"],
                "To Account": r["to_account"] or "",
                "Amount": r["amount"],
                "Merchant": (r["merchant"] if "merchant" in r.keys() else "") or "",
                "Sub-Category": r["subcategory"],
                "Category": r["category"],
                "Name": r["name"] or "",
                "Memorandum": r["memorandum"] or "",
                "Note": (r["note"] if "note" in r.keys() else "") or "",
                "Description": r["description"] or "",
                "Status": r["transfer_status"] or "",
                "Tags": r["tags"] if "tags" in r.keys() else "",
                "FITID": r["fitid"] or "",
            })
        pd.DataFrame(data).to_excel(path, index=False)

    # ── Manage dialog helpers ─────────────────────────────────────
    def get_transaction_count_for_account(self, account_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE account_id=? OR to_account_id=?",
            (account_id, account_id)
        ).fetchone()[0]

    def get_account_name_by_id(self, account_id):
        row = self.conn.execute(
            "SELECT name FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        return row["name"] if row else None

    def get_account_with_bank_by_id(self, account_id):
        acc = self.conn.execute(
            "SELECT * FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        bank = self.conn.execute(
            "SELECT * FROM account_ids WHERE account_id=?", (account_id,)
        ).fetchone()
        return acc, bank

    @atomic
    def delete_account_id_by_account(self, account_id):
        self.conn.execute(
            "DELETE FROM account_ids WHERE account_id=?", (account_id,)
        )

    def get_account_color_by_id(self, account_id):
        row = self.conn.execute(
            "SELECT color FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        return row["color"] if row else None

    def get_transaction_count_for_type(self, type_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE type_id=?", (type_id,)
        ).fetchone()[0]

    def get_rule_count_for_type(self, type_id):
        return self.conn.execute("""
                                 SELECT COUNT(*)
                                 FROM import_mappings m
                                          JOIN subcategories s ON m.subcategory_id = s.id
                                          JOIN categories c ON s.category_id = c.id
                                 WHERE c.type_id = ?
                                 """, (type_id,)).fetchone()[0]

    def get_category_count_for_type(self, type_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM categories WHERE type_id=?", (type_id,)
        ).fetchone()[0]

    def get_transaction_count_for_category(self, category_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id=?", (category_id,)
        ).fetchone()[0]

    def get_rule_count_for_category(self, category_id):
        return self.conn.execute("""
                                 SELECT COUNT(*)
                                 FROM import_mappings m
                                          JOIN subcategories s ON m.subcategory_id = s.id
                                 WHERE s.category_id = ?
                                 """, (category_id,)).fetchone()[0]

    def get_subcategory_count_for_category(self, category_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM subcategories WHERE category_id=?", (category_id,)
        ).fetchone()[0]

    def get_transaction_count_for_subcategory(self, subcategory_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE subcategory_id=?", (subcategory_id,)
        ).fetchone()[0]

    def get_rule_count_for_subcategory(self, subcategory_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM import_mappings WHERE subcategory_id=?", (subcategory_id,)
        ).fetchone()[0]

    def get_rules_for_subcategory(self, subcategory_id):
        return self.conn.execute("""
                                 SELECT m.id,
                                        m.name,
                                        m.memorandum,
                                        a.name as account_name,
                                        m.account_id,
                                        m.type_id,
                                        m.subcategory_id,
                                        m.category_id,
                                        m.merchant
                                 FROM import_mappings m
                                          LEFT JOIN accounts a ON m.account_id = a.id
                                 WHERE m.subcategory_id = ?
                                 ORDER BY a.name, m.name, m.memorandum
                                 """, (subcategory_id,)).fetchall()

    @atomic
    def delete_rule(self, rule_id):
        self.conn.execute("DELETE FROM import_mappings WHERE id=?", (rule_id,))

    @atomic
    def delete_rule_and_save(self, rule_id, type_name, account_name,
                             name, memorandum, subcategory_id, category_id, merchant=None):
        self.conn.execute("DELETE FROM import_mappings WHERE id=?", (rule_id,))
        self.save_mapping(
            type_name=type_name,
            account_name=account_name,
            name=name,
            memorandum=memorandum,
            subcategory_id=subcategory_id,
            category_id=category_id,
            merchant=merchant,
        )

    # ── Tags ──────────────────────────────────────────────────────
    def get_tags(self):
        return self.conn.execute(
            "SELECT id, name FROM tags ORDER BY name"
        ).fetchall()

    @atomic
    def add_tag(self, name):
        try:
            self.conn.execute("INSERT INTO tags(name) VALUES(?)", (name,))
            return True
        except sqlite3.IntegrityError:
            return False

    @atomic
    def rename_tag(self, tag_id, new_name):
        try:
            self.conn.execute("UPDATE tags SET name=? WHERE id=?", (new_name, tag_id))
            return True
        except sqlite3.IntegrityError:
            return False

    @atomic
    def delete_tag(self, tag_id):
        self.conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))

    def get_tags_for_transaction(self, transaction_id):
        return self.conn.execute("""
            SELECT t.id, t.name
            FROM tags t
            JOIN transaction_tags tt ON tt.tag_id = t.id
            WHERE tt.transaction_id = ?
            ORDER BY t.name
        """, (transaction_id,)).fetchall()

    @atomic
    def set_tags_for_transaction(self, transaction_id, tag_ids):
        self.conn.execute(
            "DELETE FROM transaction_tags WHERE transaction_id=?",
            (transaction_id,)
        )
        for tag_id in tag_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO transaction_tags(transaction_id, tag_id) VALUES(?,?)",
                (transaction_id, tag_id)
            )

    def get_transaction_count_for_tag(self, tag_id):
        return self.conn.execute(
            "SELECT COUNT(*) FROM transaction_tags WHERE tag_id=?", (tag_id,)
        ).fetchone()[0]