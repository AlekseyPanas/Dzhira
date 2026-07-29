# CLAUDE.md — Dzhira

## ⚠️ Working directives (read first, every session)

1. **Discussion mode is the default. Do NOT write code until the user green-lights it.**
   Any new request starts as a conversation: understand it, surface a plan, clarify. Only begin
   editing files / writing code once the user explicitly says to go. (A green light for one task
   does not carry over to the next — return to discussion mode after each task.)
2. **Follow the user's instructions and clarify where unsure.** The user is a skilled programmer.
   Do not silently make consequential decisions on their behalf — propose, ask, then act. When a
   design has real forks, present them and let the user choose rather than guessing.
3. **Checkpoint discipline.** Large builds proceed in checkpoints. Each checkpoint must land the app
   in a *working* state (never mid-write), then record memory so a session can stop and resume
   cleanly. See the memory index at
   `~/.claude/projects/-Users-alexpanas-Repos-Dzhira/memory/MEMORY.md`.

## What Dzhira is

A parody of Jira's Kanban board — a deliberately small subset of the fundamentals, with a UI that
looks "designed by a 12-year-old in MS Paint" (goofy but readable). Single-user. The full product
spec + evolving developer docs live in `README.md` (the spec is the source of truth; keep it beauty
and turn it into dev docs as code lands).

Core features: a Kanban board with status columns; task cards (title, description preview, colored
tag chips, `#PROJ-NNN` id, assignee initial-circle); drag-to-reorder / move-between-columns with a
dotted ghost placeholder; topbar popouts to manage Tasks, Tags, Projects, the single Assignee, and
Status columns; JSON-file persistence.

## Stack & architecture

- **Frontend:** Nano JSX + TypeScript, bundled by **bun** (`bun run build` → `dist/`).
- **Backend:** Python + **FastAPI**, served by uvicorn. Running the backend builds the frontend
  (if needed) then serves the API + static bundle. `--host` / `--port` args supported.
- **Persistence:** a *folder of JSON files* (no database). Consistency via **watchdog** (observe
  file changes) + **flock** + atomic temp-file-then-rename writes.
- **The governing pattern (ported from the eventCamera repo):**
  - *Derived dicts* — read-only, observable backend state that is a pure function of the JSON
    folder. A watchdog mirror re-reads changed files, diffs to key-level, and publishes
    `(key_path, value|__DELETED__, seq)` updates. Writers never notify directly; the change
    propagates disk → watchdog → derived dict → websocket → frontend frame (single source of truth,
    no optimistic UI).
  - *Websocket hub* — one shared multiplexed socket per client; `subscribe(derived_dict, key_path)`
    streams the snapshot then live updates, seq-filtered and in order.
  - *Frontend frames* — wrap a Nano `Store`; `SyncedClientFrame` mirrors a backend derived dict over
    the socket, `LocalClientFrame` holds frontend-only shared state. Components call `bindFrames` in
    their constructor to re-render on change.
  - *Write API* — plain HTTP `POST` returning a bare ack (or error string); the result shows up via
    the derived-dict stream, never an echoed payload.

## Reference repos — READ SCOPE IS RESTRICTED

The spec authorized reading ONLY these, ONLY for the parts named. Do not fish around other repos.
- `~/Repos/eventCamera` — the derived-dict library (`derived_dicts/library/`), websocket hub +
  registry + services (`webgui/library/`), and frontend frames (`frontend/src/`). This is the
  architecture Dzhira ports/simplifies.
- `~/Repos/SadkoTrans/admin_dash` — a reference nano-jsx + bun app (build setup).
- `~/Repos/nano` — the nano-jsx source itself, for reference when unsure of the API.

## Environment notes

- `bun` 1.2.18 and `python3` 3.14 are installed. FastAPI/uvicorn/watchdog are NOT yet installed —
  use a venv + `requirements.txt`. `nano-jsx` is fetched by `bun install` (needs network the first time).
