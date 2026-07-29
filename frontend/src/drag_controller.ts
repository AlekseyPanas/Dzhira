// Pointer-based drag & drop for task cards, deliberately OUTSIDE the Nano JSX render cycle: it works
// off DOM data attributes and manipulates the DOM directly during a drag, then commits once on drop
// via taskApi.move — the board then re-renders from the resulting websocket update (never optimistic).
// Doing it this way keeps the drag smooth (no full-board re-render on every pointermove) and survives
// board re-renders because every listener is delegated on `document`.
//
// The experience: press a card and move past a small threshold to pick it up (a smaller move is a
// click that opens the editor). A floating copy follows the cursor; a dotted "ghost slot" shows
// exactly where the card lands — reordering within a column or moving between columns. Release to drop.

import { taskApi } from "./api";

const DRAG_THRESHOLD_PX = 5;

interface Pending { taskId: string; startX: number; startY: number; card: HTMLElement; }
interface Dragging {
    taskId: string;
    original: HTMLElement;      // the source card, hidden in place (restored if the drop fails)
    floating: HTMLElement;      // the copy that follows the cursor
    ghost: HTMLElement;         // the dotted placeholder
    grabOffsetX: number;
    grabOffsetY: number;
    width: number;
}

let pending: Pending | null = null;
let dragging: Dragging | null = null;
let justDragged = false;        // set on drop so the card's click handler skips opening the editor

/** True (once) if a drag just ended — the card onClick checks this to avoid opening the editor. */
export function consumeDragClick(): boolean {
    if (justDragged) { justDragged = false; return true; }
    return false;
}

export function installDragController(): void {
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("pointermove", onPointerMove, true);
    document.addEventListener("pointerup", onPointerUp, true);
}

function onPointerDown(event: PointerEvent): void {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest(".card-trash")) return;              // the trash button owns its own clicks
    const card = target.closest<HTMLElement>(".task-card");
    if (!card || !card.dataset.taskId) return;
    justDragged = false;
    pending = { taskId: card.dataset.taskId, startX: event.clientX, startY: event.clientY, card };
}

function onPointerMove(event: PointerEvent): void {
    if (dragging) { updateDrag(event); return; }
    if (!pending) return;
    if (Math.hypot(event.clientX - pending.startX, event.clientY - pending.startY) < DRAG_THRESHOLD_PX) {
        return;
    }
    beginDrag(event);
}

function beginDrag(event: PointerEvent): void {
    if (!pending) return;
    const card = pending.card;
    const rect = card.getBoundingClientRect();

    const ghost = document.createElement("div");
    ghost.className = "ghost-slot";
    ghost.style.height = `${rect.height}px`;

    const floating = card.cloneNode(true) as HTMLElement;
    floating.classList.add("dragging-float");
    floating.style.width = `${rect.width}px`;
    floating.querySelector(".card-trash")?.remove();

    card.classList.add("drag-hidden");                      // keep it in place (restore on failure)
    card.parentElement?.insertBefore(ghost, card);
    document.body.appendChild(floating);
    document.body.classList.add("is-dragging");

    dragging = {
        taskId: pending.taskId,
        original: card,
        floating,
        ghost,
        grabOffsetX: event.clientX - rect.left,
        grabOffsetY: event.clientY - rect.top,
        width: rect.width,
    };
    pending = null;
    updateDrag(event);
}

function updateDrag(event: PointerEvent): void {
    if (!dragging) return;
    dragging.floating.style.left = `${event.clientX - dragging.grabOffsetX}px`;
    dragging.floating.style.top = `${event.clientY - dragging.grabOffsetY}px`;

    const container = columnUnder(event.clientX);
    if (!container) return;
    const cards = liveCards(container, dragging.taskId);
    let insertBefore: HTMLElement | null = null;
    for (const card of cards) {
        const rect = card.getBoundingClientRect();
        if (event.clientY < rect.top + rect.height / 2) { insertBefore = card; break; }
    }
    container.insertBefore(dragging.ghost, insertBefore);
}

function onPointerUp(_event: PointerEvent): void {
    if (!dragging) { pending = null; return; }              // a plain click — let it open the editor
    const drag = dragging;
    dragging = null;
    justDragged = true;

    const container = drag.ghost.parentElement as HTMLElement | null;
    const statusId = container?.dataset.columnId;
    const index = container ? indexOfGhost(container, drag.ghost, drag.taskId) : 0;

    drag.floating.remove();
    drag.ghost.remove();
    document.body.classList.remove("is-dragging");

    if (!statusId) { drag.original.classList.remove("drag-hidden"); return; }   // dropped nowhere
    // Commit. On success the websocket update re-renders the whole board (dropping our hidden
    // original + ghost with it); only restore the original if the write is rejected.
    void taskApi.move(drag.taskId, statusId, index).then((error) => {
        if (error) {
            console.error("[drag] move failed:", error);
            drag.original.classList.remove("drag-hidden");
        }
    });
}

// ------------------------------------------------------------------ DOM helpers
/** The `.column-tasks` container whose column sits under the cursor's X (nearest if none contains it). */
function columnUnder(clientX: number): HTMLElement | null {
    const columns = [...document.querySelectorAll<HTMLElement>(".board-column")];
    let nearest: HTMLElement | null = null;
    let nearestDistance = Infinity;
    for (const column of columns) {
        const rect = column.getBoundingClientRect();
        const tasks = column.querySelector<HTMLElement>(".column-tasks");
        if (!tasks) continue;
        if (clientX >= rect.left && clientX <= rect.right) return tasks;
        const distance = clientX < rect.left ? rect.left - clientX : clientX - rect.right;
        if (distance < nearestDistance) { nearestDistance = distance; nearest = tasks; }
    }
    return nearest;
}

/** The real task cards in a container, excluding the one being dragged (which is hidden in place). */
function liveCards(container: HTMLElement, draggedId: string): HTMLElement[] {
    return [...container.querySelectorAll<HTMLElement>(".task-card")]
        .filter((card) => card.dataset.taskId !== draggedId);
}

/** How many real (non-dragged) cards precede the ghost — the insertion index the backend expects. */
function indexOfGhost(container: HTMLElement, ghost: HTMLElement, draggedId: string): number {
    let index = 0;
    for (const child of [...container.children]) {
        if (child === ghost) break;
        const element = child as HTMLElement;
        if (element.classList.contains("task-card") && element.dataset.taskId !== draggedId) index++;
    }
    return index;
}
