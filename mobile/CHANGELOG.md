# Changelog of Daftarche on the phone

Released with tags `phone-vX.Y.Z`; each release carries the signed APK.

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
