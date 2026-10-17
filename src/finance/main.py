"""Entry point of the ``finance`` command."""

import argparse
import sys

from finance import __version__
from finance.app_info import APP_NAME as APP_DISPLAY_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finance", description="Finance Manager: personal finance desktop app.")
    parser.add_argument("--version", action="version", version=f"finance {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("view", help="open the app (default)")

    install = sub.add_parser("install-app", help="add the app to Applications / the Start menu / the app menu")
    install.add_argument("--remove", action="store_true", help="remove the launcher again")
    return parser


def run_install_app(args: argparse.Namespace) -> int:
    from sciwidgets.app.launcher import install_app_command

    from finance.app_info import APP

    return install_app_command(APP, remove=args.remove)


def refresh_launcher() -> None:
    """Rebuild an app launcher of this installation made by an older version (never raises)."""
    from sciwidgets.app.launcher import refresh_if_outdated

    from finance.app_info import APP

    refresh_if_outdated(APP)


SPLASH_SECONDS = 4.5  # the splash stays at least this long, so it can be seen


def run_view() -> int:
    import time

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QColor, QIcon
    from PySide6.QtWidgets import QApplication

    from finance.app_info import APP, APP_IMAGE

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("finance")
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

    from finance.window import MainWindow  # the slow imports, behind the splash

    if splash:
        splash.show_message("Opening the database...")
    window = MainWindow()

    def show_window() -> None:
        window.show()
        if splash:
            splash.finish(window)

    remaining = SPLASH_SECONDS - (time.monotonic() - shown_at) if splash else 0
    if remaining > 0:
        QTimer.singleShot(round(1000 * remaining), show_window)
    else:
        show_window()
    QTimer.singleShot(round(1000 * max(remaining, 0)) + 2000, refresh_launcher)
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    argv = [a for a in argv if not a.startswith("-psn_")]  # old macOS Finder argument
    args = build_parser().parse_args(argv)
    if args.command == "install-app":
        return run_install_app(args)
    return run_view()


if __name__ == "__main__":
    sys.exit(main())
