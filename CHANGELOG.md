# Changelog

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
