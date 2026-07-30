"""``BoardAPI`` — the writer for ONE board's content (its columns / tags / projects / tasks).

Constructed with a single board's folder (``boards/<bid>/``); every op reads/writes within it. Same
contract as before: return ``None`` (or a new id) and raise ``ValueError`` on bad input; success
produces no client payload — the change propagates disk → watchdog → that board's derived dict →
websocket → the frontend. Locking + atomic writes come from ``jsonstore``.

Multi-assignee (v2 of the app): a task carries ``assignees: [user_id, …]`` (0..n). ``BoardAPI`` stores
whatever ids it's given — validating them against the board's membership is the caller's job (it holds
the boards store). The single global "assignee" of the pre-accounts app is gone.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

from backend.db import ids
from backend.db.jsonstore import atomic_write_json, locked_read_modify_write, read_json
from backend.db.paths import COLUMNS_DIR, ORDER_STEP, PROJECTS_DIR, TAGS_DIR, TASKS_DIR
from backend.db.seeding import default_project_color


class BoardAPI:

    def __init__(self, board_folder: Union[str, Path]) -> None:
        self._root = Path(board_folder).resolve()

    # ==============================================================================================
    #  Tasks
    # ==============================================================================================
    def create_task(self, project_code: str, title: str, description: str = "",
                     tags: Optional[List[str]] = None,
                     assignees: Optional[List[str]] = None) -> str:
        """Reserve the next id for ``project_code`` and create the task at the TOP of the leftmost
        column. Returns the new task id (e.g. ``ENG-4``)."""
        code = ids.normalize_project_code(project_code)
        self._require_project(code)
        clean_tags = self._validate_tags(tags or [])
        status_id = self._leftmost_column_id()

        number = self._reserve_next_number(code)
        task_id = f"{code}-{number}"
        order = self._order_at_top_of(status_id)
        self._atomic_write(self._task_path(task_id), {
            "id": task_id,
            "title": str(title),
            "description": str(description),
            "tags": clean_tags,
            "status": status_id,
            "order": order,
            "assignees": list(assignees or []),
        })
        return task_id

    def update_task(self, task_id: str, title: str, description: str,
                    tags: Optional[List[str]] = None,
                    assignees: Optional[List[str]] = None) -> None:
        """Edit a task's content (title / description / tags / assignees). Status + order are
        board-positional and change only via ``move_task``; the id is immutable."""
        ids.validate_task_id(task_id)
        clean_tags = self._validate_tags(tags or [])

        def mutate(task: dict) -> None:
            task["title"] = str(title)
            task["description"] = str(description)
            task["tags"] = clean_tags
            task["assignees"] = list(assignees or [])

        locked_read_modify_write(self._task_path(task_id), mutate)

    def delete_task(self, task_id: str) -> None:
        ids.validate_task_id(task_id)
        path = self._task_path(task_id)
        if not path.is_file():
            raise ValueError(f"Task '{task_id}' does not exist.")
        path.unlink()

    def move_task(self, task_id: str, status_id: str, index: int) -> None:
        """Drag-and-drop: place ``task_id`` into column ``status_id`` at ``index`` (0 = top). Computes
        a fractional ``order`` between the neighbors there, rebalancing the lane only if it collapses."""
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
    #  Columns
    # ==============================================================================================
    def create_column(self, name: str) -> str:
        column_id = ids.new_id("col")
        order = self._max_order(self._entries(COLUMNS_DIR)) + ORDER_STEP
        self._atomic_write(self._column_path(column_id),
                           {"id": column_id, "name": str(name), "order": order})
        return column_id

    def rename_column(self, column_id: str, name: str) -> None:
        ids.validate_generated_id(column_id, "column")
        locked_read_modify_write(self._column_path(column_id),
                                 lambda column: column.__setitem__("name", str(name)))

    def move_column(self, column_id: str, direction: str) -> None:
        ids.validate_generated_id(column_id, "column")
        if direction not in ("left", "right"):
            raise ValueError(f"direction must be 'left' or 'right', not '{direction}'.")
        columns = sorted(self._entries(COLUMNS_DIR), key=lambda column: column["order"])
        position = next((i for i, column in enumerate(columns) if column["id"] == column_id), None)
        if position is None:
            raise ValueError(f"Column '{column_id}' does not exist.")
        neighbor_position = position - 1 if direction == "left" else position + 1
        if not 0 <= neighbor_position < len(columns):
            return
        this_order = columns[position]["order"]
        neighbor = columns[neighbor_position]
        self._set_column_order(column_id, neighbor["order"])
        self._set_column_order(neighbor["id"], this_order)

    def delete_column(self, column_id: str) -> None:
        ids.validate_generated_id(column_id, "column")
        columns = sorted(self._entries(COLUMNS_DIR), key=lambda column: column["order"])
        position = next((i for i, column in enumerate(columns) if column["id"] == column_id), None)
        if position is None:
            raise ValueError(f"Column '{column_id}' does not exist.")
        if len(columns) <= 1:
            raise ValueError("Can't delete the last column — a board needs at least one.")
        target = columns[position + 1] if position + 1 < len(columns) else columns[position - 1]
        orphans = sorted(self._tasks_in_column(column_id), key=lambda task: task["order"])
        next_order = self._max_order(self._tasks_in_column(target["id"])) + ORDER_STEP
        for task in orphans:
            self._set_task_position(task["id"], target["id"], next_order)
            next_order += ORDER_STEP
        self._column_path(column_id).unlink()

    # ==============================================================================================
    #  Tags
    # ==============================================================================================
    def create_tag(self, name: str, color: str) -> str:
        tag_id = ids.new_id("tag")
        self._atomic_write(self._tag_path(tag_id),
                           {"id": tag_id, "name": str(name), "color": str(color)})
        return tag_id

    def update_tag(self, tag_id: str, name: str, color: str) -> None:
        ids.validate_generated_id(tag_id, "tag")

        def mutate(tag: dict) -> None:
            tag["name"] = str(name)
            tag["color"] = str(color)

        locked_read_modify_write(self._tag_path(tag_id), mutate)

    def delete_tag(self, tag_id: str) -> None:
        ids.validate_generated_id(tag_id, "tag")
        path = self._tag_path(tag_id)
        if not path.is_file():
            raise ValueError(f"Tag '{tag_id}' does not exist.")
        for task in self._entries(TASKS_DIR):
            if tag_id in task.get("tags", []):
                locked_read_modify_write(
                    self._task_path(task["id"]),
                    lambda t: t.__setitem__("tags", [x for x in t.get("tags", []) if x != tag_id]))
        path.unlink()

    # ==============================================================================================
    #  Projects
    # ==============================================================================================
    def create_project(self, code: str, color: Optional[str] = None) -> str:
        code = ids.normalize_project_code(code)
        path = self._project_path(code)
        if path.exists():
            raise ValueError(f"Project '{code}' already exists.")
        self._atomic_write(path, {"code": code, "next_num": 1,
                                  "color": color or default_project_color(code)})
        return code

    def set_project_color(self, code: str, color: str) -> None:
        code = ids.normalize_project_code(code)
        locked_read_modify_write(self._project_path(code),
                                 lambda project: project.__setitem__("color", str(color)))

    def rename_project(self, code: str, new_code: str) -> None:
        code = ids.normalize_project_code(code)
        new_code = ids.normalize_project_code(new_code)
        if new_code == code:
            return
        if not self._project_path(code).is_file():
            raise ValueError(f"Project '{code}' does not exist.")
        if self._project_path(new_code).exists():
            raise ValueError(f"Project '{new_code}' already exists.")

        old_project = read_json(self._project_path(code)) or {}
        self._atomic_write(self._project_path(new_code), {
            "code": new_code,
            "next_num": old_project.get("next_num", 1),
            "color": old_project.get("color") or default_project_color(new_code),
        })
        for task in self._tasks_for_project(code):
            old_task_id = task["id"]
            new_task_id = f"{new_code}-{old_task_id.split('-', 1)[1]}"
            task["id"] = new_task_id
            self._atomic_write(self._task_path(new_task_id), task)
            self._task_path(old_task_id).unlink(missing_ok=True)
        self._project_path(code).unlink(missing_ok=True)

    def delete_project(self, code: str) -> None:
        code = ids.normalize_project_code(code)
        path = self._project_path(code)
        if not path.is_file():
            raise ValueError(f"Project '{code}' does not exist.")
        for task in self._tasks_for_project(code):
            self._task_path(task["id"]).unlink(missing_ok=True)
        path.unlink()

    # ==============================================================================================
    #  Internal queries
    # ==============================================================================================
    def _entries(self, subfolder: str) -> List[dict]:
        results: List[dict] = []
        for path in (self._root / subfolder).glob("*.json"):
            entry = read_json(path)
            if entry is not None:
                results.append(entry)
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
        reserved: Dict[str, int] = {}

        def mutate(project: dict) -> None:
            reserved["n"] = int(project.get("next_num", 1))
            project["next_num"] = reserved["n"] + 1

        locked_read_modify_write(self._project_path(code), mutate)
        return reserved["n"]

    def _set_task_position(self, task_id: str, status_id: str, order: float) -> None:
        def mutate(task: dict) -> None:
            task["status"] = status_id
            task["order"] = order

        locked_read_modify_write(self._task_path(task_id), mutate)

    def _set_column_order(self, column_id: str, order: float) -> None:
        locked_read_modify_write(self._column_path(column_id),
                                 lambda column: column.__setitem__("order", order))

    def _rebalance_lane_with_insertion(self, status_id: str, lane_without: List[dict],
                                       index: int, task_id: str) -> None:
        final_ids = [task["id"] for task in lane_without]
        final_ids.insert(index, task_id)
        for position, an_id in enumerate(final_ids):
            self._set_task_position(an_id, status_id, ORDER_STEP * (position + 1))

    # ==============================================================================================
    #  Guards + paths
    # ==============================================================================================
    def _require_project(self, code: str) -> None:
        if not self._project_path(code).is_file():
            raise ValueError(f"Project '{code}' does not exist.")

    def _require_column(self, column_id: str) -> None:
        if not self._column_path(column_id).is_file():
            raise ValueError(f"Column '{column_id}' does not exist.")

    def _validate_tags(self, tags: List[str]) -> List[str]:
        existing = {tag["id"] for tag in self._entries(TAGS_DIR)}
        clean: List[str] = []
        for tag_id in tags:
            ids.validate_generated_id(tag_id, "tag")
            if tag_id not in existing:
                raise ValueError(f"Tag '{tag_id}' does not exist.")
            if tag_id not in clean:
                clean.append(tag_id)
        return clean

    def _task_path(self, task_id: str) -> Path:
        return self._root / TASKS_DIR / f"{ids.validate_task_id(task_id)}.json"

    def _column_path(self, column_id: str) -> Path:
        return self._root / COLUMNS_DIR / f"{ids.validate_generated_id(column_id, 'column')}.json"

    def _tag_path(self, tag_id: str) -> Path:
        return self._root / TAGS_DIR / f"{ids.validate_generated_id(tag_id, 'tag')}.json"

    def _project_path(self, code: str) -> Path:
        return self._root / PROJECTS_DIR / f"{ids.normalize_project_code(code)}.json"

    @staticmethod
    def _atomic_write(target: Path, tree: dict) -> None:
        atomic_write_json(target, tree)
