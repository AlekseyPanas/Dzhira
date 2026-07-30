// Typed views over the board frames. Board CONTENT (columns/tasks/tags/projects/board.json) lives in
// boardFrame (websocket-synced). The MEMBER list (id -> username/color/role) lives in boardMetaFrame,
// fetched via API. Components re-render (bindFrames) when either changes.

import { authFrame, boardFrame, boardMetaFrame, nowFrame } from "./frames/shared_frames";
import { DELETED } from "./key_paths";

export interface Column { id: string; name: string; order: number; }
export interface Tag { id: string; name: string; color: string; }
export interface Task {
    id: string; title: string; description: string;
    tags: string[]; status: string; order: number; assignees: string[];
    deadline?: string | null;
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

// ---- per-user filters (views) ---------------------------------------------------------------
export interface View { assignees: string[]; tags: string[]; projects: string[]; }

// A sentinel that can appear in view.assignees to explicitly filter for tasks with NO assignee. It's
// safe to store alongside real ids: user ids are "usr_…", so this can never collide with one.
export const UNASSIGNED = "__none__";

export function myUserId(): string {
    const user = authFrame.read("user");
    return user && typeof user === "object" ? user.id : "";
}

/** This viewer's saved filter for the current board (from the board mirror), or an empty filter. */
export function myView(): View {
    const raw = boardFrame.read(`views/${myUserId()}.json`);
    if (raw === DELETED || raw === null || typeof raw !== "object") {
        return { assignees: [], tags: [], projects: [] };
    }
    return { assignees: raw.assignees ?? [], tags: raw.tags ?? [], projects: raw.projects ?? [] };
}

export function filtersActive(view: View = myView()): boolean {
    return view.assignees.length > 0 || view.tags.length > 0 || view.projects.length > 0;
}

/** Within a category any-of-selected (OR); across categories all must pass (AND); empty = no filter.
 *  The assignee category also honours the UNASSIGNED sentinel: it matches tasks with no assignee. */
export function taskPassesView(task: Task, view: View): boolean {
    if (view.assignees.length) {
        const matchesMember = task.assignees.some((a) => view.assignees.includes(a));
        const matchesUnassigned = view.assignees.includes(UNASSIGNED) && task.assignees.length === 0;
        if (!matchesMember && !matchesUnassigned) return false;
    }
    if (view.tags.length && !task.tags.some((t) => view.tags.includes(t))) return false;
    if (view.projects.length && !view.projects.includes(projectOf(task.id))) return false;
    return true;
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

// ---- deadlines ------------------------------------------------------------------------------
export const DEADLINE_SOON_DAYS = 3;

function isoDate(d: Date): string {
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** The viewer's LOCAL calendar date, YYYY-MM-DD. */
export function todayLocal(): string {
    return isoDate(new Date());
}

function addDays(iso: string, days: number): string {
    const d = new Date(`${iso}T00:00:00`);
    d.setDate(d.getDate() + days);
    return isoDate(d);
}

/** Colour bucket for a deadline vs the viewer's local today (from nowFrame): overdue / due-soon /
 *  later. ISO date strings order correctly with `<`, so no Date parsing needed for the comparison. */
export function deadlineStatus(deadline?: string | null): "past" | "soon" | "later" | null {
    if (!deadline) return null;
    const today = (nowFrame.read("today") as string) || todayLocal();
    if (deadline < today) return "past";
    if (deadline <= addDays(today, DEADLINE_SOON_DAYS)) return "soon";
    return "later";
}

/** A short human date for the chip, e.g. "Aug 1". */
export function formatDeadline(deadline: string): string {
    return new Date(`${deadline}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
