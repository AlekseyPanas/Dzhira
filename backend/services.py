"""``AppServices`` — the one object that owns the stores and the operations that span more than one.

The HTTP router and the websocket hub both take an ``AppServices`` so cross-store logic (accept an
invite → add a member + delete the invite; delete a board → also purge its invites; build a member
list by resolving ids to usernames; the max-2-owned and owner-only permission checks) lives in exactly
one place. Every method that mutates on a user's behalf takes the acting ``user`` and enforces access.
"""

from pathlib import Path
from typing import List, Optional, Union

from backend.db import ids, paths
from backend.db.accounts import AccountsStore
from backend.db.board_api import BoardAPI
from backend.db.boards import BoardsStore
from backend.db.invites import InvitesStore
from backend.db.sessions import SessionStore


class AppServices:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self.root = paths.ensure_db(db_root)
        self.accounts = AccountsStore(self.root)
        self.sessions = SessionStore(self.root)
        self.boards = BoardsStore(self.root)
        self.invites = InvitesStore(self.root)

    # ------------------------------------------------------------------ auth
    def user_for_session(self, session_id: Optional[str]) -> Optional[dict]:
        user_id = self.sessions.get_user_id(session_id)
        return self.accounts.get_user(user_id) if user_id else None

    # ------------------------------------------------------------------ boards
    def board_api(self, board_id: str) -> BoardAPI:
        return BoardAPI(paths.board_dir(self.root, board_id))

    def accessible_board_by_name(self, name: str, user: dict) -> Optional[dict]:
        """The board with this name IF the user may see it, else ``None``."""
        board = self.boards.resolve_by_name(name)
        if board is not None and self.boards.has_access(board, user["id"]):
            return board
        return None

    def default_board_name(self, user: dict) -> Optional[str]:
        boards = self.boards.boards_for_user(user["id"])
        return boards[0]["name"] if boards else None

    def board_members_public(self, board: dict) -> List[dict]:
        """``[{id, username, color, role}]`` for everyone with access, owner first, missing users
        skipped (e.g. a deleted account)."""
        result = []
        for user_id in self.boards.member_ids(board):
            pub = self.accounts.public(user_id)
            if pub is not None:
                result.append({**pub, "role": self.boards.role(board, user_id)})
        return result

    def delete_board(self, user: dict, board_id: str) -> None:
        board = self._require_owner(user, board_id)
        self.invites.delete_for_board(board["id"])
        self.boards.delete_board(board_id)

    def kick(self, user: dict, board_id: str, target_id: str) -> None:
        board = self._require_owner(user, board_id)
        if target_id == board["owner_id"]:
            raise ValueError("The owner can't be kicked.")
        self.boards.kick_member(board_id, target_id)

    def transfer(self, user: dict, board_id: str, new_owner_id: str) -> None:
        self._require_owner(user, board_id)
        self.boards.transfer_ownership(board_id, new_owner_id)

    # ------------------------------------------------------------------ invites
    def create_invite(self, user: dict, board_id: str, invitee_username: str) -> dict:
        board = self._require_access(user, board_id)          # any member may invite ("full access")
        invitee = self.accounts.get_by_username(invitee_username)
        if invitee is None:
            raise ValueError(f"No user named '{invitee_username}'.")
        if invitee["id"] == user["id"]:
            raise ValueError("You can't invite yourself.")
        if self.boards.has_access(board, invitee["id"]):
            raise ValueError("That user is already on this board.")
        return self.invites.create(board_id, invitee["username"].lower(), user["id"])

    def invites_for_user(self, user: dict) -> List[dict]:
        """Pending invites addressed to this user, enriched with board + inviter names for display."""
        out = []
        for invite in self.invites.for_user(user["username"].lower()):
            board = self.boards.get_board(invite["board_id"])
            inviter = self.accounts.public(invite["inviter_id"])
            if board is None:                                 # board vanished — drop the stale invite
                self.invites.delete(invite["id"])
                continue
            out.append({"id": invite["id"], "board_name": board["name"],
                        "inviter": inviter["username"] if inviter else "?"})
        return out

    def invites_for_board(self, user: dict, board_id: str) -> List[dict]:
        self._require_access(user, board_id)
        return [{"id": i["id"], "invitee": i["invitee_lower"]}
                for i in self.invites.for_board(board_id)]

    def accept_invite(self, user: dict, invite_id: str) -> None:
        invite = self._require_own_invite(user, invite_id)
        self.boards.add_member(invite["board_id"], user["id"])
        self.invites.delete(invite_id)

    def reject_invite(self, user: dict, invite_id: str) -> None:
        self._require_own_invite(user, invite_id)
        self.invites.delete(invite_id)

    def withdraw_invite(self, user: dict, invite_id: str) -> None:
        invite = self.invites.get(invite_id)
        if invite is None:
            return
        self._require_access(user, invite["board_id"])        # a board member may withdraw an invite
        self.invites.delete(invite_id)

    # ------------------------------------------------------------------ permission guards
    def _require_access(self, user: dict, board_id: str) -> dict:
        board = self.boards.get_board(board_id)
        if board is None or not self.boards.has_access(board, user["id"]):
            raise ValueError("You don't have access to that board.")
        return board

    def _require_owner(self, user: dict, board_id: str) -> dict:
        board = self._require_access(user, board_id)
        if board["owner_id"] != user["id"]:
            raise ValueError("Only the board owner can do that.")
        return board

    def _require_own_invite(self, user: dict, invite_id: str) -> dict:
        invite = self.invites.get(invite_id)
        if invite is None or invite.get("invitee_lower") != user["username"].lower():
            raise ValueError("No such invite.")
        return invite

    def valid_assignees(self, board: dict, assignees: List[str]) -> List[str]:
        """Keep only ids that are members of the board (order-preserving, de-duped)."""
        allowed = set(self.boards.member_ids(board))
        seen, clean = set(), []
        for uid in assignees or []:
            if uid in allowed and uid not in seen:
                seen.add(uid)
                clean.append(uid)
        return clean
