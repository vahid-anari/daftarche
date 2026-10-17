"""Automatic backups of the database, made at every start.

    backups/daftarche-last.db      overwritten at every start (undo the last session)
    backups/daftarche-2026-10.db   first start of each month; never overwritten

Only the newest KEEP_MONTHS monthly snapshots are kept. Copies are made with
SQLite's backup API, so they are consistent even while the database is open.

An extra folder (Settings → Extra backup folder, e.g. on iCloud Drive or an
external disk) gets a copy of the monthly snapshots too, with the same rotation;
when the folder is not there (a disconnected disk), it is skipped.
"""

import shutil
import sqlite3
from datetime import date
from pathlib import Path

from daftarche.paths import BACKUP_DIR

KEEP_MONTHS = 12
LAST_BACKUP = BACKUP_DIR / "daftarche-last.db"
MONTHLY_GLOB = "daftarche-????-??.db"


def copy_db(conn: sqlite3.Connection, destination: Path | str) -> None:
    """Write a consistent copy of the open database to ``destination``."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination) as target:
        conn.backup(target)
    target.close()


def _rotate(folder: Path) -> None:
    for old in sorted(folder.glob(MONTHLY_GLOB))[:-KEEP_MONTHS]:
        old.unlink()


def mirror_snapshots(extra_dir: Path | str | None) -> list[Path]:
    """Copy the monthly snapshots missing from ``extra_dir`` there; returns the files copied."""
    if not extra_dir:
        return []
    extra_dir = Path(extra_dir).expanduser()
    if not extra_dir.is_dir():
        return []
    copied = []
    for snapshot in sorted(BACKUP_DIR.glob(MONTHLY_GLOB))[-KEEP_MONTHS:]:
        target = extra_dir / snapshot.name
        if not target.exists():
            shutil.copy2(snapshot, target)
            copied.append(target)
    _rotate(extra_dir)
    return copied


def startup_backup(conn: sqlite3.Connection, today: date | None = None,
                   extra_dir: Path | str | None = None) -> list[Path]:
    """The backups made at start-up; returns the files written."""
    today = today or date.today()
    written = [LAST_BACKUP]
    copy_db(conn, LAST_BACKUP)
    monthly = BACKUP_DIR / f"daftarche-{today:%Y-%m}.db"
    if not monthly.exists():
        copy_db(conn, monthly)
        written.append(monthly)
    _rotate(BACKUP_DIR)
    try:
        written += mirror_snapshots(extra_dir)
    except OSError as exc:
        print(f"Extra backup to {extra_dir} failed: {exc}")
    return written
