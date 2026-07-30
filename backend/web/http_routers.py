"""All HTTP routes: auth + account + boards + invites + members, and the board-scoped content writes.

Auth/account/board/invite calls are ordinary request/response (with replies the frontend shows). The
content writes (tasks/columns/tags/projects) still return a bare ack — their real effect streams back
over that board's websocket derived dict. Every protected route requires a valid session (the
``require_login`` dependency); every content/board write also checks the user's access to the board.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.services import AppServices
from backend.util.logs import warn
from backend.web.auth import COOKIE_NAME, clear_session_cookie, set_session_cookie

ACK = {"ok": True}


# ------------------------------------------------------------------ request bodies
class AuthBody(BaseModel):
    username: str
    password: str


class RenameAccountBody(BaseModel):
    username: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


class CreateBoardBody(BaseModel):
    name: str


class BoardIdBody(BaseModel):
    board_id: str


class KickBody(BaseModel):
    board_id: str
    user_id: str


class TransferBody(BaseModel):
    board_id: str
    new_owner_id: str


class InviteBody(BaseModel):
    board_id: str
    username: str


class InviteIdBody(BaseModel):
    invite_id: str


class CreateTaskBody(BaseModel):
    board_id: str
    project_code: str
    title: str
    description: str = ""
    tags: List[str] = []
    assignees: List[str] = []


class UpdateTaskBody(BaseModel):
    board_id: str
    task_id: str
    title: str
    description: str = ""
    tags: List[str] = []
    assignees: List[str] = []


class TaskIdBody(BaseModel):
    board_id: str
    task_id: str


class MoveTaskBody(BaseModel):
    board_id: str
    task_id: str
    status_id: str
    index: int


class ColumnCreateBody(BaseModel):
    board_id: str
    name: str


class ColumnRenameBody(BaseModel):
    board_id: str
    column_id: str
    name: str


class ColumnMoveBody(BaseModel):
    board_id: str
    column_id: str
    direction: str


class ColumnIdBody(BaseModel):
    board_id: str
    column_id: str


class TagCreateBody(BaseModel):
    board_id: str
    name: str
    color: str


class TagUpdateBody(BaseModel):
    board_id: str
    tag_id: str
    name: str
    color: str


class TagIdBody(BaseModel):
    board_id: str
    tag_id: str


class ProjectCreateBody(BaseModel):
    board_id: str
    code: str
    color: Optional[str] = None


class ProjectRenameBody(BaseModel):
    board_id: str
    code: str
    new_code: str


class ProjectColorBody(BaseModel):
    board_id: str
    code: str
    color: str


class ProjectCodeBody(BaseModel):
    board_id: str
    code: str


# ------------------------------------------------------------------ router
def build_api_router(services: AppServices) -> APIRouter:
    router = APIRouter(prefix="/api")

    def require_login(request: Request) -> dict:
        user = services.user_for_session(request.cookies.get(COOKIE_NAME))
        if user is None:
            raise HTTPException(status_code=401, detail="Not logged in.")
        return user

    def require_board(user: dict, board_id: str) -> dict:
        board = services.boards.get_board(board_id)
        if board is None:
            raise HTTPException(status_code=404, detail="No such board.")
        if not services.boards.has_access(board, user["id"]):
            raise HTTPException(status_code=403, detail="You don't have access to that board.")
        return board

    def acked(operation) -> dict:
        try:
            operation()
            return ACK
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        except Exception as error:                          # never leak a raw 500 to the UI
            warn(f"Write op failed unexpectedly: {error!r}")
            raise HTTPException(status_code=400, detail=str(error))

    def acked_board(board: dict, operation) -> dict:
        """A board-content write: run it, then IMMEDIATELY push the change to that board's live
        websockets in-process (so updates don't wait on / trust the filesystem watcher). ``acked``
        raises on failure, so the poke only runs on success."""
        result = acked(operation)
        services.notify_board_changed(board["id"])
        return result

    # ================================================================ auth
    @router.post("/auth/register")
    def register(body: AuthBody, response: Response):
        try:
            user = services.accounts.register(body.username, body.password)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        set_session_cookie(response, services.sessions.create(user["id"]))
        return {"user": services.accounts.public(user)}

    @router.post("/auth/login")
    def login(body: AuthBody, response: Response):
        user = services.accounts.authenticate(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Wrong username or password.")
        set_session_cookie(response, services.sessions.create(user["id"]))
        return {"user": services.accounts.public(user)}

    @router.post("/auth/logout")
    def logout(request: Request, response: Response):
        services.sessions.delete(request.cookies.get(COOKIE_NAME))
        clear_session_cookie(response)
        return ACK

    @router.get("/auth/me")
    def me(request: Request):
        """Bootstrap: 200 with the current user or ``null`` — the frontend branches on this rather
        than treating 'logged out' as an error."""
        user = services.user_for_session(request.cookies.get(COOKIE_NAME))
        return {"user": services.accounts.public(user) if user else None}

    # ================================================================ account
    @router.post("/account/rename")
    def account_rename(body: RenameAccountBody, user: dict = Depends(require_login)):
        return acked(lambda: services.accounts.rename(user["id"], body.username))

    @router.post("/account/change_password")
    def account_change_password(body: ChangePasswordBody, user: dict = Depends(require_login)):
        return acked(lambda: services.accounts.change_password(
            user["id"], body.current_password, body.new_password))

    # ================================================================ boards
    @router.get("/boards")
    def list_boards(user: dict = Depends(require_login)):
        return {"boards": [{"id": b["id"], "name": b["name"],
                            "role": services.boards.role(b, user["id"])}
                           for b in services.boards.boards_for_user(user["id"])]}

    @router.post("/boards/create")
    def create_board(body: CreateBoardBody, user: dict = Depends(require_login)):
        try:
            board = services.boards.create_board(body.name, user["id"])
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {"name": board["name"]}

    @router.post("/board/delete")
    def delete_board(body: BoardIdBody, user: dict = Depends(require_login)):
        return acked(lambda: services.delete_board(user, body.board_id))

    @router.post("/board/kick")
    def kick(body: KickBody, user: dict = Depends(require_login)):
        return acked(lambda: services.kick(user, body.board_id, body.user_id))

    @router.post("/board/transfer")
    def transfer(body: TransferBody, user: dict = Depends(require_login)):
        return acked(lambda: services.transfer(user, body.board_id, body.new_owner_id))

    @router.get("/board/{name}/members")
    def board_members(name: str, user: dict = Depends(require_login)):
        board = services.accessible_board_by_name(name, user)
        if board is None:
            raise HTTPException(status_code=404, detail="No such board.")
        return {"board_id": board["id"], "members": services.board_members_public(board)}

    @router.get("/board/{name}/invites")
    def board_invites(name: str, user: dict = Depends(require_login)):
        board = services.accessible_board_by_name(name, user)
        if board is None:
            raise HTTPException(status_code=404, detail="No such board.")
        return {"invites": services.invites_for_board(user, board["id"])}

    @router.post("/board/invite")
    def invite(body: InviteBody, user: dict = Depends(require_login)):
        try:
            services.create_invite(user, body.board_id, body.username)
            return ACK
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    # ================================================================ invites (invitee side)
    @router.get("/invites")
    def my_invites(user: dict = Depends(require_login)):
        return {"invites": services.invites_for_user(user)}

    @router.post("/invite/accept")
    def accept_invite(body: InviteIdBody, user: dict = Depends(require_login)):
        return acked(lambda: services.accept_invite(user, body.invite_id))

    @router.post("/invite/reject")
    def reject_invite(body: InviteIdBody, user: dict = Depends(require_login)):
        return acked(lambda: services.reject_invite(user, body.invite_id))

    @router.post("/invite/withdraw")
    def withdraw_invite(body: InviteIdBody, user: dict = Depends(require_login)):
        return acked(lambda: services.withdraw_invite(user, body.invite_id))

    # ================================================================ board content (scoped writes)
    # Every one uses acked_board(board, ...) so the change is pushed to the board's websockets in the
    # same request (independent of the filesystem watcher).
    @router.post("/task/create")
    def task_create(body: CreateTaskBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        api = services.board_api(board["id"])
        assignees = services.valid_assignees(board, body.assignees)
        return acked_board(board, lambda: api.create_task(body.project_code, body.title,
                                                          body.description, body.tags, assignees))

    @router.post("/task/update")
    def task_update(body: UpdateTaskBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        api = services.board_api(board["id"])
        assignees = services.valid_assignees(board, body.assignees)
        return acked_board(board, lambda: api.update_task(body.task_id, body.title,
                                                          body.description, body.tags, assignees))

    @router.post("/task/delete")
    def task_delete(body: TaskIdBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).delete_task(body.task_id))

    @router.post("/task/move")
    def task_move(body: MoveTaskBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).move_task(
            body.task_id, body.status_id, body.index))

    @router.post("/column/create")
    def column_create(body: ColumnCreateBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).create_column(body.name))

    @router.post("/column/rename")
    def column_rename(body: ColumnRenameBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).rename_column(body.column_id, body.name))

    @router.post("/column/move")
    def column_move(body: ColumnMoveBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).move_column(body.column_id, body.direction))

    @router.post("/column/delete")
    def column_delete(body: ColumnIdBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).delete_column(body.column_id))

    @router.post("/tag/create")
    def tag_create(body: TagCreateBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).create_tag(body.name, body.color))

    @router.post("/tag/update")
    def tag_update(body: TagUpdateBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).update_tag(body.tag_id, body.name, body.color))

    @router.post("/tag/delete")
    def tag_delete(body: TagIdBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).delete_tag(body.tag_id))

    @router.post("/project/create")
    def project_create(body: ProjectCreateBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).create_project(body.code, body.color))

    @router.post("/project/rename")
    def project_rename(body: ProjectRenameBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).rename_project(body.code, body.new_code))

    @router.post("/project/set_color")
    def project_set_color(body: ProjectColorBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).set_project_color(body.code, body.color))

    @router.post("/project/delete")
    def project_delete(body: ProjectCodeBody, user: dict = Depends(require_login)):
        board = require_board(user, body.board_id)
        return acked_board(board, lambda: services.board_api(board["id"]).delete_project(body.code))

    return router
