"""Every test runs against a throw-away data folder, never the real one."""

import gc
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


_kept = []


def keep(widget):
    """Hold a window a test made until the test ends, then delete it through Qt's event loop
    (as the app does): dropped by Python at a random moment, a window can crash PySide."""
    _kept.append(widget)
    return widget


@pytest.fixture(autouse=True)
def _delete_kept_windows():
    yield
    _delete_kept()
    # Python's cycle collector runs in whichever thread happens to allocate: left for later, a
    # window's wrapper from this test could be freed in the sign-in server's thread of a later
    # one (test_phone_link), which crashed Qt now and then. Collected here, on the main thread;
    # what is still alive then is set aside (gc.freeze), so the next collections stay quick.
    gc.collect()
    gc.freeze()


def _delete_kept():
    if _kept:
        from PySide6.QtCore import QCoreApplication, QEvent
        for widget in _kept:
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:  # already deleted (e.g. WA_DeleteOnClose)
                pass
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        _kept.clear()


@pytest.fixture(autouse=True, scope="session")
def _tidy_qt_at_the_end():
    """After the last test, delete the windows still open (dialogs a test made inside a tab,
    combo popups) while Python is still whole: left to PySide's own clean-up at exit, one of
    them now and then crashed the interpreter after every test had passed."""
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    import gc
    gc.collect()
