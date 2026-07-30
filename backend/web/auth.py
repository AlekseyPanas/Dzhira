"""Session-cookie helpers shared by the HTTP router and the websocket hub.

The session id rides in an httponly cookie. Both transports read it the same way (the browser sends it
on same-origin ws upgrades too), so a single place owns the cookie name + set/clear logic.
"""

from typing import Optional

from fastapi import Response

from backend.db.sessions import MAX_AGE_SECONDS

COOKIE_NAME = "dzhira_session"


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(COOKIE_NAME, session_id, max_age=MAX_AGE_SECONDS,
                        httponly=True, samesite="lax", path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def session_id_from_cookies(cookies: dict) -> Optional[str]:
    return cookies.get(COOKIE_NAME)
