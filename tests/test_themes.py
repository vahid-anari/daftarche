"""0.23: Dark, Light and Match macOS themes, each with its own colour changes."""

import json
from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from daftarche import style
    path = tmp_path / "config.json"
    monkeypatch.setattr(style, "CONFIG_PATH", str(path))
    return style.Settings, path


def test_old_colour_changes_become_changes_to_the_dark_theme(settings):
    from daftarche.style import DARK_COLORS, LIGHT_COLORS
    Settings, path = settings
    path.write_text(json.dumps({"accent": "#ff0000", "bg_base": DARK_COLORS["bg_base"], "font_size": 15}))
    s = Settings()
    assert s.theme() == "dark" and s.get("accent") == "#ff0000" and s.get("font_size") == 15
    s.set("theme", "light")
    assert s.get("accent") == LIGHT_COLORS["accent"]  # the light theme has its own
    saved = json.loads(path.read_text())
    assert saved["colors_dark"] == {"accent": "#ff0000"} and "accent" not in saved


def test_a_colour_change_belongs_to_the_theme_on_screen(settings):
    from daftarche.style import DARK_COLORS
    Settings, path = settings
    s = Settings()
    s.set("theme", "light")
    s.set("income", "#00aa00")
    assert s.get("income") == "#00aa00"
    s.set("theme", "dark")
    assert s.get("income") == DARK_COLORS["income"]
    assert Settings().theme_colors("light")["income"] == "#00aa00"  # kept in the file


def test_match_macos_follows_the_system(settings):
    from daftarche.style import DARK_COLORS, LIGHT_COLORS
    Settings, _ = settings
    s = Settings()
    s.set("theme", "system")
    with mock.patch("daftarche.style.system_theme", return_value="light"):
        assert s.active_theme() == "light" and s.get("bg_base") == LIGHT_COLORS["bg_base"]
    with mock.patch("daftarche.style.system_theme", return_value="dark"):
        assert s.get("bg_base") == DARK_COLORS["bg_base"]


def test_settings_window_switches_and_resets_a_theme(qapp, settings):
    from daftarche.style import DARK_COLORS, LIGHT_COLORS
    from daftarche.window import SettingsDialog
    Settings, _ = settings
    s = Settings()
    d = keep(SettingsDialog(s))
    d.f_theme.setCurrentIndex(d.f_theme.findData("light"))
    assert d._colors()["accent"] == LIGHT_COLORS["accent"]
    d._colors()["accent"] = "#123456"  # as the colour picker does
    with mock.patch.object(d, "accept"), mock.patch("daftarche.window.mirror_snapshots"):
        d._save()
    assert s.theme() == "light" and s.get("accent") == "#123456"
    assert s.theme_colors("dark")["accent"] == DARK_COLORS["accent"]
    d = keep(SettingsDialog(s))
    d._reset()  # the light theme's own colours again
    with mock.patch.object(d, "accept"), mock.patch("daftarche.window.mirror_snapshots"):
        d._save()
    assert s.get("accent") == LIGHT_COLORS["accent"]


def test_the_window_follows_the_mac_only_on_match_macos(qapp, settings, tmp_path, monkeypatch):
    from daftarche import window as W
    Settings, _ = settings
    monkeypatch.setattr(W, "DB_PATH", tmp_path / "w.db")
    with mock.patch.object(W, "startup_backup"):
        w = keep(W.MainWindow())
    w.settings = Settings()
    with mock.patch.object(w, "_restyle") as restyle:
        w._system_theme_changed()
        assert not restyle.called  # Dark: stays dark
        w.settings.set("theme", "system")
        w._system_theme_changed()
        assert restyle.called
    w.settings.set("theme", "light")
    w._restyle()  # every tab is redrawn with the new colours, nothing breaks
    assert w.styleSheet()
