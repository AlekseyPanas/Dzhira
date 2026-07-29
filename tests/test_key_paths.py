"""The pure key-path grammar + tree helpers — deterministic, no I/O."""

from backend.derived.key_paths import (
    delete_at_path,
    diff_trees,
    get_at_path,
    join_key_path,
    paths_intersect,
    set_at_path,
    split_key_path,
)


def test_split_and_join_roundtrip():
    assert split_key_path("") == []
    assert split_key_path("a/b[2][0]/c") == ["a", "b", 2, 0, "c"]
    assert join_key_path("a/b", "c") == "a/b/c"
    assert join_key_path("a", 3) == "a[3]"
    assert join_key_path("", "root") == "root"


def test_paths_intersect():
    assert paths_intersect("", "anything/here")
    assert paths_intersect("tasks", "tasks/ENG-1.json")     # ancestor
    assert paths_intersect("tasks/ENG-1.json", "tasks")     # descendant
    assert not paths_intersect("tasks/ENG-1.json", "tasks/ENG-2.json")


def test_get_set_delete():
    tree = {}
    set_at_path(tree, ["tasks", "ENG-1.json", "tags"], [])
    set_at_path(tree, ["tasks", "ENG-1.json", "tags", 0], "tag_x")   # extend list
    assert get_at_path(tree, ["tasks", "ENG-1.json", "tags", 0]) == (True, "tag_x")
    assert delete_at_path(tree, ["tasks", "ENG-1.json", "tags", 0]) is True
    assert get_at_path(tree, ["tasks", "ENG-1.json", "tags"]) == (True, [])
    assert get_at_path(tree, ["nope"]) == (False, None)


def test_diff_trees_emits_key_level_changes():
    old = {"title": "a", "tags": ["x", "y"], "order": 1}
    new = {"title": "b", "tags": ["x", "z"], "order": 1, "status": "col_1"}
    emitted = {}
    diff_trees(old, new, "task", lambda path, value: emitted.__setitem__(path, value), "__DELETED__")
    # title changed, tags[1] changed x/y->x/z (equal-length list recurses per index), status added.
    assert emitted == {"task/title": "b", "task/tags[1]": "z", "task/status": "col_1"}


def test_diff_trees_deletion_sentinel():
    old = {"a": 1, "b": 2}
    new = {"a": 1}
    emitted = {}
    diff_trees(old, new, "", lambda path, value: emitted.__setitem__(path, value), "__DELETED__")
    assert emitted == {"b": "__DELETED__"}
