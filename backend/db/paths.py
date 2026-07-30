"""The DB layout for the multi-user, multi-board world.

    db/
      users/<uid>.json            {id, username, password{...}, color}
      user_names/<lower>.json     {user_id}                # case-insensitive uniqueness + login
      sessions/<sid>.json         {user_id, created_at}
      invites/<iid>.json          {id, board_id, invitee_lower, inviter_id}
      boards/<bid>/
        board.json                {id, name, owner_id, members:[uid,...]}
        columns/<cid>.json  tags/<tid>.json  projects/<CODE>.json  tasks/<CODE-n>.json

Each board folder is what a per-connection derived dict mirrors (see the websocket hub); the top-level
folders (users / sessions / invites) are account-level and are read/written directly by the stores.
"""

from pathlib import Path
from typing import Union

# --- top-level ---------------------------------------------------------------------------------
USERS_DIR = "users"
USER_NAMES_DIR = "user_names"
SESSIONS_DIR = "sessions"
INVITES_DIR = "invites"
BOARDS_DIR = "boards"
TOP_LEVEL_DIRS = (USERS_DIR, USER_NAMES_DIR, SESSIONS_DIR, INVITES_DIR, BOARDS_DIR)

# --- per board ---------------------------------------------------------------------------------
BOARD_FILE = "board.json"
COLUMNS_DIR = "columns"
TAGS_DIR = "tags"
PROJECTS_DIR = "projects"
TASKS_DIR = "tasks"
VIEWS_DIR = "views"        # per-user filter preferences: views/<user_id>.json (in the board mirror)
BOARD_SUBFOLDERS = (COLUMNS_DIR, TAGS_DIR, PROJECTS_DIR, TASKS_DIR, VIEWS_DIR)

# Spacing between freshly-created siblings' fractional order values (see the ordering model).
ORDER_STEP = 1000.0


def ensure_db(root: Union[str, Path]) -> Path:
    """Create the top-level DB folders (idempotent). No global seeding — a starter board's contents
    are seeded per board, at creation time (see seeding.py)."""
    root = Path(root)
    for name in TOP_LEVEL_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def board_dir(root: Union[str, Path], board_id: str) -> Path:
    return Path(root) / BOARDS_DIR / board_id
