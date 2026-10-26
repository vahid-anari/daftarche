"""0.30.0: a rule added or edited in Manage → Merchants can also be set on the transactions there
are ("Also set this merchant and category on them")."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def hw(db):
    """Five EXAMPLE HDW expenses: no merchant, no category, both missing, all there, and split."""
    db.get_or_create_account("Card")
    db.get_or_create_account("Chequing")
    db.add_category("Home", "Expense")
    home = db.get_category_by_name("Home", type_name="Expense")["id"]
    db.add_subcategory("Tools", home)
    db.add_subcategory("Garden", home)
    tools = db.get_subcategory_by_name("Tools", home)["id"]
    garden = db.get_subcategory_by_name("Garden", home)["id"]
    uc, us = db.get_uncategorized_ids()
    ids = {
        "no_merchant": db.add_transaction(2026, "May", 1, "Expense", "Card", 10, garden, home, name="EXAMPLE HDW 1"),
        "no_category": db.add_transaction(2026, "May", 2, "Expense", "Card", 20, us, uc, name="EXAMPLE HDW 2",
                                          merchant="Hardware Co"),
        "nothing": db.add_transaction(2026, "May", 3, "Expense", "Chequing", 30, us, uc, name="EXAMPLE HDW 3"),
        "done": db.add_transaction(2026, "May", 4, "Expense", "Card", 40, garden, home, name="EXAMPLE HDW 4",
                                   merchant="Garden Centre"),
        "split": db.add_transaction(2026, "May", 5, "Expense", "Card", 50, us, uc, name="EXAMPLE HDW 5"),
    }
    db.set_splits(ids["split"], [(home, tools, 25, None), (home, garden, 25, None)])
    return {"home": home, "tools": tools, "garden": garden, "ids": ids}


def tx(db, tx_id):
    return db.conn.execute("""SELECT t.merchant, c.name AS cat, s.name AS sub FROM transactions t
                              LEFT JOIN categories c ON c.id = t.category_id
                              LEFT JOIN subcategories s ON s.id = t.subcategory_id WHERE t.id = ?""",
                           (tx_id,)).fetchone()


def dialog(db, name="EXAMPLE HDW", cat="Home", sub="Tools", **kw):
    from daftarche.tabs.manage import RuleEditDialog
    d = keep(RuleEditDialog(db, merchant="Example Hardware", **kw))
    d.f_cat.setCurrentText(cat)
    if sub:
        d.f_sub.setCurrentText(sub)
    d.f_name.setText(name)
    return d


# ── the database ─────────────────────────────────────────────────────────────
def test_only_what_is_missing_then_everything(db, hw):
    ids = hw["ids"]
    every = [ids[k] for k in ("no_merchant", "no_category", "nothing", "done", "split")]
    n = db.apply_rule_to_transactions(every, "Example Hardware", hw["home"], hw["tools"])
    assert n == 3
    assert tuple(tx(db, ids["no_merchant"])) == ("Example Hardware", "Home", "Garden")  # its category kept
    assert tuple(tx(db, ids["no_category"])) == ("Hardware Co", "Home", "Tools")  # its merchant kept
    assert tuple(tx(db, ids["nothing"])) == ("Example Hardware", "Home", "Tools")
    assert tuple(tx(db, ids["done"])) == ("Garden Centre", "Home", "Garden")
    assert tx(db, ids["split"])["merchant"] is None and len(db.get_splits(ids["split"])) == 2
    assert db.apply_rule_to_transactions(every, "Example Hardware", hw["home"], hw["tools"], everything=True) == 3
    assert tuple(tx(db, ids["done"])) == ("Example Hardware", "Home", "Tools")
    assert tx(db, ids["split"])["merchant"] is None  # split: still left alone


def test_a_merchant_only_rule_never_changes_a_category(db, hw):
    uc, us = db.get_uncategorized_ids()
    done = hw["ids"]["done"]
    assert db.apply_rule_to_transactions([done], "Example Hardware", uc, us, everything=True) == 1
    assert tuple(tx(db, done)) == ("Example Hardware", "Home", "Garden")


# ── the rule window ──────────────────────────────────────────────────────────
def test_the_window_counts_and_chooses_those_missing_something(qapp, db, hw):
    d = dialog(db)
    assert not d.apply_box.isHidden()
    assert d.rb_missing.isChecked()
    assert d.rb_missing.text() == "Those missing a merchant or category (3)"
    assert d.rb_all.text() == "All 4, even those already categorized"  # the split one left out
    ids, everything = d.to_apply()
    assert sorted(ids) == sorted(hw["ids"][k] for k in ("no_merchant", "no_category", "nothing"))
    assert not everything
    d.rb_all.setChecked(True)
    assert len(d.to_apply()[0]) == 4 and d.to_apply()[1]
    d.rb_none.setChecked(True)
    assert d.to_apply() is None


def test_a_merchant_only_rule_offers_the_merchant(qapp, db, hw):
    from daftarche.tabs.manage import YOU_CHOOSE
    d = dialog(db, cat=YOU_CHOOSE, sub=None)
    assert d.apply_title.text() == "Also set this merchant on them:"
    assert d.rb_missing.text() == "Those with no merchant (2)"
    assert d.rb_all.text() == "All 4, even those with another merchant"


def test_one_account_and_no_matches(qapp, db, hw):
    d = dialog(db)
    d.f_account.setCurrentText("Chequing")
    assert d.rb_all.text().startswith("All 1,")
    d.f_name.setText("NOTHING LIKE IT")
    assert d.apply_box.isHidden() and d.to_apply() is None


def test_a_more_specific_rule_keeps_its_transactions(qapp, db, hw):
    uc, us = db.get_uncategorized_ids()
    db.save_mapping("Expense", None, name="EXAMPLE HDW 3", subcategory_id=us, category_id=uc, merchant="Other")
    db.save_mapping("Expense", None, name="EXAMPLE HDW", subcategory_id=us, category_id=uc, merchant="Older")
    d = dialog(db)
    assert d.rb_all.text().startswith("All 3,")  # HDW 3 stays with its own rule; the older tie loses
    assert hw["ids"]["nothing"] not in d.to_apply()[0]


def test_your_choice_is_kept_while_typing(qapp, db, hw):
    d = dialog(db)
    d.rb_none.click()
    d.f_name.setText("EXAMPLE")
    assert d.rb_none.isChecked()


def test_transfer_rules_offer_nothing(qapp, db, hw):
    d = dialog(db, sub=None)
    d.f_type.setCurrentText("Transfer")
    assert d.apply_box.isHidden() and d.to_apply() is None


def test_editing_a_rule_does_not_compete_with_itself(qapp, db, hw):
    from daftarche.tabs.manage import RuleEditDialog
    db.save_mapping("Expense", None, name="EXAMPLE HDW", subcategory_id=hw["tools"], category_id=hw["home"],
                    merchant="Example Hardware")
    rule = db.get_rules("Example Hardware")[0]
    d = keep(RuleEditDialog(db, existing=rule))
    assert d.rb_all.text().startswith("All 4,")


# ── Manage → Merchants ───────────────────────────────────────────────────────
def test_adding_a_rule_sets_it_on_the_transactions(qapp, db, hw):
    from daftarche.tabs.manage import ManageDialog
    dlg = keep(ManageDialog(db, lambda: None))
    panel = dlg.merchants_panel

    def fill(d):
        d.f_merchant.setCurrentText("Example Hardware")
        d.f_cat.setCurrentText("Home")
        d.f_sub.setCurrentText("Tools")
        d.f_name.setText("EXAMPLE HDW")
        return True

    with mock.patch("daftarche.tabs.manage.RuleEditDialog.exec", fill):
        panel.add_rule()
    assert tuple(tx(db, hw["ids"]["nothing"])) == ("Example Hardware", "Home", "Tools")
    assert tuple(tx(db, hw["ids"]["done"])) == ("Garden Centre", "Home", "Garden")
    assert dlg.note.text() == "✅ Rule saved and set on 3 transactions."
    assert panel._selected()["merchant"] == "Example Hardware"


def test_saving_and_applying_is_all_or_nothing(qapp, db, hw):
    from daftarche.tabs.manage import save_rule
    d = dialog(db)
    with mock.patch.object(db, "apply_rule_to_transactions", side_effect=RuntimeError("disk full")):
        with pytest.raises(RuntimeError):
            save_rule(db, d.values(), apply=d.to_apply())
    assert db.get_rules("Example Hardware") == []
