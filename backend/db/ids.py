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
# Generated ids: a short prefix, an underscore, and 8 hex chars.
_GENERATED_ID_RE = re.compile(r"^[a-z]+_[0-9a-f]{8}$")


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
