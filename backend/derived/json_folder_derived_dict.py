"""``JsonFolderDerivedDict`` — a live, read-only mirror of a folder of ``.json`` files.

This is Dzhira's whole persistence-read side. It holds an in-memory MIRROR of the DB folder tree:
directories are nested dicts, each ``.json`` file's key holds that file's parsed content. So the key
grammar runs straight through: ``tasks/ENG-222.json/title``. Empty directories ARE represented (as
empty dicts) — the seeded ``tasks/``, ``columns/`` … folders show even when empty. Non-``.json``
files are invisible.

A watchdog observer re-reads any changed file, DIFFS old-vs-new to key level, updates the mirror, and
publishes each changed key path (value, or DELETED) — whether the change came from the ``BoardAPI``,
a hand edit, or a ``git pull``. This is the read/observe side ONLY; it never writes. Writers rename
atomically, so a read here always sees a complete old-or-new file; a malformed mid-write read is
SKIPPED (returns ``None`` from the parse), never poisoning the mirror.

Merges eventCamera's ``AWatchdogFolderMirror`` + ``FolderContentsDerivedDict`` + a JSON parser into
one concrete class — Dzhira needs exactly this flavor, so the format-agnostic layering there would be
ceremony. Lifecycle (``start_watching`` / ``stop_watching``) is owned by the composition root (§8);
downstreams only subscribe. Observer-first ordering in ``start_watching`` is deliberate: a change
racing the initial scan just produces a duplicate event, and every apply diffs against the mirror, so
a duplicate is a no-op — the reverse order could drop a change that lands in the gap.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.derived.key_paths import (
    delete_at_path,
    diff_trees,
    get_at_path,
    set_at_path,
    split_key_path,
)
from backend.derived.node_types import TNodeValue
from backend.derived.pub_sub_derived_dict import DELETED, APubSubDerivedDict
from backend.util.logs import warn

FILE_EXTENSION = ".json"


class JsonFolderDerivedDict(APubSubDerivedDict):

    def __init__(self, root_folder: Union[str, Path]) -> None:
        super().__init__()
        self._root_folder = Path(root_folder).resolve()
        self._mirror: Dict[str, TNodeValue] = {}
        self._observer: Optional[Observer] = None

    def _current_full(self) -> Dict[str, TNodeValue]:
        return self._mirror

    # ------------------------------------------------------------------ lifecycle
    def start_watching(self) -> None:
        """Start the observer, THEN scan the folder in (see the module docstring on ordering)."""
        if self._observer is not None:
            return
        self._observer = Observer()
        self._observer.schedule(_FolderEventForwarder(self), str(self._root_folder), recursive=True)
        self._observer.start()
        self._scan_subtree(self._root_folder)
        self._drain_pending_updates()

    def stop_watching(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join()
        self._observer = None

    # ------------------------------------------------------------------ parse hook
    @staticmethod
    def _parse_file(raw_text: str, rel_file_path: str) -> Optional[TNodeValue]:
        """Parse one file's raw text, or ``None`` for "malformed — SKIP this event, keep the
        previous mirror value" (the mid-write protection)."""
        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            return None                                     # likely a torn mid-write read — skip

    # ------------------------------------------------------------------ scanning / applying
    def _scan_subtree(self, absolute_folder: Path) -> None:
        """Mirror in every directory and ``.json`` file under ``absolute_folder`` (recursive)."""
        for current_dir, _child_dirs, child_file_names in os.walk(absolute_folder):
            rel_dir = self._relative_posix(current_dir)
            if rel_dir is None:
                continue
            if rel_dir != "":
                self._apply_directory_created(rel_dir)
            for file_name in sorted(child_file_names):
                if file_name.endswith(FILE_EXTENSION):
                    rel_file = f"{rel_dir}/{file_name}" if rel_dir else file_name
                    self._apply_file_read(rel_file)

    def _apply_file_read(self, rel_file_path: str) -> None:
        """(Re-)read + parse one file and publish the key-level diff vs the mirror."""
        absolute = self._root_folder / rel_file_path
        try:
            raw_text = absolute.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._apply_path_deleted(rel_file_path)         # raced a deletion; treat as deleted
            return
        except OSError as error:
            warn(f"Could not read '{absolute}': {error}. Keeping the previous mirror value.")
            return
        new_tree = self._parse_file(raw_text, rel_file_path)
        if new_tree is None:                                # malformed (likely mid-write) -> SKIP
            return
        steps = split_key_path(rel_file_path)
        with self._state_lock:
            found, old_tree = get_at_path(self._mirror, steps)
            if not found:
                set_at_path(self._mirror, steps, new_tree)
                self._publish(rel_file_path, new_tree)
            elif old_tree != new_tree:
                # Collect the key-level diff FIRST (pure), then swap the mirror and publish every
                # changed path under the one lock hold — one atomic multi-key change.
                changed: List[Tuple[str, TNodeValue]] = []
                diff_trees(old_tree, new_tree, rel_file_path,
                           lambda path, value: changed.append((path, value)), DELETED)
                set_at_path(self._mirror, steps, new_tree)
                for changed_path, changed_value in changed:
                    self._publish(changed_path, changed_value)
        self._drain_pending_updates()

    def _apply_directory_created(self, rel_dir_path: str) -> None:
        """Represent a (possibly empty) new directory as an empty dict in the mirror."""
        steps = split_key_path(rel_dir_path)
        with self._state_lock:
            found, _ = get_at_path(self._mirror, steps)
            if not found:
                set_at_path(self._mirror, steps, {})
                self._publish(rel_dir_path, {})
        self._drain_pending_updates()

    def _apply_path_deleted(self, rel_path: str) -> None:
        """Drop a file or directory subtree from the mirror; one DELETED publish covers it."""
        with self._state_lock:
            existed = delete_at_path(self._mirror, split_key_path(rel_path))
            if existed:
                self._publish(rel_path, DELETED)
        self._drain_pending_updates()

    # ------------------------------------------------------------------ watchdog entry
    def _on_filesystem_event(self, event: FileSystemEvent) -> None:
        """Runs on the observer thread. We do NOT trust the event TYPE — only the path(s) it names —
        and reconcile each against disk truth. This is deliberate: an atomic save (temp file +
        ``os.replace`` over the existing target, how ``BoardAPI`` writes) fires, on macOS FSEvents,
        a spurious ``deleted`` for a path that is actually still there. Trusting that ``deleted``
        would drop the entry from the mirror and never re-add it. Reconciling against disk makes the
        mirror robust to whatever the platform's event stream reports (spurious deletes, coalesced
        renames, missing creates)."""
        try:
            if event.event_type == "moved":
                self._reconcile_path(self._relative_posix(event.src_path))
                self._reconcile_path(self._relative_posix(event.dest_path))
            else:
                self._reconcile_path(self._relative_posix(event.src_path))
        except Exception as error:                          # the observer thread must never die
            warn(f"Watchdog event handling failed for {event!r}: {error!r}")

    def _reconcile_path(self, rel: Optional[str]) -> None:
        """Bring one path in line with disk, whatever the event claimed happened to it: a directory
        gets (re-)scanned, an existing ``.json`` file gets (re-)read + diffed, and a path that is
        genuinely gone is dropped from the mirror. Empty/root/outside paths are ignored."""
        if not rel:                                         # outside root, or the root itself
            return
        absolute = self._root_folder / rel
        if absolute.is_dir():
            self._scan_subtree(absolute)                    # may have arrived with contents already
            self._drain_pending_updates()
        elif absolute.is_file():
            if rel.endswith(FILE_EXTENSION):
                self._apply_file_read(rel)
        else:
            self._apply_path_deleted(rel)

    # ------------------------------------------------------------------ path helper
    def _relative_posix(self, absolute_path: str) -> Optional[str]:
        """Path of an event target relative to the root ("" = the root itself); None if outside."""
        try:
            relative = Path(absolute_path).resolve().relative_to(self._root_folder).as_posix()
        except ValueError:
            return None
        return "" if relative == "." else relative          # relative_to() spells the root "."


class _FolderEventForwarder(FileSystemEventHandler):
    """Thin adapter: watchdog wants a handler object; the mirror wants one entry point."""

    def __init__(self, folder_mirror: JsonFolderDerivedDict) -> None:
        self._folder_mirror = folder_mirror

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._folder_mirror._on_filesystem_event(event)
