# Changelog

## 0.14.0 — 2026-10-18

- Transactions: a Note column for your own words (what a purchase was). Double-click the
  cell to type; it is also in Edit Transaction, in the search (on unless turned off in 🔍)
  and in the Excel export. The database layout goes to 2: older versions of Daftarche
  will ask to be updated before opening it.
- The Sort window sorted by the wrong column for Name, Memorandum, FITID and Tags.
- tools/export_shop_charges.py writes the Amazon and AliExpress transactions to a CSV
  file; tools/import_notes.py writes notes (and categories) from such a file back, after
  showing them and backing up the database.

## 0.13.2 — 2026-10-18

- Fixed a crash when quitting after Edit Category / Sub-Category had been opened: the
  closed window stayed in memory until quit, and Python's shutdown crashed while cleaning
  it up. The window is now deleted as soon as it closes.

## 0.13.1 — 2026-10-18

- Edit Category / Sub-Category: the list of suggestions while typing uses the theme's
  colours (it was white), and switching names no longer leaves the old rule rows
  painted at the bottom of the window.

## 0.13.0 — 2026-10-18

- A new Edit Category / Sub-Category window (Transactions and Import tabs):
  - both names can be typed (the list narrows to names containing what is typed) or
    picked; a green "New" marks a name that will be added when you press OK;
  - below, the rules of the chosen sub-category: account, name and memo can be edited,
    × removes a rule, and a new rule (account All, the transaction's name and memo to
    trim) is added with Add;
  - "Also apply the new rule to N matching uncategorized transactions" categorizes the
    others the new rule matches (in the Import tab: the rows of the preview);
  - nothing is saved before OK.
- The category boxes of Edit Transaction can be typed in too (0.12.0 asked, but the
  boxes did not take typing); clicking into a box selects its text.

## 0.12.0 — 2026-10-18

- Edit Category / Sub-Category (Transactions and Import) and Edit Transaction: a new
  category or sub-category can be typed in; it is added after asking (Add / Go Back),
  so a typo is not saved as a new name. A name typed in other letter case ("pets") uses
  the existing one, and a category is only reused from the row's own type.

## 0.11.0 — 2026-10-18

- Charts: a Total line at the end of the category list adds up the ticked categories
  over the range, and follows the ticks.
- Charts: hover labels of the line and bar charts also show the month's total of the
  ticked categories.

## 0.10.0 — 2026-10-18

- Charts: Donut is a choice in the Chart list. For one month the list is Donut, Bars
  (one bar per category, largest first) and Stacked Bars; for several months it is
  Line, Spline, Grouped Bars, Stacked Bars and Donut (each category's total over the range).
  A line picked for several months comes back when the range does.

## 0.9.0 — 2026-10-18

- View → Uncategorized… (⌘U): income and expense transactions still to sort, all time,
  as a tree: fully uncategorized rows, and categories whose sub-category is still
  Uncategorized. Double-click a line to see those transactions.
- View → Unmatched Transfers… (⇧⌘U): transfers whose other side has not been found, per
  account and direction (Internal and External), with a Match Transfers button.
- The Dashboard's warning opens these windows.
- A transaction can have a category with the sub-category left as Uncategorized (offered
  first in the sub-category lists); an import rule may set only the category.
- Import: the status bar counts new transfers, uncategorized rows and rows without a
  sub-category. Importing with uncategorized rows asks first (Import / Go Back); they are
  saved as Uncategorized.

## 0.8.2 — 2026-10-18

- Settings → Splash Screen (s): how long the splash screen stays at start-up
  (default 3.5 s; 0 turns it off).

## 0.8.1 — 2026-10-17

- The drop-down popups (multi-select lists, date picker) now belong to their widget, so
  they are deleted with the window instead of during Python's shutdown, where they could
  crash the app as it quit (seen with Python 3.15).
- Needs sciwidgets 0.11.2: Restart Now after an update reopens Daftarche itself on macOS
  instead of starting it as "Python".

## 0.8.0 — 2026-10-17

Speed and robustness.

- Settings are written to a temporary file and swapped in, so a crash can no longer leave
  a half-written `config.json` (which used to reset every setting silently); a damaged
  file is kept as `config.json.broken`.
- The database records its layout version; an older Daftarche refuses to open, or
  restore, a database written by a newer one instead of changing it.
- Account balances are computed in one pass and reused until the data changes (three
  tabs used to recompute them on every refresh); months without transactions now appear
  in the Accounts tab with the balance carried over.
- After a change only the tab on screen refreshes; the others refresh when shown. The
  search box filters once typing pauses. Duplicate checks during import are one query
  per row; three database indexes added.
- Charts: replaced charts are deleted (each refresh leaked them), the Charts tab builds
  once per change instead of twice, and a month without data shows as zero.
- Export writes the rows as shown (same filters, same order) with Tags and FITID, adds
  `.xlsx` when missing, and says so when the file cannot be written (e.g. open in Excel).
- A failed automatic backup is shown in the window's status bar.
- Code clean-up; `ruff` now runs in CI.

## 0.7.0 — 2026-10-17

Dates, transfers and statements.

- Date picker: browsing to another month no longer changes the date until a day is
  picked (Jan 31 → February used to leave an impossible Feb 31, which broke the
  Dashboard, Charts and Accounts tabs). Clicking a grey day of the next or previous
  month picks it. In month mode the month changes only on OK.
- Custom ranges: setting "To" before "From" moves "From" back with it; a range never ends
  before it starts.
- Match Transfers pairs the closest dates first, keeps the incoming side's tags, name and
  memo, and keeps transfers labelled Internal.
- Statements are decoded with the charset their header names (CIBC: Windows-1252), so
  ’ – € and accented letters come through.
- Credit cards are recognised from the statement itself, not only from an account name
  containing "credit"; "PAYMENT" must be a whole word ("PAYMENTUS …" is not a payment).
- Rows of a statement that cannot be read are counted in the Import status bar
  ("⚠️ N unreadable", reasons in its tooltip) instead of disappearing silently.
- Transfers are stored with the category the import preview showed.
- Edit Category: a typed category or sub-category that does not exist is refused with a
  message, instead of saving the rows as "no category".

## 0.6.0 — 2026-10-17

Rules and merges.

- Rule matching: a rule's words must appear as whole words, so "Ali" no longer matches
  "NATALIE" or "ALIMENTATION". When several rules match, the most specific wins (the most
  matched text, then a rule for this account, then the newest), so "Ali Mohammad" beats
  "Ali". `tools/compare_rules.py` lists the past transactions the new matching would
  categorize differently (read-only).
- Saving a rule again changes it instead of adding a copy; existing copies are cleaned
  up on first start, keeping the newest.
- Renaming onto an existing name asks first, then merges completely:
  - accounts: transactions, bank IDs and rules move (this used to fail half-way);
  - categories: sub-categories with the same name are merged too, rules move;
  - sub-categories: rules move instead of being deleted.
- A category name used under two types (e.g. "Other" under Income and Expense) is no
  longer confused with the other one when editing, renaming or moving sub-categories.
- Moving a sub-category to another category also moves its transactions.
- Deleting a category that a rule points to works; deleting or renaming a type that is
  in use explains why it can't instead of failing silently.
- Needs sciwidgets 0.11.1 (reliable Update Now).

## 0.5.0 — 2026-10-17

Data safety fixes.

- Restore checks the chosen file first (a database, not damaged, a Daftarche database)
  and keeps a copy of the current data as `backups/daftarche-before-restore-<time>.db`;
  a wrong file used to replace the database and stop the app from starting.
- Every change to the database is all-or-nothing: a step that fails undoes the steps
  before it, instead of leaving them to be saved by the next change.
- Import is all-or-nothing too: an error part-way imports nothing, and a retry does not
  duplicate rows. Impossible dates in a statement are skipped.
- Loading a statement that has no transactions no longer leaves the previous file's
  rows in the preview, where Import New would have put them in the new account.
- Editing a transaction no longer changes its category (Uncategorized rows) or its
  account (closed accounts, incoming transfers) when only other fields were edited.

## 0.4.0 — 2026-10-17

- Menu bar inside the window (File, Edit, Help), in the app's colours, instead of
  the macOS menu bar; it replaces the row of buttons above the tabs.
- File: Back Up Database…, Restore Backup…, Show Data Folder, Quit (⌘Q).
  Edit: Manage… (⌘M), Settings… (⌘,). Help: Check for Updates…, Show Data Folder, About.

## 0.3.0 — 2026-10-17

- Settings → Extra backup folder: the monthly snapshots are also copied to a folder
  of your choice (iCloud Drive, an external disk), with the same 12-month rotation;
  skipped when the folder is not there.
- Help → About Daftarche (in the app menu on macOS) and Help → Show Data Folder.

## 0.2.0 — 2026-10-17

- Renamed to **Daftarche** (package, command `daftarche`, app name).
- Data folder is now `~/Library/Application Support/Daftarche/` with `daftarche.db`
  (override with `DAFTARCHE_HOME`); the old `Finance` folder is moved there on first start.
- Backups: `daftarche-last.db` at every start, plus a monthly snapshot
  `daftarche-YYYY-MM.db` that is never overwritten; the last 12 are kept.
- `daftarche update [--check] [-y]`, a quiet update check at start-up and
  Help → Check for Updates… (needs the package on PyPI).
- MIT licence, tests (database, QFX parsing, backups, command line) and GitHub
  Actions: tests on every push, a GitHub Release from CHANGELOG.md on every `v*` tag.

## 0.1.0 — 2026-10-17

First packaged version.

- Installable package (`pip install -e .`) with a `finance` command and `finance install-app`.
- Data (database, settings, backups) moved out of the source tree into
  `~/Library/Application Support/Finance/` (override with `FINANCE_HOME`).
- Automatic backup written to `backups/finance_backup.db` at every start.
- App icon and splash screen, drawn by `tools/make_icon.py` (variants: bars, combo).
