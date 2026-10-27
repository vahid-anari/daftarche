"""0.33.0: a rule for several accounts (table rule_accounts, layout 7)."""

import pytest

from conftest import keep
from daftarche.db import Database


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shop(db):
    for name in ("Visa", "Chequing", "Savings"):
        db.get_or_create_account(name)
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    subs = {}
    for s in ("Tools", "Garden", "Kitchen"):
        db.add_subcategory(s, home)
        subs[s] = db.get_subcategory_by_name(s, home)["id"]
    db.conn.commit()
    return {"home": home, **subs}


def sub_of(db, account, name="HDW 1"):
    r = db.lookup_mapping("Expense", account, name=name)
    return db.get_subcategory_by_id(r["subcategory_id"])["name"] if r else None


def rule(db, shop, accounts, sub="Tools", name="HDW"):
    return db.save_mapping("Expense", accounts, name=name, subcategory_id=shop[sub], category_id=shop["home"],
                           merchant="Hardware")


# ── the database ─────────────────────────────────────────────────────────────
def test_a_rule_for_two_accounts(db, shop):
    rule_id = rule(db, shop, ["Visa", "Chequing"])
    assert [sub_of(db, a) for a in ("Visa", "Chequing", "Savings")] == ["Tools", "Tools", None]
    assert db.lookup_mapping("Expense", "Visa", name="HDW")["account_ids"] == db.account_id_set(["Visa", "Chequing"])
    assert db.get_rules("Hardware")[0]["accounts"] == ["Chequing", "Visa"]  # A to Z
    assert db.get_rule_id("Expense", ["Chequing", "Visa"], "hdw") == rule_id  # the same accounts, any order
    assert db.get_rule_id("Expense", ["Visa"], "HDW") is None and db.get_rule_id("Expense", None, "HDW") is None


def test_fewer_accounts_win_then_all_accounts_last(db, shop):
    rule(db, shop, ["Visa"], "Garden")
    rule(db, shop, ["Visa", "Chequing"], "Tools")
    rule(db, shop, None, "Kitchen")  # the newest, but for all accounts
    assert [sub_of(db, a) for a in ("Visa", "Chequing", "Savings")] == ["Garden", "Tools", "Kitchen"]
    assert sub_of(db, "Visa", "HDW LONGER") == "Garden"


def test_saving_the_same_rule_again_changes_it(db, shop):
    first = rule(db, shop, ["Visa", "Chequing"], "Tools")
    assert rule(db, shop, ["Chequing", "Visa"], "Garden") == first
    other = rule(db, shop, ["Visa"], "Kitchen")  # other accounts: another rule
    assert other != first and len(db.get_rules("Hardware")) == 2


def test_counting_texts_for_several_accounts(db, shop):
    for account in ("Visa", "Chequing", "Savings"):
        db.add_transaction(2026, "May", 1, "Expense", account, 5, shop["Tools"], shop["home"], name="HDW " + account)
    assert sorted(n for n, _ in db.get_rule_texts("Expense", ["Visa", "Savings"])) == ["HDW Savings", "HDW Visa"]
    assert len(db.get_rule_texts("Expense", None)) == 3


def test_deleting_an_account(db, shop):
    only = rule(db, shop, ["Savings"], "Garden")
    both = rule(db, shop, ["Savings", "Visa"], "Tools")
    db.delete_account(db.get_account_by_name("Savings")["id"])
    ids = {r["id"]: r["accounts"] for r in db.get_rules("Hardware")}
    assert only not in ids and ids[both] == ["Visa"]  # not widened to all accounts


def test_merging_accounts_moves_their_rules(db, shop):
    moved = rule(db, shop, ["Savings"], "Garden", name="GARDEN")
    rule(db, shop, ["Savings"], "Tools")
    kept = rule(db, shop, ["Visa"], "Kitchen")  # the same as the moved one will be
    db.rename_account("Savings", "Visa")
    rules = {r["id"]: (r["accounts"], r["subcategory"]) for r in db.get_rules("Hardware")}
    assert rules[moved] == (["Visa"], "Garden") and rules[kept] == (["Visa"], "Kitchen") and len(rules) == 2


# ── the upgrade from layout 6 ────────────────────────────────────────────────
def test_an_older_database_moves_the_accounts_and_joins_same_rules(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    for name in ("Visa", "Chequing", "Savings"):
        db.get_or_create_account(name)
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    db.add_subcategory("Tools", home)
    tools = db.get_subcategory_by_name("Tools", home)["id"]
    ids = {n: db.get_account_by_name(n)["id"] for n in ("Visa", "Chequing", "Savings")}
    type_id = db.get_type_id("Expense")

    def old_rule(account, name, merchant="Hardware"):
        return db.conn.execute("INSERT INTO import_mappings(type_id, account_id, name, subcategory_id, category_id, "
                               "merchant) VALUES (?, ?, ?, ?, ?, ?)",
                               (type_id, ids.get(account), name, tools, home, merchant)).lastrowid
    old_rule("Visa", "HDW")
    newest = old_rule("Chequing", "hdw")  # the same rule but for its account: joined
    old_rule(None, "HDW")  # for all accounts: stays its own
    other = old_rule("Savings", "HDW", merchant="Other")  # another merchant: stays its own
    db.conn.execute("PRAGMA user_version = 6")
    db.conn.commit()
    db.conn.close()

    db = Database(path)
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 7
    before = tmp_path / "old-before-layout-7.db"  # the file as it was, for an older Daftarche
    import sqlite3
    with sqlite3.connect(before) as old:
        assert old.execute("PRAGMA user_version").fetchone()[0] == 6
        assert old.execute("SELECT COUNT(*) FROM import_mappings WHERE account_id IS NOT NULL").fetchone()[0] == 3
    assert db.conn.execute("SELECT COUNT(*) FROM import_mappings WHERE account_id IS NOT NULL").fetchone()[0] == 0
    rules = {r["id"]: r["accounts"] for r in db.get_rules("Hardware")}
    assert rules == {newest: ["Chequing", "Visa"], newest + 1: []}
    assert db.get_rules("Other")[0]["id"] == other and db.get_rules("Other")[0]["accounts"] == ["Savings"]
    assert sub_of(db, "Visa") == "Tools" and sub_of(db, "Savings") == "Tools"
    db.conn.close()
    assert Database(path).get_rules("Hardware")[0]["accounts"] in (["Chequing", "Visa"], [])  # opens again


# ── the windows ──────────────────────────────────────────────────────────────
def test_the_accounts_box(qapp):
    from daftarche.widgets import AccountsCombo, accounts_label
    box = keep(AccountsCombo(["Visa", "Chequing", "Savings"], ["Old card"]))
    assert box.accounts() == ["Old card"] and box._items[-1] == "Old card"  # a closed account is offered
    box.set_accounts([])
    assert box.accounts() == [] and box.text().startswith("All")
    box.set_accounts(["Savings", "Visa"])
    assert box.accounts() == ["Visa", "Savings"] and box.text().startswith("2 accounts") and box.toolTip() == "Visa\nSavings"
    box.set_accounts(["Visa", "Chequing", "Savings", "Old card"])  # every one: those, not all accounts
    assert len(box.accounts()) == 4 and box.text().startswith("4 accounts")
    assert accounts_label([]) == "All" and accounts_label(["A"]) == "A"


def test_the_rule_window_saves_several_accounts(qapp, db, shop):
    from daftarche.tabs.manage import ManageDialog, RuleEditDialog, save_rule
    for account in ("Visa", "Chequing", "Savings"):
        db.add_transaction(2026, "May", 1, "Expense", account, 5, *db.get_uncategorized_ids()[::-1],
                           name="HDW " + account)
    d = keep(RuleEditDialog(db, merchant="Hardware"))
    d.f_cat.setCurrentText("Home")
    d.f_sub.setCurrentText("Tools")
    d.f_name.setText("HDW")
    assert d.matches.text().startswith("Matches 3 ")
    d.f_account.set_accounts(["Visa", "Savings"])
    assert d.matches.text().startswith("Matches 2 ") and d.rb_all.text().startswith("All 2,")
    save_rule(db, d.values(), apply=d.to_apply())
    assert db.get_rules("Hardware")[0]["accounts"] == ["Savings", "Visa"]
    assert [sub_of(db, a) for a in ("Visa", "Chequing", "Savings")] == ["Tools", None, "Tools"]
    m = keep(ManageDialog(db, lambda: None)).merchants_panel
    m.select("Hardware")
    item = m.rules.item(0, m.R_ACCOUNT)
    assert item.text() == "2 accounts" and item.toolTip() == "Savings\nVisa"
    edit = keep(RuleEditDialog(db, existing=db.get_rules("Hardware")[0]))
    assert edit.f_account.accounts() == ["Savings", "Visa"]  # as the list orders them


def test_the_edit_window_rule_rows_keep_several_accounts(qapp, db, shop):
    from unittest import mock
    from daftarche.category_dialog import CategoryDialog
    rule(db, shop, ["Visa", "Chequing"], "Tools")
    d = keep(CategoryDialog(db, "Expense", preset_cat="Home", preset_sub="Tools"))
    entry, account, *_ = d._rule_rows[0]
    assert entry["values"][0] == ("Chequing", "Visa") and account.accounts() == ["Chequing", "Visa"]
    d.new_name.setText("PAINT")
    d.new_rule_merchant.setText("Paint Shop")
    d.new_account.set_accounts(["Savings", "Visa"])
    d._add_rule()
    with mock.patch("daftarche.category_dialog.QMessageBox"):
        d._accept()
    accounts = {r["name"]: r["accounts"] for r in db.get_rules_for_subcategory(shop["Tools"])}
    assert accounts == {"HDW": ["Chequing", "Visa"], "PAINT": ["Savings", "Visa"]}


def test_the_apps_own_database_is_copied_into_backups(tmp_path, monkeypatch):
    import daftarche.paths
    monkeypatch.setattr(daftarche.paths, "BACKUP_DIR", tmp_path / "backups")
    path = tmp_path / "daftarche.db"
    db = Database(path)
    db.conn.execute("PRAGMA user_version = 6")
    db.conn.commit()
    db.conn.close()
    Database(path).conn.close()
    assert (tmp_path / "backups" / "daftarche-before-layout-7.db").exists()
    assert not (tmp_path / "daftarche-before-layout-7.db").exists()


# ── found in review ──────────────────────────────────────────────────────────
def old_file(tmp_path, rules):
    """A layout-6 file with these rules: (account or None, name, memo, merchant, sub-category)."""
    path = tmp_path / "old.db"
    db = Database(path)
    for name in ("Visa", "Chequing", "Gone"):
        db.get_or_create_account(name)
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")["id"]
    subs = {}
    for s in ("Resto", "Groceries"):
        db.add_subcategory(s, food)
        subs[s] = db.get_subcategory_by_name(s, food)["id"]
    ids = {n: db.get_account_by_name(n)["id"] for n in ("Visa", "Chequing", "Gone")}
    type_id = db.get_type_id("Expense")
    for account, name, memo, merchant, sub in rules:
        db.conn.execute("INSERT INTO import_mappings(type_id, account_id, name, memorandum, subcategory_id, "
                        "category_id, merchant) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (type_id, ids.get(account), name, memo, subs[sub], food, merchant))
    db.conn.commit()
    db.conn.execute("PRAGMA foreign_keys = OFF")
    db.conn.execute("DELETE FROM accounts WHERE name = 'Gone'")  # as an old version could leave it
    db.conn.execute("PRAGMA user_version = 6")
    db.conn.commit()
    db.conn.close()
    return Database(path)


def lookup(db, account, name, memo=None):
    r = db.lookup_mapping("Expense", account, name=name, memorandum=memo)
    return db.get_subcategory_by_id(r["subcategory_id"])["name"] if r else None


def test_a_rule_of_an_account_that_is_gone_is_not_made_one_for_all(tmp_path):
    db = old_file(tmp_path, [("Gone", "INDIGO", None, "Indigo", "Resto")])
    assert lookup(db, "Visa", "INDIGO") is None and db.get_rules("Indigo") == []


def test_no_join_where_it_could_change_a_tie(tmp_path):
    db = old_file(tmp_path, [("Chequing", "SHOP", None, "Shop", "Resto"),
                             ("Chequing", None, "MALL", "Mall", "Groceries"),
                             ("Visa", None, "MALL", "Mall", "Groceries")])
    assert lookup(db, "Chequing", "SHOP", "MALL") == "Groceries"  # the newer one, as before
    assert sorted(r["accounts"] for r in db.get_rules("Mall")) == [["Chequing"], ["Visa"]]


def test_no_join_of_merchants_written_differently(tmp_path):
    db = old_file(tmp_path, [("Chequing", "UBER", None, "Uber", "Resto"),
                             ("Visa", "UBER", None, "uber", "Resto")])
    assert lookup(db, "Chequing", "UBER") == "Resto"
    assert [r["accounts"] for r in db.get_rules("Uber")] == [["Chequing"]]


def test_merging_accounts_the_rule_already_there_wins(db, shop):
    alone = rule(db, shop, ["Visa"], "Garden")
    both = rule(db, shop, ["Visa", "Chequing"], "Tools")
    db.rename_account("Visa", "Chequing")
    rules = {r["id"]: r["accounts"] for r in db.get_rules("Hardware")}
    assert rules == {both: ["Chequing"]} and alone not in rules
