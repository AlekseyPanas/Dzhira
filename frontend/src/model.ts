// Typed views over the DB frame. The backend mirror keys entities by file name (e.g. "ENG-1.json");
// we ignore those keys and read each file's own id/code, so nothing here parses a filename. Every
// helper reads the CURRENT dbFrame state — components re-render (via bindFrames) when it changes.

import { dbFrame } from "./frames/shared_frames";
import { DELETED } from "./key_paths";

export interface Column { id: string; name: string; order: number; }
export interface Tag { id: string; name: string; color: string; }
export interface Task {
    id: string; title: string; description: string;
    tags: string[]; status: string; order: number;
}
export interface Assignee { name: string; color: string; }

function entriesOf(subfolder: string): any[] {
    const value = dbFrame.read(subfolder);
    if (value === DELETED || value === null || typeof value !== "object") return [];
    return Object.values(value).filter((entry) => entry !== null && typeof entry === "object");
}

export function columnsSorted(): Column[] {
    return (entriesOf("columns") as Column[]).sort((a, b) => a.order - b.order);
}

export function allTasks(): Task[] {
    return entriesOf("tasks").map((task) => ({ tags: [], ...task })) as Task[];
}

export function tasksInColumn(columnId: string): Task[] {
    return allTasks().filter((task) => task.status === columnId).sort((a, b) => a.order - b.order);
}

export function taskById(taskId: string): Task | null {
    return allTasks().find((task) => task.id === taskId) ?? null;
}

export function tagsList(): Tag[] {
    return (entriesOf("tags") as Tag[]).sort((a, b) => a.name.localeCompare(b.name));
}

export function tagsById(): Record<string, Tag> {
    return Object.fromEntries(tagsList().map((tag) => [tag.id, tag]));
}

export function projectCodes(): string[] {
    return entriesOf("projects").map((project) => project.code as string).sort();
}

export function assignee(): Assignee {
    const value = dbFrame.read("meta/assignee.json");
    if (value === DELETED || typeof value !== "object" || value === null) {
        return { name: "You", color: "#ffd23f" };
    }
    return { name: value.name ?? "You", color: value.color ?? "#ffd23f" };
}

// ------------------------------------------------------------------ small view helpers
/** Black or white — whichever contrasts better with `hexColor` (per the assignee-circle spec). */
export function contrastInk(hexColor: string): string {
    const hex = (hexColor || "#000000").replace("#", "");
    const full = hex.length === 3 ? hex.split("").map((c) => c + c).join("") : hex;
    const r = parseInt(full.slice(0, 2), 16) || 0;
    const g = parseInt(full.slice(2, 4), 16) || 0;
    const b = parseInt(full.slice(4, 6), 16) || 0;
    // Perceived luminance (sRGB weights); > 140 is "light", so ink goes black.
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140 ? "#000000" : "#ffffff";
}

export function firstInitial(name: string): string {
    return (name.trim()[0] ?? "?").toUpperCase();
}

export function projectOf(taskId: string): string {
    return taskId.split("-", 1)[0]!;
}
