"""The composition root: build the services, wire transport, and serve the SPA.

No global watchdog any more — the read side is per-connection (a board dict is created when a client
opens ``/ws?board=<name>`` and dropped on disconnect; see the websocket hub). The lifespan just prunes
expired sessions at startup. The frontend is a single-page app, so every non-API/non-asset path serves
``index.html`` and the client router decides what to show.

``create_app`` is the injectable factory the tests drive (a tmp ``db_folder``, ``serve_frontend_dist``
off). ``backend/main.py`` builds the frontend then serves this on uvicorn.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse

from backend.services import AppServices
from backend.web.http_routers import build_api_router
from backend.web.websocket_hub import WebsocketHub

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_FOLDER = REPO_ROOT / "db"
FRONTEND_FOLDER = REPO_ROOT / "frontend"
FRONTEND_DIST_FOLDER = FRONTEND_FOLDER / "dist"


def create_app(db_folder: Union[str, Path] = DEFAULT_DB_FOLDER,
               serve_frontend_dist: bool = True) -> FastAPI:
    services = AppServices(db_folder)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        services.sessions.cleanup_expired()
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.services = services
    websocket_hub = WebsocketHub(services)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket_hub.handle_connection(websocket)

    app.include_router(build_api_router(services))

    if serve_frontend_dist:
        _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve real files from ``frontend/dist`` and fall back to ``index.html`` for every app route
    (``/login``, ``/create``, ``/new``, ``/board/<name>``) so client-side routing works on hard reload."""
    index_path = FRONTEND_DIST_FOLDER / "index.html"

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/") or full_path == "ws":
            raise HTTPException(status_code=404)
        candidate = (FRONTEND_DIST_FOLDER / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST_FOLDER.resolve() in candidate.parents:
            return FileResponse(candidate)                  # a real asset (client.js, styles.css, …)
        if index_path.is_file():
            return FileResponse(index_path)                 # SPA fallback
        raise HTTPException(status_code=404, detail="Frontend not built.")
