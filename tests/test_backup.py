"""Start-up backups: the last session and one snapshot per month, the newest KEEP_MONTHS kept."""

import sqlite3
from datetime import date

import pytest

from daftarche import backup


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


def monthly(folder):
    return sorted(p.name for p in folder.glob(backup.MONTHLY_GLOB))


def test_first_start_of_month(folder, conn):
    written = backup.startup_backup(conn, date(2026, 10, 17))
    assert [p.name for p in written] == ["daftarche-last.db", "daftarche-2026-10.db"]
    copy = sqlite3.connect(folder / "daftarche-2026-10.db")
    assert copy.execute("SELECT x FROM t").fetchone() == (42,)
    copy.close()


def test_monthly_snapshot_never_overwritten(folder, conn):
    backup.startup_backup(conn, date(2026, 10, 1))
    conn.execute("UPDATE t SET x = 0")
    conn.commit()
    written = backup.startup_backup(conn, date(2026, 10, 20))
    assert [p.name for p in written] == ["daftarche-last.db"]
    snapshot = sqlite3.connect(folder / "daftarche-2026-10.db")
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
    assert backup.startup_backup(conn, date(2026, 10, 2), extra_dir=extra) == [backup.LAST_BACKUP]


def test_extra_folder_rotates(folder, conn, tmp_path_factory):
    extra = tmp_path_factory.mktemp("extra")
    for month in range(1, 13):
        backup.startup_backup(conn, date(2025, month, 1), extra_dir=extra)
    backup.startup_backup(conn, date(2026, 1, 1), extra_dir=extra)
    assert monthly(extra) == monthly(folder)
    assert len(monthly(extra)) == backup.KEEP_MONTHS


def test_missing_extra_folder_is_skipped(folder, conn, tmp_path):
    written = backup.startup_backup(conn, date(2026, 10, 1), extra_dir=tmp_path / "unplugged-disk")
    assert len(written) == 2
    assert not (tmp_path / "unplugged-disk").exists()
    assert backup.mirror_snapshots("") == []
