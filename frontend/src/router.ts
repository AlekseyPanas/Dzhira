// Tiny client-side router. navigate() pushes history + updates routeFrame; back/forward sync via
// popstate. Components read the current route off routeFrame (bind it) and render the right page.

import { routeFrame } from "./frames/shared_frames";

export type Route =
    | { name: "login" }
    | { name: "create" }
    | { name: "new" }
    | { name: "board"; boardName: string }
    | { name: "root" };

export function parseRoute(path: string): Route {
    if (path === "/login") return { name: "login" };
    if (path === "/create") return { name: "create" };
    if (path === "/new") return { name: "new" };
    if (path.startsWith("/board/")) {
        return { name: "board", boardName: decodeURIComponent(path.slice("/board/".length)) };
    }
    return { name: "root" };
}

export function boardPath(boardName: string): string {
    return `/board/${encodeURIComponent(boardName)}`;
}

export function currentRoute(): Route {
    return parseRoute(routeFrame.read("path") as string);
}

/** Go to a path (no-op if already there), updating history + the route frame. */
export function navigate(path: string): void {
    if (path === routeFrame.read("path")) return;
    history.pushState({}, "", path);
    routeFrame.write("path", path);
}

export function initRouter(): void {
    window.addEventListener("popstate", () => routeFrame.write("path", location.pathname));
}
