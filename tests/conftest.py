"""Every test runs against a throw-away data folder, never the real one."""

import os
import tempfile

os.environ["DAFTARCHE_HOME"] = tempfile.mkdtemp(prefix="daftarche-test-")

import pytest  # noqa: E402

from daftarche.db import Database  # noqa: E402


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.conn.close()


def answer_import(message_box):
    """For a mocked QMessageBox: the "N transactions have no category" question is answered Import."""
    box = message_box.return_value
    box.clickedButton.return_value = box.addButton.return_value
    return message_box
