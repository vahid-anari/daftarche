"""The phone snapshot: everything Daftarche on the phone shows, in one JSON file.

The phone app only reads this file (see docs/phone-snapshot.md for the format). Balances and
loans are worked out here, by the same code the desktop app uses, so the two never disagree;
the phone only adds up transaction amounts. Bank account numbers, import rules and bank
transaction ids are left out: the phone does not need them.

No Qt here: phone_sync.py seals it (seal.py) and sends it to the phones' files on Google Drive.
"""

from __future__ import annotations

import base64
from datetime import datetime

from daftarche.db import MONTH_NUM, PICTURE_PREFIX, round2

FORMAT = "daftarche-phone"
VERSION = 1
"""Raised only when the shape changes in a way an older phone app cannot read."""

_KINDS = ("Income", "Expense", "Transfer")


def _kind(type_name):
    """Income, Expense or Transfer (Daftarche matches type names by these words)."""
    name = type_name or ""
    return next((k for k in _KINDS if k in name), name)


def _month_key(year, month_name):
    return f"{year:04d}-{MONTH_NUM[month_name]:02d}"


def _num(value):
    """Rounded to cents, and never -0.0."""
    return round2(value or 0) + 0.0


def build_snapshot(db, app_version="", now=None):
    """The snapshot of ``db`` as a dict (see docs/phone-snapshot.md)."""
    conn = db.conn
    now = now or datetime.now().astimezone()

    latest = db.get_latest_account_balances()
    accounts = [{"id": a["id"], "name": a["name"], "color": a["color"] or "#7c6af7",
                 "active": bool(a["active"]), "visible": bool(a["visible"]),
                 "show_in_accounts": bool(a["show_in_accounts"]),
                 "balance": _num(latest.get(a["id"], 0))}
                for a in db.get_accounts()]

    snapshots, _ = db.get_account_monthly_balance()
    periods = sorted(snapshots, key=lambda ym: (ym[0], MONTH_NUM[ym[1]]))
    balances = {"months": [_month_key(*p) for p in periods],
                "by_account": {str(a["id"]): [_num(snapshots[p].get(a["id"], 0)) for p in periods]
                               for a in accounts}}

    # logos and pictures go as PNG (at most 128 px, as kept): "images" holds each once, by a key
    images = {}
    for r in conn.execute("SELECT merchant, image FROM merchant_logos ORDER BY merchant COLLATE NOCASE"):
        if r["image"]:  # "Café" and "CAFÉ" share a key: the first, as logo_for on the desktop
            images.setdefault(merchant_image_key(r["merchant"]), base64.b64encode(r["image"]).decode())
    pictures = {r["id"]: r["image"] for r in conn.execute("SELECT id, image FROM category_pictures")}

    def look(icon):
        """(emoji, image key) of an icon: an emoji, a logo ("logo:…") or a picture ("pic:…")."""
        icon = icon or ""
        if icon.startswith("logo:"):
            key = merchant_image_key(icon[5:])
            return None, key if key in images else None
        if icon.startswith(PICTURE_PREFIX):
            pid = int(icon[len(PICTURE_PREFIX):]) if icon[len(PICTURE_PREFIX):].isdigit() else None
            if pictures.get(pid):
                images.setdefault(icon, base64.b64encode(pictures[pid]).decode())
                return None, icon
            return None, None
        return icon or None, None

    cat_look = {r["id"]: look(r["icon"]) for r in conn.execute("SELECT id, icon FROM categories")}
    subs = {}
    for r in conn.execute("SELECT id, name, icon, category_id FROM subcategories ORDER BY name"):
        own = look(r["icon"])
        emoji, image = own if own != (None, None) else cat_look.get(r["category_id"], (None, None))
        subs.setdefault(r["category_id"], []).append({"id": r["id"], "name": r["name"], "icon": emoji, "image": image})
    categories = []
    for r in conn.execute("SELECT c.id, c.name, t.name AS type_name FROM categories c "
                          "LEFT JOIN types t ON t.id = c.type_id ORDER BY t.name, c.name"):
        emoji, image = cat_look.get(r["id"], (None, None))
        categories.append({"id": r["id"], "name": r["name"], "type": _kind(r["type_name"]), "icon": emoji,
                           "image": image, "subcategories": subs.get(r["id"], [])})

    tags = [{"id": r["id"], "name": r["name"]} for r in conn.execute("SELECT id, name FROM tags ORDER BY name")]
    tags_of = {}
    for r in conn.execute("SELECT transaction_id, tag_id FROM transaction_tags ORDER BY tag_id"):
        tags_of.setdefault(r["transaction_id"], []).append(r["tag_id"])
    part_tags = {}  # a part's own tags: with the part (the phone adds up a transaction's tags as a whole)
    for r in conn.execute("SELECT split_id, tag_id FROM split_tags ORDER BY tag_id"):
        part_tags.setdefault(r["split_id"], []).append(r["tag_id"])
    parts_of = {}
    for r in conn.execute("SELECT id, transaction_id, category_id, subcategory_id, amount, note "
                          "FROM transaction_splits ORDER BY transaction_id, position, id"):
        parts_of.setdefault(r["transaction_id"], []).append(
            {"category": r["category_id"], "subcategory": r["subcategory_id"], "amount": _num(r["amount"]),
             "note": r["note"], "tags": part_tags.get(r["id"], [])})

    transactions = []
    for r in conn.execute("""SELECT t.id, t.date, ty.name AS type_name, t.account_id, t.to_account_id, t.amount,
                                    t.category_id, t.subcategory_id, t.merchant, t.note, t.name, t.transfer_status
                             FROM transactions t LEFT JOIN types ty ON ty.id = t.type_id
                             ORDER BY t.date DESC, t.id DESC"""):
        kind = _kind(r["type_name"])
        transactions.append({
            "id": r["id"], "date": r["date"], "type": kind,
            "account": r["account_id"], "to_account": r["to_account_id"], "amount": _num(r["amount"]),
            "category": r["category_id"], "subcategory": r["subcategory_id"],
            "merchant": r["merchant"], "note": r["note"], "name": r["name"],
            "transfer": r["transfer_status"] if kind == "Transfer" else None,
            "tags": tags_of.get(r["id"], []), "parts": parts_of.get(r["id"], []),
        })

    loans = [{"person": e["merchant"], "opening": _num(e["opening"]), "paid_out": _num(e["paid_out"]),
              "received": _num(e["received"]), "written_off": _num(e["written_off"]),
              "balance": _num(e["balance"]), "count": e["count"], "last": e["last"], "note": e["note"]}
             for e in db.get_loans()]

    return {"format": FORMAT, "version": VERSION, "created": now.isoformat(timespec="seconds"),
            "app_version": app_version, "accounts": accounts, "balances": balances,
            "categories": categories, "tags": tags, "transactions": transactions, "loans": loans,
            "images": images}


def merchant_image_key(merchant):
    """The key of a merchant's logo in the snapshot's "images" (names match whatever the case)."""
    return "logo:" + (merchant or "").strip().casefold()
