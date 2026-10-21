# Changelog of Daftarche on the phone

Released with tags `phone-vX.Y.Z`; each release carries the signed APK.

## 0.2.5 — 2026-10-21

- Transactions → Show only has a Merchant box (type in it to narrow the list), with
  "(no merchant)" for the transactions without one.
- In the list of transactions the account has a line of its own under the category, so its
  name is no longer cut off.

## 0.2.4 — 2026-10-21

- The row of periods no longer slides back to the start when you tap one at its end.

## 0.2.3 — 2026-10-21

- After an update, Open in the installer no longer starts a second Daftarche beside the old
  one: the app keeps a single window. (The update to this version may still show two once;
  from then on, one.)

## 0.2.2 — 2026-10-21

- Home, This Month and Last Month: a donut of the month's spending by category, as in Charts
  (in the same colours as Expenses by Category below it), instead of the last six months' bars.
- Choosing a period, a filter, a category or a month no longer jumps back to the top of the
  tab: it stays where you were.

## 0.2.1 — 2026-10-21

- Charts follows the period: for one month (This Month, Last Month) a donut shows how it
  divides between categories, with the month's total in the middle; for several months,
  the stacked bars as before.
- Tap a month's bar to see that month's categories below (the other months dim); tap it
  again, or the month's ✕, for the whole period. Show transactions from there shows that
  month, and Back returns to it.
- With a few months the bars share the card's width, wider and easier to tap, instead of
  sitting at the left; with many, they scroll sideways and open at the newest month. The
  Dashboard's Income vs Expense bars too.

## 0.2.0 — 2026-10-21

- Android's Back goes back one step instead of leaving the app: it closes an open sheet,
  returns from Show transactions (or an account's transactions) to where you were, as you
  left it, goes to the Dashboard from another tab, and on the Dashboard says "Press Back
  again to exit" first.
- Swipe left or right to change tabs; the tab bar follows.
- Sheets (filters, a transaction's details, Settings) no longer slip under Android's Back /
  Home buttons: their buttons stay above them.
- Android's own bars take the app's colours: the button strip like the tab bar, the status
  bar like the page, with symbols that stay readable in the light theme.

## 0.1.1 — 2026-10-20

- Daftarche's own icon (the rising green bars) and start-up screen, instead of Flet's.
- A much smaller download: the APK is built for 64-bit ARM phones only (nearly every
  Android phone of the last years), not for every kind of processor.

## 0.1.0 — 2026-10-20

- The first version: Dashboard, Transactions, Charts and Accounts (with loans) from the
  phone snapshot of Daftarche 0.26 or later, in Daftarche's dark and light colours.
- Reads the folder Syncthing keeps (Android's "All files access", asked for once), and
  reads it again each time you come back to the app.
- Looks for a newer version once a day and offers to download it.
