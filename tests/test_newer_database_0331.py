"""0.33.1: a database from a newer Daftarche: the message offers the update check (the window,
which has it, cannot open)."""

from unittest import mock

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class FakeBox:
    """QMessageBox stand-in: remembers its buttons, 'clicks' the one named ``answer``."""
    answer = "Quit"
    Warning = AcceptRole = RejectRole = None

    def __init__(self, *args):
        self.text, self.buttons, self.info = args[2], [], ""

    def setInformativeText(self, text):
        self.info = text

    def addButton(self, text, role):
        self.buttons.append(text)
        return self.buttons[-1]  # the object itself: the app compares with "is"

    def setDefaultButton(self, button):
        self.default = button

    def exec(self):
        FakeBox.shown = self

    def clickedButton(self):
        return next(b for b in self.buttons if b == self.answer)


def run(qapp, answer):
    from daftarche import main
    FakeBox.answer = answer
    app = mock.Mock()  # the QApplication: its event loop is not run here
    with mock.patch("PySide6.QtWidgets.QMessageBox", FakeBox), \
            mock.patch("sciwidgets.app.update_ui.AppUpdates") as updates:
        code = main.offer_update_for_newer_database(app, "This database was saved by a newer version")
    return code, updates, app.exec


def test_quit_does_not_check(qapp):
    code, updates, loop = run(qapp, "Quit")
    assert code == 1 and not updates.called and not loop.called
    assert FakeBox.shown.buttons == ["Check for Updates", "Quit"] and FakeBox.shown.default == "Check for Updates"


def test_check_for_updates_runs_the_apps_own_check(qapp):
    code, updates, loop = run(qapp, "Check for Updates")
    assert code == 1 and loop.called
    updates.return_value.check.assert_called_once_with(manual=True)
    from daftarche.app_info import APP
    assert updates.call_args.args[1] is APP
