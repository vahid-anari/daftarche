"""Finance Manager as an app: its name, and the description used by the launcher and the update check."""

from pathlib import Path

from sciwidgets.app import AppInfo

from finance import __version__

APP_NAME = "Finance Manager"
"""Name shown to the user (window, splash, launcher)."""

APP_VERSION = __version__

DIST_NAME = "finance"
"""Name of the package (PyPI, once public)."""

APP = AppInfo(
    name=APP_NAME,
    version=APP_VERSION,
    dist_name=DIST_NAME,
    module="finance",
    command="finance",
    github_repo="vahid-anari/finance",
    icon=Path(__file__).resolve().parent / "data" / "icons" / "app_icon.png",
    bundle_id="io.github.vahid-anari.finance",
    linux_id="finance",
    marker="Finance",
    comment="Track bank transactions imported from QFX and Excel statements",
    categories="Office;Finance;",
)
"""Finance Manager for ``sciwidgets.app`` (launcher, update check)."""
