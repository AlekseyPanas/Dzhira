"""Shared fixtures. ``board`` gives a clean, UNSEEDED DB (just the empty subfolders) so each test
builds exactly the columns/projects/tasks it needs and asserts against nothing it didn't create."""

import json

import pytest

from backend.db.board_api import BoardAPI
from backend.db.layout import SUBFOLDERS


@pytest.fixture
def db_root(tmp_path):
    for subfolder in SUBFOLDERS:
        (tmp_path / subfolder).mkdir()
    return tmp_path


@pytest.fixture
def board(db_root):
    return BoardAPI(db_root)


def load_json(db_root, subfolder, name):
    return json.loads((db_root / subfolder / f"{name}.json").read_text(encoding="utf-8"))


def exists(db_root, subfolder, name):
    return (db_root / subfolder / f"{name}.json").is_file()
