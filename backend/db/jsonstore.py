"""Shared JSON file helpers: atomic writes + flocked read-modify-write.

Every store (accounts, boards, invites, sessions, the per-board BoardAPI) reads/writes single JSON
files the same safe way — a temp-file-then-rename atomic write, and a per-file flock for read-modify-
write — so a reader (including the watchdog derived dict) never sees a torn file. Extracted here so
that logic lives in exactly one place. (Ported from the original SettingsAPI locking model.)
"""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional


def read_json(path: Path) -> Optional[dict]:
    """Parse a JSON object file, or ``None`` if it's missing / unreadable / not an object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def atomic_write_json(target: Path, tree: dict) -> None:
    """Write via a temp file in the same directory + rename — a reader never sees a torn file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_path = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temp_file:
            json.dump(tree, temp_file, indent=2)
        os.replace(temp_path, target)                       # atomic on POSIX
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def locked_read_modify_write(target: Path, mutate: Callable[[dict], None]) -> None:
    """flock the target file, parse, ``mutate`` in place, atomic temp+rename, release."""
    with _flock_current_inode(target) as locked_file:
        tree = json.loads(locked_file.read())
        if not isinstance(tree, dict):
            raise ValueError(f"'{target.name}' does not contain a json object.")
        mutate(tree)
        atomic_write_json(target, tree)


@contextmanager
def _flock_current_inode(target: Path):
    """flock the file CURRENTLY at ``target`` — with the open-then-verify-inode retry, because a
    writer replaces the file by rename, so a waiter can win the lock on an inode that is no longer
    the file at that path."""
    while True:
        try:
            locked_file = open(target, "r+", encoding="utf-8")
        except FileNotFoundError:
            raise ValueError(f"'{target.name}' does not exist.")
        fcntl.flock(locked_file.fileno(), fcntl.LOCK_EX)
        try:
            if os.fstat(locked_file.fileno()).st_ino == os.stat(target).st_ino:
                yield locked_file                           # fd is the live file: safe to RMW
                return
        except FileNotFoundError:                           # deleted while we waited: next loop
            pass
        finally:
            fcntl.flock(locked_file.fileno(), fcntl.LOCK_UN)
            locked_file.close()
