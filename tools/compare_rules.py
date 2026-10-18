"""Which past transactions would the new rule matching (0.6.0) categorize differently?

Read-only: opens your database without changing anything. Run from the repository root:

    python tools/compare_rules.py                       # your data folder
    python tools/compare_rules.py path/to/daftarche.db  # another copy

For every transaction with a name or memo it asks both the old matching (terms found
anywhere, first-saved rule wins ties) and the new one (whole words, most specific rule
wins) which rule applies, and lists the transactions where the answer differs.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daftarche.db import rule_match_length  # noqa: E402


def old_length(value, pattern):
    """0.5.0 and earlier: substring matching, score = number of terms."""
    if not pattern:
        return 0
    value = (value or "").lower()
    terms = [p.strip().lower() for p in pattern.split("|")]
    return len(terms) if all(t in value for t in terms) else None


def pick(rules, account_id, name, memo, length, newest_wins):
    best, best_key = None, None
    for r in rules:
        if r["account_id"] not in (None, account_id):
            continue
        n, m = length(name, r["name"]), length(memo, r["memorandum"])
        if n is None or m is None:
            continue
        key = (n + m + (0 if newest_wins else (1 if r["account_id"] else 0)),
               r["account_id"] is not None if newest_wins else 0,
               r["id"] if newest_wins else -r["id"])
        if best_key is None or key > best_key:
            best, best_key = r, key
    return best


def label(rule, subs):
    if rule is None:
        return "(no rule)"
    sub = subs.get(rule["subcategory_id"], "?")
    pattern = " / ".join(p for p in (rule["name"], rule["memorandum"]) if p)
    return f"{sub}  [rule: {pattern or 'any'}]"


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        from daftarche.paths import DB_PATH
        path = DB_PATH
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rules = conn.execute("SELECT * FROM import_mappings ORDER BY id").fetchall()
    subs = {r["id"]: f'{r["cat"]} › {r["name"]}' for r in conn.execute(
        "SELECT s.id, s.name, c.name AS cat FROM subcategories s JOIN categories c ON c.id = s.category_id")}
    by_type = {}
    for r in rules:
        by_type.setdefault(r["type_id"], []).append(r)
    txs = conn.execute("""SELECT t.id, t.date, t.amount, t.type_id, t.account_id, t.name, t.memorandum,
                                 s.name AS sub, c.name AS cat
                          FROM transactions t LEFT JOIN subcategories s ON s.id = t.subcategory_id
                                              LEFT JOIN categories c ON c.id = t.category_id
                          WHERE t.name IS NOT NULL OR t.memorandum IS NOT NULL
                          ORDER BY t.date""").fetchall()
    changed = 0
    for t in txs:
        candidates = by_type.get(t["type_id"], [])
        old = pick(candidates, t["account_id"], t["name"], t["memorandum"], old_length, newest_wins=False)
        new = pick(candidates, t["account_id"], t["name"], t["memorandum"], rule_match_length, newest_wins=True)
        if (old and old["id"]) != (new and new["id"]) and \
                (old and old["subcategory_id"]) != (new and new["subcategory_id"]):
            changed += 1
            print(f'{t["date"]}  {t["amount"]:>10.2f}  {t["name"] or ""}  {t["memorandum"] or ""}')
            print(f'    now stored: {t["cat"]} › {t["sub"]}')
            print(f'    old rule:   {label(old, subs)}')
            print(f'    new rule:   {label(new, subs)}')
    print(f"\n{len(txs)} transactions, {len(rules)} rules: {changed} would be categorized differently.")
    conn.close()


if __name__ == "__main__":
    main()
