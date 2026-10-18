"""Write the online-shop purchases (Amazon, AliExpress) from your database to a CSV file.

Read-only: the database is opened without changing anything. Run from the repository root:

    python tools/export_shop_charges.py                      # → shop_charges.csv
    python tools/export_shop_charges.py -o ~/Desktop/shops.csv
    python tools/export_shop_charges.py --match "AMAZON|AMZN|ALIEXPRESS|TEMU"

Only transactions whose name or memo contains one of the --match words are written, and only
the columns needed to pair each one with its order on the shop's site: id (to write notes back
with tools/import_notes.py), date, account, type, amount, name, memo, category, sub-category
and the note. Nothing else from the database is in the file.
"""
import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DEFAULT_MATCH = "AMAZON|AMZN|ALIEXPRESS|ALIEXP|ALIPAY"
COLUMNS = ["id", "date", "account", "type", "amount", "name", "memo", "category", "subcategory", "note"]


def shop_rows(conn, words):
    """The matching transactions, oldest first, as dicts with COLUMNS."""
    has_note = "note" in [r[1] for r in conn.execute("PRAGMA table_info(transactions)")]
    where = " OR ".join("UPPER(COALESCE(t.name, '') || ' ' || COALESCE(t.memorandum, '')) LIKE ?" for _ in words)
    rows = conn.execute(f"""
        SELECT t.id, t.date, a.name AS account, ty.name AS type, t.amount, t.name, t.memorandum AS memo,
               c.name AS category, s.name AS subcategory, {"t.note" if has_note else "NULL"} AS note
        FROM transactions t
             LEFT JOIN accounts a ON a.id = t.account_id
             LEFT JOIN types ty ON ty.id = t.type_id
             LEFT JOIN categories c ON c.id = t.category_id
             LEFT JOIN subcategories s ON s.id = t.subcategory_id
        WHERE {where}
        ORDER BY t.date, t.id""", [f"%{w.upper()}%" for w in words]).fetchall()
    return [dict(zip(COLUMNS, r)) for r in rows]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", nargs="?", help="a database file (default: your data folder)")
    parser.add_argument("-o", "--output", default="shop_charges.csv", help="the CSV file to write")
    parser.add_argument("--match", default=DEFAULT_MATCH, help="words separated by | (default: %(default)s)")
    args = parser.parse_args(argv)
    if args.database:
        path = Path(args.database)
    else:
        from daftarche.paths import DB_PATH
        path = DB_PATH
    words = [w.strip() for w in args.match.split("|") if w.strip()]
    conn = sqlite3.connect(f"{path.expanduser().resolve().as_uri()}?mode=ro", uri=True)
    rows = shop_rows(conn, words)
    conn.close()
    out = Path(args.output).expanduser()
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} transactions matching {'|'.join(words)} → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
