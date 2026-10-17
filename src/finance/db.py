import sqlite3
import pandas as pd
import os
import re
from datetime import datetime, date as _date
import calendar
from decimal import Decimal, ROUND_HALF_UP
from finance.style import TAB20_COLORS

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


class Database:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._migrate()

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
        cat_indices = [r[1] for r in c.execute("PRAGMA index_list(categories)").fetchall()]
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

        c.commit()
        self._seed_uncategorized()
        self._seed_transfer_categories()

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

    def add_type(self, name):
        try:
            self.conn.execute("INSERT INTO types(name) VALUES(?)", (name,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_type(self, old_name, new_name):
        self.conn.execute("UPDATE types SET name=? WHERE name=?", (new_name, old_name))
        self.conn.commit()

    def delete_type(self, name):
        self.conn.execute("DELETE FROM types WHERE name=?", (name,))
        self.conn.commit()

    # ── Categories ────────────────────────────────────────────────
    def get_categories(self, type_id=None):
        if type_id:
            return self.conn.execute(
                "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.type_id=? ORDER BY c.name",
                (type_id,)).fetchall()
        return self.conn.execute(
            "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id ORDER BY c.name"
        ).fetchall()

    def get_category_by_name(self, name, type_id=None):
        if type_id is not None:
            return self.conn.execute(
                "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.name=? AND c.type_id=?",
                (name, type_id)).fetchone()
        return self.conn.execute(
            "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.name=? LIMIT 1",
            (name,)).fetchone()

    def get_category_by_id(self, id_):
        return self.conn.execute(
            "SELECT c.*, t.name as type_name FROM categories c LEFT JOIN types t ON c.type_id=t.id WHERE c.id=?",
            (id_,)).fetchone()

    def add_category(self, name, type_name=None):
        try:
            type_id = self.get_type_id(type_name) if type_name else None
            self.conn.execute("INSERT INTO categories(name, type_id) VALUES(?,?)", (name, type_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already exists under same type

    def rename_category(self, old_name, new_name):
        old = self.get_category_by_name(old_name)
        if not old:
            return
        existing = self.get_category_by_name(new_name, old["type_id"])
        if existing and existing["id"] != old["id"]:
            self.conn.execute(
                "UPDATE transactions SET category_id=? WHERE category_id=?",
                (existing["id"], old["id"]))
            self.conn.execute(
                "UPDATE subcategories SET category_id=? WHERE category_id=?",
                (existing["id"], old["id"]))
            self.conn.execute("DELETE FROM categories WHERE id=?", (old["id"],))
        else:
            self.conn.execute("UPDATE categories SET name=? WHERE id=?", (new_name, old["id"]))
        self.conn.commit()

    def delete_category(self, cat_id):
        uncat_cat_id, uncat_sub_id = self.get_uncategorized_ids()
        self.conn.execute("""
                          UPDATE transactions
                          SET category_id=?,
                              subcategory_id=?
                          WHERE category_id = ?
                          """, (uncat_cat_id, uncat_sub_id, cat_id))
        self.conn.execute("DELETE FROM categories WHERE id=?", (cat_id,))
        self.conn.commit()

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

    def add_subcategory(self, name, category_id):
        try:
            self.conn.execute("INSERT INTO subcategories(name, category_id) VALUES(?,?)", (name, category_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_subcategory(self, subcat_id, new_name, new_category_id=None):
        old = self.get_subcategory_by_id(subcat_id)
        if not old:
            return
        target_cat_id = new_category_id if new_category_id else old["category_id"]
        existing = self.get_subcategory_by_name(new_name, target_cat_id)
        if existing and existing["id"] != subcat_id:
            self.conn.execute(
                "UPDATE transactions SET subcategory_id=? WHERE subcategory_id=?",
                (existing["id"], subcat_id))
            self.conn.execute("DELETE FROM subcategories WHERE id=?", (subcat_id,))
        else:
            self.conn.execute(
                "UPDATE subcategories SET name=?, category_id=? WHERE id=?",
                (new_name, target_cat_id, subcat_id))
        self.conn.commit()

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

        self.conn.commit()

    def delete_subcategory(self, subcat_id):
        uncat_cat_id, uncat_sub_id = self.get_uncategorized_ids()
        self.conn.execute("""
                          UPDATE transactions
                          SET category_id=?,
                              subcategory_id=?
                          WHERE subcategory_id = ?
                          """, (uncat_cat_id, uncat_sub_id, subcat_id))
        self.conn.execute("DELETE FROM subcategories WHERE id=?", (subcat_id,))
        self.conn.commit()

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

    def get_or_create_account(self, name):
        row = self.conn.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()
        if row:
            return row["id"]
        used = [r["color"] for r in self.conn.execute("SELECT color FROM accounts").fetchall()]
        color = next((c for c in TAB20_COLORS if c not in used), TAB20_COLORS[0])
        cur = self.conn.execute("INSERT INTO accounts(name, color) VALUES(?,?)", (name, color))
        self.conn.commit()
        return cur.lastrowid

    def update_account(self, account_id, **kwargs):
        sets = ", ".join(f"{k}=?" for k in kwargs)
        self.conn.execute(f"UPDATE accounts SET {sets} WHERE id=?",
                          list(kwargs.values()) + [account_id])
        self.conn.commit()

    def rename_account(self, old_name, new_name):
        existing = self.get_account_by_name(new_name)
        old = self.get_account_by_name(old_name)
        if not old:
            return
        if existing and existing["id"] != old["id"]:
            self.conn.execute(
                "UPDATE transactions SET account_id=? WHERE account_id=?",
                (existing["id"], old["id"]))
            self.conn.execute(
                "UPDATE transactions SET to_account_id=? WHERE to_account_id=?",
                (existing["id"], old["id"]))
            self.conn.execute("DELETE FROM accounts WHERE id=?", (old["id"],))
        else:
            self.conn.execute("UPDATE accounts SET name=? WHERE name=?", (new_name, old_name))
        self.conn.commit()

    def delete_account(self, account_id):
        self.conn.execute("UPDATE transactions SET account_id=NULL WHERE account_id=?", (account_id,))
        self.conn.execute("UPDATE transactions SET to_account_id=NULL WHERE to_account_id=?", (account_id,))
        self.conn.execute("UPDATE import_mappings SET account_id=NULL WHERE account_id=?", (account_id,))
        self.conn.execute("DELETE FROM account_ids WHERE account_id=?", (account_id,))
        self.conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self.conn.commit()

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

    def add_transaction(self, year, month, day, type_name, account_name, amount,
                        subcategory_id, category_id, name=None, memorandum=None,
                        description=None, to_account_name=None, transfer_status=None,
                        fitid=None):
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
                                                   description, fitid, transfer_status)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                          """, (date_str, type_id, account_id, to_account_id,
                                amount, subcategory_id, category_id, name, memorandum,
                                description, fitid, transfer_status))
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

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
            kwargs["account_id"] = self.get_or_create_account(kwargs.pop("account_name"))
        if "to_account_name" in kwargs:
            n = kwargs.pop("to_account_name")
            kwargs["to_account_id"] = self.get_or_create_account(n) if n else None
        if "amount" in kwargs:
            kwargs["amount"] = round2(kwargs["amount"])
        sets = ", ".join(f"{k}=?" for k in kwargs)
        self.conn.execute(f"UPDATE transactions SET {sets} WHERE id=?",
                          list(kwargs.values()) + [tx_id])
        self.conn.commit()

    def delete_transaction(self, tx_id):
        self.conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        self.conn.commit()

    def fitid_exists(self, fitid, account_name):
        if not fitid:
            return False
        acc = self.get_account_by_name(account_name)
        if not acc:
            return False
        row = self.conn.execute("""
                                SELECT fitid
                                FROM transactions
                                WHERE account_id = ?
                                  AND fitid IS NOT NULL
                                """, (acc["id"],)).fetchall()
        for r in row:
            stored = r["fitid"] or ""
            if fitid in stored.split("|"):
                return True
        row2 = self.conn.execute("""
                                 SELECT fitid
                                 FROM transactions
                                 WHERE to_account_id = ?
                                   AND fitid IS NOT NULL
                                 """, (acc["id"],)).fetchall()
        for r in row2:
            stored = r["fitid"] or ""
            if fitid in stored.split("|"):
                return True
        return False

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
        self.conn.commit()
        return True

    def get_all_account_ids(self):
        return self.conn.execute("""
                                 SELECT ai.id, ai.acctid, ai.accttype, ai.bankid, a.name as account_name
                                 FROM account_ids ai
                                          LEFT JOIN accounts a ON ai.account_id = a.id
                                 ORDER BY a.name, ai.acctid
                                 """).fetchall()

    # ── Transfer matching ─────────────────────────────────────────
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

        used = set()
        matched = 0

        for r1 in from_rows:
            if r1["id"] in used:
                continue

            r1_ttype = _transfer_type(r1["memorandum"], r1["name"])

            best = None
            best_diff = 999
            for r2 in to_rows:
                if r2["id"] in used:
                    continue
                if round2(r2["amount"]) != round2(r1["amount"]):
                    continue
                if r2["to_account_id"] == r1["account_id"]:
                    continue

                r2_ttype = _transfer_type(r2["memorandum"], r2["name"])
                if r1_ttype != "other" and r2_ttype != "other" and r1_ttype != r2_ttype:
                    continue

                try:
                    diff = abs((_date.fromisoformat(r2["date"]) - _date.fromisoformat(r1["date"])).days)
                except Exception:
                    diff = 999
                if diff <= 10 and diff < best_diff:
                    best = r2
                    best_diff = diff

            if best is None:
                continue

            r2 = best
            acc1_name = self.conn.execute(
                "SELECT name FROM accounts WHERE id=?", (r1["account_id"],)
            ).fetchone()
            acc2_name = self.conn.execute(
                "SELECT name FROM accounts WHERE id=?", (r2["to_account_id"],)
            ).fetchone()

            cat_id, sub_id = self.get_transfer_cat_sub(
                from_account=acc1_name["name"] if acc1_name else "",
                to_account=acc2_name["name"] if acc2_name else "",
                matched=True
            )

            fitid1 = r1["fitid"] or ""
            fitid2 = r2["fitid"] or ""
            combined_fitid = "|".join(f for f in [fitid1, fitid2] if f) or None

            self.conn.execute("""
                              UPDATE transactions
                              SET to_account_id=?,
                                  transfer_status=?,
                                  subcategory_id=?,
                                  category_id=?,
                                  fitid=?
                              WHERE id = ?
                              """, (r2["to_account_id"], TRANSFER_MATCHED,
                                    sub_id, cat_id, combined_fitid, r1["id"]))
            self.conn.execute("DELETE FROM transactions WHERE id=?", (r2["id"],))

            used.add(r1["id"])
            used.add(r2["id"])
            matched += 1

        self.conn.commit()
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
                    )
                """
                params += [kw, kw, kw, kw, kw, kw, kw, kw]
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
    def save_mapping(self, type_name, account_name, name=None, memorandum=None,
                     subcategory_id=None, category_id=None):
        type_id = self.get_type_id(type_name) if type_name else None
        acc = self.get_account_by_name(account_name) if account_name else None
        account_id = acc["id"] if acc else None

        self.conn.execute("""
                          INSERT INTO import_mappings(type_id, account_id, name, memorandum, subcategory_id, category_id)
                          VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(type_id, account_id, name, memorandum) DO
                          UPDATE SET
                              subcategory_id = excluded.subcategory_id,
                              category_id = excluded.category_id
                          """, (type_id, account_id, name, memorandum, subcategory_id, category_id))
        self.conn.commit()

    def lookup_mapping(self, type_name, account_name, name=None, memorandum=None):
        type_id = self.get_type_id(type_name) if type_name else None
        if account_name:
            acc = self.get_account_by_name(account_name)
            account_id = acc["id"] if acc else None
        else:
            account_id = None

        def _field_matches(value, pattern):
            if not pattern:
                return True, 0
            value = (value or "").lower()
            terms = [p.strip().lower() for p in pattern.split("|")]
            matched = all(t in value for t in terms)
            return matched, len(terms) if matched else 0

        candidates = self.conn.execute("""
                                       SELECT *
                                       FROM import_mappings
                                       WHERE type_id = ?
                                         AND (account_id = ? OR account_id IS NULL)
                                       """, (type_id, account_id)).fetchall()

        best = None
        best_score = -1
        for row in candidates:
            name_ok, name_score = _field_matches(name, row["name"])
            memo_ok, memo_score = _field_matches(memorandum, row["memorandum"])
            if not name_ok or not memo_ok:
                continue
            score = (1 if row["account_id"] else 0) + name_score + memo_score
            if score > best_score:
                best_score = score
                best = row

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

        q += f" GROUP BY {key_expr} HAVING total > 0 ORDER BY total DESC"
        rows = self.conn.execute(q, params).fetchall()
        return {r["k"]: round2(r["total"] or 0) for r in rows if r["k"]}

    def get_account_monthly_balance(self):
        """Running balance per account per month, starting from 0."""
        rows = self.conn.execute("""
                                 SELECT strftime('%Y', t.date) AS year,
                   strftime('%m', t.date) AS month_num,
                   a.id as account_id, a.name as account,
                   ty.name as type_name,
                   t.amount as total,
                   ta.id as to_account_id, ta.name as to_account
                                 FROM transactions t
                                     LEFT JOIN types ty
                                 ON t.type_id=ty.id
                                     LEFT JOIN accounts a ON t.account_id=a.id
                                     LEFT JOIN accounts ta ON t.to_account_id=ta.id
                                 ORDER BY t.date
                                 """, []).fetchall()

        accounts = {a["id"]: a["name"] for a in self.get_accounts()}
        running = {aid: 0.0 for aid in accounts}
        snapshots = {}

        all_periods = sorted(
            {(int(r["year"]), MONTHS_ORDER[int(r["month_num"]) - 1]) for r in rows},
            key=lambda ym: (ym[0], MONTH_NUM.get(ym[1], 0))
        )

        for period in all_periods:
            y, m = period
            mn = f"{MONTH_NUM.get(m, 1):02d}"
            for r in rows:
                if r["year"] != str(y) or r["month_num"] != mn:
                    continue
                type_name = r["type_name"] or ""
                aid = r["account_id"]
                taid = r["to_account_id"]
                total = r["total"] or 0

                if "Income" in type_name:
                    if aid:  running[aid] = running.get(aid, 0) + total
                elif "Expense" in type_name:
                    if aid:  running[aid] = running.get(aid, 0) - total
                elif "Transfer" in type_name:
                    if aid:  running[aid] = running.get(aid, 0) - total
                    if taid: running[taid] = running.get(taid, 0) + total

            snapshots[period] = {aid: round2(bal) for aid, bal in running.items()}

        return snapshots, accounts

    def get_categories_in_month_range(self, from_year, from_month, to_year, to_month,
                                      type_filter, account_names=None):
        from_str, to_str = self._month_range_dates(from_year, from_month, to_year, to_month)
        q = f"""
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

        q += " GROUP BY c.name HAVING SUM(t.amount) > 0 ORDER BY c.name"
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
    def export_to_xlsx(self, path, filters=None):
        rows = self.get_transactions(filters)
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
                "Sub-Category": r["subcategory"],
                "Category": r["category"],
                "Name": r["name"] or "",
                "Memorandum": r["memorandum"] or "",
                "Description": r["description"] or "",
                "Status": r["transfer_status"] or "",
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

    def delete_account_id_by_account(self, account_id):
        self.conn.execute(
            "DELETE FROM account_ids WHERE account_id=?", (account_id,)
        )
        self.conn.commit()

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
                                        m.category_id
                                 FROM import_mappings m
                                          LEFT JOIN accounts a ON m.account_id = a.id
                                 WHERE m.subcategory_id = ?
                                 ORDER BY a.name, m.name, m.memorandum
                                 """, (subcategory_id,)).fetchall()

    def delete_rule(self, rule_id):
        self.conn.execute("DELETE FROM import_mappings WHERE id=?", (rule_id,))
        self.conn.commit()

    def delete_rule_and_save(self, rule_id, type_name, account_name,
                             name, memorandum, subcategory_id, category_id):
        with self.conn:
            self.conn.execute("DELETE FROM import_mappings WHERE id=?", (rule_id,))
            self.save_mapping(
                type_name=type_name,
                account_name=account_name,
                name=name,
                memorandum=memorandum,
                subcategory_id=subcategory_id,
                category_id=category_id,
            )

    # ── Tags ──────────────────────────────────────────────────────
    def get_tags(self):
        return self.conn.execute(
            "SELECT id, name FROM tags ORDER BY name"
        ).fetchall()

    def add_tag(self, name):
        try:
            self.conn.execute("INSERT INTO tags(name) VALUES(?)", (name,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def rename_tag(self, tag_id, new_name):
        try:
            self.conn.execute("UPDATE tags SET name=? WHERE id=?", (new_name, tag_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_tag(self, tag_id):
        self.conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
        self.conn.commit()

    def get_tags_for_transaction(self, transaction_id):
        return self.conn.execute("""
            SELECT t.id, t.name
            FROM tags t
            JOIN transaction_tags tt ON tt.tag_id = t.id
            WHERE tt.transaction_id = ?
            ORDER BY t.name
        """, (transaction_id,)).fetchall()

    def set_tags_for_transaction(self, transaction_id, tag_ids):
        with self.conn:
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