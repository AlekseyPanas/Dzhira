"""``BoardAPI`` — the ONLY writer of the DB folder (§7).

Every mutation returns ``None`` (or, for creates, the new id — handy for tests) and raises
``ValueError`` on any bad input; SUCCESS PRODUCES NO CLIENT PAYLOAD by design. The change propagates
disk → watchdog → the ``DB`` derived dict → websocket → the frontend frame, and THAT is the source of
truth the UI re-renders from — never an optimistic echo.

Locking model (ported from eventCamera's ``SettingsAPI``): a read-modify-write on a single file takes
a brief ``flock`` on JUST that file for the op, then writes atomically (temp file + rename in the same
dir). Whole-file ops (create/rename/delete) are atomic at the FS level. The per-file flock only
serializes concurrent writers of the SAME file; atomic renames keep every reader (the watchdog mirror
included) consistent. Cross-file operations (a cascade delete, a lane rebalance) are a SEQUENCE of
atomic single-file ops — not one transaction — which is fine for this single-user parody: the board
converges as each change streams out.

``BoardAPI`` reads the current on-disk state directly for its own queries (a column's tasks, a
project's tasks) — it is the writer, so it wants the freshest truth, not the possibly-lagging mirror.
"""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from backend.db import ids
from backend.db.layout import (
    ASSIGNEE_FILE,
    COLUMNS_DIR,
    META_DIR,
    ORDER_STEP,
    PROJECTS_DIR,
    TAGS_DIR,
    TASKS_DIR,
)


class BoardAPI:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self._root = Path(db_root).resolve()

    # ==============================================================================================
    #  Tasks
    # ==============================================================================================
    def create_task(self, project_code: str, title: str,
                     description: str = "", tags: Optional[List[str]] = None) -> str:
        """Reserve the next id for ``project_code`` and create the task at the TOP of the leftmost
        column. Returns the new task id (e.g. ``ENG-4``)."""
        code = ids.normalize_project_code(project_code)
        self._require_project(code)
        clean_tags = self._validate_tags(tags or [])
        status_id = self._leftmost_column_id()

        number = self._reserve_next_number(code)
        task_id = f"{code}-{number}"
        order = self._order_at_top_of(status_id)
        self._atomic_write_json(self._task_path(task_id), {
            "id": task_id,
            "title": str(title),
            "description": str(description),
            "tags": clean_tags,
            "status": status_id,
            "order": order,
        })
        return task_id

    def update_task(self, task_id: str, title: str, description: str,
                    tags: Optional[List[str]] = None) -> None:
        """Edit a task's CONTENT (title / description / tags). Status + order are board-positional
        and change only via ``move_task``; the id is immutable."""
        ids.validate_task_id(task_id)
        clean_tags = self._validate_tags(tags or [])

        def mutate(task: dict) -> None:
            task["title"] = str(title)
            task["description"] = str(description)
            task["tags"] = clean_tags

        self._locked_read_modify_write(self._task_path(task_id), mutate)

    def delete_task(self, task_id: str) -> None:
        ids.validate_task_id(task_id)
        path = self._task_path(task_id)
        if not path.is_file():
            raise ValueError(f"Task '{task_id}' does not exist.")
        path.unlink()

    def move_task(self, task_id: str, status_id: str, index: int) -> None:
        """The drag-and-drop op: place ``task_id`` into column ``status_id`` at position ``index``
        (0 = top). Reads the destination lane, computes a fractional ``order`` between the neighbors
        at that index, and rebalances the whole lane only if the gap has collapsed."""
        ids.validate_task_id(task_id)
        ids.validate_generated_id(status_id, "column")
        self._require_column(status_id)
        if not self._task_path(task_id).is_file():
            raise ValueError(f"Task '{task_id}' does not exist.")

        lane = [task for task in self._tasks_in_column(status_id) if task["id"] != task_id]
        lane.sort(key=lambda task: task["order"])
        index = max(0, min(int(index), len(lane)))

        left = lane[index - 1]["order"] if index > 0 else None
        right = lane[index]["order"] if index < len(lane) else None
        new_order = self._between(left, right)
        if left is not None and right is not None and not (left < new_order < right):
            self._rebalance_lane_with_insertion(status_id, lane, index, task_id)
            return
        self._set_task_position(task_id, status_id, new_order)

    # ==============================================================================================
    #  Columns (statuses)
    # ==============================================================================================
    def create_column(self, name: str) -> str:
        column_id = ids.new_id("col")
        order = self._max_order(self._entries(COLUMNS_DIR)) + ORDER_STEP
        self._atomic_write_json(self._column_path(column_id),
                                {"id": column_id, "name": str(name), "order": order})
        return column_id

    def rename_column(self, column_id: str, name: str) -> None:
        ids.validate_generated_id(column_id, "column")
        self._locked_read_modify_write(self._column_path(column_id),
                                       lambda column: column.__setitem__("name", str(name)))

    def move_column(self, column_id: str, direction: str) -> None:
        """Swap this column with its left/right neighbor by exchanging their ``order`` values."""
        ids.validate_generated_id(column_id, "column")
        if direction not in ("left", "right"):
            raise ValueError(f"direction must be 'left' or 'right', not '{direction}'.")
        columns = sorted(self._entries(COLUMNS_DIR), key=lambda column: column["order"])
        position = next((i for i, column in enumerate(columns) if column["id"] == column_id), None)
        if position is None:
            raise ValueError(f"Column '{column_id}' does not exist.")
        neighbor_position = position - 1 if direction == "left" else position + 1
        if not 0 <= neighbor_position < len(columns):
            return                                          # already at the edge — nothing to do
        this_order = columns[position]["order"]
        neighbor = columns[neighbor_position]
        self._set_column_order(column_id, neighbor["order"])
        self._set_column_order(neighbor["id"], this_order)

    def delete_column(self, column_id: str) -> None:
        """Delete a column, reassigning its tasks to the nearest remaining column (§ delete rules).
        At least one column must always remain."""
        ids.validate_generated_id(column_id, "column")
        columns = sorted(self._entries(COLUMNS_DIR), key=lambda column: column["order"])
        position = next((i for i, column in enumerate(columns) if column["id"] == column_id), None)
        if position is None:
            raise ValueError(f"Column '{column_id}' does not exist.")
        if len(columns) <= 1:
            raise ValueError("Can't delete the last column — a board needs at least one.")

        # Nearest surviving column = the right neighbor if any, else the left one.
        target = columns[position + 1] if position + 1 < len(columns) else columns[position - 1]
        orphans = sorted(self._tasks_in_column(column_id), key=lambda task: task["order"])
        next_order = self._max_order(self._tasks_in_column(target["id"])) + ORDER_STEP
        for task in orphans:                                # append them onto the target, in order
            self._set_task_position(task["id"], target["id"], next_order)
            next_order += ORDER_STEP
        self._column_path(column_id).unlink()

    # ==============================================================================================
    #  Tags
    # ==============================================================================================
    def create_tag(self, name: str, color: str) -> str:
        tag_id = ids.new_id("tag")
        self._atomic_write_json(self._tag_path(tag_id),
                                {"id": tag_id, "name": str(name), "color": str(color)})
        return tag_id

    def update_tag(self, tag_id: str, name: str, color: str) -> None:
        ids.validate_generated_id(tag_id, "tag")

        def mutate(tag: dict) -> None:
            tag["name"] = str(name)
            tag["color"] = str(color)

        self._locked_read_modify_write(self._tag_path(tag_id), mutate)

    def delete_tag(self, tag_id: str) -> None:
        """Delete a tag and remove it from every task that carries it (§ delete rules)."""
        ids.validate_generated_id(tag_id, "tag")
        path = self._tag_path(tag_id)
        if not path.is_file():
            raise ValueError(f"Tag '{tag_id}' does not exist.")
        for task in self._entries(TASKS_DIR):
            if tag_id in task.get("tags", []):
                self._locked_read_modify_write(
                    self._task_path(task["id"]),
                    lambda t: t.__setitem__("tags", [x for x in t.get("tags", []) if x != tag_id]))
        path.unlink()

    # ==============================================================================================
    #  Projects
    # ==============================================================================================
    def create_project(self, code: str) -> str:
        code = ids.normalize_project_code(code)
        path = self._project_path(code)
        if path.exists():
            raise ValueError(f"Project '{code}' already exists.")
        self._atomic_write_json(path, {"code": code, "next_num": 1})
        return code

    def rename_project(self, code: str, new_code: str) -> None:
        """Change a project's code, re-id-ing every one of its tasks (``ENG-7`` -> ``ABC-7``), since
        a task's id is hard-tied to the project code."""
        code = ids.normalize_project_code(code)
        new_code = ids.normalize_project_code(new_code)
        if new_code == code:
            return
        if not self._project_path(code).is_file():
            raise ValueError(f"Project '{code}' does not exist.")
        if self._project_path(new_code).exists():
            raise ValueError(f"Project '{new_code}' already exists.")

        old_project = self._read_json(self._project_path(code))
        self._atomic_write_json(self._project_path(new_code),
                                {"code": new_code, "next_num": old_project.get("next_num", 1)})
        for task in self._tasks_for_project(code):
            old_task_id = task["id"]
            new_task_id = f"{new_code}-{old_task_id.split('-', 1)[1]}"
            task["id"] = new_task_id
            self._atomic_write_json(self._task_path(new_task_id), task)
            self._task_path(old_task_id).unlink(missing_ok=True)
        self._project_path(code).unlink(missing_ok=True)

    def delete_project(self, code: str) -> None:
        """Delete a project AND all its tasks (the id is hard-tied — § delete rules)."""
        code = ids.normalize_project_code(code)
        path = self._project_path(code)
        if not path.is_file():
            raise ValueError(f"Project '{code}' does not exist.")
        for task in self._tasks_for_project(code):
            self._task_path(task["id"]).unlink(missing_ok=True)
        path.unlink()

    # ==============================================================================================
    #  Assignee (the single user)
    # ==============================================================================================
    def set_assignee(self, name: str, color: str) -> None:
        self._atomic_write_json(self._root / META_DIR / ASSIGNEE_FILE,
                                {"name": str(name), "color": str(color)})

    # ==============================================================================================
    #  Internal queries (read the freshest on-disk truth)
    # ==============================================================================================
    def _entries(self, subfolder: str) -> List[dict]:
        """Every parseable json object in a subfolder. Skips a file mid-write (unparseable) — the
        caller is a writer computing orders/cascades, and a torn read would just be excluded."""
        results: List[dict] = []
        for path in (self._root / subfolder).glob("*.json"):
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return results

    def _tasks_in_column(self, column_id: str) -> List[dict]:
        return [task for task in self._entries(TASKS_DIR) if task.get("status") == column_id]

    def _tasks_for_project(self, code: str) -> List[dict]:
        prefix = f"{code}-"
        return [task for task in self._entries(TASKS_DIR)
                if isinstance(task.get("id"), str) and task["id"].startswith(prefix)]

    def _leftmost_column_id(self) -> str:
        columns = sorted(self._entries(COLUMNS_DIR), key=lambda column: column["order"])
        if not columns:
            raise ValueError("No columns exist — the board needs at least one column.")
        return columns[0]["id"]

    def _order_at_top_of(self, column_id: str) -> float:
        tasks = self._tasks_in_column(column_id)
        return (min(task["order"] for task in tasks) - ORDER_STEP) if tasks else ORDER_STEP

    @staticmethod
    def _max_order(entries: List[dict]) -> float:
        return max((entry["order"] for entry in entries), default=0.0)

    @staticmethod
    def _between(left: Optional[float], right: Optional[float]) -> float:
        """A fresh order between two neighbors (either may be absent at a lane end)."""
        if left is None and right is None:
            return ORDER_STEP
        if left is None:
            return right - ORDER_STEP
        if right is None:
            return left + ORDER_STEP
        return (left + right) / 2.0

    # ==============================================================================================
    #  Internal mutators
    # ==============================================================================================
    def _reserve_next_number(self, code: str) -> int:
        """Take-and-increment the project's id counter. Numbers are monotonic and never reused (a
        deleted task's number is gone forever), so ids are stable references."""
        reserved: Dict[str, int] = {}

        def mutate(project: dict) -> None:
            reserved["n"] = int(project.get("next_num", 1))
            project["next_num"] = reserved["n"] + 1

        self._locked_read_modify_write(self._project_path(code), mutate)
        return reserved["n"]

    def _set_task_position(self, task_id: str, status_id: str, order: float) -> None:
        def mutate(task: dict) -> None:
            task["status"] = status_id
            task["order"] = order

        self._locked_read_modify_write(self._task_path(task_id), mutate)

    def _set_column_order(self, column_id: str, order: float) -> None:
        self._locked_read_modify_write(self._column_path(column_id),
                                       lambda column: column.__setitem__("order", order))

    def _rebalance_lane_with_insertion(self, status_id: str, lane_without: List[dict],
                                       index: int, task_id: str) -> None:
        """Re-space an entire column's tasks when a midpoint gap collapsed: the final order is
        ``lane_without`` with ``task_id`` inserted at ``index``, each given a clean ``ORDER_STEP``
        multiple."""
        final_ids = [task["id"] for task in lane_without]
        final_ids.insert(index, task_id)
        for position, an_id in enumerate(final_ids):
            self._set_task_position(an_id, status_id, ORDER_STEP * (position + 1))

    # ==============================================================================================
    #  Existence guards
    # ==============================================================================================
    def _require_project(self, code: str) -> None:
        if not self._project_path(code).is_file():
            raise ValueError(f"Project '{code}' does not exist.")

    def _require_column(self, column_id: str) -> None:
        if not self._column_path(column_id).is_file():
            raise ValueError(f"Column '{column_id}' does not exist.")

    def _validate_tags(self, tags: List[str]) -> List[str]:
        """Keep the given tag ids, rejecting any that don't exist (and de-duping, order-preserving)."""
        existing = {tag["id"] for tag in self._entries(TAGS_DIR)}
        clean: List[str] = []
        for tag_id in tags:
            ids.validate_generated_id(tag_id, "tag")
            if tag_id not in existing:
                raise ValueError(f"Tag '{tag_id}' does not exist.")
            if tag_id not in clean:
                clean.append(tag_id)
        return clean

    # ==============================================================================================
    #  Path helpers
    # ==============================================================================================
    def _task_path(self, task_id: str) -> Path:
        return self._root / TASKS_DIR / f"{ids.validate_task_id(task_id)}.json"

    def _column_path(self, column_id: str) -> Path:
        return self._root / COLUMNS_DIR / f"{ids.validate_generated_id(column_id, 'column')}.json"

    def _tag_path(self, tag_id: str) -> Path:
        return self._root / TAGS_DIR / f"{ids.validate_generated_id(tag_id, 'tag')}.json"

    def _project_path(self, code: str) -> Path:
        return self._root / PROJECTS_DIR / f"{ids.normalize_project_code(code)}.json"

    # ==============================================================================================
    #  flock + atomic write plumbing (ported from eventCamera's SettingsAPI)
    # ==============================================================================================
    def _locked_read_modify_write(self, target: Path, mutate: Callable[[dict], None]) -> None:
        """flock the target file, parse, ``mutate`` in place, atomic temp+rename, release."""
        with self._flock_current_inode(target) as locked_file:
            tree = json.loads(locked_file.read())
            if not isinstance(tree, dict):
                raise ValueError(f"'{target.name}' does not contain a json object.")
            mutate(tree)
            self._atomic_write_json(target, tree)

    @contextmanager
    def _flock_current_inode(self, target: Path):
        """flock the file CURRENTLY at ``target`` — with the open-then-verify-inode retry, because a
        writer replaces the file by rename, so a waiter can win the lock on an inode that is no
        longer the file at that path."""
        while True:
            try:
                locked_file = open(target, "r+", encoding="utf-8")
            except FileNotFoundError:
                raise ValueError(f"'{target.name}' does not exist.")
            fcntl.flock(locked_file.fileno(), fcntl.LOCK_EX)
            try:
                if os.fstat(locked_file.fileno()).st_ino == os.stat(target).st_ino:
                    yield locked_file                       # fd is the live file: safe to RMW
                    return
            except FileNotFoundError:                       # deleted while we waited: next loop
                pass                                        # re-raises the clean error above
            finally:
                fcntl.flock(locked_file.fileno(), fcntl.LOCK_UN)
                locked_file.close()

    def _atomic_write_json(self, target: Path, tree: dict) -> None:
        """Write via a temp file in the same directory + rename — a reader never sees a torn file."""
        file_descriptor, temp_path = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as temp_file:
                json.dump(tree, temp_file, indent=2)
            os.replace(temp_path, target)                   # atomic on POSIX
        except BaseException:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))
