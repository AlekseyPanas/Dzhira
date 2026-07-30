"""File-backed sessions (the Python answer to express-session with a file store).

A session is ``sessions/<sid>.json = {user_id, created_at}``. The session id is a long random
url-safe token carried in an httponly cookie. Lifetime is effectively forever (10 years) — this is a
joke showcase, there is no password reset and no real expiry pressure — but we still stamp a
``created_at`` and prune anything past the max age, both lazily (on lookup) and in bulk at startup, so
the folder can't grow without bound.
"""

import re
import time
from pathlib import Path
from typing import Optional, Union

from backend.db.jsonstore import atomic_write_json, read_json
from backend.db.paths import SESSIONS_DIR

_SID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_AGE_SECONDS = 10 * 365 * 24 * 60 * 60                   # ~10 years


class SessionStore:

    def __init__(self, db_root: Union[str, Path]) -> None:
        self._root = Path(db_root)

    def create(self, user_id: str) -> str:
        import secrets
        session_id = secrets.token_urlsafe(32)
        atomic_write_json(self._path(session_id),
                          {"user_id": user_id, "created_at": time.time()})
        return session_id

    def get_user_id(self, session_id: Optional[str]) -> Optional[str]:
        """The user id for a valid, unexpired session, else ``None``. A malformed id (e.g. a tampered
        cookie) returns ``None`` and never touches the filesystem beyond its own guarded path."""
        if not session_id or not _SID_RE.match(session_id):
            return None
        record = read_json(self._path(session_id))
        if record is None:
            return None
        if time.time() - float(record.get("created_at", 0)) > MAX_AGE_SECONDS:
            self.delete(session_id)                         # lazily prune the expired one
            return None
        return record.get("user_id")

    def delete(self, session_id: Optional[str]) -> None:
        if session_id and _SID_RE.match(session_id):
            self._path(session_id).unlink(missing_ok=True)

    def cleanup_expired(self) -> None:
        """Bulk-prune expired sessions (called once at startup)."""
        now = time.time()
        for path in (self._root / SESSIONS_DIR).glob("*.json"):
            record = read_json(path)
            if record is None or now - float(record.get("created_at", 0)) > MAX_AGE_SECONDS:
                path.unlink(missing_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._root / SESSIONS_DIR / f"{session_id}.json"
