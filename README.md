# Finance Manager

Personal finance desktop app — PySide6 + SQLite. Imports CIBC QFX/OFX statements
(and historical Excel files), tracks income, expenses and transfers across
accounts, with dashboards, charts, categories, tags and transfer matching.

## Install

```zsh
pip install -e .
finance                 # run
finance install-app     # add to Applications / Dock
```

## Data

Nothing personal lives in this repository. The app keeps its files in

```
~/Library/Application Support/Finance/
    finance.db                  the database
    config.json                 theme and view settings
    backups/finance_backup.db   written automatically at every start
```

Set `FINANCE_HOME=/some/folder` to use another location (e.g. a test copy).
Backup / Restore in the app's top bar save and load a copy of the database.

## Layout

```
src/finance/
    main.py         command-line entry point
    window.py       main window, Settings dialog
    paths.py        data locations
    db.py           SQLite layer (all queries live here)
    style.py        stylesheet + settings
    widgets.py      shared widgets
    chart_utils.py  QChart helpers
    tabs/           dashboard, transactions, charts, accounts, import, manage
tools/make_icon.py  draws data/icons/app_icon.png
```

## Development

```zsh
pip install -e ".[dev]"
pytest
ruff check src
```
