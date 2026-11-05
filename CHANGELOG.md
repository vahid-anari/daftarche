# Changelog

## 0.35.7 — 2026-11-04

- The icon window: a website's icon is got right in it — **Website: … Get** under Logos &
  Pictures (in the background; Get turns into Cancel) — instead of in a second window that had its
  own file button too; Choose a Picture… is the one place for a file.
- A larger icon window shows more icons in a line and more lines in sight (emoji, logos and
  pictures alike), instead of wider gaps between them.

## 0.35.6 — 2026-11-04

- A merchant can be a person: tick **👤 A person, not a shop** in Edit Merchant, and 👤 shows
  beside its name where a logo would be (in Transactions, Merchants and Categories); the 👤 button
  in Merchants shows only people. It follows a rename or a merge. Database layout 9 (a copy of
  the file as it was is kept first; an older Daftarche cannot open it).
- Get Logo works in the background: the window stays alive (Daftarche no longer seems to hang on
  a site that does not answer), the button turns into **Cancel** meanwhile, and a site gets 20
  seconds at most, all told. tools/pick_logos.py has the same limit.
- The icon window (a category's or sub-category's ✏️) has two columns: **Emoji** on the left, and
  on the right **Logos & Pictures**, as tall, with a field to find a merchant's logo by name. A
  picture of its own, no merchant's, can be added there — **Choose a Picture…** (a file) or
  **From a Website…** — and deleted with a right-click (categories that had it then have none).
  The phone shows only emoji. The paste field has the usual font size again (its right-click menu
  too).
- The lists to choose a merchant show its logo (or 👤), as those of categories and sub-categories
  show their icons; the Transactions filters (Category, Sub-Category, Merchant) too.

## 0.35.5 — 2026-11-04

- Manage › Categories: the merchants are listed A to Z (they were by how many transactions); a
  click on a heading sorts by it — Merchant, Tx, R or Total, numbers largest first — and a second
  click the other way round. The choice is kept; the line of those with no merchant stays last.
- Edit Merchant: a logo got after the window opened no longer goes under the buttons (the
  wrapped note above it was counted as one line).

## 0.35.4 — 2026-11-04

- Manage › Categories: a list is never cut any more (its Total hidden past its edge) after
  choosing a type with longer names, or when it is long enough for its scroll bar; and in a short
  window a long list scrolls its own lines (they could be cut off at the bottom).
- The columns of the transactions in Manage have a few pixels to spare, so a date is not cut
  with "…" on a Retina screen.
- **File › Save Checkpoint** (⌘S): the data now, kept among the copies made at each start
  (backups/sessions; none when nothing changed since the newest). The last twenty are kept (ten
  before). **File › Revert to a Save…** (instead of Revert to When Opened) lists them — when, and
  Opened or Saved — the newest chosen; after asking, the data goes back to the one picked, and
  what is there now is kept in a copy first. Back Up Database… is now ⇧⌘S.
- Manage › Categories: right-click a merchant › **Edit Merchant…** — its name and logo, the same
  window as in the Merchants tab; it stays selected under its new name.

## 0.35.3 — 2026-11-04

- The edit window's Account has an empty line, so an income (money that came from outside, such
  as starting money) can be made a transfer from outside: Type Transfer, Account empty, To
  Account the one it came into. An income or expense still needs its account.
- Manage › Categories: in a window narrower than the four lists, their row scrolls sideways as
  one (each list keeps the width of its text and scrolls only up and down), so Manage can be
  made narrower on a laptop.

## 0.35.2 — 2026-11-03

- Manage › Merchants: **Edit Merchant** — a merchant's name and logo in one window (double-click
  its name, the ✏️ button, or right-click › Edit Merchant…), as a category's name and icon are;
  OK keeps both, Cancel neither. A name another merchant has merges the two (after asking); a
  logo chosen there wins over the one of the merchant it is merged into. Rename / Merge… and
  Logo… are no longer separate.
- Get Logo finds sharper logos: also the icons a site's web app manifest names (192 or 512 px
  on most large sites), and the same with "www." when nothing sharp was found.
- `tools/pick_logos.py`: many merchants' logos at once, from a CSV of merchant and website:
  each is got from the shop's site, shown with its size beside the one it has now (one under
  64 px is marked "small" and not ticked by itself), and Apply saves the ticked ones (a copy of
  the database first). "Also try Google's icons" asks Google's icon service for those still
  small or not found — only when ticked, as it sends the site's name to Google.

## 0.35.1 — 2026-11-03

- Manage › Categories: the last line of each type's categories, **(no category)**, holds its
  transactions with no category yet (To review: Uncategorized belongs to no type, so it was in
  no list), with how many and their total; select it to see their merchants and the
  transactions, and give them a category there.
- A category's "Uncategorized" sub-category is shown as **(no sub-category)**, last, and only
  when transactions or rules are in it (an empty one is made again when needed).
- Neither line is renamed, moved or deleted: they say why instead.
- Backups, each kind in its own folder: **backups/sessions** — a copy at each start that finds
  the data changed since the last one, the last ten kept (starting again with nothing changed,
  a test or a restart after an update, adds none and pushes none out); **backups/daily** — the
  first start of each day, the last fourteen; **backups/monthly** — as before, the last twelve
  (older monthly copies are moved in). `daftarche-last.db` stays.
- **File › Revert to When Opened…**: after asking, your data as it was when Daftarche started;
  what is there now is kept in a copy first, as with Restore.

## 0.35.0 — 2026-11-03

- **Balance Check** (View › Balance Check…, or a click on the Dashboard's Total Balance): the
  Total Balance built up again from the transactions, a line at a time — income less expenses
  (the line under Manage › Merchants), transfers with only one of your accounts (from or to
  outside, the starting money among them; Loans; one-sided Internal Transfers), what moved
  between your accounts — with where to compare each, whether the two agree, and each account's
  income, expenses, transfers in and out and balance.
- Manage › Categories: the transactions are under all the lists, across the whole width, with a
  line to drag between them; each list is as wide as its text and scrolls only up and down.
  Type, Category and Sub-Category have a **Total** column (red spent, green money in; "—" for transfers).
- A split transaction seen in one category (a category filter, or Manage) shows its share
  there — "$40.00 of $100.00" — and that part's category and sub-category, instead of the
  whole amount and "Split (2)"; the tooltip lists the parts.
- Manage: the sums under the transactions go on to a second line when the room is narrow, so
  the line between a list and its transactions can be dragged much further; at first a list
  takes at most half the width. The buttons of Accounts and Tags stay at their list's top right
  corner (they went to the far right of the window with Show transactions off).

## 0.34.4 — 2026-11-03

- Manage: when the transactions shown are only loans (Transfer › Loans, or one person's), the line
  under them says what went Out and came In, and what They owe you / You owe, as the Loans window
  counts it (starting balances and Mark Settled included), instead of one Transfer sum that
  added money lent and money paid back together.
- The icon window keeps its emoji in six rows that scroll (the logos in two), so it stays short
  and no longer goes under the Dock; it is never taller than the screen, and the current icon
  is scrolled into sight.

## 0.34.3 — 2026-11-03

- Manage › Merchants: a double-click on a merchant's name opens Rename / Merge, as in Categories
  and Tags; on its numbers (Tx, Total) it shows its transactions in Transactions, as before.

## 0.34.2 — 2026-11-03

- Right-click › **Set Merchant…** (in Transactions and in Manage's transactions): one merchant for
  the selected rows, and nothing else changes — their categories, sub-categories, types and the
  parts of split ones stay as they are, and no rule is made. Rows of different types can be set
  together (transfers too); an empty box takes the merchant off.

## 0.34.1 — 2026-11-03

- The transactions in Manage: each column is as wide as its longest text in any row, so nothing
  far down the list is cut with "…" (the widths came from the first rows only). Showing them is
  also a little quicker.

## 0.34.0 — 2026-11-03

- Merchants' logos: right-click a merchant in Manage › Merchants and choose **Logo…**. Write the
  shop's website and press Get Logo (its app icon, else the icons its page names, else its
  favicon; taken once from the shop's own site, no other service), or choose a picture file; a
  preview shows it on a white square with round corners before OK, and No Logo takes it away.
- The logo shows beside the merchant's name in Manage › Merchants, in the merchants of Categories
  and in the Merchant column of Transactions; a merchant without one keeps an empty space, so
  the names stay in line (when no merchant has a logo, there is no space).
- A category or sub-category can have a merchant's logo as its icon: the icon window has a
  **Logos** row above the emoji.
- Icons and logos beside names grow with the font size (Settings).
- Renaming or merging a merchant takes its logo along (when merged into one that has a logo, that
  one stays); deleting it removes the logo and a category icon that used it.
- Logos are kept in your data (layout 8, a new table) and backed up with it; they are not sent to
  the phone, which shows only emoji. Before the upgrade, a copy is saved in the backups folder
  (`daftarche-before-layout-8.db`); older versions cannot open the updated file.

## 0.33.5 — 2026-11-02

- A sub-category with no icon of its own shows none (it used to show its category's, which is
  beside it already); a name without an icon keeps an empty space, so the names stay in line —
  in Transactions, the lists of Manage and the category boxes.
- Tests: the splash test no longer depends on how fast the machine builds the window.

## 0.33.4 — 2026-11-02

- A rule's transactions: select a rule (or several) and the transactions below are only those it
  recognises and wins now, whatever merchant they have now (the Merchant column shows it). A click
  on the merchant again, or Show All, shows all of them; a rule and a line of Used in narrow them
  one at a time.
- The rules have a **Tx** column (how many transactions each one wins: 0, no use any more?) and a
  line under them compares: how many of the merchant's transactions come from its rules, from no
  rule (set by hand), from another merchant's rule, and how many its rules give another merchant.
- The rules list leaves out Accounts when all of them are for all accounts, and keeps its whole
  width; Used in beside it scrolls when the window is narrow.

## 0.33.3 — 2026-11-02

- Manage › Merchants: a 🚩 column to tick the merchants to look at again while tidying up, and
  untick when done. The 🚩 button beside the search shows only those; a click on the 🚩 header
  puts them first; the line under the list counts them; right-click ticks or unticks one. The
  ticks are kept in the settings (on this computer), not in your data, and follow a merchant
  that is renamed or merged.

## 0.33.2 — 2026-10-27

- Categories and sub-categories: ＋ and ✏️ open one window for the **name and the icon**. The icon
  chosen shows large beside the name; a click in the grid chooses one (OK keeps it), and the one
  that suits the name is offered as you type it. The separate icon button is gone.
- The emoji in that window are drawn whole (they were cut off), and so is one pasted into its
  field. Any other emoji can be **looked for by name** there (car, cake, money…), among the
  1,300 or so Python knows; ⌃⌘Space, which did not reach the window, is no longer mentioned.
- Every list in Manage has a **right-click menu** with the commands of its buttons; on an empty
  part of the list, only adding one. In Categories, a merchant offers its rules or its
  transactions there.
- The buttons of each list are on its **title line**, at the top, so they stay in sight when the
  list is tall; the rules' hint is under the lists.
- Merchants: the list of merchants is as wide as its contents (the longest name, at most 300
  pixels; a longer one ends in "…" and shows whole on hover); a bigger window widens the rules
  and transactions beside it.
- Under the transactions in Categories, Merchants and Tags: one **Total**, as the lists count it
  (spent minus income, transfers left out), instead of a red Expense that ignored money back.
  Accounts keeps Income, Expense and Net.
- Totals are coloured by what they mean, everywhere in Manage: red when money was spent, green
  when more came in (or back), a 0 dim; also in the Total columns and Used in.

## 0.33.1 — 2026-10-27

- When the data was saved by a newer Daftarche (another copy on the Mac was updated first), the
  message now offers **Check for Updates**: the usual update notice, with Update Now and restart,
  instead of only closing.

## 0.33.0 — 2026-10-27

- A rule can be for several accounts: in the rule window (Manage › Merchants) and in the rule rows of
  Edit Merchant / Category, **Accounts** is a box to tick one or several; none ticked is All (also
  accounts added later). The rules list shows All, the account, or "2 accounts" (hold the pointer
  over it for their names). "Matches N" and "Also set … on them" count the ticked accounts.
- When rules match the same words, the one for fewer accounts wins; one for all accounts comes last.
- Deleting an account deletes the rules that were only for it (they used to become rules for all
  accounts); merging accounts moves their rules, and the rule already there wins a tie.
- The database layout changes (7): on the first start, Daftarche saves the file as it was in the
  backups folder (`daftarche-before-layout-7.db`) and then moves each rule's account into the new
  table. Rules that were the same but for their account become one rule, where that cannot change
  which rule an import picks. Older Daftarche versions cannot open the updated file.
- Manage › Merchants: the rules list leaves out Type when all of a merchant's rules have the same one.
- `tools/remap_categories.py` and `tools/compare_rules.py` read the rules' accounts the new way.

## 0.32.0 — 2026-10-27

- A shop where you buy many kinds of things: select its transactions in Transactions and
  right-click. **Use a Category of …** lists the categories its transactions had before (of the
  same type), the most used first, and the last one chosen on top when it is not among the first
  three, each with how many. One click sets it; no rule is made. **Other…** opens Edit Merchant /
  Category.
- Edit Merchant / Category: a **Used before** row with a button for each of those categories;
  one click fills in Category and Sub-Category.
- When the category you give differs from the one the shop's rule gives, Daftarche asks once:
  **Only the Merchant** (the rule sets only the merchant from now on; new ones wait in To
  review), **Not Now** (asks again next time) or **Don't Ask for This Rule**.
- Manage › Merchants: **Used in**, beside the rules, lists the merchant's categories with how many
  and their total; a click shows only those transactions below (Show All: all again).
- The Review button of Transactions no longer shows in Manage's transactions.

## 0.31.3 — 2026-10-26

- The transactions in Manage are the Transactions table itself and work as there: select one row
  or several, right-click to edit their merchant and category (with its rules), split them, make
  them a loan, tag, copy or delete them, double-click a cell to change it, ⌘C, Delete. The lists of
  Manage follow at once. Its sums line shows only the sums that mean something there.
- Tests: what Python's collector frees is freed on the main thread after each test (a rare Qt
  crash on CI), and quickly.

## 0.31.2 — 2026-10-26

- Manage › Accounts and Tags show the selected account's or tag's transactions too, beside the
  list (a tag's with their total). Their lists are only as wide as their text, with the buttons
  under them, as in the other tabs.
- **Show transactions** is beside the tabs, once for all four.
- One way of writing numbers in Manage: short headings (Tx, Cats, Subs, M for merchants, R for
  rules; hold the pointer over one to read it), a 0 written in the dim colour, never a dash, and
  **Total** for the money (in Merchants: spent minus income), also for the transactions with no
  merchant.
- Sub-categories show how many merchants (M) and rules (R) they have.
- Merchants: a line under the list adds up the merchants shown (all, or those you looked for).
- Manage follows the changes made in the main window (an import, a category set in Transactions),
  so the Refresh button is gone. Suggest Icons… is gone too: the icon window offers an icon that
  suits the name when there is none yet.
- The line between a list and its transactions lights up in the accent colour under the pointer
  (and while it is dragged), is easier to grab, and has room above and below it; the hints beside
  and under the lists take only the lines they need, and a split transaction counts once.

## 0.31.1 — 2026-10-26

- The transactions in Manage › Categories and Merchants show the same columns as Transactions,
  in its order (its Columns button), with a scroll bar when they do not fit; a column with one value
  for all of them there is left out.
- The lists above them are only as wide as their text, so the transactions get the rest of a big
  screen; the hints sit beside them. Type, Category and Sub-Category no longer show an empty
  header beside their columns.

## 0.31.0 — 2026-10-26

- Manage › Categories and Manage › Merchants can show the transactions themselves: tick **Show
  transactions** (one setting for both tabs) and the column on the right is in two rows, the
  merchants (or a merchant's rules) above and their transactions below, with a line between them
  to drag. Newest first, sortable, with their number and total (net spent in Merchants); a part
  of a split transaction shows its own amount, marked ✂; the account and the bank's text show on
  hover. In Categories, a click on a merchant shows only its own (Show All: every merchant again).
  Double-click one to open it in Transactions.
- Manage opens at the size and place it was left; the first time transactions are shown, it
  fills the screen.

## 0.30.0 — 2026-10-26

- A rule added or edited in Manage › Merchants can also be set on the transactions you already
  have. Below "Matches N of your transactions", choose: No (only new imports), those missing a
  merchant or category (the default: only what is empty is filled in, nothing set by hand
  changes), or all of them. Split transactions, and those a more specific rule matches, are left
  alone; a rule that only sets the merchant never takes a category off. Saving the rule and
  changing the transactions happen together, and Manage says how many changed.
- Radio buttons drawn in the app's style, and the rule window opens tall enough for its hints.

## 0.29.1 — 2026-10-24

- Built on sciwidgets 0.15.4 (was 0.14.3), the same version as the author's other apps, so they
  can be installed side by side. With it, Check for Updates also works with Python from
  python.org on macOS before its "Install Certificates" step has been run.
- The tests no longer ask Google to forget the sign-in when they sign out (this crashed them on
  Python 3.14).

## 0.29.0 — 2026-10-23

- The whole window follows the theme: in Dark on a Mac set to Light, the title bar, the system's
  dialogs and the parts outside Daftarche's own colours were light; they are now dark too (and
  light in Light). The Help windows (About, updates) follow it as well.
- View → Appearance switches the theme from the menu: Same as System, Light or Dark, the same
  setting as Settings › Theme.
- "Match macOS" is now called "Same as System", as in the author's other apps; a saved choice is
  kept.
- `tools/figures.py` retakes the pictures and the animation of the docs from a new demo database
  (sciwidgets.devtools); the README shows the animation.
- Needs sciwidgets 0.14.3.

## 0.28.1 — 2026-10-21

- Settings is in three tabs, Appearance, Backups and Phone, instead of one tall window, and opens
  on the tab used last. Reset to Defaults shows on Appearance, the only tab it changes; the
  Backups tab says where the automatic backups are kept.

## 0.28.0 — 2026-10-21

- The phone connects through your own Google Drive, paired by a QR code, instead of a
  Syncthing folder. Settings › Phone: **Sign In with Google…** once (Daftarche may only see
  the files it makes itself), then **Connect a Phone…**, name it, and scan the code with the
  phone's camera (or Copy Link and paste it in the phone app). Each phone has its own file,
  locked with its own key before it leaves the Mac; the key is only in the QR code, so
  Google holds nothing it can read.
- Your changes go to the phones by themselves, about a minute after the last one, right
  after an import and when Daftarche closes, and again later if you were offline.
  Settings › Phone lists the phones with when each was last sent, and has Send Now and
  Disconnect (which deletes that phone's copy). A failed send shows in the status bar.
- File › Update Phone Snapshot and the phone folder are gone. New dependency: segno (the
  QR code).

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
