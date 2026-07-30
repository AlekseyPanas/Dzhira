"""Id + name validation and generation for the DB entities.

Every id here can end up as a FILE NAME (``tasks/<task_id>.json``, ``columns/<col_id>.json`` …), so
the validators are also the traversal guard — a client-supplied task id or project code is checked
against a strict pattern before it is ever joined onto a path. Generated ids (columns, tags) are
opaque random hex, so they need no validation on the way back in.
"""

import re
import secrets

# A project code is exactly three ASCII letters, stored uppercase (e.g. ENG, DZH).
_PROJECT_CODE_RE = re.compile(r"^[A-Za-z]{3}$")
# A task id is a project code, a dash, and a positive integer (e.g. ENG-222).
_TASK_ID_RE = re.compile(r"^[A-Z]{3}-[1-9][0-9]*$")
# Generated ids: a short prefix, an underscore, and 8 hex chars (usr_, brd_, inv_, col_, tag_).
_GENERATED_ID_RE = re.compile(r"^[a-z]+_[0-9a-f]{8}$")
# A username: 1-24 chars of letters/digits/._- (filename + URL safe). Case-INSENSITIVE uniqueness.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,24}$")
# A board name: 1-40 chars of letters/digits/space/_- (shown as-is; unique case-insensitively).
_BOARD_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")


def new_id(prefix: str) -> str:
    """A fresh opaque id like ``col_1a2b3c4d`` — used for columns and tags (whose names are mutable,
    so the id must be stable and independent of the name)."""
    return f"{prefix}_{secrets.token_hex(4)}"


def normalize_project_code(code: str) -> str:
    """Validate + uppercase a client-supplied project code, or raise ``ValueError``."""
    if not isinstance(code, str) or not _PROJECT_CODE_RE.match(code):
        raise ValueError(f"'{code}' is not a valid project code (exactly 3 letters).")
    return code.upper()


def validate_task_id(task_id: str) -> str:
    """Validate a client-supplied task id (also the traversal guard), or raise ``ValueError``."""
    if not isinstance(task_id, str) or not _TASK_ID_RE.match(task_id):
        raise ValueError(f"'{task_id}' is not a valid task id (e.g. ENG-222).")
    return task_id


def validate_generated_id(entity_id: str, kind: str) -> str:
    """Validate a client-supplied column/tag id (traversal guard), or raise ``ValueError``."""
    if not isinstance(entity_id, str) or not _GENERATED_ID_RE.match(entity_id):
        raise ValueError(f"'{entity_id}' is not a valid {kind} id.")
    return entity_id


def project_code_of_task(task_id: str) -> str:
    """``ENG-222`` -> ``ENG``."""
    return task_id.split("-", 1)[0]


def validate_username(username: str) -> str:
    """Validate a client-supplied username (also the ``user_names/`` index filename safety), returning
    it trimmed as entered. Uniqueness is enforced case-insensitively via ``username_lower`` elsewhere."""
    trimmed = username.strip() if isinstance(username, str) else ""
    if not _USERNAME_RE.match(trimmed):
        raise ValueError("Username must be 1-24 characters: letters, digits, . _ or - only.")
    return trimmed


def username_lower(username: str) -> str:
    """The case-folded key used for uniqueness + login lookup (Bob and bob are the same user)."""
    return validate_username(username).lower()


def validate_board_name(name: str) -> str:
    """Validate a board name, returning it trimmed as entered (shown as-is; unique case-insensitively)."""
    trimmed = name.strip() if isinstance(name, str) else ""
    if not _BOARD_NAME_RE.match(trimmed):
        raise ValueError("Board name must be 1-40 characters: letters, digits, spaces, _ or - only.")
    return trimmed


def board_name_lower(name: str) -> str:
    return validate_board_name(name).lower()
