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

To update, use Help → Check for Updates… in the app (it also checks quietly at
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

Import → Select QFX File… reads a statement downloaded from your bank's website;
the account is recognised from the file, transactions already imported are
skipped, and saved mappings fill in the categories. Edit what is left in the
preview, then Import New. Transactions → Match Transfers pairs the two sides of
a transfer between your accounts. Edit → Manage… edits the types, accounts,
categories and tags; Edit → Settings… (⌘,) changes the font and colours.
View → Uncategorized… (⌘U) and View → Unmatched Transfers… (⇧⌘U) show what is
still left to sort, all time; double-click a line to see those transactions.

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
File → Back Up Database… and Restore Backup… save and load a copy of the database by hand.
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

Two one-off tools fill in notes for past online purchases: `python tools/export_shop_charges.py`
writes the Amazon and AliExpress transactions (only those, and only the columns needed) to
`shop_charges.csv`; `python tools/import_notes.py notes.csv` shows the notes and categories a
filled-in copy would write, and `--apply` writes them after backing up the database.
`python tools/list_categories.py` prints every category and sub-category with its number of
transactions and rules (`--totals` adds amounts).
Pushing a tag `vX.Y.Z` publishes a GitHub Release with that version's section of
[`CHANGELOG.md`](CHANGELOG.md); `python -m build && twine upload dist/*` puts it on PyPI.

## License

MIT License. See [LICENSE](LICENSE).

## Author

Vahid Anari ·
[GitHub](https://github.com/vahid-anari) ·
[LinkedIn](https://www.linkedin.com/in/vahid-anari/)

Related projects: [linecat](https://github.com/vahid-anari/linecat) ·
[sciwidgets](https://github.com/vahid-anari/sciwidgets) ·
[Maxwell Bloch Studio](https://github.com/vahid-anari/maxwell-bloch-studio)
