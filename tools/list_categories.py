"""Print every type, category and sub-category, with how many transactions and rules each has.

Read-only: the database is opened without changing anything. Run from the repository root:

    python tools/list_categories.py                     # your data folder, to the screen
    python tools/list_categories.py -o ~/Desktop/categories.txt
    python tools/list_categories.py --totals            # also the total amount of each

Only names and counts are written (and totals with --totals): no transactions, accounts or notes.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def category_tree(conn, totals=False):
    """Lines of text: one per type, category (indented) and sub-category (indented more)."""
    rows = conn.execute("""
        SELECT COALESCE(ty.name, '(no type)') AS type, c.id AS cid, c.name AS cat, s.id AS sid, s.name AS sub
        FROM categories c
             LEFT JOIN types ty ON ty.id = c.type_id
             LEFT JOIN subcategories s ON s.category_id = c.id
        ORDER BY ty.name IS NULL, ty.name, c.name, s.name""").fetchall()
    tx = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(
        "SELECT category_id, subcategory_id, COUNT(*), ROUND(SUM(amount), 2) FROM transactions "
        "GROUP BY category_id, subcategory_id")}
    rules = {r[0]: r[1] for r in conn.execute(
        "SELECT subcategory_id, COUNT(*) FROM import_mappings GROUP BY subcategory_id")}

    def counts(n, total, n_rules):
        parts = [f"{n} tx"]
        if totals:
            total = total or 0
            parts.append(f"-${-total:,.2f}" if total < 0 else f"${total:,.2f}")
        if n_rules:
            parts.append(f"{n_rules} rule{'s' if n_rules != 1 else ''}")
        return "  (" + ", ".join(parts) + ")"

    lines, last_type, last_cat = [], None, None
    for r in rows:
        if r["type"] != last_type:
            lines.append(("" if not lines else "\n") + r["type"].upper())
            last_type, last_cat = r["type"], None
        if r["cid"] != last_cat:
            mine = [v for (c, _s), v in tx.items() if c == r["cid"]]
            lines.append(f"  {r['cat']}" + counts(sum(v[0] for v in mine), sum(v[1] or 0 for v in mine), 0))
            last_cat = r["cid"]
        if r["sid"] is not None:
            n, total = tx.get((r["cid"], r["sid"]), (0, 0))
            lines.append(f"      {r['sub']}" + counts(n, total, rules.get(r["sid"], 0)))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", nargs="?", help="a database file (default: your data folder)")
    parser.add_argument("-o", "--output", help="write to this file instead of the screen")
    parser.add_argument("--totals", action="store_true", help="also show the total amount of each")
    args = parser.parse_args(argv)
    if args.database:
        path = Path(args.database)
    else:
        from daftarche.paths import DB_PATH
        path = DB_PATH
    conn = sqlite3.connect(f"{path.expanduser().resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    text = "\n".join(category_tree(conn, totals=args.totals)) + "\n"
    conn.close()
    if args.output:
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        print(f"Written to {args.output}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
