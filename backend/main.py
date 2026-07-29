"""The launcher (run this): ``python backend/main.py [--host H] [--port P] [--db-folder DIR]``.

It builds the bun frontend (install when ``node_modules`` is missing, then ``bun run build``) and
serves the API + static bundle on uvicorn. ``--skip-frontend-build`` serves the existing
``frontend/dist`` as-is; a build failure aborts the launch rather than silently serving a stale
bundle. (Structure ported from eventCamera's ``webgui2.py``.)
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:                          # direct-script run support
    sys.path.insert(0, str(REPO_ROOT))

from backend.app import DEFAULT_DB_FOLDER, FRONTEND_FOLDER, create_app  # noqa: E402


def build_frontend_or_abort() -> None:
    """``bun install`` (when node_modules is missing) + ``bun run build``. A build failure aborts."""
    if not FRONTEND_FOLDER.is_dir():
        print(f"[dzhira] No frontend/ folder at {FRONTEND_FOLDER}; serving API only.")
        return
    if not (FRONTEND_FOLDER / "node_modules").is_dir():
        _run_frontend_step(["bun", "install"])
    _run_frontend_step(["bun", "run", "build"])


def _run_frontend_step(command) -> None:
    print(f"[dzhira] Running {' '.join(command)} in {FRONTEND_FOLDER} ...")
    try:
        result = subprocess.run(command, cwd=FRONTEND_FOLDER)
    except FileNotFoundError:
        raise SystemExit(
            "[dzhira] bun is not installed (https://bun.sh — `curl -fsSL https://bun.sh/install "
            "| bash`). Install it, or delete/rename frontend/ to serve the API only.")
    if result.returncode != 0:
        raise SystemExit(f"[dzhira] Frontend build step failed: {' '.join(command)} "
                         f"(exit {result.returncode}). Aborting launch.")


if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(
        description="Dzhira — builds the frontend (bun) then serves the whole app.")
    parser.add_argument("--db-folder", default=str(DEFAULT_DB_FOLDER),
                        help="the JSON DB folder (created + seeded on first run)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-frontend-build", action="store_true",
                        help="serve the existing frontend/dist without rebuilding")
    arguments = parser.parse_args()

    if not arguments.skip_frontend_build:
        build_frontend_or_abort()
    uvicorn.run(create_app(db_folder=arguments.db_folder), host=arguments.host, port=arguments.port)
