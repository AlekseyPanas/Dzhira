"""The on-disk DB layout + first-run seeding.

The DB is a plain folder of JSON files (no database), one subfolder per entity type. A single derived
dict (``JsonFolderDerivedDict``) mirrors the whole thing, so the frontend gets it as one nested tree:

    db/
      meta/assignee.json            {name, color}                    # the single user
      projects/<CODE>.json          {code, next_num}                 # 3-letter code + id counter
      tags/<tag_id>.json            {id, name, color}
      columns/<col_id>.json         {id, name, order}                # a Kanban status column
      tasks/<CODE>-<n>.json         {id, title, description,
                                     tags:[tag_id...], status:col_id, order}

ORDERING (chosen model): ``order`` is a float; the board is a pure projection — group tasks by
``status``, sort by ``order`` — so a drag/reorder rewrites exactly ONE task file (its status+order).
Columns are ordered the same way. Fresh items are spaced ``ORDER_STEP`` apart; ``BoardAPI`` inserts
at fractional midpoints and rebalances a lane only if the gap collapses.

``ensure_scaffold`` is idempotent: it makes the subfolders and, ONLY when the board is empty, seeds a
friendly starting set so first run isn't a blank page.
"""

import json
from pathlib import Path
from typing import Union

from backend.db.ids import new_id

META_DIR = "meta"
PROJECTS_DIR = "projects"
TAGS_DIR = "tags"
COLUMNS_DIR = "columns"
TASKS_DIR = "tasks"
SUBFOLDERS = (META_DIR, PROJECTS_DIR, TAGS_DIR, COLUMNS_DIR, TASKS_DIR)

ASSIGNEE_FILE = "assignee.json"

# Spacing between freshly-created siblings' order values. Big enough that thousands of midpoint
# inserts between two neighbors never run out of float precision before a rebalance.
ORDER_STEP = 1000.0

DEFAULT_ASSIGNEE = {"name": "You", "color": "#ffd23f"}


def ensure_scaffold(db_root: Union[str, Path]) -> None:
    """Create the DB folder + subfolders (idempotent) and seed a starting board when it's empty."""
    root = Path(db_root)
    root.mkdir(parents=True, exist_ok=True)
    for subfolder in SUBFOLDERS:
        (root / subfolder).mkdir(exist_ok=True)

    if not (root / META_DIR / ASSIGNEE_FILE).exists():
        _write_json(root / META_DIR / ASSIGNEE_FILE, DEFAULT_ASSIGNEE)

    # Seed the rest ONLY when the board has never been used (no columns yet). Guarding on columns
    # (the one entity the app mandates ≥1 of) means we never resurrect things the user deleted.
    if not any((root / COLUMNS_DIR).glob("*.json")):
        _seed_starter_board(root)


def _seed_starter_board(root: Path) -> None:
    columns = [("To Do", ORDER_STEP), ("Doing", 2 * ORDER_STEP), ("Done", 3 * ORDER_STEP)]
    column_ids = []
    for name, order in columns:
        col_id = new_id("col")
        column_ids.append(col_id)
        _write_json(root / COLUMNS_DIR / f"{col_id}.json", {"id": col_id, "name": name, "order": order})

    tags = [("bug", "#ff5c5c"), ("feature", "#4fd06a"), ("spicy", "#ff77dd")]
    tag_ids = []
    for name, color in tags:
        tag_id = new_id("tag")
        tag_ids.append(tag_id)
        _write_json(root / TAGS_DIR / f"{tag_id}.json", {"id": tag_id, "name": name, "color": color})

    _write_json(root / PROJECTS_DIR / "DZH.json", {"code": "DZH", "next_num": 4})

    todo, doing, done = column_ids
    bug, feature, spicy = tag_ids
    samples = [
        ("DZH-1", "Make it look worse", "Needs more clashing colors and at least one Comic Sans.",
         [feature, spicy], todo, ORDER_STEP),
        ("DZH-2", "Fix the drag jank", "The ghost slot should slot in, not teleport around.",
         [bug], doing, ORDER_STEP),
        ("DZH-3", "Touch grass", "This one is already done. Look at us go.",
         [], done, ORDER_STEP),
    ]
    for task_id, title, description, task_tags, status, order in samples:
        _write_json(root / TASKS_DIR / f"{task_id}.json", {
            "id": task_id, "title": title, "description": description,
            "tags": task_tags, "status": status, "order": order})


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
