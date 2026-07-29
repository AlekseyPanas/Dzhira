"""The shared key-path grammar + nested-tree navigation helpers.

Grammar: ``"/"`` separates dict keys; ``"[i]"`` suffixes address list elements — e.g.
``"tasks/ENG-222.json/tags[0]"``. The separator MUST be "/" (not "."): file names like
``ENG-222.json`` are ordinary dict keys in the folder mirror, so dots are data, never separators.
The empty path ``""`` addresses the whole tree.

Ported (near-verbatim) from eventCamera's ``derived_dicts/library/key_paths.py`` and mirrored on the
frontend in ``frontend/src/key_paths.ts``. Used by the pub/sub core (§4) and the folder mirror (§5).
"""

import re
from typing import Callable, Dict, List, Tuple, Union

from backend.derived.node_types import TNodeValue

# One parsed path step: a dict key (str) or a list index (int).
TPathStep = Union[str, int]

_INDEX_SUFFIX_RE = re.compile(r"\[(\d+)\]")


def split_key_path(key_path: str) -> List[TPathStep]:
    """``"a/b[2][0]/c"`` -> ``["a", "b", 2, 0, "c"]``. An empty path -> ``[]`` (the whole tree)."""
    if key_path == "":
        return []
    steps: List[TPathStep] = []
    for segment in key_path.split("/"):
        bracket_at = segment.find("[")
        name = segment if bracket_at == -1 else segment[:bracket_at]
        steps.append(name)
        if bracket_at != -1:
            for index_text in _INDEX_SUFFIX_RE.findall(segment[bracket_at:]):
                steps.append(int(index_text))
    return steps


def join_key_path(parent_path: str, step: TPathStep) -> str:
    """Append one step: a dict key adds ``/key`` (no leading slash at root), an int adds ``[i]``."""
    if isinstance(step, int):
        return f"{parent_path}[{step}]"
    return f"{parent_path}/{step}" if parent_path else step


def paths_intersect(key_path_a: str, key_path_b: str) -> bool:
    """True iff a change at one path can affect the value at the other (ancestor/descendant/equal):
    one path's steps are a prefix of the other's. The empty path intersects everything."""
    steps_a = split_key_path(key_path_a)
    steps_b = split_key_path(key_path_b)
    shorter, longer = (steps_a, steps_b) if len(steps_a) <= len(steps_b) else (steps_b, steps_a)
    return longer[:len(shorter)] == shorter


def get_at_path(tree: TNodeValue, steps: List[TPathStep]) -> Tuple[bool, TNodeValue]:
    """Walk ``steps`` through nested dicts/lists. Returns ``(found, value)`` — never raises."""
    current = tree
    for step in steps:
        if isinstance(step, int):
            if isinstance(current, list) and 0 <= step < len(current):
                current = current[step]
                continue
        elif isinstance(current, dict) and step in current:
            current = current[step]
            continue
        return False, None
    return True, current


def set_at_path(tree: Dict[str, TNodeValue], steps: List[TPathStep], value: TNodeValue) -> None:
    """Set ``value`` at ``steps``, creating missing parents (creates-are-updates, §4.1).

    A missing dict key creates a nested dict; a missing/short list index EXTENDS the list with
    ``None`` filler up to that index. An existing intermediate of the wrong container type is
    replaced outright. ``steps`` must be non-empty (the whole-tree case is a plain reassignment
    at the caller).
    """
    parent = tree
    for step_number, step in enumerate(steps[:-1]):
        next_step = steps[step_number + 1]
        wanted_child_type = list if isinstance(next_step, int) else dict
        if isinstance(step, int):
            while len(parent) <= step:                      # parent guaranteed list by prior step
                parent.append(None)
            if not isinstance(parent[step], wanted_child_type):
                parent[step] = wanted_child_type()
            parent = parent[step]
        else:
            if not isinstance(parent, dict):
                raise ValueError(f"Cannot set dict key '{step}' inside a non-dict parent.")
            if not isinstance(parent.get(step), wanted_child_type):
                parent[step] = wanted_child_type()
            parent = parent[step]
    last_step = steps[-1]
    if isinstance(last_step, int):
        if not isinstance(parent, list):
            raise ValueError(f"Cannot set list index [{last_step}] inside a non-list parent.")
        while len(parent) <= last_step:
            parent.append(None)
        parent[last_step] = value
    else:
        if not isinstance(parent, dict):
            raise ValueError(f"Cannot set dict key '{last_step}' inside a non-dict parent.")
        parent[last_step] = value


def delete_at_path(tree: Dict[str, TNodeValue], steps: List[TPathStep]) -> bool:
    """Delete the value at ``steps``. Returns False when the path doesn't exist. A list-index
    delete REMOVES the element (the list shrinks and later elements shift left)."""
    if not steps:
        return False
    found, parent = get_at_path(tree, steps[:-1])
    if not found:
        return False
    last_step = steps[-1]
    if isinstance(last_step, int):
        if isinstance(parent, list) and 0 <= last_step < len(parent):
            del parent[last_step]
            return True
        return False
    if isinstance(parent, dict) and last_step in parent:
        del parent[last_step]
        return True
    return False


def diff_trees(old_tree: TNodeValue, new_tree: TNodeValue, base_path: str,
               emit: Callable[[str, TNodeValue], None], deleted_sentinel: TNodeValue) -> None:
    """Diff two value trees to key-level updates, at the deepest granularity that stays honest:
    dicts recurse per key; equal-length lists recurse per index; a length-changed list is emitted
    whole at its own path; leaves/type-changes emit at their own path. Emits nothing when equal."""
    if isinstance(old_tree, dict) and isinstance(new_tree, dict):
        for key in old_tree:
            if key not in new_tree:
                emit(join_key_path(base_path, key), deleted_sentinel)
        for key, new_value in new_tree.items():
            if key not in old_tree:
                emit(join_key_path(base_path, key), new_value)
            else:
                diff_trees(old_tree[key], new_value, join_key_path(base_path, key),
                           emit, deleted_sentinel)
        return
    if isinstance(old_tree, list) and isinstance(new_tree, list) and len(old_tree) == len(new_tree):
        for index, (old_element, new_element) in enumerate(zip(old_tree, new_tree)):
            diff_trees(old_element, new_element, join_key_path(base_path, index),
                       emit, deleted_sentinel)
        return
    if old_tree != new_tree:                                # leaf / type change / resized list
        emit(base_path, new_tree)
