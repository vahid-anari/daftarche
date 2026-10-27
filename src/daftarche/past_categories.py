"""What a merchant's transactions were given before (db.merchant_categories), offered when you
choose a category, and the one question when a rule's category no longer fits its merchant."""

from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QMessageBox

from daftarche.db import SUB_MATCHED, SUB_UNMATCHED, UNCATEGORIZED_SUB
from daftarche.style import get_settings

KEEP_KEY = "rules_keep_category"  # rules you asked not to be asked about again ("Don't Ask")


def category_label(category, subcategory):
    """ "Shopping › Household", or "Shopping" when it has no sub-category of its own."""
    if not subcategory or subcategory in (UNCATEGORIZED_SUB, SUB_MATCHED, SUB_UNMATCHED):
        return category
    return f"{category} › {subcategory}"


def entry_icon(icons, entry):
    """The emoji of a suggestion (its sub-category's own, else its category's) from db.get_icons()."""
    return (icons.get("sub_own", {}).get(entry["subcategory_id"])
            or icons.get("cat", {}).get(entry["category_id"]) or "")


def ask_merchant_only(parent, merchant, rule_sets, n_categories):
    """ "merchant" (Only the Merchant), "later" (Not Now) or "never" (Don't Ask for This Rule)."""
    box = QMessageBox(parent)
    box.setWindowTitle("Rule for " + merchant)
    box.setIcon(QMessageBox.Question)
    box.setText(f"{merchant}'s rule gives every new {merchant} transaction {rule_sets}, but its "
                f"transactions are in {n_categories} categories now.")
    box.setInformativeText("Let the rule set only the merchant? New ones then wait in To review, and a "
                           "right-click offers the categories it had before.")
    only = box.addButton("Only the Merchant", QMessageBox.AcceptRole)
    later = box.addButton("Not Now", QMessageBox.RejectRole)
    never = box.addButton("Don't Ask for This Rule", QMessageBox.DestructiveRole)
    for button in (only, later, never):  # on macOS the buttons were one width, too narrow for their text
        button.ensurePolished()
        font = QFont(button.font())
        font.setBold(True)
        button.setMinimumWidth(QFontMetrics(font).horizontalAdvance(button.text()) + 48)
    box.setDefaultButton(later)
    box.exec()
    clicked = box.clickedButton()
    return "merchant" if clicked is only else "never" if clicked is never else "later"


def offer_merchant_only(parent, db, rows, category_id, subcategory_id):
    """After ``rows`` (Transactions rows) were given this category: for each rule that recognises
    one of them, sets their merchant and a category other than this one, ask (once per rule
    and change) whether it should set only the merchant from now on. Returns the rules changed."""
    uncat_cat, _ = db.get_uncategorized_ids()
    kept = set(get_settings().get(KEEP_KEY) or [])
    seen, changed = set(), []
    for r in rows:
        account = r.get("account") or r.get("to_account")
        rule = db.lookup_mapping(r["type"], account, r.get("name") or None, r.get("memorandum") or None)
        if (rule is None or rule["id"] in seen or rule["id"] in kept or rule["category_id"] in (None, uncat_cat)
                or (rule["merchant"] or "").casefold() != (r.get("merchant") or "").casefold()
                or (rule["category_id"], rule["subcategory_id"]) == (category_id, subcategory_id)):
            continue
        seen.add(rule["id"])
        cat = db.get_category_by_id(rule["category_id"])
        sub = db.get_subcategory_by_id(rule["subcategory_id"]) if rule["subcategory_id"] else None
        n = len(db.merchant_categories(rule["merchant"], r["type"]))
        answer = ask_merchant_only(parent, rule["merchant"], category_label(cat["name"], sub["name"] if sub else None),
                                   max(n, 2))
        if answer == "merchant":
            db.make_rule_merchant_only(rule["id"])
            changed.append(rule["id"])
        elif answer == "never":
            get_settings().set(KEEP_KEY, sorted(kept | {rule["id"]}))
            kept.add(rule["id"])
    return changed
