"""Shared fixtures. ``board`` gives a clean, UNSEEDED board folder (just the empty content subfolders)
so each test builds exactly the columns/projects/tasks it needs and asserts against nothing else."""

import json

import pytest

from backend.db.board_api import BoardAPI
from backend.db.paths import BOARD_SUBFOLDERS


@pytest.fixture
def board_dir(tmp_path):
    folder = tmp_path / "board"
    for subfolder in BOARD_SUBFOLDERS:
        (folder / subfolder).mkdir(parents=True)
    return folder


@pytest.fixture
def board(board_dir):
    return BoardAPI(board_dir)


def load_json(root, subfolder, name):
    return json.loads((root / subfolder / f"{name}.json").read_text(encoding="utf-8"))


def exists(root, subfolder, name):
    return (root / subfolder / f"{name}.json").is_file()
