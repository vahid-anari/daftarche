"""Where the app keeps its data: the database, backups and settings.

Everything lives in one folder outside the source tree, so the app can run from
anywhere (Dock, terminal) and nothing personal can end up in git:

    ~/Library/Application Support/Finance/     (macOS; override with $FINANCE_HOME)
        finance.db
        config.json
        backups/finance_backup.db
"""

import os
import sys
from pathlib import Path


def _default_home() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Finance"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "Finance"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "finance"


DATA_DIR = Path(os.environ.get("FINANCE_HOME") or _default_home()).expanduser()
DB_PATH = DATA_DIR / "finance.db"
CONFIG_PATH = DATA_DIR / "config.json"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_PATH = BACKUP_DIR / "finance_backup.db"

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
