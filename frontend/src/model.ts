// Typed views over the board frames. Board CONTENT (columns/tasks/tags/projects/board.json) lives in
// boardFrame (websocket-synced). The MEMBER list (id -> username/color/role) lives in boardMetaFrame,
// fetched via API. Components re-render (bindFrames) when either changes.

import { boardFrame, boardMetaFrame } from "./frames/shared_frames";
import { DELETED } from "./key_paths";

export interface Column { id: string; name: string; order: number; }
export interface Tag { id: string; name: string; color: string; }
export interface Task {
    id: string; title: string; description: string;
    tags: string[]; status: string; order: number; assignees: string[];
}
export interface Project { code: string; color: string; }
export interface Member { id: string; username: string; color: string; role: string; }

function entriesOf(subfolder: string): any[] {
    const value = boardFrame.read(subfolder);
    if (value === DELETED || value === null || typeof value !== "object") return [];
    return Object.values(value).filter((entry) => entry !== null && typeof entry === "object");
}

// ---- board content --------------------------------------------------------------------------
export function columnsSorted(): Column[] {
    return (entriesOf("columns") as Column[]).sort((a, b) => a.order - b.order);
}

export function allTasks(): Task[] {
    return entriesOf("tasks").map((task) => ({ tags: [], assignees: [], ...task })) as Task[];
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

export interface ProjectRow { code: string; color: string; }
export function projectCodes(): string[] {
    return entriesOf("projects").map((project) => project.code as string).sort();
}

const PROJECT_COLOR_PALETTE = ["#ff5c5c", "#ffa23a", "#ffd23f", "#7bd854", "#3ec6c6", "#5b9bff", "#b06bff", "#ff77dd"];
export function defaultProjectColor(code: string): string {
    const sum = [...code].reduce((total, ch) => total + ch.charCodeAt(0), 0);
    return PROJECT_COLOR_PALETTE[sum % PROJECT_COLOR_PALETTE.length]!;
}
export function projects(): Project[] {
    return entriesOf("projects")
        .map((p) => ({ code: p.code as string, color: (p.color as string) || defaultProjectColor(p.code) }))
        .sort((a, b) => a.code.localeCompare(b.code));
}
export function projectColor(code: string): string {
    const project = entriesOf("projects").find((p) => p.code === code);
    return project && project.color ? project.color : defaultProjectColor(code);
}

// ---- members (from boardMetaFrame, API-fetched) ---------------------------------------------
export function members(): Member[] {
    const value = boardMetaFrame.read("members");
    return Array.isArray(value) ? value as Member[] : [];
}
export function membersById(): Record<string, Member> {
    return Object.fromEntries(members().map((m) => [m.id, m]));
}
export function myRole(): string | null {
    const role = boardMetaFrame.read("myRole");
    return typeof role === "string" ? role : null;
}
export function boardId(): string {
    const id = boardMetaFrame.read("id");
    return typeof id === "string" ? id : "";
}
export function boardName(): string {
    const name = boardMetaFrame.read("name");
    return typeof name === "string" ? name : "";
}

// ---- small view helpers ---------------------------------------------------------------------
export function contrastInk(hexColor: string): string {
    const hex = (hexColor || "#000000").replace("#", "");
    const full = hex.length === 3 ? hex.split("").map((c) => c + c).join("") : hex;
    const r = parseInt(full.slice(0, 2), 16) || 0;
    const g = parseInt(full.slice(2, 4), 16) || 0;
    const b = parseInt(full.slice(4, 6), 16) || 0;
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140 ? "#000000" : "#ffffff";
}
export function firstInitial(name: string): string {
    return (name.trim()[0] ?? "?").toUpperCase();
}
export function projectOf(taskId: string): string {
    return taskId.split("-", 1)[0]!;
}
