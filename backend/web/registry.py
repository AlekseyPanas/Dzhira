"""The derived-dict registry — one map from wire-constant names to live derived-dict instances,
built once at startup by the composition root. The enum MEMBER NAMES are the shared wire constants:
the frontend mirrors them verbatim in ``frontend/src/derived_dicts.ts``, and the websocket hub
resolves a client's ``subscribe(derived_dict, key_path)`` through ``get_derived_dict``.

Dzhira exposes exactly one: ``DB`` — the whole JSON DB folder as a nested tree. (Kept as a
registry/enum anyway so adding a second read surface later is a one-line change on each side.)
"""

from enum import Enum
from typing import Dict, Union

from backend.derived.pub_sub_derived_dict import APubSubDerivedDict


class DerivedDicts(str, Enum):
    DB = "DB"                                               # the entire db/ folder, mirrored


class DerivedDictsRegistry:

    def __init__(self) -> None:
        self._instances: Dict[DerivedDicts, APubSubDerivedDict] = {}

    def register(self, member: DerivedDicts, instance: APubSubDerivedDict) -> None:
        if member in self._instances:
            raise ValueError(f"'{member.value}' is already registered.")
        self._instances[member] = instance

    def get_derived_dict(self, member_or_name: Union[DerivedDicts, str]) -> APubSubDerivedDict:
        """Resolve an enum member OR its wire name (what a websocket client sends)."""
        member = DerivedDicts(member_or_name)               # raises ValueError on unknown names
        if member not in self._instances:
            raise ValueError(f"'{member.value}' has no registered instance.")
        return self._instances[member]
