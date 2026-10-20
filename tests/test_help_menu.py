"""0.24: the Help menu shared with the other apps (sciwidgets.app.help), and Manage… off ⌘M."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch, tmp_path):
    from daftarche import window as W
    monkeypatch.setattr(W, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(W, "startup_backup"):
        return keep(W.MainWindow())


def test_help_menu_is_the_shared_one(win):
    actions = [a for a in win.help_menu.actions() if not a.isSeparator()]
    assert [a.text() for a in actions] == ["User Guide", "Check for Updates…", "About Daftarche"]
    assert actions[1].shortcut().toString() == "Ctrl+U"
    assert "Built with" in win.help.about_html() and "PySide6" in win.help.about_html()


def test_user_guide_is_shipped():
    from daftarche.app_info import USER_GUIDE
    assert USER_GUIDE.name == "user_guide.pdf" and USER_GUIDE.parent.name == "data"
    assert USER_GUIDE.is_file(), "build it with sh tools/build_docs.sh"


def test_manage_is_not_on_the_minimise_key(win):
    shortcuts = {a.text(): a.shortcut().toString() for menu in win.menuBar().findChildren(type(win.help_menu))
                 for a in menu.actions()}
    assert shortcuts["Manage…"] == "Ctrl+Shift+M"
    assert "Ctrl+M" not in shortcuts.values()
