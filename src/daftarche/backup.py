"""Automatic backups of the database, made at every start, each kind in its own folder:

    backups/daftarche-last.db                          overwritten at every start
    backups/sessions/daftarche-2026-11-03-221500.db    a start that found the data changed since
                                                       the last such copy; the newest KEEP_SESSIONS kept
    backups/daily/daftarche-2026-11-03.db              first start of each day; the newest KEEP_DAYS
    backups/monthly/daftarche-2026-10.db               first start of each month; the newest KEEP_MONTHS

Starting again without changing anything (a test, a restart after an update) adds no session
copy, so it pushes no older one out. Copies are made with SQLite's backup API, so they are
consistent even while the database is open. Monthly copies of older versions, in backups/
itself, are moved into backups/monthly/.

An extra folder (Settings → Extra backup folder, e.g. on iCloud Drive or an external disk)
gets a copy of the monthly snapshots too, with the same rotation; when the folder is not there
(a disconnected disk), it is skipped.
"""

import hashlib
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from daftarche.db import SCHEMA_VERSION
from daftarche.paths import BACKUP_DIR

KEEP_MONTHS = 12
KEEP_DAYS = 14
KEEP_SESSIONS = 10  # the data as it was at the last starts that found it changed
LAST_BACKUP = BACKUP_DIR / "daftarche-last.db"
MONTHLY_GLOB = "daftarche-????-??.db"
DAILY_GLOB = "daftarche-????-??-??.db"
SESSION_GLOB = "daftarche-????-??-??-??????.db"


def folder(kind: str) -> Path:
    """backups/sessions, backups/daily or backups/monthly."""
    return BACKUP_DIR / kind


def copy_db(conn: sqlite3.Connection, destination: Path | str) -> None:
    """Write a consistent copy of the open database to ``destination``."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination) as target:
        conn.backup(target)
    target.close()


def _copy_file(source: Path, target: Path) -> None:
    """Copy under a temporary name, then rename: a full disk or a quit half way never leaves a
    broken file under the real name (which would never be replaced)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        shutil.copyfile(source, part)
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)


def _keep_newest(where: Path, pattern: str, keep: int, made: Path | None = None) -> None:
    """The newest ``keep`` by name (a date); ``made``, just written, is kept whatever its name
    (a clock set back would make it the "oldest")."""
    files = [f for f in sorted(where.glob(pattern)) if f != made]
    for old in files[:max(0, len(files) - (keep - (made is not None)))]:
        old.unlink()


def _rotate(where: Path) -> None:
    _keep_newest(where, MONTHLY_GLOB, KEEP_MONTHS)


def _digest(path: Path) -> str | None:
    """The data in a copy (not its bytes: SQLite's header changes at every open); None when it
    cannot be read (a damaged copy: a new one is made)."""
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            h = hashlib.sha256()
            for line in conn.iterdump():
                h.update(line.encode())
            return h.hexdigest()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return None


def session_backups() -> list[Path]:
    """The copies made at the last starts, newest first."""
    return sorted(folder("sessions").glob(SESSION_GLOB), reverse=True)


def _move_old_monthly() -> None:
    """Monthly copies of versions before 0.35.1 were in backups/ itself."""
    for old in BACKUP_DIR.glob(MONTHLY_GLOB):
        target = folder("monthly") / old.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.move(str(old), target)


def mirror_snapshots(extra_dir: Path | str | None) -> list[Path]:
    """Copy the monthly snapshots missing from ``extra_dir`` there; returns the files copied."""
    if not extra_dir:
        return []
    extra_dir = Path(extra_dir).expanduser()
    if not extra_dir.is_dir():
        return []
    copied = []
    for snapshot in sorted(folder("monthly").glob(MONTHLY_GLOB))[-KEEP_MONTHS:]:
        target = extra_dir / snapshot.name
        if not target.exists():
            _copy_file(snapshot, target)
            copied.append(target)
    _rotate(extra_dir)
    return copied


def startup_backup(conn: sqlite3.Connection, today: date | None = None,
                   extra_dir: Path | str | None = None, now: datetime | None = None) -> list[Path]:
    """The backups made at start-up; returns the files written, the second one always this
    start's session copy (a new one, or the newest when nothing changed since: the same data),
    for File › Revert to When Opened."""
    now = now or datetime.now()
    today = today or now.date()
    copy_db(conn, LAST_BACKUP)
    written = [LAST_BACKUP]
    sessions = session_backups()
    newest = _digest(sessions[0]) if sessions else None
    if newest is not None and newest == _digest(LAST_BACKUP):
        written.append(sessions[0])  # nothing changed: no new copy, none pushed out
    else:
        session = folder("sessions") / f"daftarche-{now:%Y-%m-%d-%H%M%S}.db"
        while session.exists():  # two starts in one second: the next free one
            now += timedelta(seconds=1)
            session = folder("sessions") / f"daftarche-{now:%Y-%m-%d-%H%M%S}.db"
        _copy_file(LAST_BACKUP, session)
        written.append(session)
        _keep_newest(folder("sessions"), SESSION_GLOB, KEEP_SESSIONS, made=session)
    for kind, name, pattern, keep in (("daily", f"daftarche-{today:%Y-%m-%d}.db", DAILY_GLOB, KEEP_DAYS),
                                      ("monthly", f"daftarche-{today:%Y-%m}.db", MONTHLY_GLOB, KEEP_MONTHS)):
        if kind == "monthly":
            _move_old_monthly()
        target = folder(kind) / name
        made = None
        if not target.exists():
            _copy_file(LAST_BACKUP, target)
            written.append(target)
            made = target
        _keep_newest(folder(kind), pattern, keep, made=made)
    try:
        written += mirror_snapshots(extra_dir)
    except OSError as exc:
        print(f"Extra backup to {extra_dir} failed: {exc}")
    return written


REQUIRED_TABLES = {"transactions", "accounts", "types", "categories", "subcategories"}


def check_backup(path: Path | str) -> None:
    """Raise ValueError (with a message for the user) unless ``path`` is a sound Daftarche database."""
    path = Path(path)
    with open(path, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise ValueError(f"{path.name} is not a database file.")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"{path.name} is damaged (integrity check failed).")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError(f"{path.name} is not a Daftarche database (missing: {', '.join(sorted(missing))}).")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError(f"{path.name} was saved by a newer version of Daftarche; update Daftarche first.")
    finally:
        conn.close()


def copy_for_viewing(path: Path | str) -> Path:
    """A copy of the database at ``path`` in a new temporary folder, to open without changing
    ``path`` itself (opening upgrades an older layout, and the copy takes that). The caller
    deletes the folder (``copy.parent``) when done."""
    check_backup(path)
    folder = Path(tempfile.mkdtemp(prefix="daftarche-view-"))
    copy = folder / Path(path).name
    source = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        with sqlite3.connect(copy) as target:
            source.backup(target)
        target.close()
    finally:
        source.close()
    return copy


def restore_backup(conn: sqlite3.Connection, path: Path | str) -> Path:
    """Replace the open database with the backup at ``path``; returns the copy of the data it replaced.

    The backup is checked first, and the current data is saved to
    ``backups/daftarche-before-restore-<time>.db``, so a restore can always be undone.
    """
    check_backup(path)
    safety = BACKUP_DIR / f"daftarche-before-restore-{datetime.now():%Y-%m-%d-%H%M%S}.db"
    copy_db(conn, safety)
    source = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        source.backup(conn)
    finally:
        source.close()
    return safety
