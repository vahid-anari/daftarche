# Daftarche

*Daftarche* (دفترچه, "little account book") is a personal bookkeeping desktop app —
PySide6 + SQLite. It imports CIBC QFX/OFX statements (and historical Excel files),
tracks income, expenses and transfers across accounts, with dashboards, charts,
categories, tags and transfer matching.

## Install

```zsh
pip install -e .
daftarche               # run
daftarche install-app   # add to Applications / Dock
daftarche update        # update from PyPI (asks first)
```

## Data

Nothing personal lives in this repository. The app keeps its files in

```
~/Library/Application Support/Daftarche/
    daftarche.db                     the database
    config.json                      theme and view settings
    backups/daftarche-last.db        written at every start
    backups/daftarche-YYYY-MM.db     first start of each month; the last 12 are kept
```

Set `DAFTARCHE_HOME=/some/folder` to use another location (e.g. a test copy).
Backup / Restore in the app's top bar save and load a copy of the database.

## Layout

```
src/daftarche/
    main.py         command-line entry point
    window.py       main window, Settings dialog
    paths.py        data locations
    backup.py       automatic backups
    db.py           SQLite layer (all queries live here)
    style.py        stylesheet + settings
    widgets.py      shared widgets
    chart_utils.py  QChart helpers
    tabs/           dashboard, transactions, charts, accounts, import, manage
tools/make_icon.py  draws data/icons/app_icon.png and splash.png
tests/              pytest suite (synthetic data only)
```

## Development

```zsh
pip install -e ".[dev]"
pytest
```

## Release

1. Bump `version` in `pyproject.toml` and add a `## X.Y.Z — date` section to `CHANGELOG.md`.
2. Commit, then `git tag vX.Y.Z && git push --tags` — the release workflow publishes
   the GitHub Release with that changelog section.
3. `python -m build && twine upload dist/*` — PyPI.

## License

MIT
