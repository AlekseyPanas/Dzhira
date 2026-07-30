// The board "session": what board the app is currently viewing, driven by the route (not by a
// component lifecycle). When the route is /board/<name> it fetches that board's members (also the
// access check + board id), connects the websocket, subscribes the content frame, and watches
// board.json so membership changes refetch the member list. Access failures bounce you elsewhere.

import { boardsApi, setActiveBoardId } from "./api";
import { authFrame, boardFrame, boardMetaFrame } from "./frames/shared_frames";
import { DELETED } from "./key_paths";
import { boardPath, currentRoute, navigate } from "./router";
import { routeFrame } from "./frames/shared_frames";
import { sharedSocket } from "./ws/socket";

let currentBoardName = "";
let membersUnsub: (() => void) | null = null;
let lastMembershipKey = "";

export function initBoardSession(): void {
    sharedSocket.setConnectionErrorHandler((message) => {
        if (message === "unauthorized") { authFrame.write("user", null); navigate("/login"); }
        else void gotoDefault();
    });
    routeFrame.subscribe("path", () => syncToRoute());
    syncToRoute();
}

function syncToRoute(): void {
    const route = currentRoute();
    if (route.name === "board") {
        if (route.boardName !== currentBoardName) void enterBoard(route.boardName);
    } else {
        leaveBoard();
    }
}

function roleOf(members: Array<{ id: string; role: string }>): string | null {
    const me = authFrame.read("user");
    const mine = me ? members.find((m) => m.id === me.id) : undefined;
    return mine ? mine.role : null;
}

async function enterBoard(name: string): Promise<void> {
    currentBoardName = name;
    try {
        const { board_id, members } = await boardsApi.members(name);
        boardMetaFrame.write("", { name, id: board_id, members, myRole: roleOf(members) });
        setActiveBoardId(board_id);
    } catch {
        await gotoDefault();
        return;
    }
    sharedSocket.connect(name);
    boardFrame.sub("");
    membersUnsub?.();
    lastMembershipKey = "";
    membersUnsub = boardFrame.subscribe("board.json", () => void onBoardJsonChange());
}

function leaveBoard(): void {
    currentBoardName = "";
    membersUnsub?.();
    membersUnsub = null;
    boardFrame.unsub();
    sharedSocket.close();
}

async function onBoardJsonChange(): Promise<void> {
    const boardJson = boardFrame.read("board.json");
    if (boardJson === DELETED || !boardJson || typeof boardJson !== "object") {
        await gotoDefault();                                // the board was deleted under us
        return;
    }
    const key = JSON.stringify([boardJson.owner_id, boardJson.members]);
    if (key === lastMembershipKey) return;
    lastMembershipKey = key;
    try {
        const { members } = await boardsApi.members(currentBoardName);
        boardMetaFrame.write("members", members);
        boardMetaFrame.write("myRole", roleOf(members));
    } catch {
        await gotoDefault();                                // lost access (kicked)
    }
}

async function gotoDefault(): Promise<void> {
    leaveBoard();
    try {
        const { boards } = await boardsApi.list();
        navigate(boards.length ? boardPath(boards[0].name) : "/new");
    } catch {
        navigate("/login");
    }
}
