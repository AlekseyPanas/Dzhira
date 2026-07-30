"""``AppServices`` — the one object that owns the stores and the operations that span more than one.

The HTTP router and the websocket hub both take an ``AppServices`` so cross-store logic (accept an
invite → add a member + delete the invite; delete a board → also purge its invites; build a member
list by resolving ids to usernames; the max-2-owned and owner-only permission checks) lives in exactly
one place. Every method that mutates on a user's behalf takes the acting ``user`` and enforces access.
"""

import threading
from pathlib import Path
from typing import Dict, List, Optional, Union

from backend.db import ids, paths
from backend.db.accounts import AccountsStore
from backend.db.board_api import BoardAPI
from backend.db.boards import BoardsStore
from backend.db.invites import InvitesStore
from backend.db.sessions import SessionStore
from backend.derived.json_folder_derived_dict import JsonFolderDerivedDict
from backend.util.logs import warn


class AppServices:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self.root = paths.ensure_db(db_root)
        self.accounts = AccountsStore(self.root)
        self.sessions = SessionStore(self.root)
        self.boards = BoardsStore(self.root)
        self.invites = InvitesStore(self.root)
        # ONE live mirror per board that has >= 1 websocket, ref-counted: created (and its single
        # watcher started) on the first connection, dropped on the last. Every socket on the board
        # subscribes to this same mirror, so publish fans out to all of them (the pub/sub core is
        # multi-subscriber). Writes poke the ONE mirror (notify_board_changed) so live updates don't
        # depend on watchdog/inotify firing. Guarded: sockets acquire/release on their own threads
        # while HTTP writes poke from the request threadpool.
        self._board_mirrors: Dict[str, dict] = {}           # board_id -> {"mirror": …, "refs": int}
        self._mirrors_lock = threading.Lock()

    # ------------------------------------------------------------------ live board mirrors (shared)
    def acquire_board_mirror(self, board_id: str) -> JsonFolderDerivedDict:
        """Get the board's shared mirror, creating + starting it on the first caller. Ref count up.
        start_watching runs under the lock (a fast folder scan) so the mirror is fully populated
        before any subscriber reads its snapshot."""
        with self._mirrors_lock:
            entry = self._board_mirrors.get(board_id)
            if entry is None:
                mirror = JsonFolderDerivedDict(paths.board_dir(self.root, board_id))
                mirror.start_watching()
                self._board_mirrors[board_id] = {"mirror": mirror, "refs": 1}
                return mirror
            entry["refs"] += 1
            return entry["mirror"]

    def release_board_mirror(self, board_id: str) -> None:
        """Ref count down; on the last release, drop the mirror and stop its watcher OUTSIDE the lock
        (``stop_watching`` joins the observer thread, which can be slow — don't serialize others)."""
        to_stop = None
        with self._mirrors_lock:
            entry = self._board_mirrors.get(board_id)
            if entry is None:
                return
            entry["refs"] -= 1
            if entry["refs"] <= 0:
                self._board_mirrors.pop(board_id, None)
                to_stop = entry["mirror"]
        if to_stop is not None:
            to_stop.stop_watching()

    def notify_board_changed(self, board_id: str) -> None:
        """Called right after any write to a board: re-scan the board's ONE live mirror and push the
        diffs to every socket on it NOW, without waiting on (or trusting) the filesystem watcher."""
        with self._mirrors_lock:
            entry = self._board_mirrors.get(board_id)
            mirror = entry["mirror"] if entry else None
        if mirror is not None:
            try:
                mirror.resync()
            except Exception as error:                       # a bad mirror must not fail the write
                warn(f"Board resync failed for '{board_id}': {error!r}")

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
        self.notify_board_changed(board_id)                  # connected clients see it vanish -> redirect

    def kick(self, user: dict, board_id: str, target_id: str) -> None:
        board = self._require_owner(user, board_id)
        if target_id == board["owner_id"]:
            raise ValueError("The owner can't be kicked.")
        self.boards.kick_member(board_id, target_id)
        self.notify_board_changed(board_id)                  # membership + task assignees changed

    def transfer(self, user: dict, board_id: str, new_owner_id: str) -> None:
        self._require_owner(user, board_id)
        self.boards.transfer_ownership(board_id, new_owner_id)
        self.notify_board_changed(board_id)

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
        self.notify_board_changed(invite["board_id"])        # existing members see the newcomer live

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
