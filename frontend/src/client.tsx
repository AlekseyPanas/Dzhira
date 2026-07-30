// The client entrypoint. The theme selector is intentionally hidden and PAINT is forced — for the
// showcase we want only the paint look, uncustomizable.
//
// Routing note: instead of a reactive root Component (nano-jsx's root component.update() is fragile —
// it doesn't call didMount on the root and throws if a mid-transition child's DOM is already gone), we
// re-render the WHOLE app with Nano.render (which clears + rebuilds #root) whenever auth or the route
// changes. Those changes are infrequent (login / navigation); board CONTENT and popouts update through
// their own component subscriptions, NOT this, so the board stays smooth.

import Nano, { h } from "nano-jsx";
import { authApi, boardsApi } from "./api";
import { authFrame, routeFrame } from "./frames/shared_frames";
import { installDragController } from "./drag_controller";
import { initBoardSession } from "./board_session";
import { boardPath, currentRoute, initRouter, navigate } from "./router";
import { applyTheme } from "./theme";
import { AuthPage } from "./components/AuthPage";
import { NoBoardsPage } from "./components/NoBoardsPage";
import { BoardView } from "./components/BoardView";
import "./styles.scss";
import "./styles-paint.scss";

function currentPage() {
    const user = authFrame.read("user");
    const route = currentRoute();
    if (!user) return <AuthPage />;                         // AuthPage reads the route (login vs create)
    if (route.name === "board") return <BoardView />;
    if (route.name === "new") return <NoBoardsPage />;
    return <div class="auth-page"><div class="auth-card"><div class="muted">Loading…</div></div></div>;
}

function renderApp(): void {
    Nano.render(currentPage(), document.getElementById("root"));
}

async function boot(): Promise<void> {
    applyTheme("paint");                                    // force paint; the switcher is hidden
    initRouter();
    installDragController();
    authFrame.subscribe("", renderApp);                    // re-render the app on login / logout
    routeFrame.subscribe("", renderApp);                   // ...and on navigation
    renderApp();

    try {
        const { user } = await authApi.me();
        authFrame.write("user", user);
        if (!user) {
            const route = currentRoute();
            if (route.name !== "login" && route.name !== "create") navigate("/login");
        } else {
            const route = currentRoute();
            if (route.name !== "board" && route.name !== "new") {   // honor an explicit board/new URL
                const { boards } = await boardsApi.list();
                navigate(boards.length ? boardPath(boards[0].name) : "/new");
            }
        }
    } catch {
        navigate("/login");
    } finally {
        // ALWAYS wire the route -> board-session link, even if we booted logged-out. Otherwise a user
        // who logs in / registers later this session would navigate to a board whose socket, members,
        // and active-board-id were never set up (that's the empty-board + "'' is not a valid board id"
        // invite bug). syncToRoute no-ops on non-board routes, so this is safe on /login too.
        initBoardSession();
    }
}

boot();
