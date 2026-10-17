"""The command line."""

import pytest

from daftarche import __version__, paths
from daftarche.main import build_parser, main


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"daftarche {__version__}"


def test_commands():
    parser = build_parser()
    assert parser.parse_args(["install-app", "--remove"]).remove
    args = parser.parse_args(["update", "--check"])
    assert args.check and not args.yes
    assert parser.parse_args([]).command is None


def test_data_folder_is_the_test_one(tmp_path_factory):
    assert "daftarche-test-" in str(paths.DATA_DIR)
    assert paths.DB_PATH.parent == paths.DATA_DIR
    assert paths.BACKUP_DIR.is_dir()
