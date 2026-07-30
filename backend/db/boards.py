"""The boards store: create / delete / list / access / membership / ownership.

A board is a folder ``boards/<bid>/`` whose ``board.json`` is ``{id, name, owner_id, members:[uid…]}``
(``members`` = the non-owner accessors; access = owner OR member). Board names are unique
case-insensitively and set at creation (no rename). A user may OWN at most ``MAX_OWNED`` boards; shared
membership is unlimited. Kicking a member also strips them from every task's assignees in that board.
"""

import shutil
from pathlib import Path
from typing import List, Optional, Union

from backend.db import ids, paths
from backend.db.jsonstore import atomic_write_json, locked_read_modify_write, read_json
from backend.db.seeding import seed_board_contents

MAX_OWNED = 2


class BoardsStore:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self._root = Path(db_root)

    # ------------------------------------------------------------------ create / delete
    def create_board(self, name: str, owner_id: str) -> dict:
        name = ids.validate_board_name(name)
        if self.resolve_by_name(name) is not None:
            raise ValueError(f"A board named '{name}' already exists.")
        if self.owned_count(owner_id) >= MAX_OWNED:
            raise ValueError(f"You can own at most {MAX_OWNED} boards.")
        board_id = ids.new_id("brd")
        folder = paths.board_dir(self._root, board_id)
        folder.mkdir(parents=True, exist_ok=True)
        board = {"id": board_id, "name": name, "owner_id": owner_id, "members": []}
        atomic_write_json(folder / paths.BOARD_FILE, board)
        seed_board_contents(folder, owner_id)
        return board

    def delete_board(self, board_id: str) -> None:
        folder = self._board_dir(board_id)
        if not (folder / paths.BOARD_FILE).is_file():
            raise ValueError("No such board.")
        shutil.rmtree(folder, ignore_errors=True)

    # ------------------------------------------------------------------ read / resolve
    def get_board(self, board_id: str) -> Optional[dict]:
        return read_json(self._board_dir(board_id) / paths.BOARD_FILE)

    def resolve_by_name(self, name: str) -> Optional[dict]:
        try:
            wanted = ids.board_name_lower(name)
        except ValueError:
            return None
        for board in self.list_all():
            if board.get("name", "").lower() == wanted:
                return board
        return None

    def list_all(self) -> List[dict]:
        boards_root = self._root / paths.BOARDS_DIR
        result: List[dict] = []
        if not boards_root.is_dir():
            return result
        for entry in boards_root.iterdir():
            board = read_json(entry / paths.BOARD_FILE) if entry.is_dir() else None
            if board is not None:
                result.append(board)
        return result

    def boards_for_user(self, user_id: str) -> List[dict]:
        return sorted((b for b in self.list_all() if self.has_access(b, user_id)),
                      key=lambda b: b.get("name", "").lower())

    def owned_count(self, user_id: str) -> int:
        return sum(1 for b in self.list_all() if b.get("owner_id") == user_id)

    @staticmethod
    def has_access(board: dict, user_id: str) -> bool:
        return board.get("owner_id") == user_id or user_id in board.get("members", [])

    @staticmethod
    def role(board: dict, user_id: str) -> Optional[str]:
        if board.get("owner_id") == user_id:
            return "owner"
        if user_id in board.get("members", []):
            return "member"
        return None

    # ------------------------------------------------------------------ membership / ownership
    def add_member(self, board_id: str, user_id: str) -> None:
        def mutate(board: dict) -> None:
            if user_id != board.get("owner_id") and user_id not in board.get("members", []):
                board.setdefault("members", []).append(user_id)
        locked_read_modify_write(self._board_dir(board_id) / paths.BOARD_FILE, mutate)

    def kick_member(self, board_id: str, user_id: str) -> None:
        """Remove a member from the board, from every task they're assigned to, and drop their saved
        filter view."""
        def mutate(board: dict) -> None:
            board["members"] = [uid for uid in board.get("members", []) if uid != user_id]
        locked_read_modify_write(self._board_dir(board_id) / paths.BOARD_FILE, mutate)
        self._strip_assignee_from_tasks(board_id, user_id)
        (self._board_dir(board_id) / paths.VIEWS_DIR / f"{user_id}.json").unlink(missing_ok=True)

    def transfer_ownership(self, board_id: str, new_owner_id: str) -> None:
        """Hand the board to an existing member; the old owner becomes a plain member."""
        board = self.get_board(board_id)
        if board is None:
            raise ValueError("No such board.")
        if new_owner_id != board.get("owner_id") and new_owner_id not in board.get("members", []):
            raise ValueError("You can only transfer ownership to a current member.")

        def mutate(current: dict) -> None:
            old_owner = current.get("owner_id")
            members = [uid for uid in current.get("members", []) if uid != new_owner_id]
            if old_owner is not None and old_owner != new_owner_id:
                members.append(old_owner)
            current["owner_id"] = new_owner_id
            current["members"] = members
        locked_read_modify_write(self._board_dir(board_id) / paths.BOARD_FILE, mutate)

    def member_ids(self, board: dict) -> List[str]:
        """Everyone with access, owner first."""
        return [board["owner_id"], *[uid for uid in board.get("members", []) if uid != board["owner_id"]]]

    # ------------------------------------------------------------------ internals
    def _strip_assignee_from_tasks(self, board_id: str, user_id: str) -> None:
        tasks_dir = self._board_dir(board_id) / paths.TASKS_DIR
        if not tasks_dir.is_dir():
            return
        for task_path in tasks_dir.glob("*.json"):
            task = read_json(task_path)
            if task and user_id in task.get("assignees", []):
                locked_read_modify_write(task_path, lambda t: t.__setitem__(
                    "assignees", [uid for uid in t.get("assignees", []) if uid != user_id]))

    def _board_dir(self, board_id: str) -> Path:
        return paths.board_dir(self._root, ids.validate_generated_id(board_id, "board"))
