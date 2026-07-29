"""The thin HTTP write routers — every mutation is a plain POST returning a bare ack (or a 400 with
the error message); the REAL result of a successful write propagates over the websocket via the
``DB`` derived dict (the source of truth). No optimistic payloads. (Ported from eventCamera's
``http_routers.py``, pointed at ``BoardAPI``.)
"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.board_api import BoardAPI
from backend.util.logs import warn

ACK = {"ok": True}


# ------------------------------------------------------------------ request bodies
class CreateTaskBody(BaseModel):
    project_code: str
    title: str
    description: str = ""
    tags: List[str] = []


class UpdateTaskBody(BaseModel):
    task_id: str
    title: str
    description: str = ""
    tags: List[str] = []


class TaskIdBody(BaseModel):
    task_id: str


class MoveTaskBody(BaseModel):
    task_id: str
    status_id: str
    index: int


class ColumnCreateBody(BaseModel):
    name: str


class ColumnRenameBody(BaseModel):
    column_id: str
    name: str


class ColumnMoveBody(BaseModel):
    column_id: str
    direction: str                                          # "left" | "right"


class ColumnIdBody(BaseModel):
    column_id: str


class TagCreateBody(BaseModel):
    name: str
    color: str


class TagUpdateBody(BaseModel):
    tag_id: str
    name: str
    color: str


class TagIdBody(BaseModel):
    tag_id: str


class ProjectCreateBody(BaseModel):
    code: str


class ProjectRenameBody(BaseModel):
    code: str
    new_code: str


class ProjectCodeBody(BaseModel):
    code: str


class AssigneeBody(BaseModel):
    name: str
    color: str


# ------------------------------------------------------------------ router
def build_api_router(board: BoardAPI) -> APIRouter:
    router = APIRouter(prefix="/api")

    def acked(operation) -> dict:
        """Run one write op -> bare ack, mapping a rejected write to a clean 400."""
        try:
            operation()
            return ACK
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        except Exception as error:                          # never leak a raw 500 to the UI
            warn(f"Write op failed unexpectedly: {error!r}")
            raise HTTPException(status_code=400, detail=str(error))

    # ---- tasks -----------------------------------------------------------------------------------
    @router.post("/task/create")
    def task_create(body: CreateTaskBody):
        return acked(lambda: board.create_task(body.project_code, body.title,
                                               body.description, body.tags))

    @router.post("/task/update")
    def task_update(body: UpdateTaskBody):
        return acked(lambda: board.update_task(body.task_id, body.title,
                                               body.description, body.tags))

    @router.post("/task/delete")
    def task_delete(body: TaskIdBody):
        return acked(lambda: board.delete_task(body.task_id))

    @router.post("/task/move")
    def task_move(body: MoveTaskBody):
        return acked(lambda: board.move_task(body.task_id, body.status_id, body.index))

    # ---- columns ---------------------------------------------------------------------------------
    @router.post("/column/create")
    def column_create(body: ColumnCreateBody):
        return acked(lambda: board.create_column(body.name))

    @router.post("/column/rename")
    def column_rename(body: ColumnRenameBody):
        return acked(lambda: board.rename_column(body.column_id, body.name))

    @router.post("/column/move")
    def column_move(body: ColumnMoveBody):
        return acked(lambda: board.move_column(body.column_id, body.direction))

    @router.post("/column/delete")
    def column_delete(body: ColumnIdBody):
        return acked(lambda: board.delete_column(body.column_id))

    # ---- tags ------------------------------------------------------------------------------------
    @router.post("/tag/create")
    def tag_create(body: TagCreateBody):
        return acked(lambda: board.create_tag(body.name, body.color))

    @router.post("/tag/update")
    def tag_update(body: TagUpdateBody):
        return acked(lambda: board.update_tag(body.tag_id, body.name, body.color))

    @router.post("/tag/delete")
    def tag_delete(body: TagIdBody):
        return acked(lambda: board.delete_tag(body.tag_id))

    # ---- projects --------------------------------------------------------------------------------
    @router.post("/project/create")
    def project_create(body: ProjectCreateBody):
        return acked(lambda: board.create_project(body.code))

    @router.post("/project/rename")
    def project_rename(body: ProjectRenameBody):
        return acked(lambda: board.rename_project(body.code, body.new_code))

    @router.post("/project/delete")
    def project_delete(body: ProjectCodeBody):
        return acked(lambda: board.delete_project(body.code))

    # ---- assignee --------------------------------------------------------------------------------
    @router.post("/assignee/set")
    def assignee_set(body: AssigneeBody):
        return acked(lambda: board.set_assignee(body.name, body.color))

    return router
