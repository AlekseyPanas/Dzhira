"""Color palettes (projects + users) and the per-board starter content.

A project and a user each always have a color; when none is given we pick a stable default from a
palette by hashing the id/code, and the frontend mirrors the SAME rule (frontend/src/model.ts) so a
value with no stored color still resolves consistently. ``seed_board_contents`` fills a freshly-created
board with a friendly starting set (three columns, a few tags, a DZH project, a few sample tasks
assigned to the board's owner) so a new board isn't a blank page.
"""

import json
from pathlib import Path

from backend.db import paths

PROJECT_COLOR_PALETTE = [
    "#ff5c5c", "#ffa23a", "#ffd23f", "#7bd854",
    "#3ec6c6", "#5b9bff", "#b06bff", "#ff77dd",
]
USER_COLOR_PALETTE = [
    "#e26d5c", "#e0a458", "#c6b447", "#5aa469",
    "#3f9ab0", "#5f7fd0", "#9a6fc0", "#c96fa0",
]


def default_project_color(code: str) -> str:
    return PROJECT_COLOR_PALETTE[sum(ord(ch) for ch in code) % len(PROJECT_COLOR_PALETTE)]


def default_user_color(user_id: str) -> str:
    return USER_COLOR_PALETTE[sum(ord(ch) for ch in user_id) % len(USER_COLOR_PALETTE)]


def seed_board_contents(board_folder: Path, owner_id: str) -> None:
    """Create the board's content subfolders and a starter set. Idempotent-ish: only seeds when the
    board has no columns yet (the app mandates >= 1 column, so that's the 'never used' signal)."""
    for subfolder in paths.BOARD_SUBFOLDERS:
        (board_folder / subfolder).mkdir(parents=True, exist_ok=True)
    if any((board_folder / paths.COLUMNS_DIR).glob("*.json")):
        return

    from backend.db.ids import new_id                       # local import avoids a cycle
    step = paths.ORDER_STEP

    column_ids = []
    for name, order in [("To Do", step), ("Doing", 2 * step), ("Done", 3 * step)]:
        col_id = new_id("col")
        column_ids.append(col_id)
        _write(board_folder / paths.COLUMNS_DIR / f"{col_id}.json",
               {"id": col_id, "name": name, "order": order})

    tag_ids = []
    for name, color in [("bug", "#ff5c5c"), ("feature", "#4fd06a"), ("spicy", "#ff77dd")]:
        tag_id = new_id("tag")
        tag_ids.append(tag_id)
        _write(board_folder / paths.TAGS_DIR / f"{tag_id}.json",
               {"id": tag_id, "name": name, "color": color})

    _write(board_folder / paths.PROJECTS_DIR / "DZH.json",
           {"code": "DZH", "next_num": 4, "color": default_project_color("DZH")})

    todo, doing, done = column_ids
    bug, feature, spicy = tag_ids
    samples = [
        ("DZH-1", "No HR Violation", "Spend 3 days without an HR violation.",
         [feature, spicy], todo, step),
        ("DZH-2", "Git gud.", "Acquire skills, become good.",
         [bug], doing, step),
        ("DZH-3", "Touch grass", "Go outside.",
         [], done, step),
    ]
    for task_id, title, description, task_tags, status, order in samples:
        _write(board_folder / paths.TASKS_DIR / f"{task_id}.json", {
            "id": task_id, "title": title, "description": description,
            "tags": task_tags, "status": status, "order": order, "assignees": [owner_id]})


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
