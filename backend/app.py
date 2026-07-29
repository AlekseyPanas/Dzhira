"""The thin composition root — the ONLY place instances are constructed and lifecycles are owned.

Build order: scaffold the DB folder → the one folder-backed derived dict (``DB``) → the ``BoardAPI``
writer → the registry → transport (websocket hub + HTTP router) → static frontend LAST (so ``/ws``
and ``/api/*`` win the route match). The watchdog observer starts in the FastAPI lifespan and stops
on shutdown.

``create_app`` is the injectable factory the tests drive (a tmp ``db_folder``, ``serve_frontend_dist``
off). ``backend/main.py`` is the launcher that builds the frontend then serves this on uvicorn.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from backend.db.board_api import BoardAPI
from backend.db.layout import ensure_scaffold
from backend.derived.json_folder_derived_dict import JsonFolderDerivedDict
from backend.web.http_routers import build_api_router
from backend.web.registry import DerivedDicts, DerivedDictsRegistry
from backend.web.websocket_hub import WebsocketHub

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_FOLDER = REPO_ROOT / "db"
FRONTEND_FOLDER = REPO_ROOT / "frontend"
FRONTEND_DIST_FOLDER = FRONTEND_FOLDER / "dist"


def create_app(db_folder: Union[str, Path] = DEFAULT_DB_FOLDER,
               serve_frontend_dist: bool = True) -> FastAPI:
    db_folder = Path(db_folder)
    ensure_scaffold(db_folder)                              # make subfolders + seed a starter board

    db_derived_dict = JsonFolderDerivedDict(db_folder)      # the read side: mirror the DB folder
    board = BoardAPI(db_folder)                             # the write side: the only writer

    registry = DerivedDictsRegistry()
    registry.register(DerivedDicts.DB, db_derived_dict)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        db_derived_dict.start_watching()                    # observer up, then initial scan
        yield
        db_derived_dict.stop_watching()

    app = FastAPI(lifespan=lifespan)
    websocket_hub = WebsocketHub(registry)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket_hub.handle_connection(websocket)

    app.include_router(build_api_router(board))

    # Static frontend LAST so /ws and /api/* match first.
    if serve_frontend_dist and FRONTEND_DIST_FOLDER.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST_FOLDER, html=True), name="frontend")

    return app
