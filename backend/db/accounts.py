"""The users store: register / authenticate / rename / change-password.

A user is ``{id, username, password{...}, color}``. Usernames are unique case-insensitively, tracked
by a ``user_names/<lower>.json -> {user_id}`` index (also the login lookup). Passwords are hashed
(passwords.py); the plaintext is never stored. ``public`` strips the password for anything the client
may see.
"""

from pathlib import Path
from typing import Dict, List, Optional, Union

from backend.db import ids, passwords
from backend.db.jsonstore import atomic_write_json, locked_read_modify_write, read_json
from backend.db.paths import USER_NAMES_DIR, USERS_DIR
from backend.db.seeding import default_user_color


class AccountsStore:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self._root = Path(db_root)

    # ------------------------------------------------------------------ create / auth
    def register(self, username: str, password: str) -> dict:
        name = ids.validate_username(username)
        lower = name.lower()
        if not isinstance(password, str) or len(password) < 1:
            raise ValueError("Password must not be empty.")
        if self._name_index(lower).exists():
            raise ValueError(f"Username '{name}' is taken.")
        user_id = ids.new_id("usr")
        user = {"id": user_id, "username": name, "password": passwords.hash_password(password),
                "color": default_user_color(user_id)}
        atomic_write_json(self._user_path(user_id), user)
        atomic_write_json(self._name_index(lower), {"user_id": user_id})
        return user

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        user = self.get_by_username(username)
        if user is None or not passwords.verify_password(password, user.get("password", {})):
            return None
        return user

    # ------------------------------------------------------------------ read
    def get_user(self, user_id: str) -> Optional[dict]:
        ids.validate_generated_id(user_id, "user")
        return read_json(self._user_path(user_id))

    def get_by_username(self, username: str) -> Optional[dict]:
        try:
            lower = ids.username_lower(username)
        except ValueError:
            return None
        index = read_json(self._name_index(lower))
        return self.get_user(index["user_id"]) if index and index.get("user_id") else None

    def public(self, user_id_or_user: Union[str, dict]) -> Optional[dict]:
        """The client-safe view of a user: ``{id, username, color}`` (no password)."""
        user = user_id_or_user if isinstance(user_id_or_user, dict) else self.get_user(user_id_or_user)
        if user is None:
            return None
        return {"id": user["id"], "username": user["username"],
                "color": user.get("color") or default_user_color(user["id"])}

    def public_many(self, user_ids: List[str]) -> List[dict]:
        return [pub for uid in user_ids if (pub := self.public(uid)) is not None]

    # ------------------------------------------------------------------ mutate
    def rename(self, user_id: str, new_username: str) -> None:
        new_name = ids.validate_username(new_username)
        new_lower = new_name.lower()
        current = self.get_user(user_id)
        if current is None:
            raise ValueError("No such user.")
        old_lower = current["username"].lower()
        if new_lower != old_lower and self._name_index(new_lower).exists():
            raise ValueError(f"Username '{new_name}' is taken.")
        locked_read_modify_write(self._user_path(user_id),
                                 lambda u: u.__setitem__("username", new_name))
        if new_lower != old_lower:
            atomic_write_json(self._name_index(new_lower), {"user_id": user_id})
            self._name_index(old_lower).unlink(missing_ok=True)

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        user = self.get_user(user_id)
        if user is None:
            raise ValueError("No such user.")
        if not passwords.verify_password(current_password, user.get("password", {})):
            raise ValueError("Current password is incorrect.")
        if not isinstance(new_password, str) or len(new_password) < 1:
            raise ValueError("New password must not be empty.")
        locked_read_modify_write(
            self._user_path(user_id),
            lambda u: u.__setitem__("password", passwords.hash_password(new_password)))

    # ------------------------------------------------------------------ paths
    def _user_path(self, user_id: str) -> Path:
        return self._root / USERS_DIR / f"{ids.validate_generated_id(user_id, 'user')}.json"

    def _name_index(self, lower: str) -> Path:
        return self._root / USER_NAMES_DIR / f"{lower}.json"
