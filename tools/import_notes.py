"""Write notes (and optionally categories) from a CSV file into your database.

The CSV has a header with ``id`` and ``note``, and may have ``category`` and ``subcategory``
(e.g. the file tools/export_shop_charges.py wrote, filled in). Close Daftarche first.

    python tools/import_notes.py notes.csv            # only shows what would change
    python tools/import_notes.py notes.csv --apply    # backs up the database, then writes

- A note is written only where the transaction has none yet (--overwrite replaces them).
- A category is changed only when both category and sub-category are given and already
  exist for that transaction's type; anything else is listed and skipped.
- Before writing, a copy of the database is saved in the backups folder.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def plan(db, rows, overwrite=False):
    """What would change: [(id, field, old, new)], and the problems found: [str]."""
    changes, problems = [], []
    for line, row in enumerate(rows, start=2):
        try:
            tx_id = int(row.get("id") or "")
        except ValueError:
            problems.append(f"line {line}: no id")
            continue
        tx = db.conn.execute(
            """SELECT t.note, ty.name AS type, c.name AS category, s.name AS subcategory
               FROM transactions t LEFT JOIN types ty ON ty.id = t.type_id
                    LEFT JOIN categories c ON c.id = t.category_id
                    LEFT JOIN subcategories s ON s.id = t.subcategory_id WHERE t.id = ?""", (tx_id,)).fetchone()
        if not tx:
            problems.append(f"line {line}: no transaction {tx_id}")
            continue
        note = (row.get("note") or "").strip()
        if note and note != (tx["note"] or "") and (overwrite or not tx["note"]):
            changes.append((tx_id, "note", tx["note"] or "", note))
        elif note and tx["note"] and note != tx["note"]:
            problems.append(f"line {line}: transaction {tx_id} already has a note (use --overwrite)")
        cat, sub = (row.get("category") or "").strip(), (row.get("subcategory") or "").strip()
        if not (cat or sub) or (cat, sub) == (tx["category"], tx["subcategory"]):
            continue
        found = db.get_category_by_name(cat, type_name=tx["type"]) if cat and sub else None
        if found and found["type_name"] not in (None, tx["type"]):
            found = None
        if not found or not db.get_subcategory_by_name(sub, found["id"]):
            problems.append(f"line {line}: '{cat} › {sub}' is not a {tx['type']} category and sub-category")
            continue
        changes.append((tx_id, "category", f"{tx['category']} › {tx['subcategory']}", f"{cat} › {sub}"))
    return changes, problems


def apply(db, changes, type_of):
    with db.transaction():
        for tx_id, field, _old, new in changes:
            if field == "note":
                db.update_transaction(tx_id, note=new)
            else:
                cat_name, sub_name = new.split(" › ", 1)
                cat = db.get_category_by_name(cat_name, type_name=type_of(tx_id))
                sub = db.get_subcategory_by_name(sub_name, cat["id"])
                db.update_transaction(tx_id, category_id=cat["id"], subcategory_id=sub["id"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", help="the CSV file with id, note (and category, subcategory)")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: only show them)")
    parser.add_argument("--overwrite", action="store_true", help="replace notes that are already there")
    parser.add_argument("--database", help="a database file (default: your data folder)")
    args = parser.parse_args(argv)

    from daftarche.backup import copy_db
    from daftarche.db import Database
    from daftarche.paths import BACKUP_DIR, DB_PATH
    with open(Path(args.csv).expanduser(), newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    db = Database(Path(args.database).expanduser() if args.database else DB_PATH)
    changes, problems = plan(db, rows, overwrite=args.overwrite)
    for tx_id, field, old, new in changes:
        print(f"{tx_id:>6}  {field:<8}  {old or '—'}  →  {new}")
    for problem in problems:
        print(f"skipped: {problem}")
    print(f"\n{len(changes)} change{'s' if len(changes) != 1 else ''}, {len(problems)} skipped.")
    if args.apply and changes:
        backup = BACKUP_DIR / f"daftarche-before-notes-{datetime.now():%Y%m%d-%H%M%S}.db"
        copy_db(db.conn, backup)

        def type_of(tx_id):
            return db.conn.execute("SELECT ty.name FROM transactions t JOIN types ty ON ty.id = t.type_id "
                                   "WHERE t.id = ?", (tx_id,)).fetchone()[0]
        apply(db, changes, type_of)
        print(f"Written. The database before this is saved as {backup}")
    elif changes:
        print("Nothing written yet: run again with --apply.")
    db.conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
