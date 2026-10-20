"""Daftarche as an app: its name, and the description used by the launcher and the update check."""

from pathlib import Path

from sciwidgets.app import AppInfo

from daftarche import __version__

APP_NAME = "Daftarche"
"""Name shown to the user (window, splash, launcher)."""

APP_VERSION = __version__

ICONS = Path(__file__).resolve().parent / "data" / "icons"
APP_IMAGE = ICONS / "splash.png"
USER_GUIDE = ICONS.parent / "user_guide.pdf"
"""The User Guide, built from docs/user_guide.tex by tools/build_docs.sh."""
"""Background of the splash screen (drawn by tools/make_icon.py)."""

DIST_NAME = "daftarche"
"""Name of the package (PyPI, once public)."""

APP = AppInfo(
    name=APP_NAME,
    version=APP_VERSION,
    dist_name=DIST_NAME,
    module="daftarche",
    command="daftarche",
    github_repo="vahid-anari/daftarche",
    icon=ICONS / "app_icon.png",
    bundle_id="io.github.vahid-anari.daftarche",
    linux_id="daftarche",
    marker="Daftarche",
    comment="Personal bookkeeping: bank transactions from QFX and Excel statements",
    categories="Office;Finance;",
)
"""Daftarche for ``sciwidgets.app`` (launcher, update check)."""
