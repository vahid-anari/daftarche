"""Make a demo database with a year of invented transactions, for screenshots and trying the app.

Nothing is real: the accounts, merchants and amounts are made up (same numbers every run).
The database goes into its own data folder, so your own data is never touched:

    python tools/make_demo_db.py                      # ~/Desktop/daftarche-demo
    python tools/make_demo_db.py --folder /tmp/demo --months 18
    DAFTARCHE_HOME=~/Desktop/daftarche-demo daftarche  # open the app on the demo data

An existing demo database in that folder is replaced; any other file there is refused.
"""
import argparse
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from daftarche.db import MONTHS_ORDER, Database  # noqa: E402

CHEQUING, SAVINGS, VISA = "Demo Bank Chequing", "Demo Bank Savings", "Demo Visa"

# type -> category -> sub-categories
CATEGORIES = {
    "Income": {"Salary": ["Pay"], "Side Work": ["Tutoring", "Consulting"]},
    "Expense": {
        "Home": ["Rent", "Hydro", "Internet"],
        "Groceries": ["Supermarket", "Bakery", "Market"],
        "Transport": ["Transit", "Taxi"],
        "Eating Out": ["Restaurants", "Coffee"],
        "Phone": ["Mobile Plan"],
        "Health": ["Pharmacy", "Dentist"],
        "Leisure": ["Books", "Cinema", "Streaming"],
        "Shopping": ["Clothes", "Household"],
    },
}

# (category, sub-category, merchant, how many per month (min, max), amount range, account)
SPENDING = [
    ("Groceries", "Supermarket", "Maple Grocer", (3, 5), (35, 140), VISA),
    ("Groceries", "Bakery", "Sunrise Bakery", (1, 3), (6, 22), VISA),
    ("Groceries", "Market", "Harbour Farmers Market", (0, 2), (15, 45), CHEQUING),
    ("Transport", "Taxi", "Quick Cab", (0, 2), (14, 38), VISA),
    ("Eating Out", "Restaurants", "Lakeside Bistro", (1, 3), (28, 85), VISA),
    ("Eating Out", "Coffee", "Bean There Cafe", (3, 7), (4, 9), VISA),
    ("Health", "Pharmacy", "Corner Pharmacy", (0, 2), (9, 48), VISA),
    ("Leisure", "Books", "Paper Trail Books", (0, 1), (18, 60), VISA),
    ("Leisure", "Cinema", "Starlight Cinema", (0, 2), (14, 32), VISA),
    ("Shopping", "Clothes", "Northwind Outfitters", (0, 1), (40, 160), VISA),
    ("Shopping", "Household", "Hearth & Home", (0, 2), (12, 75), VISA),
]

# (category, sub-category, merchant, day of month, amount, account) every month
MONTHLY = [
    ("Home", "Rent", "Elm Street Property Mgmt", 1, 1850.00, CHEQUING),
    ("Home", "Hydro", "City Hydro", 12, None, CHEQUING),
    ("Home", "Internet", "FastNet", 15, 75.00, CHEQUING),
    ("Phone", "Mobile Plan", "Northern Mobile", 18, 55.00, VISA),
    ("Transport", "Transit", "Metro Transit Pass", 2, 156.00, CHEQUING),
    ("Leisure", "Streaming", "StreamBox", 20, 16.99, VISA),
]


def months_back(n, today):
    """The ``n`` months up to and including the current one, oldest first, as (year, month)."""
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def make_demo(folder: Path, months: int = 12, seed: int = 7, today: date | None = None) -> Path:
    """Write ``folder/daftarche.db`` with ``months`` months of invented data; returns its path."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "daftarche.db"
    if path.exists():
        path.unlink()
    rng = random.Random(seed)
    today = today or date.today()
    db = Database(str(path))

    sub_ids = {}
    for type_name, cats in CATEGORIES.items():
        for cat, subs in cats.items():
            db.add_category(cat, type_name)
            cat_id = db.get_category_by_name(cat, type_name=type_name)["id"]
            for sub in subs:
                db.add_subcategory(sub, cat_id)
                sub_ids[cat, sub] = (cat_id, db.get_subcategory_by_name(sub, cat_id)["id"])

    visa = {"charged": 0.0, "to_pay": 0.0}  # this month's card charges; last month's, paid on the 22nd

    def spend(y, month, day, cat, sub, merchant, amount, account, type_name="Expense"):
        cat_id, sub_id = sub_ids[cat, sub]
        if account == VISA:
            visa["charged"] += round(amount, 2)
        db.add_transaction(y, month, day, type_name, account, round(amount, 2), sub_id, cat_id,
                           name=merchant.upper(), merchant=merchant)

    for y, m in months_back(months, today):
        month = MONTHS_ORDER[m - 1]
        last_day = 28 if m == 2 else 30
        if (y, m) == (today.year, today.month):
            last_day = max(1, min(last_day, today.day))

        def day(d):
            return min(d, last_day)

        for d in (1, 15):
            if d <= last_day:
                spend(y, month, d, "Salary", "Pay", "Acme Research Ltd", 2650.00, CHEQUING, "Income")
        if rng.random() < 0.35:
            sub = rng.choice(["Tutoring", "Consulting"])
            spend(y, month, day(rng.randint(5, 25)), "Side Work", sub, f"{sub} client", rng.uniform(120, 480),
                  CHEQUING, "Income")

        for cat, sub, merchant, d, amount, account in MONTHLY:
            if d > last_day:
                continue
            if amount is None:  # hydro follows the season
                amount = 60 + 45 * (1 if m in (12, 1, 2) else 0.4 if m in (7, 8) else 0) + rng.uniform(-8, 8)
            spend(y, month, d, cat, sub, merchant, amount, account)

        for cat, sub, merchant, (lo, hi), (a, b), account in SPENDING:
            for _ in range(rng.randint(lo, hi)):
                spend(y, month, rng.randint(1, last_day), cat, sub, merchant, rng.uniform(a, b), account)
        if rng.random() < 0.15:
            spend(y, month, day(rng.randint(3, 27)), "Health", "Dentist", "Bright Smile Dental", rng.uniform(90, 240),
                  VISA)
        if rng.random() < 0.3:  # a refund now and then
            spend(y, month, day(rng.randint(3, 27)), "Shopping", "Clothes", "Northwind Outfitters",
                  -rng.uniform(20, 60), VISA)

        for d, to_account, amount, text in ((2, SAVINGS, 400.00, "INTERNET TRANSFER TO SAVINGS"),
                                            (22, VISA, round(visa["to_pay"], 2), "INTERNET TRANSFER VISA PAYMENT")):
            if d > last_day or amount <= 0:
                continue
            cat_id, sub_id = db.get_transfer_cat_sub(text, matched=True, from_account=CHEQUING,
                                                     to_account=to_account)
            db.add_transaction(y, month, d, "Transfer", CHEQUING, amount, sub_id, cat_id, name=text,
                               description=text, to_account_name=to_account)
        visa["to_pay"], visa["charged"] = visa["charged"], 0.0
    db.conn.commit()
    db.conn.close()
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=Path.home() / "Desktop" / "daftarche-demo",
                        help="data folder for the demo (default ~/Desktop/daftarche-demo)")
    parser.add_argument("--months", type=int, default=12, help="how many months of data (default 12)")
    args = parser.parse_args(argv)
    folder = args.folder.expanduser()
    others = [p.name for p in folder.glob("*") if p.name not in ("daftarche.db", "config.json", "backups")]
    if others:
        parser.error(f"{folder} already holds other files ({', '.join(sorted(others)[:3])}); choose an empty folder")
    path = make_demo(folder, args.months)
    print(f"Demo database: {path}")
    print(f"Open it with:  DAFTARCHE_HOME='{folder}' daftarche")


if __name__ == "__main__":
    main()
