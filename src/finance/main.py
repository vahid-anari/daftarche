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


def run_view() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from finance.app_info import APP

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("finance")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setStyle("Fusion")
    if APP.icon.exists():
        app.setWindowIcon(QIcon(str(APP.icon)))

    from finance.window import MainWindow  # the slow imports

    window = MainWindow()
    window.show()
    QTimer.singleShot(2000, refresh_launcher)
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
