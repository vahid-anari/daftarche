# Daftarche on the phone: the snapshot file

Daftarche on the Mac puts everything the phone shows into one snapshot (JSON, below). The
phone app only reads it. It never changes your data and does no bookkeeping of its own:
balances and loans are worked out on the Mac, by the same code the desktop app uses, so the
two can never disagree.

## How it gets to the phone (0.28.0 and later)

- The Mac signs in to Google once (Settings › Phone), asking only for `drive.file`: it can
  see and change the files it made itself, nothing else in your Drive.
- **Connect a Phone…** makes a file for that phone, *Daftarche phone - <name>*, shared as
  "anyone with the link" so the phone can download it without signing in, and shows a QR
  code with the pairing link `https://vahid-anari.github.io/pair/#v=1&f=<file id>&k=<key>&n=<name>`.
  Any phone camera opens a web link; that page (`docs/site/pair/`) hands everything after `#` to the
  app as `daftarche://pair?…`. Browsers never send the part after `#` to a server, so the key does
  not reach GitHub either.
- The snapshot is **sealed** with that phone's own random 32-byte key before it is uploaded
  (`src/daftarche/seal.py`): compressed with zlib, encrypted with an HMAC-SHA256 keystream
  (a fresh 16-byte nonce each time) and authenticated with HMAC-SHA256 (encrypt-then-MAC).
  Google only ever holds scrambled bytes; the key travels only in the QR code.
- The Mac sends about a minute after the last change, right after an import and when it
  closes; it tries again by itself when offline. Never for a database opened to look at.
- The phone fetches `https://drive.usercontent.google.com/download?id=<file id>` when opened,
  opens it with its key, and keeps the sealed copy for when there is no connection.
- **Disconnect** on the Mac deletes the phone's file; the phone, finding it gone, removes its
  copy and the key.
- The sign-in and the phones' keys are kept in `phone-link.json` next to the database
  (readable only by you).

Before 0.28.0 the snapshot was a file, `daftarche-phone.json`, in a folder shared with the
phone by Syncthing; that is gone.

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
