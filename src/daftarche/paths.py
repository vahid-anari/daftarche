"""Where the app keeps its data: the database, backups and settings.

Everything lives in one folder outside the source tree, so the app can run from
anywhere (Dock, terminal) and nothing personal can end up in git:

    ~/Library/Application Support/Daftarche/     (macOS; override with $DAFTARCHE_HOME)
        daftarche.db
        config.json
        backups/

The folder of the earlier name (``Finance``, ``finance.db``) is moved here once.
"""

import os
import shutil
import sys
from pathlib import Path


def _support_dir(name: str) -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / name
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / name.lower()


_OVERRIDE = os.environ.get("DAFTARCHE_HOME")
DATA_DIR = Path(_OVERRIDE or _support_dir("Daftarche")).expanduser()
DB_PATH = DATA_DIR / "daftarche.db"
CONFIG_PATH = DATA_DIR / "config.json"
BACKUP_DIR = DATA_DIR / "backups"


def _migrate_old_name() -> None:
    """Move ``Finance/finance.db`` (app name before 0.2.0) to ``Daftarche/daftarche.db``, once."""
    old = _support_dir("Finance")
    if _OVERRIDE or DATA_DIR.exists() or not old.is_dir():
        return
    shutil.move(str(old), str(DATA_DIR))
    if (DATA_DIR / "finance.db").exists() and not DB_PATH.exists():
        (DATA_DIR / "finance.db").rename(DB_PATH)


_migrate_old_name()
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
