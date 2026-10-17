"""Daftarche: personal bookkeeping desktop app (PySide6 + SQLite)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("daftarche")
except PackageNotFoundError:  # running from a checkout without `pip install -e .`
    __version__ = "0.0.0"
