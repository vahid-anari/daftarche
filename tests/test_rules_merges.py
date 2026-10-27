"""Batch B (0.6.0): rule matching, one rule per key, merges that keep everything, type-aware look-ups."""

import subprocess
import sys
from pathlib import Path

import pytest

from daftarche.db import Database, rule_match_length


def cat(db, name, type_name="Expense"):
    db.add_category(name, type_name)
    return db.get_category_by_name(name, db.get_type_id(type_name))["id"]


def sub(db, name, cat_id):
    db.add_subcategory(name, cat_id)
    return db.get_subcategory_by_name(name, cat_id)["id"]


def tx(db, cat_id, sub_id, account="A", type_name="Expense", name="x"):
    return db.add_transaction(2026, "March", 1, type_name, account, 10, sub_id, cat_id, name=name)


def rule_sub(db, name, account=None, memo=None, type_name="Expense"):
    r = db.lookup_mapping(type_name, account, name=name, memorandum=memo)
    return db.get_subcategory_by_id(r["subcategory_id"])["name"] if r else None


def count(db, table, where="1"):
    return db.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]


# ── rule matching ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value, pattern, expected", [
    ("E-TRANSFER ALI MOHAMMAD", "Ali", 3),
    ("E-TRANSFER ALI MOHAMMAD", "ali mohammad", 12),
    ("E-TRANSFER  ALI   MOHAMMAD", "Ali Mohammad", 12),
    ("NATALIE SMITH", "Ali", None),
    ("ALIMENTATION COUCHE-TARD", "Ali", None),
    ("TIM HORTONS #123", "tim hortons|#123", 15),
    ("TIM HORTONS #123", "tim horton", None),
    ("anything", "", 0),
    (None, "Ali", None),
])
def test_rule_match_length(value, pattern, expected):
    assert rule_match_length(value, pattern) == expected


def test_most_specific_rule_wins(db):
    c = cat(db, "People")
    ali, ali_m = sub(db, "Ali", c), sub(db, "Ali Mohammad", c)
    db.save_mapping("Expense", None, name="Ali", subcategory_id=ali, category_id=c)
    db.save_mapping("Expense", None, name="Ali Mohammad", subcategory_id=ali_m, category_id=c)
    assert rule_sub(db, "E-TRANSFER ALI MOHAMMAD") == "Ali Mohammad"
    assert rule_sub(db, "E-TRANSFER ALI") == "Ali"
    assert rule_sub(db, "NATALIE SMITH") is None


def test_account_rule_beats_global_rule_of_equal_length(db):
    db.get_or_create_account("A")
    c = cat(db, "Food")
    one, two = sub(db, "Global", c), sub(db, "Mine", c)
    db.save_mapping("Expense", None, name="Shop", subcategory_id=one, category_id=c)
    db.save_mapping("Expense", "A", name="Shop", subcategory_id=two, category_id=c)
    assert rule_sub(db, "SHOP 12", account="A") == "Mine"
    assert rule_sub(db, "SHOP 12", account="B") == "Global"


def test_saving_a_rule_again_updates_it(db):
    c = cat(db, "Food")
    a, b = sub(db, "A", c), sub(db, "B", c)
    db.save_mapping("Expense", None, name="Shop", subcategory_id=a, category_id=c)
    db.save_mapping("Expense", None, name="Shop", memorandum="", subcategory_id=b, category_id=c)
    assert count(db, "import_mappings") == 1
    assert rule_sub(db, "SHOP") == "B"


def test_old_duplicate_rules_are_cleaned_keeping_the_newest(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    c = cat(db, "Food")
    a, b = sub(db, "A", c), sub(db, "B", c)
    type_id = db.get_type_id("Expense")
    for s in (a, b):  # what 0.5.0's save_mapping did with an empty memo
        db.conn.execute("INSERT INTO import_mappings(type_id, account_id, name, memorandum, subcategory_id, "
                        "category_id) VALUES (?, NULL, 'Shop', NULL, ?, ?)", (type_id, s, c))
    db.conn.commit()
    db.conn.close()
    db = Database(path)
    assert count(db, "import_mappings") == 1
    assert rule_sub(db, "SHOP") == "B"
    db.conn.close()


# ── merges ───────────────────────────────────────────────────────────────────

def test_account_merge_moves_bank_ids_and_rules(db):
    c = cat(db, "Food")
    s = sub(db, "Shop", c)
    tx(db, c, s, account="A")
    tx(db, c, s, account="B")
    db.save_account_id("123", "A")
    db.save_mapping("Expense", "A", name="Shop", subcategory_id=s, category_id=c)
    db.rename_account("A", "B")
    b = db.get_account_by_name("B")["id"]
    assert db.get_account_by_name("A") is None
    assert count(db, "transactions", f"account_id={b}") == 2
    assert db.get_account_by_acctid("123")["name"] == "B"
    assert rule_sub(db, "SHOP", account="B") == "Shop"


def test_category_merge_with_same_named_subcategories(db):
    old, new = cat(db, "Eating out"), cat(db, "Food")
    old_coffee, new_coffee = sub(db, "Coffee", old), sub(db, "Coffee", new)
    lunch = sub(db, "Lunch", old)
    t1, t2 = tx(db, old, old_coffee), tx(db, old, lunch)
    db.save_mapping("Expense", None, name="Tim", subcategory_id=old_coffee, category_id=old)
    db.rename_category(old, "Food")
    rows = {r["id"]: (r["category"], r["subcategory"]) for r in db.get_transactions()}
    assert rows == {t1: ("Food", "Coffee"), t2: ("Food", "Lunch")}
    assert db.get_subcategory_by_id(new_coffee)["cat_name"] == "Food"
    assert count(db, "subcategories", f"category_id={old}") == 0
    assert db.get_category_by_id(old) is None
    r = db.lookup_mapping("Expense", None, name="TIM")
    assert (r["category_id"], r["subcategory_id"]) == (new, new_coffee)


def test_subcategory_merge_keeps_its_rules(db):
    c = cat(db, "Food")
    a = sub(db, "Cafe", c)
    sub(db, "Coffee", c)
    db.save_mapping("Expense", None, name="Tim", subcategory_id=a, category_id=c)
    db.rename_subcategory(a, "Coffee")
    assert rule_sub(db, "TIM") == "Coffee"


def test_subcategory_moved_to_another_category_takes_its_transactions(db):
    c1, c2 = cat(db, "One"), cat(db, "Two")
    s = sub(db, "Thing", c1)
    t = tx(db, c1, s)
    db.rename_subcategory(s, "Thing", new_category_id=c2)
    assert {r["id"]: r["category"] for r in db.get_transactions()}[t] == "Two"


def test_delete_category_with_a_category_only_rule(db):
    c = cat(db, "Food")
    db.save_mapping("Expense", None, name="Shop", category_id=c)
    db.delete_category(c)
    assert db.get_category_by_id(c) is None and count(db, "import_mappings") == 0


# ── type-aware look-ups, type errors ─────────────────────────────────────────

def test_same_category_name_under_two_types(db):
    income, expense = cat(db, "Other", "Income"), cat(db, "Other", "Expense")
    assert db.get_category_by_name("Other", type_name="Expense")["id"] == expense
    assert db.get_category_by_name("Other", type_name="Income")["id"] == income
    db.rename_category(expense, "Misc")
    assert db.get_category_by_id(income)["name"] == "Other"
    assert db.get_category_by_id(expense)["name"] == "Misc"


def test_uncategorized_found_from_any_type(db):
    cat_id, _ = db.get_uncategorized_ids()
    assert db.get_category_by_name("Uncategorized", type_name="Expense")["id"] == cat_id


def test_type_errors_are_explained(db):
    with pytest.raises(ValueError, match="already exists"):
        db.rename_type("Income", "Expense")
    cat(db, "Food")
    with pytest.raises(ValueError, match="1 category"):
        db.delete_type("Expense")
    db.add_type("Unused")
    db.delete_type("Unused")
    assert db.get_type_by_name("Unused") is None


# ── the comparison tool ──────────────────────────────────────────────────────

def test_compare_rules_tool_lists_changes_read_only(tmp_path):
    path = tmp_path / "real.db"
    db = Database(path)
    c = cat(db, "People")
    ali, ali_m = sub(db, "Ali", c), sub(db, "Ali Mohammad", c)
    db.save_mapping("Expense", None, name="Ali", subcategory_id=ali, category_id=c)
    db.save_mapping("Expense", None, name="Ali Mohammad", subcategory_id=ali_m, category_id=c)
    tx(db, c, ali, name="E-TRANSFER ALI MOHAMMAD")
    tx(db, c, ali, name="E-TRANSFER ALI")
    db.conn.close()
    before = path.read_bytes()
    tool = Path(__file__).resolve().parents[1] / "tools" / "compare_rules.py"
    out = subprocess.run([sys.executable, str(tool), str(path)], capture_output=True, text=True, check=True).stdout
    assert "E-TRANSFER ALI MOHAMMAD" in out and "People › Ali Mohammad" in out
    assert "1 would be categorized differently" in out
    assert path.read_bytes() == before
