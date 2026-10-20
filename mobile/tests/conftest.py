"""The app's code is in src/; Daftarche itself (for the cross-checks) never sees your real data."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["DAFTARCHE_HOME"] = tempfile.mkdtemp(prefix="daftarche-phone-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
