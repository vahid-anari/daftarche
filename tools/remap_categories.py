"""Move your categories to the 0.17 way: a merchant field, and categories by kind of spending.

Two steps, with a CSV file in between that you check (and change) yourself. Close Daftarche first.

    python tools/remap_categories.py export -o mapping.csv     # one line per sub-category
    (edit mapping.csv in Excel or Numbers)
    python tools/remap_categories.py apply mapping.csv          # only shows what would change
    python tools/remap_categories.py apply mapping.csv --apply  # backs up the database, then writes

The CSV has one line per income and expense sub-category you have now (``type``, ``category``,
``subcategory``, with how many transactions and rules use it), and what it becomes:

- ``merchant``: the shop or person its transactions and rules get (Amazon). Empty: none.
- ``new_type``: Income or Expense. A sub-category moved to the other type is money back:
  its amounts become negative there (Income › Refund › Amazon → a negative Expense).
- ``new_category``, ``new_subcategory``: where its transactions go (made when missing).
  An empty sub-category: the category alone. An empty category: Uncategorized (To review).
- ``rules``: ``category`` (the rules set the merchant and the new category) or ``merchant``
  (they only set the merchant: new transactions wait in To review, e.g. Amazon or a friend).

The export fills in the usual move: the sub-category name becomes the merchant and the
transactions go to the category alone. A line whose new_* columns are its own names, with no
merchant, changes nothing. Each line moves only the transactions and rules it had before the
run (a line moving into another line's sub-category does not move them again). Sub-categories
and categories emptied by the move are deleted at the end. Nothing changes without --apply, and before writing
a copy of the database is saved in the backups folder.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

FIELDS = ["type", "category", "subcategory", "transactions", "total", "rules",
          "merchant", "new_type", "new_category", "new_subcategory", "rules_set"]
RULES_CATEGORY, RULES_MERCHANT = "category", "merchant"
TYPES = ("Income", "Expense")


# ── export ────────────────────────────────────────────────────────────────────

def current_rows(db):
    """Every income and expense sub-category now, with its counts: the lines of the CSV."""
    from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB
    rows = db.conn.execute("""
        SELECT ty.name AS type, c.name AS category, s.name AS subcategory, s.id AS sid,
               (SELECT COUNT(*) FROM transactions t WHERE t.subcategory_id = s.id) AS n,
               (SELECT ROUND(COALESCE(SUM(t.amount), 0), 2) FROM transactions t WHERE t.subcategory_id = s.id) AS total,
               (SELECT COUNT(*) FROM import_mappings m WHERE m.subcategory_id = s.id) AS rules
        FROM subcategories s JOIN categories c ON c.id = s.category_id JOIN types ty ON ty.id = c.type_id
        WHERE ty.name IN ('Income', 'Expense')
        ORDER BY ty.name DESC, c.name, s.name""").fetchall()
    out = []
    for r in rows:
        if r["subcategory"] == UNCATEGORIZED_SUB and not r["n"] and not r["rules"]:
            continue
        plain = r["subcategory"] in (UNCATEGORIZED_SUB,) or r["category"] == UNCATEGORIZED_CAT
        out.append({
            "type": r["type"], "category": r["category"], "subcategory": r["subcategory"],
            "transactions": r["n"], "total": f"{r['total']:.2f}", "rules": r["rules"],
            "merchant": "" if plain else r["subcategory"],  # until now the sub-category was the shop
            "new_type": r["type"], "new_category": r["category"], "new_subcategory": "",
            "rules_set": RULES_CATEGORY,
        })
    return out


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # -sig: Excel reads it as UTF-8
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ── apply ─────────────────────────────────────────────────────────────────────

def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(f)]


def plan(db, rows):
    """The moves to make, and the problems found: ([move], [str]).

    A move: {old: (type, category, sub-category), sid, merchant, new: (type, category,
    sub-category or ""), rules_set, flip, n, rules}."""
    from daftarche.db import UNCATEGORIZED_CAT
    moves, problems = [], []
    for line, row in enumerate(rows, start=2):
        old = (row.get("type", ""), row.get("category", ""), row.get("subcategory", ""))
        if not all(old):
            problems.append(f"line {line}: type, category and subcategory are needed")
            continue
        found = db.conn.execute("""
            SELECT s.id FROM subcategories s JOIN categories c ON c.id = s.category_id
                 JOIN types ty ON ty.id = c.type_id
            WHERE ty.name = ? AND c.name = ? AND s.name = ?""", old).fetchone()
        if not found:
            problems.append(f"line {line}: there is no {old[0]} sub-category {old[1]} › {old[2]}")
            continue
        new_type = row.get("new_type") or old[0]
        new_type = next((t for t in TYPES if t.casefold() == new_type.casefold()), None)
        if not new_type:
            problems.append(f"line {line}: new_type must be Income or Expense")
            continue
        rules_set = (row.get("rules_set") or RULES_CATEGORY).casefold()
        if rules_set not in (RULES_CATEGORY, RULES_MERCHANT):
            problems.append(f"line {line}: rules_set must be '{RULES_CATEGORY}' or '{RULES_MERCHANT}'")
            continue
        merchant = row.get("merchant", "")
        new_cat = row.get("new_category") or UNCATEGORIZED_CAT
        if (rules_set == RULES_MERCHANT or new_cat == UNCATEGORIZED_CAT) and not merchant and \
                db.conn.execute("SELECT 1 FROM import_mappings WHERE subcategory_id = ?", (found["id"],)).fetchone():
            problems.append(f"line {line}: its rules would only set the merchant: write a merchant")
            continue
        new_sub = "" if new_cat == UNCATEGORIZED_CAT else row.get("new_subcategory", "")
        new = (new_type, new_cat, new_sub)
        if new == old and not merchant and rules_set == RULES_CATEGORY:
            continue  # left as it is
        counts = db.conn.execute(
            "SELECT (SELECT COUNT(*) FROM transactions WHERE subcategory_id = :s),"
            "       (SELECT COUNT(*) FROM import_mappings WHERE subcategory_id = :s)", {"s": found["id"]}).fetchone()
        if new_type != old[0] and db.conn.execute(
                """SELECT 1 FROM transaction_splits sp WHERE sp.subcategory_id = :s
                   OR sp.transaction_id IN (SELECT id FROM transactions WHERE subcategory_id = :s)""",
                {"s": found["id"]}).fetchone():
            problems.append(f"line {line}: split transactions use it: join them (or move it within its type)")
            continue
        moves.append({"old": old, "sid": found["id"], "merchant": merchant or None, "new": new,
                      "rules_set": rules_set, "flip": new_type != old[0], "n": counts[0], "rules": counts[1]})
    return moves, problems


def describe(move):
    old, new = move["old"], move["new"]
    where = f"{new[0]} › {new[1]}" + (f" › {new[2]}" if new[2] else "")
    parts = [f"{old[0]} › {old[1]} › {old[2]}  ({move['n']} tx, {move['rules']} rules)  →  {where}"]
    if move["merchant"]:
        parts.append(f"merchant {move['merchant']}")
    if move["flip"]:
        parts.append("amounts made negative (money back)")
    if move["rules"] and move["rules_set"] == RULES_MERCHANT:
        parts.append("rules set only the merchant")
    return ";  ".join(parts)


def _target(db, new):
    """(category id, sub-category id) of ``new``, made when missing."""
    from daftarche.db import UNCATEGORIZED_CAT
    new_type, cat_name, sub_name = new
    if cat_name == UNCATEGORIZED_CAT:
        return db.get_uncategorized_ids()
    cat = db.get_category_by_name(cat_name, type_id=db.get_type_id(new_type))
    if not cat:
        db.add_category(cat_name, new_type)
        cat = db.get_category_by_name(cat_name, type_id=db.get_type_id(new_type))
    if not sub_name:
        return cat["id"], db.uncategorized_subcategory(cat["id"])["id"]
    sub = db.get_subcategory_by_name(sub_name, cat["id"])
    if not sub:
        db.add_subcategory(sub_name, cat["id"])
        sub = db.get_subcategory_by_name(sub_name, cat["id"])
    return cat["id"], sub["id"]


def apply(db, moves):
    """Make the moves, all of them or (on any error) none; returns what was deleted after."""
    from daftarche.db import UNCATEGORIZED_CAT, UNCATEGORIZED_SUB
    c = db.conn
    emptied = []
    with db.transaction():
        targets = {move["new"]: _target(db, move["new"]) for move in moves}
        # what each line moves, taken before anything moves: a line that moves into another
        # line's sub-category must not have its rows picked up (and flipped) again
        tx_ids = {id(m): [r[0] for r in c.execute("SELECT id FROM transactions WHERE subcategory_id = ?",
                                                   (m["sid"],))] for m in moves}
        rules_of = {id(m): c.execute("SELECT * FROM import_mappings WHERE subcategory_id = ?", (m["sid"],)).fetchall()
                    for m in moves}
        parts_of = {id(m): [r[0] for r in c.execute("SELECT id FROM transaction_splits WHERE subcategory_id = ?",
                                                     (m["sid"],))] for m in moves}
        for move in moves:
            cat_id, sub_id = targets[move["new"]]
            type_id = db.get_type_id(move["new"][0])
            sign = -1 if move["flip"] else 1
            c.executemany("""UPDATE transactions SET category_id = ?, subcategory_id = ?, type_id = ?,
                                    amount = amount * ?, merchant = COALESCE(merchant, ?) WHERE id = ?""",
                          [(cat_id, sub_id, type_id, sign, move["merchant"], tx_id) for tx_id in tx_ids[id(move)]])
            c.executemany("UPDATE transaction_splits SET category_id = ?, subcategory_id = ? WHERE id = ?",
                          [(cat_id, sub_id, pid) for pid in parts_of[id(move)]])  # parts go along (same type)
            if move["rules_set"] == RULES_MERCHANT:
                cat_id, sub_id = db.get_uncategorized_ids()
            for rule in rules_of[id(move)]:
                if not c.execute("SELECT 1 FROM import_mappings WHERE id = ?", (rule["id"],)).fetchone():
                    continue  # already merged into its twin
                twin = c.execute("""SELECT id, merchant FROM import_mappings WHERE id <> ? AND type_id = ?
                                    AND account_id IS ? AND name IS ? AND memorandum IS ?""",
                                 (rule["id"], type_id, rule["account_id"], rule["name"], rule["memorandum"])).fetchone()
                if twin:  # the other type already has this rule (Amazon): it stays, with the merchant
                    c.execute("UPDATE import_mappings SET merchant = COALESCE(merchant, ?) WHERE id = ?",
                              (move["merchant"], twin["id"]))
                    c.execute("DELETE FROM import_mappings WHERE id = ?", (rule["id"],))
                else:
                    c.execute("""UPDATE import_mappings SET type_id = ?, category_id = ?, subcategory_id = ?,
                                        merchant = COALESCE(?, merchant) WHERE id = ?""",
                              (type_id, cat_id, sub_id, move["merchant"], rule["id"]))
        # what the move left empty: the old sub-categories, then categories with nothing left
        for move in moves:
            sid = move["sid"]
            used = c.execute("SELECT (SELECT COUNT(*) FROM transactions WHERE subcategory_id = :s) +"
                             " (SELECT COUNT(*) FROM transaction_splits WHERE subcategory_id = :s) +"
                             " (SELECT COUNT(*) FROM import_mappings WHERE subcategory_id = :s)", {"s": sid}).fetchone()[0]
            if not used:
                c.execute("DELETE FROM subcategories WHERE id = ?", (sid,))
                emptied.append(" › ".join(move["old"]))
        for cat in c.execute("SELECT c.id, c.name, ty.name AS type FROM categories c JOIN types ty ON ty.id = c.type_id "
                             "WHERE ty.name IN ('Income', 'Expense') AND c.name <> ?", (UNCATEGORIZED_CAT,)).fetchall():
            used = c.execute("""SELECT (SELECT COUNT(*) FROM transactions WHERE category_id = :c) +
                                       (SELECT COUNT(*) FROM transaction_splits WHERE category_id = :c) +
                                       (SELECT COUNT(*) FROM import_mappings WHERE category_id = :c) +
                                       (SELECT COUNT(*) FROM subcategories WHERE category_id = :c AND name <> :u)""",
                             {"c": cat["id"], "u": UNCATEGORIZED_SUB}).fetchone()[0]
            was_moved = any(m["old"][:2] == (cat["type"], cat["name"]) for m in moves)
            if not used and was_moved:
                c.execute("DELETE FROM categories WHERE id = ?", (cat["id"],))
                emptied.append(f"{cat['type']} › {cat['name']}")
    return emptied


# ── command line ──────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", help="a database file (default: your data folder)")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write the CSV of your sub-categories, to fill in")
    exp.add_argument("-o", "--output", default="mapping.csv", help="the CSV to write (default: mapping.csv)")
    app = sub.add_parser("apply", help="move the categories as the CSV says")
    app.add_argument("csv", help="the CSV file, filled in")
    app.add_argument("--apply", action="store_true", help="write the changes (default: only show them)")
    args = parser.parse_args(argv)

    from daftarche.backup import copy_db
    from daftarche.db import Database
    from daftarche.paths import BACKUP_DIR, DB_PATH
    db = Database(Path(args.database).expanduser() if args.database else DB_PATH)
    try:
        if args.command == "export":
            rows = current_rows(db)
            write_csv(rows, Path(args.output).expanduser())
            print(f"Written {len(rows)} lines to {args.output}")
            return 0
        moves, problems = plan(db, read_csv(Path(args.csv).expanduser()))
        for move in moves:
            print(describe(move))
        for problem in problems:
            print(f"skipped: {problem}")
        n_tx = sum(m["n"] for m in moves)
        print(f"\n{len(moves)} sub-categories to move ({n_tx} transactions), {len(problems)} skipped.")
        if args.apply and moves:
            backup = BACKUP_DIR / f"daftarche-before-remap-{datetime.now():%Y%m%d-%H%M%S}.db"
            copy_db(db.conn, backup)
            emptied = apply(db, moves)
            if emptied:
                print("Deleted, now empty: " + ", ".join(emptied))
            print(f"Written. The database before this is saved as {backup}")
        elif moves:
            print("Nothing written yet: run again with --apply.")
        return 0
    finally:
        db.conn.close()


if __name__ == "__main__":
    sys.exit(main())
