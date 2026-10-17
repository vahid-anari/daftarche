"""Entry point of the ``daftarche`` command."""

import argparse
import sys

from daftarche import __version__
from daftarche.app_info import APP_NAME as APP_DISPLAY_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="daftarche", description="Daftarche: personal bookkeeping desktop app.")
    parser.add_argument("--version", action="version", version=f"daftarche {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("view", help="open the app (default)")

    update = sub.add_parser("update", help="update daftarche from PyPI (asks first)")
    update.add_argument("--check", action="store_true", help="only tell whether a newer version exists")
    update.add_argument("--yes", "-y", action="store_true", help="update without asking")

    install = sub.add_parser("install-app", help="add the app to Applications / the Start menu / the app menu")
    install.add_argument("--remove", action="store_true", help="remove the launcher again")
    return parser


def run_install_app(args: argparse.Namespace) -> int:
    from sciwidgets.app.launcher import install_app_command

    from daftarche.app_info import APP

    return install_app_command(APP, remove=args.remove)


def after_start(updates) -> None:
    """A few seconds after start-up: a quiet update check and refreshing an old app launcher."""
    updates.check(manual=False)
    refresh_launcher()


def refresh_launcher() -> None:
    """Rebuild an app launcher of this installation made by an older version (never raises)."""
    from sciwidgets.app.launcher import refresh_if_outdated

    from daftarche.app_info import APP

    refresh_if_outdated(APP)


def add_update_menu(window):
    """Help → Check for Updates… (in the macOS menu bar); returns the update checker."""
    from sciwidgets.app.update_ui import AppUpdates

    from daftarche.app_info import APP

    updates = AppUpdates(window, APP)
    window.menuBar().addMenu("Help").addAction("Check for Updates…", lambda: updates.check(manual=True))
    return updates


SPLASH_SECONDS = 4.5  # the splash stays at least this long, so it can be seen


def run_view() -> int:
    import time

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QColor, QIcon
    from PySide6.QtWidgets import QApplication

    from daftarche.app_info import APP, APP_IMAGE

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("daftarche")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setStyle("Fusion")
    if APP.icon.exists():
        app.setWindowIcon(QIcon(str(APP.icon)))

    splash = None
    shown_at = time.monotonic()
    if APP_IMAGE.exists():
        from sciwidgets.splash import SplashScreen

        base = 35
        splash = SplashScreen(
            APP_IMAGE,
            size=(16 * base, 9 * base),
            title=APP_DISPLAY_NAME.replace(" ", "\n"),
            subtitle=f"Version {__version__}",
            font_family="Helvetica Neue",
            title_color=QColor("#e8e0d0"),
            subtitle_color=QColor("#e8e0d0"),
            message_color=QColor("#9a9080"),
            delay=0.05,
        )
        splash.show_message("Starting...")

    from daftarche.window import MainWindow  # the slow imports, behind the splash

    if splash:
        splash.show_message("Opening the database...")
    window = MainWindow()
    updates = add_update_menu(window)

    def show_window() -> None:
        window.show()
        if splash:
            splash.finish(window)

    remaining = SPLASH_SECONDS - (time.monotonic() - shown_at) if splash else 0
    if remaining > 0:
        QTimer.singleShot(round(1000 * remaining), show_window)
    else:
        show_window()
    QTimer.singleShot(round(1000 * max(remaining, 0)) + 2000, lambda: after_start(updates))
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    argv = [a for a in argv if not a.startswith("-psn_")]  # old macOS Finder argument
    args = build_parser().parse_args(argv)
    if args.command == "install-app":
        return run_install_app(args)
    if args.command == "update":
        from sciwidgets.app.update import run_update

        from daftarche.app_info import APP

        return run_update(APP, args)
    return run_view()


if __name__ == "__main__":
    sys.exit(main())
