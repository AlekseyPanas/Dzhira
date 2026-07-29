"""The folder mirror: initial scan, key-level publish on change, DELETED on removal.

Split into a deterministic part (drive the apply methods directly — no observer, no timing) and one
end-to-end part that actually runs the watchdog observer, polled with a timeout.
"""

import json
import os
import tempfile
import time

from backend.derived.json_folder_derived_dict import JsonFolderDerivedDict
from backend.derived.pub_sub_derived_dict import DELETED


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _atomic_replace(path, data):
    """Write like BoardAPI does — temp file in the same dir + os.replace over the target."""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temp, path)


def _wait_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


# ------------------------------------------------------------------ deterministic (no observer)
def test_initial_scan_mirrors_the_folder(tmp_path):
    _write(tmp_path / "tasks" / "ENG-1.json", {"id": "ENG-1", "title": "Hi"})
    (tmp_path / "columns").mkdir()

    dd = JsonFolderDerivedDict(tmp_path)
    dd._scan_subtree(tmp_path)
    dd._drain_pending_updates()

    assert dd.read("tasks/ENG-1.json") == {"id": "ENG-1", "title": "Hi"}
    assert dd.read("tasks/ENG-1.json/title") == "Hi"
    assert dd.read("columns") == {}                          # empty dir shows as {}
    assert dd.read("nope") == DELETED


def test_key_level_publish_on_change(tmp_path):
    _write(tmp_path / "tasks" / "ENG-1.json", {"id": "ENG-1", "title": "Old", "order": 1})
    dd = JsonFolderDerivedDict(tmp_path)
    dd._scan_subtree(tmp_path)
    dd._drain_pending_updates()

    received = []
    dd.subscribe("tasks", lambda update: received.append((update.key_path, update.value)))

    # A new file publishes the whole file value.
    _write(tmp_path / "tasks" / "ENG-2.json", {"id": "ENG-2", "title": "New"})
    dd._apply_file_read("tasks/ENG-2.json")
    assert ("tasks/ENG-2.json", {"id": "ENG-2", "title": "New"}) in received

    # A single-key change publishes ONLY that key path.
    received.clear()
    _write(tmp_path / "tasks" / "ENG-1.json", {"id": "ENG-1", "title": "Renamed", "order": 1})
    dd._apply_file_read("tasks/ENG-1.json")
    assert received == [("tasks/ENG-1.json/title", "Renamed")]


def test_delete_publishes_deleted(tmp_path):
    _write(tmp_path / "tasks" / "ENG-1.json", {"id": "ENG-1"})
    dd = JsonFolderDerivedDict(tmp_path)
    dd._scan_subtree(tmp_path)
    dd._drain_pending_updates()

    received = []
    dd.subscribe("tasks/ENG-1.json", lambda update: received.append((update.key_path, update.value)))
    dd._apply_path_deleted("tasks/ENG-1.json")
    assert received == [("tasks/ENG-1.json", DELETED)]
    assert dd.read("tasks/ENG-1.json") == DELETED


def test_malformed_read_is_skipped(tmp_path):
    _write(tmp_path / "tasks" / "ENG-1.json", {"id": "ENG-1", "title": "Good"})
    dd = JsonFolderDerivedDict(tmp_path)
    dd._scan_subtree(tmp_path)
    dd._drain_pending_updates()

    (tmp_path / "tasks" / "ENG-1.json").write_text("{ this is not json", encoding="utf-8")
    dd._apply_file_read("tasks/ENG-1.json")                 # torn mid-write read -> skipped
    assert dd.read("tasks/ENG-1.json") == {"id": "ENG-1", "title": "Good"}


# ------------------------------------------------------------------ end-to-end (real observer)
def test_watchdog_observer_end_to_end(tmp_path):
    (tmp_path / "tasks").mkdir()
    dd = JsonFolderDerivedDict(tmp_path)
    dd.start_watching()
    try:
        _write(tmp_path / "tasks" / "ENG-9.json", {"id": "ENG-9", "title": "Live"})
        assert _wait_until(lambda: dd.read("tasks/ENG-9.json") != DELETED)
        assert dd.read("tasks/ENG-9.json/title") == "Live"

        (tmp_path / "tasks" / "ENG-9.json").unlink()
        assert _wait_until(lambda: dd.read("tasks/ENG-9.json") == DELETED)
    finally:
        dd.stop_watching()


def test_watchdog_survives_atomic_replace_over_existing_file(tmp_path):
    # Regression: an atomic save (temp + os.replace) OVER an existing file must UPDATE the mirror,
    # not drop the entry — on macOS FSEvents this fires a spurious 'deleted' for the live path.
    (tmp_path / "tasks").mkdir()
    task = tmp_path / "tasks" / "ENG-1.json"
    _write(task, {"id": "ENG-1", "status": "todo"})
    dd = JsonFolderDerivedDict(tmp_path)
    dd.start_watching()
    try:
        assert _wait_until(lambda: dd.read("tasks/ENG-1.json") != DELETED)
        _atomic_replace(task, {"id": "ENG-1", "status": "doing"})   # the move/edit write pattern
        assert _wait_until(lambda: dd.read("tasks/ENG-1.json/status") == "doing")
        assert dd.read("tasks/ENG-1.json") == {"id": "ENG-1", "status": "doing"}   # still present
    finally:
        dd.stop_watching()
