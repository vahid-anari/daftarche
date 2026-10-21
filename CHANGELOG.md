# Changelog

## 0.27.0 — 2026-10-21

- Rules now live with their merchant: Manage → Merchants shows a shop's rules beside it (the
  bank text each one looks for, what it sets, type and account), with add, edit and delete
  there. Every rule sets a merchant; rules without one are listed under "(no merchant)" at the
  bottom, where you can select several and give them one at once.
- The rule window has its own Merchant, Type, Category and Sub-Category boxes (it used to take
  them from what was selected), and says as you type how many of your transactions the words
  match, with examples. "— you choose (To review)" is the category for a shop that sells many
  things: the rule then sets only the merchant. Saving words another rule already has asks
  before replacing it.
- Manage → Categories (no longer "Categories & Rules"): the fourth list shows the merchants
  whose money goes to the chosen category or sub-category, with their transactions, total and
  rules. Double-click a merchant to see its rules, its numbers to see those transactions. The
  "(merchant only)" line is gone: those rules are under their merchant.
- Fixed: an e-transfer caught by a Transfer rule always went to External Transfer, without the
  rule's merchant. It now gets the person, and the rule's category: a rule to Transfer › Loans
  puts the e-transfer in the Loans window. Re-apply Mappings in Import does the same.
- A rule's words match in any letter case, so saving "kobo" when "KOBO" is there now changes
  that rule (after asking) instead of adding a second one that quietly took over.
- Edit Merchant / Category asks for the merchant of a rule added or changed there.

## 0.26.1 — 2026-10-21

- Transactions has a Merchant filter, next to Sub-Cat, with a search box inside: tick one or
  several merchants, or "(no merchant)" for the transactions without one. Opening a
  merchant's or a person's transactions from Manage → Merchants or from Loans now ticks it
  there, so you can see why the list is short and widen or clear it like any filter.
- A click in Transactions selects the whole line (⇧-click and ⌘-click for several), as every
  action there works on whole transactions anyway. Right-click → Copy Cell copies just the
  value under the mouse; ⌘C still copies the lines.
- The filter boxes say "All" when nothing is ticked (they said "None", though everything was
  shown), and show the ticked names on hover; the Reset button is now the broom at the end
  of the row, so six boxes fit the narrowest window.
- Manage: the small buttons under the lists (✏️ 😀 🔀 🗑️) are no longer cut off, and each
  says what it does on hover.

## 0.26.0 — 2026-10-20

- The phone snapshot, first step towards Daftarche on the phone: choose a phone folder in
  Settings → Phone (a Syncthing folder shared with the phone, say) and Daftarche keeps a
  read-only copy of your data there, `daftarche-phone.json`, after every import and when you
  quit; File → Update Phone Snapshot writes it at any time. Balances and loans are worked out
  on the Mac; bank account numbers, import rules and bank ids are left out. Off until a folder
  is chosen, and never for a database opened with Open Database…. The format is in
  `docs/phone-snapshot.md`.

## 0.25.1 — 2026-10-19

- User Guide: the author on the cover and in the PDF's properties, and a closing line with the
  license and where to find the source code.

## 0.25.0 — 2026-10-19

- A User Guide: Help → User Guide (⌘?) opens it. Plain language and the app's own colours,
  with screenshots: getting started, importing statements, sorting with categories and rules,
  To Review, the four tabs, transfers, refunds, splits and loans, Manage and Settings, your
  data and backups, updates, a shortcut sheet and common questions. Built from `docs/` with
  `tools/build_docs.sh` (XeLaTeX).
- The README shows screenshots made with the demo data; examples say "Vahid" instead of
  "Zahra"; the README's shortcut lines match the app again (To Review ⇧⌘R, Manage ⇧⌘M).

## 0.24.1 — 2026-10-19

- Help → Check for Updates… chosen while the automatic check at start-up was still running no
  longer shows the update notice twice (sciwidgets 0.12.2).
- `tools/make_demo_db.py` makes a demo database with invented data, for screenshots or trying
  the app; the README shows screenshots made with it.

## 0.24.0 — 2026-10-19

- The Help menu is the same as in the author's other apps (Maxwell Bloch Studio, Line Catalog
  Explorer), from sciwidgets 0.12: Check for Updates… (⌘U) and About Daftarche, which now also
  lists the libraries the app is built on, with their versions and licenses. Show Data Folder
  stays in the File menu (it was in both).
- Edit → Manage… is now ⌘⇧M: ⌘M is the Mac's Minimize key.
- Needs sciwidgets 0.12.

## 0.23.0 — 2026-10-19

- Themes: Edit → Settings → Theme is Dark (as before), Light, or Match macOS, which follows
  the Mac's Appearance and switches by itself when the Mac does (e.g. Auto at sunset).
- Each theme keeps its own colour changes: the colour buttons change the theme shown, and
  switching back and forth loses nothing. Reset to Defaults gives the theme shown its own
  colours again. Colours you had changed before are kept as changes to Dark.
- The whole window takes the new colours at once, the Manage and Loans windows too.
- Hover colours darken on light backgrounds, so they show in Light.
- Dashboard: the old account cards no longer linger for a moment after a refresh.

## 0.22.0 — 2026-10-19

- Category icons: each category can have an emoji, shown before its name in Transactions,
  the Charts list, the Dashboard's categories and every category picker. Names don't change
  (search, filters and rules are as before), and the charts themselves stay without icons.
- A sub-category can have its own icon (Transport › Gas ⛽); without one it shows its
  category's.
- Edit → Manage → Categories & Rules: the 😀 button sets the icon of the selected category or
  sub-category (a grid of icons, or type any one emoji; No Icon takes it off).
- ✨ Suggest Icons… (at the bottom of Manage) suggests icons for the categories with none,
  from their names, and for sub-categories only where a different icon fits better than
  their category's. Untick a line or change its icon, then Save.
- Merging two categories or sub-categories keeps an icon.
- The database layout is now 6 (adds the icons): an older Daftarche can't open it.

## 0.21.0 — 2026-10-19

- Loans: money lent to or borrowed from a person is a Transfer › Loans row with the person as
  merchant, not income or spending. Money that left your account is "Out" (you lent it, or
  paid a loan back); money that came in is "In" (you borrowed it, or were paid back). Loan
  rows are never matched with other transfers and are not in the Unmatched list.
- View → Loans… (⇧⌘L): one line per person with the balance ("You owe $x", "Owes you $x",
  "Settled"), money paid out and received, the starting balance and the last date. Starting
  Balance… is for a loan older than your records; Mark Settled writes off a small leftover
  (no transaction is made; Undo Settled brings it back). Double-click a person to see their
  loan rows in Transactions, with "← Back to Loans".
- Right-click income or expense rows in Transactions → Make It a Loan…: they become loan rows
  for the person you choose, keeping their direction (a refund is money in), so account
  balances do not change. In Edit Transaction, Transfer › Loans shows one account and Money:
  In or Out.
- The Accounts tab shows what you owe and what is owed to you, under the accounts.
- Renaming or merging a merchant carries its loan along. Transfer › Loans can't be renamed
  or deleted. A rule that sets a merchant now sets it on imported transfers too.
- tools/move_loans.py moves old loan categories (Expense › Debt, Income › Personal Loan by
  default) to Transfer › Loans, the sub-category naming the person, with starting balances
  (--i-owed, --they-owed) and --settle. It only shows what would change (on a copy: your file
  is not touched) until --apply, which first backs up the file as it was.
- The database layout is now 5 (adds the loans).

## 0.20.1 — 2026-10-19

- Manage has a Merchants tab: each merchant with the category its rules give, how many
  transactions and rules it has, and Net Spent (expenses minus income; transfers left out).
  Find box at the top; click a header to sort.
- Rename / Merge: renaming to a name already there (any capitals) merges the two, with
  their transactions and rules. Delete takes the merchant off its transactions and rules;
  the transactions stay, and rules that only set that merchant are deleted.
- Set Category… gives a merchant a category for its rules (what new imports get), its
  transactions with no category, or all its transactions. Split transactions are left as
  they are. Only categories of the chosen type are offered. Choosing Uncategorized makes
  its rules set only the merchant; it never takes a category off a transaction.
- Double-click a merchant (or Transactions) to see its transactions in the main window,
  with "← Back to Manage" to return to the Merchants tab.
- Categories & Rules shows a "(merchant only)" line under Income and Expense with the
  rules that set only the merchant. It can't be renamed or deleted, and a rule added
  there needs a merchant.
- Tags: in every tag picker, type a tag that doesn't exist and press Enter (or "＋ Add")
  to add it; it shows ticked with "New" and is created when you Save. The Tags box in
  Edit Transaction takes new tags the same way.

## 0.20.0 — 2026-10-19

- Split a transaction: one bank row in parts, each with its own category, sub-category,
  amount and note (an $80 Amazon order: $50 Household › Cleaning, $30 Personal Care ›
  Hair). Right-click → Split…, the Split… button in Edit Transaction, or double-click the
  Category of a split row. "Left: $0.00" must be reached before OK; Join Again undoes it.
- The table shows "Split (2)" (or the one category the parts share, with "Split (2)" as
  the sub-category); the parts show on hover. Filtering by a category or sub-category
  finds a split row with a part in it.
- Charts, the Dashboard's categories, To review and the details panel count each part in
  its own category (the panel lists the part, with its note). Totals of income and
  expenses are unchanged. Export to Excel writes one line per part ("Split": 1 of 2).
- Giving a split row one category (Edit Merchant / Category) asks first, then joins it;
  double-clicking its Merchant opens the whole Edit window, which keeps the split.
- With a category filter, a split row counts only its parts in that category in the
  summary bar; a category and a sub-category filter must both match the same part.
  Search also looks in the parts' notes and categories.
- A split transaction's amount or type cannot change without its parts (Edit Transaction
  says so), and parts must be in categories of its type.
- Merging, moving or deleting a category or sub-category carries the parts along.
- The database layout is now 4 (adds the parts).

## 0.19.0 — 2026-10-19

- Import several statements at once: choose several QFX files (⌘-click) or drop several on
  the window. Each file's account comes from the file; the list on the left shows each
  one: ✓ ready (with how many are new), ⚠ account to choose (Choose account…), or ✗ left
  out with the reason (not a statement, unreadable, empty). Import New imports every
  ready file at once, all or nothing. A row that is in two files (overlapping statements)
  is imported once.
- After the import: one summary of the balances (the bank's, from each account's newest
  file, against the calculated one), and Match Transfers runs by itself when transfers came
  in, so both sides imported together are paired.
- An unknown account can be a new one: type a name in the account window (a "New" mark
  shows; a name in your Person-Bank-Type style is suggested). Files with the same account
  number are asked about once; Change account… corrects a choice. The new account and the
  account number's link are saved only when you import. For a new account whose balance
  is off, the import offers to add the difference as its starting balance (an External
  Transfer the day before its first transaction in any of its files).
- Charts: double-clicking a line of the details panel shows those transactions for the
  months the panel showed, not for all dates; Back (or ×) puts your own period back, and
  your saved period is not changed by the jump.
- A filter box showing one name with "&" ("Coffee & Snacks") no longer shows it as
  "Coffee _Snacks".

## 0.18.0 — 2026-10-19

- Import is a window now: File → Import Statement… (⌘I) asks for the file straight away, or
  drag a QFX/OFX file onto the main window. After the import, Transactions shows just the
  new rows ("Just imported"); × shows everything again. Four tabs remain.
- To review stays in Transactions: View → To Review (⇧⌘R, or ⌥⌘U), the Review button and
  the Dashboard warning all show the income and expenses with no category, expenses first,
  with the count above the table. Each one you give a category leaves the list.
- "← Back to …": when the Dashboard, Charts (the details panel) or Unmatched Transfers
  send you to Transactions, a bar says where from; ← Back (or ⌘[) returns there.
  Changing the filters yourself, or ×, ends it.
- Charts and the details panel list categories and sub-categories that are negative
  (more money back than spent, e.g. Insurance Claims) as a green "-$…", so the lines add
  up to the total; shares are of what was spent.
- Shortcuts: Go menu ⌘1–⌘4 (Dashboard, Transactions, Charts, Accounts) and ⌘[ (Back);
  ⌘U Check for Updates; ⌘S Back Up; ⇧⌘O Back to My Database; ⌘R Refresh; ⌘N Add
  Transaction; ⌘F Find; ⌘E Export. Restore has none on purpose.
- `tools/list_categories.py` writes negative totals as -$141.85.

## 0.17.1 — 2026-10-19

- File → Open Database… (Ctrl+O) shows another database, a backup say, without changing
  it or yours: a temporary copy of it is opened (an older one is upgraded only in the
  copy), and a bar on top says so. Back to my database (on the bar or in File) returns to
  your own; the copy is dropped. Back Up and Restore are off meanwhile.
- Restore Backup's question says it replaces your data, and points to Open Database… for
  only looking.
- Transactions: the Review button moved to the right end of the period row, so the
  toolbar buttons are not cut on a narrower window.

## 0.17.0 — 2026-10-18

- A Merchant for every transaction: the shop or person (Amazon, Vahid). A new column in
  Transactions and in the Import preview, a field in Edit Transaction, searched like the
  other fields, and written to the Excel export.
- Money back is a negative amount of the same type, in the category it was spent in: a
  refund shows as a green "-$30.00" and is taken off that category's total, so income and
  expenses are no longer both inflated. On import, a credit that only an expense rule knows
  (an Amazon refund) becomes such a refund by itself. Edit Merchant / Category has "Counts
  as" to turn an income into money back of an expense (and back).
- Rules set the merchant too. A rule with no category sets only the merchant: for a shop
  whose purchases go to different categories, or a friend who pays back; those
  transactions wait in "To review" for a category. Leave the category empty to make one.
- Transactions: "To review (N)" lists the income and expenses with no category. A category
  without a sub-category shows "—": nothing is missing.
- When choosing a category, the ones used before for that merchant come first.
- `tools/remap_categories.py` moves existing categories to this way (sub-category names
  become merchants; refunds become negative expenses), from a CSV you check first.
- The database layout is now 3 (adds the merchant): older Daftarche versions will ask to
  be updated before opening it.

## 0.16.0 — 2026-10-18

- Charts: a details panel to the right of the category list shows what is inside the
  category under the mouse: its sub-categories with totals and shares, or, when the
  Category box is set to one category, the transactions of the sub-category. Hovering the
  list covers the whole range; hovering a point, bar or slice on the chart covers that
  month. A click on the chart (or Pin) keeps it while the mouse moves on; Pin again or
  Esc lets go. Double-click a line to see those transactions in the Transactions tab.

## 0.15.2 — 2026-10-18

- The search fields moved into the search box: it reads "Search in Name, Memo +3…", and
  the filter icon at its right end chooses the fields. The 0.15.1 button could cover the
  search box on a narrower window.

## 0.15.1 — 2026-10-18

- The button next to Search showed an empty square on macOS (its 🔍 did not fit). It now
  says what the search looks in ("In: Name, Memo +3"); click it to change that.

## 0.15.0 — 2026-10-18

- Transactions: drag a column's header to move the column; the order is kept. The Columns
  window (☰) shows the columns in order, with ▲ ▼ to move one and Reset for the default
  order with every column shown.
- Copy (Ctrl+C) follows the order on screen. Export to Excel keeps its full layout.
- Columns are saved by name, not position (your saved choices are converted once), so new
  columns can go anywhere: a new table shows Note right after Memorandum.

## 0.14.2 — 2026-10-18

- Update Now right after a release no longer stops with "The update did not finish":
  while PyPI is still publishing the new version, the update tries again every 30 s, up
  to 5 times (sciwidgets 0.11.3).

## 0.14.1 — 2026-10-18

- Names with "&" ("Food & Drink") showed as "Food _Drink" in the Charts category list,
  the Accounts list and the tag pickers: Qt reads "&" in a checkbox label as a keyboard
  shortcut marker. They show as written now.

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
