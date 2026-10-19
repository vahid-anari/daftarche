"""File → Open Database…: look at another database through a copy; neither file changes."""

import hashlib
import sqlite3
from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def old_backup(tmp_path):
    """A backup as 0.16 wrote it (layout 2, no merchant), with one transaction."""
    from daftarche.db import Database
    path = tmp_path / "daftarche-before-remap.db"
    db = Database(path)
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "May", 1, "Expense", "Card", 12, us, uc, name="OLD SHOP")
    db.conn.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP VIEW tx_lines")
    conn.execute("DROP INDEX idx_tx_merchant")
    conn.execute("ALTER TABLE transactions DROP COLUMN merchant")
    conn.execute("ALTER TABLE import_mappings DROP COLUMN merchant")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()
    return path


def test_the_copy_is_upgraded_not_the_file(tmp_path):
    from daftarche.backup import copy_for_viewing
    from daftarche.db import Database
    path = old_backup(tmp_path)
    before = digest(path)
    copy = copy_for_viewing(path)
    db = Database(copy)
    assert [r["name"] for r in db.get_transactions()] == ["OLD SHOP"]
    db.conn.close()
    assert digest(path) == before and copy.parent != path.parent


def test_open_and_back(qapp, tmp_path, monkeypatch):
    from daftarche import window as W
    from daftarche.db import Database
    mine = tmp_path / "mine.db"
    db = Database(mine)
    uc, us = db.get_uncategorized_ids()
    db.add_transaction(2026, "June", 1, "Expense", "Card", 5, us, uc, name="MY SHOP")
    db.conn.close()
    monkeypatch.setattr(W, "DB_PATH", mine)
    with mock.patch.object(W, "startup_backup"):
        w = keep(W.MainWindow())
    backup = old_backup(tmp_path)
    before = digest(backup)
    assert w.view_bar.isHidden() and not w.back_action.isEnabled()

    with mock.patch.object(W.QFileDialog, "getOpenFileName", return_value=(str(backup), "")):
        w.open_database()
    assert not w.view_bar.isHidden() and "daftarche-before-remap.db" in w.windowTitle()
    assert not w.restore_action.isEnabled() and not w.backup_action.isEnabled()
    assert [r["name"] for r in w.db.get_transactions()] == ["OLD SHOP"]
    w.db.update_transaction(w.db.get_transactions()[0]["id"], note="tried something")  # goes to the copy
    copy_folder = w._view_copy.parent

    w.back_to_my_database()
    assert w.view_bar.isHidden() and w.windowTitle() == W.APP_NAME and w.restore_action.isEnabled()
    assert [r["name"] for r in w.db.get_transactions()] == ["MY SHOP"]
    assert not copy_folder.exists()
    assert digest(backup) == before  # byte for byte (your own file is only reopened)
    assert w.db.get_transactions()[0]["note"] is None


def test_a_file_that_is_not_a_database_is_refused(qapp, tmp_path, monkeypatch):
    from daftarche import window as W
    monkeypatch.setattr(W, "DB_PATH", tmp_path / "mine.db")
    with mock.patch.object(W, "startup_backup"):
        w = keep(W.MainWindow())
    junk = tmp_path / "notes.db"
    junk.write_text("hello")
    with mock.patch.object(W.QFileDialog, "getOpenFileName", return_value=(str(junk), "")), \
            mock.patch.object(W.QMessageBox, "critical") as critical:
        w.open_database()
    assert critical.called and w.viewing is None and w.view_bar.isHidden()
