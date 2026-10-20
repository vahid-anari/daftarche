# Daftarche

[![tests](https://github.com/vahid-anari/daftarche/actions/workflows/tests.yml/badge.svg)](https://github.com/vahid-anari/daftarche/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/daftarche)](https://pypi.org/project/daftarche/)
[![Python](https://img.shields.io/pypi/pyversions/daftarche?v=1)](https://pypi.org/project/daftarche/)
![License](https://img.shields.io/badge/license-MIT-green)

**Daftarche** (دفترچه, "little account book") is a desktop app for personal
bookkeeping. It imports bank statements in QFX/OFX format, sorts every
transaction into income, expense or transfer with categories, sub-categories
and tags, matches transfers between your own accounts, and shows where the money
went: a dashboard, monthly charts, account balances over time and a searchable
transaction table that exports to Excel.

Everything stays on your computer, in one SQLite file. Statements have been
tested with CIBC's QFX downloads; other banks' QFX/OFX files use the same format.

<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/dashboard.png" width="700" alt="Daftarche dashboard: account balances, income and expense per month, expenses by category">

The screenshots show invented data (`tools/make_demo_db.py`).

## Installation

Python 3.10 or newer. With [pipx](https://pipx.pypa.io/) (its own environment, recommended):

```
pipx install daftarche
```

or with pip, in an environment of your choice:

```
pip install daftarche
```

To start it with a double-click, run once:

```
daftarche install-app
```

This adds Daftarche to your Applications folder (macOS), the Start menu
(Windows) or the applications menu (Linux), with its own icon. It starts the
daftarche of the Python you ran the command with, and keeps working after updates.

To update, use Help → Check for Updates… (⌘U) in the app (it also checks quietly at
start-up) or `daftarche update` in a terminal.

For development, install from a clone: `git clone https://github.com/vahid-anari/daftarche.git`,
then `pip install -e ".[dev]"` in the folder; such a copy is updated with `git pull`.

## Use

```
daftarche                     open the app
daftarche update              update from PyPI (asks first; --check only looks)
daftarche install-app         add the app to Applications / Start menu (--remove to undo)
daftarche --version
```

File → Import Statement… (⌘I, or drag the file onto the window) reads a QFX
statement downloaded from your bank's website; the account is recognised from the
file, transactions already imported are skipped, and saved rules fill in the
merchant and category. Edit what is left in the preview, then Import New; the
new rows then show in Transactions, and those still without a category wait in
To review (⇧⌘R). Match Transfers in the Transactions tab pairs the two sides of
a transfer between your accounts. Edit → Manage… (⇧⌘M) edits the types, accounts,
categories and tags; Edit → Settings… (⌘,) changes the font, colours and theme.
View → To Review (⇧⌘R) and View → Unmatched Transfers… (⇧⌘U) show what is
still left to sort, all time; double-click a line to see those transactions.

<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/transactions.png" width="700" alt="Transactions tab: filters by date, type, account, category and tags, and the transaction table with totals">

Charts shows each month by category (lines or bars); hover a category to see its
sub-categories, click to keep them.

<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/charts.png" width="700" alt="Charts tab: monthly expenses by category as stacked bars, with the sub-categories of Groceries">

Accounts shows each account's balance (or income, expense, transfers) month by month.

<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/accounts.png" width="700" alt="Accounts tab: balance of each account by month, as a chart and a table">

## User Guide

Help → User Guide (⌘?) opens the guide in the app: getting started, importing statements,
sorting, the four tabs, transfers, loans and splits, settings, backups, and the shortcuts. Its
sources are in `docs/` (`user_guide.tex` with its own style, `guide.sty`); `sh tools/build_docs.sh`
builds it with XeLaTeX into `src/daftarche/data/user_guide.pdf`.

## Your data

Nothing personal is stored in the program folder or in this repository. The app
keeps its files in one folder:

```
~/Library/Application Support/Daftarche/      (macOS)
    daftarche.db                     all transactions, accounts, categories
    config.json                      theme and view settings
    backups/daftarche-last.db        written at every start
    backups/daftarche-YYYY-MM.db     first start of each month; the last 12 are kept
```

On Windows the folder is `%APPDATA%\Daftarche`, on Linux `~/.local/share/daftarche`.
Set `DAFTARCHE_HOME` to use another folder, for example a test copy.
File → Back Up Database… and Restore Backup… save and load a copy of the database by hand;
File → Open Database… shows a backup (through a copy) without changing anything.
The monthly snapshots sit on the same disk as the database; Settings → Extra
backup folder also copies them to a folder of your choice (iCloud Drive, an
external disk), and Time Machine covers the data folder too. Help → Show Data
Folder opens it.

## Development

```
pip install -e ".[dev]"
pytest
```

The tests use only invented data (`tests/data/sample.qfx`) and a temporary data
folder. `python tools/make_icon.py` redraws the icon and the splash image.
`python tools/make_demo_db.py` makes a demo database with a year of invented transactions in
its own folder (default `~/Desktop/daftarche-demo`), for screenshots or trying the app without
your own data: `DAFTARCHE_HOME=~/Desktop/daftarche-demo daftarche`.

Two one-off tools fill in notes for past online purchases: `python tools/export_shop_charges.py`
writes the Amazon and AliExpress transactions (only those, and only the columns needed) to
`shop_charges.csv`; `python tools/import_notes.py notes.csv` shows the notes and categories a
filled-in copy would write, and `--apply` writes them after backing up the database.
`python tools/list_categories.py` prints every category and sub-category with its number of
transactions and rules (`--totals` adds amounts). `python tools/remap_categories.py export`
writes one line per sub-category to `mapping.csv`, to say where each goes (merchant, new
category, money back); `apply mapping.csv` shows the moves and `--apply` makes them after
backing up the database.
Pushing a tag `vX.Y.Z` publishes a GitHub Release with that version's section of
[`CHANGELOG.md`](CHANGELOG.md); `python -m build && twine upload dist/*` puts it on PyPI.

## License

MIT License. See [LICENSE](LICENSE).

## Author

Vahid Anari ·
[GitHub](https://github.com/vahid-anari) ·
[LinkedIn](https://www.linkedin.com/in/vahid-anari/)

Built with [sciwidgets](https://github.com/vahid-anari/sciwidgets), the widget package shared with
the author's scientific apps.
