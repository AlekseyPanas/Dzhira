"""The invites store: pending board invitations.

An invite is ``invites/<iid>.json = {id, board_id, invitee_lower, inviter_id}`` — an offer for a
username (case-folded) to join a board. Accept adds the user to the board's members and deletes the
invite; reject/withdraw just delete it. Listings scan the folder (tiny scale for a joke showcase).
"""

from pathlib import Path
from typing import List, Optional, Union

from backend.db import ids
from backend.db.jsonstore import atomic_write_json, read_json
from backend.db.paths import INVITES_DIR


class InvitesStore:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self._root = Path(db_root)

    def create(self, board_id: str, invitee_lower: str, inviter_id: str) -> dict:
        for existing in self.for_board(board_id):
            if existing.get("invitee_lower") == invitee_lower:
                raise ValueError("That user already has a pending invite to this board.")
        invite_id = ids.new_id("inv")
        invite = {"id": invite_id, "board_id": board_id,
                  "invitee_lower": invitee_lower, "inviter_id": inviter_id}
        atomic_write_json(self._path(invite_id), invite)
        return invite

    def get(self, invite_id: str) -> Optional[dict]:
        ids.validate_generated_id(invite_id, "invite")
        return read_json(self._path(invite_id))

    def for_user(self, invitee_lower: str) -> List[dict]:
        return [i for i in self._all() if i.get("invitee_lower") == invitee_lower]

    def for_board(self, board_id: str) -> List[dict]:
        return [i for i in self._all() if i.get("board_id") == board_id]

    def delete(self, invite_id: str) -> None:
        ids.validate_generated_id(invite_id, "invite")
        self._path(invite_id).unlink(missing_ok=True)

    def delete_for_board(self, board_id: str) -> None:
        for invite in self.for_board(board_id):
            self._path(invite["id"]).unlink(missing_ok=True)

    def _all(self) -> List[dict]:
        folder = self._root / INVITES_DIR
        if not folder.is_dir():
            return []
        return [inv for path in folder.glob("*.json") if (inv := read_json(path)) is not None]

    def _path(self, invite_id: str) -> Path:
        return self._root / INVITES_DIR / f"{invite_id}.json"
