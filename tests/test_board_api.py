"""BoardAPI: writes land on disk atomically, fractional reorder works, and the delete cascades hold."""

import pytest

from backend.db.layout import COLUMNS_DIR, META_DIR, PROJECTS_DIR, TAGS_DIR, TASKS_DIR
from tests.conftest import exists, load_json


# ------------------------------------------------------------------ projects + task creation
def test_create_project_normalizes_and_rejects_bad_codes(board, db_root):
    assert board.create_project("eng") == "ENG"
    assert load_json(db_root, PROJECTS_DIR, "ENG") == {"code": "ENG", "next_num": 1}
    with pytest.raises(ValueError):
        board.create_project("engg")                        # 4 letters
    with pytest.raises(ValueError):
        board.create_project("ENG")                         # already exists


def test_create_task_reserves_incrementing_ids(board, db_root):
    board.create_column("To Do")
    board.create_project("ENG")
    assert board.create_task("ENG", "First") == "ENG-1"
    assert board.create_task("ENG", "Second") == "ENG-2"
    assert load_json(db_root, PROJECTS_DIR, "ENG")["next_num"] == 3
    task = load_json(db_root, TASKS_DIR, "ENG-2")
    assert task["title"] == "Second" and task["tags"] == []


def test_create_task_requires_existing_project_and_column(board):
    with pytest.raises(ValueError):
        board.create_task("ENG", "no project")              # no project
    board.create_project("ENG")
    with pytest.raises(ValueError):
        board.create_task("ENG", "no column")               # no column to land in


# ------------------------------------------------------------------ fractional reorder / move
def test_move_task_computes_fractional_order(board, db_root):
    col = board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")                           # each new task goes to the TOP
    board.create_task("ENG", "b")
    board.create_task("ENG", "c")
    # Move ENG-1 to the middle (index 1) of its column: order becomes the midpoint of its neighbors.
    board.move_task("ENG-1", col, 1)
    orders = {name: load_json(db_root, TASKS_DIR, name)["order"] for name in ("ENG-1", "ENG-2", "ENG-3")}
    ordered = sorted(orders, key=orders.get)
    assert ordered[1] == "ENG-1"                            # it sits second now


def test_move_task_between_columns(board, db_root):
    col1 = board.create_column("To Do")
    col2 = board.create_column("Done")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.move_task("ENG-1", col2, 0)
    assert load_json(db_root, TASKS_DIR, "ENG-1")["status"] == col2


def test_move_task_rejects_unknown_ids(board):
    col = board.create_column("To Do")
    with pytest.raises(ValueError):
        board.move_task("ENG-1", col, 0)                    # no such task


# ------------------------------------------------------------------ update + delete task
def test_update_and_delete_task(board, db_root):
    board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "old")
    board.update_task("ENG-1", "new title", "new desc", [])
    task = load_json(db_root, TASKS_DIR, "ENG-1")
    assert task["title"] == "new title" and task["description"] == "new desc"
    board.delete_task("ENG-1")
    assert not exists(db_root, TASKS_DIR, "ENG-1")


# ------------------------------------------------------------------ tags + cascade
def test_delete_tag_removes_it_from_tasks(board, db_root):
    board.create_column("To Do")
    board.create_project("ENG")
    tag = board.create_tag("bug", "#ff0000")
    board.create_task("ENG", "buggy", "", [tag])
    assert load_json(db_root, TASKS_DIR, "ENG-1")["tags"] == [tag]
    board.delete_tag(tag)
    assert load_json(db_root, TASKS_DIR, "ENG-1")["tags"] == []
    assert not exists(db_root, TAGS_DIR, tag)


def test_create_task_rejects_unknown_tag(board):
    board.create_column("To Do")
    board.create_project("ENG")
    with pytest.raises(ValueError):
        board.create_task("ENG", "t", "", ["tag_deadbeef"])


# ------------------------------------------------------------------ columns
def test_move_column_swaps_order(board, db_root):
    a = board.create_column("A")
    b = board.create_column("B")
    order_a, order_b = load_json(db_root, COLUMNS_DIR, a)["order"], load_json(db_root, COLUMNS_DIR, b)["order"]
    board.move_column(b, "left")
    assert load_json(db_root, COLUMNS_DIR, a)["order"] == order_b
    assert load_json(db_root, COLUMNS_DIR, b)["order"] == order_a


def test_delete_column_reassigns_tasks_and_guards_last(board, db_root):
    col1 = board.create_column("To Do")
    col2 = board.create_column("Done")
    board.create_project("ENG")
    board.create_task("ENG", "a")                           # lands in col1 (leftmost)
    board.delete_column(col1)
    assert not exists(db_root, COLUMNS_DIR, col1)
    assert load_json(db_root, TASKS_DIR, "ENG-1")["status"] == col2   # reassigned to nearest
    with pytest.raises(ValueError):
        board.delete_column(col2)                           # can't delete the last column


# ------------------------------------------------------------------ project rename + delete cascade
def test_rename_project_reids_tasks(board, db_root):
    board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.create_task("ENG", "b")
    board.rename_project("ENG", "abc")
    assert exists(db_root, TASKS_DIR, "ABC-1") and exists(db_root, TASKS_DIR, "ABC-2")
    assert not exists(db_root, TASKS_DIR, "ENG-1")
    assert exists(db_root, PROJECTS_DIR, "ABC") and not exists(db_root, PROJECTS_DIR, "ENG")
    assert load_json(db_root, TASKS_DIR, "ABC-1")["id"] == "ABC-1"


def test_delete_project_deletes_its_tasks(board, db_root):
    board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.create_task("ENG", "b")
    board.delete_project("ENG")
    assert not exists(db_root, TASKS_DIR, "ENG-1")
    assert not exists(db_root, TASKS_DIR, "ENG-2")
    assert not exists(db_root, PROJECTS_DIR, "ENG")


# ------------------------------------------------------------------ assignee
def test_set_assignee(board, db_root):
    board.set_assignee("Roxhan", "#00ffcc")
    assert load_json(db_root, META_DIR, "assignee") == {"name": "Roxhan", "color": "#00ffcc"}
