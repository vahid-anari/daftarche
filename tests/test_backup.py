"""Start-up backups: the last session and one snapshot per month, the newest KEEP_MONTHS kept."""

import sqlite3
from datetime import date

import pytest

from daftarche import backup


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(backup, "LAST_BACKUP", tmp_path / "daftarche-last.db")
    return tmp_path


@pytest.fixture
def conn(tmp_path):
    connection = sqlite3.connect(tmp_path / "live.db")
    connection.execute("CREATE TABLE t (x)")
    connection.execute("INSERT INTO t VALUES (42)")
    connection.commit()
    yield connection
    connection.close()


def names(written):
    """The files written in backups/ and backups/monthly (sessions and days: tested below)."""
    return [p.name for p in written if p.parent.name not in ("sessions", "daily")]


def monthly(folder):
    where = folder / "monthly" if (folder / "monthly").is_dir() else folder  # an extra folder: flat
    return sorted(p.name for p in where.glob(backup.MONTHLY_GLOB))


def test_first_start_of_month(folder, conn):
    written = backup.startup_backup(conn, date(2026, 10, 17))
    assert names(written) == ["daftarche-last.db", "daftarche-2026-10.db"]
    copy = sqlite3.connect(folder / "monthly" / "daftarche-2026-10.db")
    assert copy.execute("SELECT x FROM t").fetchone() == (42,)
    copy.close()


def test_monthly_snapshot_never_overwritten(folder, conn):
    backup.startup_backup(conn, date(2026, 10, 1))
    conn.execute("UPDATE t SET x = 0")
    conn.commit()
    written = backup.startup_backup(conn, date(2026, 10, 20))
    assert names(written) == ["daftarche-last.db"]
    snapshot = sqlite3.connect(folder / "monthly" / "daftarche-2026-10.db")
    assert snapshot.execute("SELECT x FROM t").fetchone() == (42,)
    snapshot.close()


def test_only_newest_months_kept(folder, conn):
    for month in range(1, 13):
        backup.startup_backup(conn, date(2025, month, 3))
    backup.startup_backup(conn, date(2026, 1, 3))
    backup.startup_backup(conn, date(2026, 2, 3))
    kept = monthly(folder)
    assert len(kept) == backup.KEEP_MONTHS
    assert kept[0] == "daftarche-2025-03.db" and kept[-1] == "daftarche-2026-02.db"


def test_other_files_left_alone(folder, conn):
    (folder / "finance_backup.db").write_bytes(b"old")
    (folder / "daftarche-backup.db").write_bytes(b"manual")
    for month in range(1, 13):
        backup.startup_backup(conn, date(2024, month, 1))
        backup.startup_backup(conn, date(2025, month, 1))
    assert (folder / "finance_backup.db").exists()
    assert (folder / "daftarche-backup.db").exists()


def test_extra_folder_gets_the_snapshots(folder, conn, tmp_path_factory):
    extra = tmp_path_factory.mktemp("extra")
    backup.startup_backup(conn, date(2026, 9, 1))
    written = backup.startup_backup(conn, date(2026, 10, 1), extra_dir=extra)
    assert sorted(p.name for p in extra.iterdir()) == ["daftarche-2026-09.db", "daftarche-2026-10.db"]
    assert extra / "daftarche-2026-10.db" in written
    assert names(backup.startup_backup(conn, date(2026, 10, 2), extra_dir=extra)) == ["daftarche-last.db"]


def test_extra_folder_rotates(folder, conn, tmp_path_factory):
    extra = tmp_path_factory.mktemp("extra")
    for month in range(1, 13):
        backup.startup_backup(conn, date(2025, month, 1), extra_dir=extra)
    backup.startup_backup(conn, date(2026, 1, 1), extra_dir=extra)
    assert monthly(extra) == monthly(folder)
    assert len(monthly(extra)) == backup.KEEP_MONTHS


def test_missing_extra_folder_is_skipped(folder, conn, tmp_path):
    written = backup.startup_backup(conn, date(2026, 10, 1), extra_dir=tmp_path / "unplugged-disk")
    assert len(names(written)) == 2
    assert not (tmp_path / "unplugged-disk").exists()
    assert backup.mirror_snapshots("") == []


def test_a_copy_at_each_start_that_changed_something(folder, conn):
    """0.35.1: backups/sessions: a copy at each start that finds the data changed, the newest
    KEEP_SESSIONS kept; starting again with nothing changed adds none (and pushes none out)."""
    from datetime import datetime, timedelta
    start = datetime(2026, 11, 3, 9, 0, 0)
    for i in range(backup.KEEP_SESSIONS + 3):
        conn.execute("UPDATE t SET x = ?", (i,))
        conn.commit()
        written = backup.startup_backup(conn, now=start + timedelta(hours=i))
    kept = backup.session_backups()
    assert len(kept) == backup.KEEP_SESSIONS and kept[0] == written[1]
    assert kept[0].name == "daftarche-2026-11-03-210000.db" and kept[0].parent == folder / "sessions"
    copy = sqlite3.connect(kept[-1])
    assert copy.execute("SELECT x FROM t").fetchone() == (3,)  # the oldest kept: the 4th start
    copy.close()
    for i in range(5):  # restarts with no change: the same copy, nothing pushed out
        again = backup.startup_backup(conn, now=start + timedelta(days=1, minutes=i))
        assert again[1] == kept[0]
    assert backup.session_backups() == kept


def test_one_copy_a_day_kept_apart(folder, conn):
    from datetime import datetime, timedelta
    start = datetime(2026, 11, 1, 9, 0, 0)
    for day in range(backup.KEEP_DAYS + 4):
        for hour in range(3):  # many starts a day, each with a change: the day's first copy stays
            conn.execute("UPDATE t SET x = ?", (day * 10 + hour,))
            conn.commit()
            backup.startup_backup(conn, now=start + timedelta(days=day, hours=hour))
    days = sorted((folder / "daily").glob(backup.DAILY_GLOB))
    assert len(days) == backup.KEEP_DAYS and days[-1].name == "daftarche-2026-11-18.db"
    copy = sqlite3.connect(days[-1])
    assert copy.execute("SELECT x FROM t").fetchone() == (170,)
    copy.close()
    assert not list(folder.glob(backup.DAILY_GLOB))  # none loose in backups/


def test_older_monthly_copies_move_into_their_folder(folder, conn):
    (folder / "daftarche-2026-09.db").write_bytes(b"old month")
    backup.startup_backup(conn, date(2026, 10, 2))
    assert (folder / "monthly" / "daftarche-2026-09.db").read_bytes() == b"old month"
    assert not (folder / "daftarche-2026-09.db").exists()


def test_revert_to_when_opened(qapp, monkeypatch, tmp_path):
    """File › Revert to When Opened asks first; then the data is this start's copy again."""
    from unittest import mock

    from PySide6.QtWidgets import QMessageBox

    from daftarche import window as window_module
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup, "LAST_BACKUP", tmp_path / "backups" / "daftarche-last.db")
    monkeypatch.setattr(window_module, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(window_module, "DB_PATH", tmp_path / "w.db")
    w = window_module.MainWindow()
    assert w.revert_action.isEnabled() and w._opened_copy.parent.name == "sessions"
    w.db.get_or_create_account("Card")
    w.db.conn.commit()
    with mock.patch.object(window_module.QMessageBox, "question", return_value=QMessageBox.No):
        w._revert_to_opened()
    assert w.db.get_account_by_name("Card")  # No: nothing changed
    with mock.patch.object(window_module.QMessageBox, "question", return_value=QMessageBox.Yes), \
            mock.patch.object(window_module.QMessageBox, "information"):
        w._revert_to_opened()
    assert not w.db.get_account_by_name("Card")
    assert list((tmp_path / "backups").glob("daftarche-before-restore-*.db"))  # what was there, kept
    w.close()


def test_a_damaged_copy_or_a_clock_set_back_loses_nothing(folder, conn):
    """A broken newest copy (a full disk) does not stop the backups; a clock set back keeps the new
    copy; two starts in one second make two copies."""
    from datetime import datetime, timedelta
    start = datetime(2027, 1, 1, 9, 0, 0)
    for i in range(backup.KEEP_SESSIONS):
        conn.execute("UPDATE t SET x = ?", (i,))
        conn.commit()
        backup.startup_backup(conn, now=start + timedelta(hours=i))
    backup.session_backups()[0].write_bytes(b"SQLite format 3\x00broken")
    written = backup.startup_backup(conn, now=datetime(2027, 1, 2, 9, 0, 0))  # same data, but unreadable copy
    assert written[1].name == "daftarche-2027-01-02-090000.db"
    assert (folder / "daily" / "daftarche-2027-01-02.db").exists()
    conn.execute("UPDATE t SET x = 99")
    conn.commit()
    back = backup.startup_backup(conn, now=datetime(2026, 11, 3, 9, 0, 0))  # the clock set back
    assert back[1].exists() and back[1] in backup.session_backups()
    assert len(backup.session_backups()) == backup.KEEP_SESSIONS
    conn.execute("UPDATE t SET x = 100")
    conn.commit()
    twice = backup.startup_backup(conn, now=datetime(2026, 11, 3, 9, 0, 0))
    assert twice[1].name == "daftarche-2026-11-03-090001.db" and twice[1].exists()  # not over the other
    assert not list(folder.rglob("*.part"))
