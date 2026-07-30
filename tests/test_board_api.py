"""BoardAPI (per-board content writer): atomic writes, fractional reorder, cascades, multi-assignee."""

import pytest

from backend.db.paths import COLUMNS_DIR, PROJECTS_DIR, TAGS_DIR, TASKS_DIR, VIEWS_DIR
from backend.db.seeding import default_project_color
from tests.conftest import exists, load_json


def test_set_view_persists_per_user_filter(board, board_dir):
    board.set_view("usr_11111111", assignees=["usr_22222222"], tags=["tag_aaaaaaaa"], projects=["ENG"])
    assert load_json(board_dir, VIEWS_DIR, "usr_11111111") == {
        "assignees": ["usr_22222222"], "tags": ["tag_aaaaaaaa"], "projects": ["ENG"]}
    board.set_view("usr_11111111")                                      # empty -> cleared filters
    assert load_json(board_dir, VIEWS_DIR, "usr_11111111") == {"assignees": [], "tags": [], "projects": []}


# ------------------------------------------------------------------ projects + task creation
def test_create_project_normalizes_and_rejects_bad_codes(board, board_dir):
    assert board.create_project("eng") == "ENG"
    project = load_json(board_dir, PROJECTS_DIR, "ENG")
    assert project["code"] == "ENG" and project["next_num"] == 1
    assert project["color"] == default_project_color("ENG")
    with pytest.raises(ValueError):
        board.create_project("engg")
    with pytest.raises(ValueError):
        board.create_project("ENG")


def test_create_task_reserves_incrementing_ids_with_assignees(board, board_dir):
    board.create_column("To Do")
    board.create_project("ENG")
    assert board.create_task("ENG", "First", assignees=["usr_11111111"]) == "ENG-1"
    assert board.create_task("ENG", "Second") == "ENG-2"
    assert load_json(board_dir, PROJECTS_DIR, "ENG")["next_num"] == 3
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["assignees"] == ["usr_11111111"]
    assert load_json(board_dir, TASKS_DIR, "ENG-2")["assignees"] == []


def test_task_deadline_stored_cleared_and_validated(board, board_dir):
    board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "t", deadline="2026-08-01")
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["deadline"] == "2026-08-01"
    board.update_task("ENG-1", "t", "", deadline="")                    # clear it
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["deadline"] is None
    with pytest.raises(ValueError):
        board.create_task("ENG", "bad", deadline="not-a-date")


def test_update_task_sets_assignees(board, board_dir):
    board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "t")
    board.update_task("ENG-1", "t2", "desc", [], ["usr_aaaaaaaa", "usr_bbbbbbbb"])
    task = load_json(board_dir, TASKS_DIR, "ENG-1")
    assert task["title"] == "t2" and task["assignees"] == ["usr_aaaaaaaa", "usr_bbbbbbbb"]


def test_create_task_requires_project_and_column(board):
    with pytest.raises(ValueError):
        board.create_task("ENG", "no project")
    board.create_project("ENG")
    with pytest.raises(ValueError):
        board.create_task("ENG", "no column")


# ------------------------------------------------------------------ fractional reorder / move
def _lane_order(board_dir, *names):
    """The given task names sorted by their stored `order` (ascending = top-to-bottom)."""
    orders = {n: load_json(board_dir, TASKS_DIR, n)["order"] for n in names}
    return sorted(orders, key=orders.get)


def test_move_task_orders_after_anchor(board, board_dir):
    col = board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.create_task("ENG", "b")
    board.create_task("ENG", "c")                       # new tasks go to top: order ENG-3<ENG-2<ENG-1
    board.move_task("ENG-1", col, "ENG-3")              # drop ENG-1 right after ENG-3
    assert _lane_order(board_dir, "ENG-1", "ENG-2", "ENG-3") == ["ENG-3", "ENG-1", "ENG-2"]


def test_move_task_anchor_none_goes_to_top(board, board_dir):
    col = board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.create_task("ENG", "b")
    board.move_task("ENG-1", col, None)                 # None anchor = top of the column
    assert _lane_order(board_dir, "ENG-1", "ENG-2")[0] == "ENG-1"


def test_move_task_unknown_anchor_goes_to_bottom(board, board_dir):
    col = board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.create_task("ENG", "b")                       # ENG-2 on top, ENG-1 below
    board.move_task("ENG-2", col, "ENG-404")            # stale/absent anchor = bottom of the lane
    assert _lane_order(board_dir, "ENG-1", "ENG-2")[-1] == "ENG-2"


def test_move_task_between_columns(board, board_dir):
    col1 = board.create_column("To Do")
    col2 = board.create_column("Done")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.move_task("ENG-1", col2, None)
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["status"] == col2


# ------------------------------------------------------------------ tags + cascade
def test_delete_tag_removes_it_from_tasks(board, board_dir):
    board.create_column("To Do")
    board.create_project("ENG")
    tag = board.create_tag("bug", "#ff0000")
    board.create_task("ENG", "buggy", "", [tag])
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["tags"] == [tag]
    board.delete_tag(tag)
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["tags"] == []
    assert not exists(board_dir, TAGS_DIR, tag)


# ------------------------------------------------------------------ columns
def test_delete_column_reassigns_tasks_and_guards_last(board, board_dir):
    col1 = board.create_column("To Do")
    col2 = board.create_column("Done")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.delete_column(col1)
    assert not exists(board_dir, COLUMNS_DIR, col1)
    assert load_json(board_dir, TASKS_DIR, "ENG-1")["status"] == col2
    with pytest.raises(ValueError):
        board.delete_column(col2)


def test_move_column_swaps_order(board, board_dir):
    a = board.create_column("A")
    b = board.create_column("B")
    order_a, order_b = load_json(board_dir, COLUMNS_DIR, a)["order"], load_json(board_dir, COLUMNS_DIR, b)["order"]
    board.move_column(b, "left")
    assert load_json(board_dir, COLUMNS_DIR, a)["order"] == order_b
    assert load_json(board_dir, COLUMNS_DIR, b)["order"] == order_a


# ------------------------------------------------------------------ project rename + delete cascade
def test_rename_project_reids_tasks_and_keeps_color(board, board_dir):
    board.create_column("To Do")
    board.create_project("ENG", color="#123456")
    board.create_task("ENG", "a")
    board.rename_project("ENG", "abc")
    assert exists(board_dir, TASKS_DIR, "ABC-1") and not exists(board_dir, TASKS_DIR, "ENG-1")
    assert load_json(board_dir, PROJECTS_DIR, "ABC")["color"] == "#123456"


def test_delete_project_deletes_its_tasks(board, board_dir):
    board.create_column("To Do")
    board.create_project("ENG")
    board.create_task("ENG", "a")
    board.delete_project("ENG")
    assert not exists(board_dir, TASKS_DIR, "ENG-1")
    assert not exists(board_dir, PROJECTS_DIR, "ENG")
