# Daftarche on the phone: the snapshot file

Daftarche on the Mac (0.26.0 and later) writes everything the phone shows into one file,
`daftarche-phone.json`, in a folder you choose (a Syncthing folder shared with the
phone). The phone app only reads this file. It never changes your data and does no
bookkeeping of its own: balances and loans are worked out on the Mac, by the same
code the desktop app uses, so the two can never disagree.

## When it is written

- after an import, and when Daftarche closes;
- from **File › Update Phone Snapshot** at any time;
- only when a phone folder is set in **Settings › Phone** (off by default).

It is written to a temporary file first and then renamed, so Syncthing never
copies a half-written file.

## What is left out

Nothing the phone does not need: no bank account numbers (`account_ids`), no
import rules, no bank transaction ids (`fitid`), no backups.

## The format (version 1)

All amounts are numbers rounded to cents and are positive as in Daftarche (an
expense of $45.20 is `45.2`; a refund is a negative expense). Dates are
`YYYY-MM-DD`. Ids are Daftarche's own and are only used to link the parts of the
file together.

```json
{
  "format": "daftarche-phone",
  "version": 1,
  "created": "2026-10-20T08:15:00-04:00",
  "app_version": "0.26.0",

  "accounts": [
    {"id": 1, "name": "Chequing", "color": "#7c6af7",
     "active": true, "visible": true, "show_in_accounts": true,
     "balance": 3120.55}
  ],

  "balances": {
    "months": ["2025-11", "2025-12", "2026-01"],
    "by_account": {"1": [2800.10, 2950.00, 3120.55]}
  },

  "categories": [
    {"id": 4, "name": "Groceries", "type": "Expense", "icon": "🛒",
     "subcategories": [{"id": 9, "name": "Supermarket", "icon": "🛒"}]}
  ],

  "tags": [{"id": 1, "name": "Trip to Italy"}],

  "transactions": [
    {"id": 812, "date": "2026-10-03", "type": "Expense",
     "account": 3, "to_account": null, "amount": 45.2,
     "category": 4, "subcategory": 9,
     "merchant": "Maple Grocer", "note": null, "name": "MAPLE GROCER #12",
     "transfer": null, "tags": [1],
     "parts": []}
  ],

  "loans": [
    {"person": "Sahar", "opening": 0, "paid_out": 500, "received": 200,
     "written_off": 0, "balance": 300, "count": 3, "last": "2026-09-14",
     "note": null}
  ]
}
```

Notes on the fields:

- **accounts.balance**: the balance today, as on the Accounts tab.
- **balances**: the balance of every account at the end of every month, from the
  first transaction to the last (what the balance chart draws).
- **categories.type** and **transactions.type**: `Income`, `Expense` or `Transfer`
  (the shared `Uncategorized` category has none: `""`).
- **subcategories.icon**: its own icon, else its category's.
- **transactions.transfer**: for transfers only: `matched`, `unmatched` or `loan`.
- **transactions.parts**: the parts of a split transaction, in order, each
  `{"category", "subcategory", "amount", "note"}`; empty when it is not split.
  Totals by category use the parts.
- **loans.balance**: more than 0, they owe you; less than 0, you owe them.

## Versions

`version` goes up only when the shape changes in a way an older phone app cannot
read (a new field does not count). A phone app that meets a newer version says
"This data is from a newer Daftarche. Please update the app." instead of
guessing.
