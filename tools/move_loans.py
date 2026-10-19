"""Move loan categories to Transfer › Loans (0.21), with the person as merchant. Close Daftarche first.

    python tools/move_loans.py                      # only shows what would change
    python tools/move_loans.py --apply              # backs up the database, then writes

By default the income and expense categories named "Debt" and "Personal Loan" are moved; give
others with --category "Expense:Debt" (repeat it). Each row keeps its account, date and amount,
so account balances do not change; income and expense totals drop by the loans. Its person is
its sub-category's name (Debt › Emad → Emad), or else its merchant; a merchant that differs
from the sub-category is listed. Money that came in (an income, or a negative expense) stays
money in. Nothing in your database is touched without --apply (not even its layout): the
preview runs on a copy.

Loans older than your records get a starting balance, and small leftovers can be marked settled:

    --i-owed "Kevin=939.22"      # before my records, I owed Kevin $939.22
    --they-owed "Ali=50"         # before my records, Ali owed me $50
    --settle Fereshteh           # what is left with Fereshteh is written off (no transaction)

Categories left empty are deleted at the end. A category that rules still use is kept (and
named), so new imports are not changed behind your back.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DEFAULT_CATEGORIES = ("Expense:Debt", "Income:Personal Loan")


def find_categories(db, specs):
    """[(spec, category row or None)]."""
    out = []
    for spec in specs:
        type_name, _, cat_name = spec.partition(":")
        type_id = db.get_type_id(type_name.strip())
        cat = db.get_category_by_name(cat_name.strip(), type_id=type_id) if type_id else None
        out.append((spec, cat))
    return out


def plan(db, cats):
    """(rows [(tx id, person, direction, amount, from)], problems)."""
    from daftarche.db import UNCATEGORIZED_SUB
    rows, problems = [], []
    known = {m.casefold(): m for m in db.get_merchants()}
    for spec, cat in cats:
        if cat is None:
            continue
        for r in db.conn.execute("""
                SELECT t.id, t.date, t.amount, t.merchant, t.account_id, ty.name AS type, s.name AS sub,
                       (SELECT COUNT(*) FROM transaction_splits sp WHERE sp.transaction_id = t.id) AS parts
                FROM transactions t JOIN types ty ON ty.id = t.type_id
                     LEFT JOIN subcategories s ON s.id = t.subcategory_id
                WHERE t.category_id = ? ORDER BY t.date""", (cat["id"],)):
            sub_name = r["sub"] if r["sub"] not in (None, UNCATEGORIZED_SUB) else ""
            merchant = (r["merchant"] or "").strip()
            person = " ".join((sub_name or merchant).split())
            person = known.get(person.casefold(), person)  # "kevin" is the Kevin already there
            if sub_name and merchant and merchant.casefold() != sub_name.casefold():
                problems.append(f"{r['date']} {r['amount']:.2f} ({spec}): merchant '{merchant}' becomes "
                                f"'{person}' (its sub-category)")
            if r["parts"]:
                problems.append(f"{r['date']} {r['amount']:.2f} ({spec}): split, left as it is")
            elif not person:
                problems.append(f"{r['date']} {r['amount']:.2f} ({spec}): no merchant or sub-category, left as it is")
            elif not r["account_id"]:
                problems.append(f"{r['date']} {r['amount']:.2f} ({spec}): no account, left as it is")
            else:
                money_in = ("Income" in r["type"]) == (r["amount"] >= 0)
                rows.append((r["id"], person, "in" if money_in else "out", abs(r["amount"]), spec))
        # the split ones' parts in these categories are not moved either
        n = db.conn.execute("SELECT COUNT(*) FROM transaction_splits WHERE category_id=?", (cat["id"],)).fetchone()[0]
        if n:
            problems.append(f"{spec}: {n} part(s) of split transactions use it, left as they are")
    return rows, problems


def parse_amounts(values, sign):
    out = {}
    for v in values or ():
        name, _, amount = v.partition("=")
        if not name.strip() or not amount.strip():
            raise SystemExit(f'Write it as "Name=amount": {v!r}')
        out[name.strip()] = sign * abs(float(amount.replace("$", "").replace(",", "")))
    return out


def summary(db):
    from daftarche.loans_dialog import balance_text
    lines = [f"  {'Person':<20}{'Paid out':>12}{'Received':>12}{'Starting':>12}  Balance"]
    for e in db.get_loans():
        lines.append(f"  {e['merchant'] or '(no person)':<20}{e['paid_out']:>12,.2f}{e['received']:>12,.2f}"
                     f"{e['opening']:>12,.2f}  {balance_text(e['balance'])}")
    you_owe, owed = db.get_loan_totals()
    lines.append(f"\n  You owe ${you_owe:,.2f} · Owed to you ${owed:,.2f}")
    return "\n".join(lines)


def apply(db, cats, rows, openings, settle):
    """All in one database transaction. Returns the names of the categories deleted, and kept."""
    deleted, kept = [], []
    with db.transaction():
        by_person = {}
        for tx_id, person, *_ in rows:
            by_person.setdefault(person, []).append(tx_id)
        for person, ids in by_person.items():
            db.make_loan(ids, person)
        for person, value in openings.items():
            db.set_loan_opening(person, value)
        for person in settle:
            db.settle_loan(person)
        for spec, cat in cats:
            if cat is None:
                continue
            used = db.conn.execute(
                """SELECT (SELECT COUNT(*) FROM transactions WHERE category_id=:c)
                        + (SELECT COUNT(*) FROM transaction_splits WHERE category_id=:c)
                        + (SELECT COUNT(*) FROM import_mappings WHERE category_id=:c)""", {"c": cat["id"]}).fetchone()[0]
            if used:
                kept.append(spec)
            else:
                db.conn.execute("DELETE FROM subcategories WHERE category_id=?", (cat["id"],))
                db.conn.execute("DELETE FROM categories WHERE id=?", (cat["id"],))
                deleted.append(spec)
    return deleted, kept


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", help="a database file (default: your data folder)")
    parser.add_argument("--category", action="append", help='"Type:Category" to move (default: Debt and Personal Loan)')
    parser.add_argument("--i-owed", action="append", metavar="NAME=AMOUNT", help="a starting balance: you owed them")
    parser.add_argument("--they-owed", action="append", metavar="NAME=AMOUNT", help="a starting balance: they owed you")
    parser.add_argument("--settle", action="append", default=[], metavar="NAME", help="write off what is left")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: only show them)")
    args = parser.parse_args(argv)
    openings = {**parse_amounts(args.i_owed, -1), **parse_amounts(args.they_owed, 1)}
    specs = args.category or DEFAULT_CATEGORIES

    import sqlite3
    import tempfile
    from daftarche.backup import copy_db
    from daftarche.db import Database
    from daftarche.paths import BACKUP_DIR, DB_PATH
    path = Path(args.database).expanduser() if args.database else DB_PATH
    if not path.exists():
        print(f"No database at {path}")
        return 1

    # the preview: the same steps on a copy (opening the real file would upgrade its layout)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "preview.db"
        raw = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            copy_db(raw, copy)
        finally:
            raw.close()
        preview = Database(copy)
        try:
            cats = find_categories(preview, specs)
            for spec, cat in cats:
                if cat is None:
                    print(f"not found: {spec}")
            rows, problems = plan(preview, cats)
            for person in sorted({r[1] for r in rows}, key=str.casefold):
                mine = [r for r in rows if r[1] == person]
                out = sum(r[3] for r in mine if r[2] == "out")
                got = sum(r[3] for r in mine if r[2] == "in")
                print(f"{person}: {len(mine)} transaction(s), paid out ${out:,.2f}, received ${got:,.2f}")
            for problem in problems:
                print(f"note: {problem}")
            print(f"\n{len(rows)} transactions to move to Transfer › Loans.")
            people = {r[1].casefold() for r in rows} | {e["merchant"].casefold() for e in preview.get_loans()}
            unknown = [n for n in list(openings) + list(args.settle) if n.casefold() not in people]
            if unknown:
                print("No loan for: " + ", ".join(unknown) + " (check the spelling). Nothing written.")
                return 1
            apply(preview, cats, rows, openings, args.settle)
            print("\nThe loans afterwards:\n" + summary(preview))
        finally:
            preview.conn.close()

    if not args.apply:
        if rows or openings or args.settle:
            print("\nNothing written yet: run again with --apply.")
        return 0
    backup = BACKUP_DIR / f"daftarche-before-loans-{datetime.now():%Y%m%d-%H%M%S}.db"
    raw = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        copy_db(raw, backup)  # the file exactly as it was, before anything (even the layout) changes
    finally:
        raw.close()
    db = Database(path)
    try:
        cats = find_categories(db, specs)
        rows, _ = plan(db, cats)
        deleted, kept = apply(db, cats, rows, openings, args.settle)
        if deleted:
            print("Deleted, now empty: " + ", ".join(deleted))
        if kept:
            print("Kept (still used, e.g. by rules): " + ", ".join(kept))
        print(f"Written. The database before this is saved as {backup}")
        return 0
    finally:
        db.conn.close()


if __name__ == "__main__":
    sys.exit(main())
