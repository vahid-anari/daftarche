"""tools/make_demo_db.py: a year of invented data in its own folder, the same every run."""

import importlib.util
import sqlite3
from datetime import date
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def make_demo():
    path = Path(__file__).resolve().parents[1] / "tools" / "make_demo_db.py"
    spec = importlib.util.spec_from_file_location("make_demo_db", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summary(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT date, amount FROM transactions ORDER BY id").fetchall()
    accounts = [r[0] for r in conn.execute("SELECT name FROM accounts ORDER BY name")]
    conn.close()
    return rows, accounts


def test_demo_database(make_demo, tmp_path):
    path = make_demo.make_demo(tmp_path / "demo", months=12, today=date(2026, 10, 19))
    rows, accounts = summary(path)
    assert path.name == "daftarche.db" and len(rows) > 250
    assert accounts == ["Demo Bank Chequing", "Demo Bank Savings", "Demo Visa"]
    assert min(r[0] for r in rows) == "2025-11-01" and max(r[0] for r in rows) <= "2026-10-19"
    again = make_demo.make_demo(tmp_path / "demo", months=12, today=date(2026, 10, 19))  # replaced, same data
    assert summary(again)[0] == rows


def test_refuses_a_folder_with_other_files(make_demo, tmp_path):
    (tmp_path / "notes.txt").write_text("mine")
    with pytest.raises(SystemExit):
        make_demo.main(["--folder", str(tmp_path)])
    assert not (tmp_path / "daftarche.db").exists()
