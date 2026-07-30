// The HTTP API client. Auth/account/board/invite calls are request/response (callers await a result
// or an error string). Board CONTENT writes (tasks/columns/tags/projects) still resolve to null (ok)
// or an error string; their real effect streams back over the board websocket. Content writes carry
// the active board id, set once when a board view mounts (setActiveBoardId) so call sites stay short.

let activeBoardId = "";
export function setActiveBoardId(id: string): void { activeBoardId = id; }

async function post(url: string, body?: object): Promise<Response> {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
    });
}

/** POST -> null on success, else the server's error message (for inline error areas). */
async function postAck(url: string, body?: object): Promise<string | null> {
    try {
        const response = await post(url, body);
        if (response.ok) return null;
        const payload = await response.json().catch(() => null);
        return payload?.detail ?? `HTTP ${response.status}`;
    } catch (error) {
        return `Request failed: ${error}`;
    }
}

/** POST/GET returning parsed JSON; throws Error(detail) on non-2xx (callers try/catch). */
async function fetchJson(url: string, method: "GET" | "POST" = "GET", body?: object): Promise<any> {
    const response = method === "POST" ? await post(url, body) : await fetch(url);
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail ?? `HTTP ${response.status}`);
    return payload;
}

// ---- auth ------------------------------------------------------------------------------------
export const authApi = {
    me: () => fetchJson("/api/auth/me"),                                    // {user|null}
    register: (username: string, password: string) => fetchJson("/api/auth/register", "POST", { username, password }),
    login: (username: string, password: string) => fetchJson("/api/auth/login", "POST", { username, password }),
    logout: () => post("/api/auth/logout"),
};

// ---- account (profile edits) ----------------------------------------------------------------
export const accountApi = {
    rename: (username: string) => postAck("/api/account/rename", { username }),
    changePassword: (currentPassword: string, newPassword: string) =>
        postAck("/api/account/change_password", { current_password: currentPassword, new_password: newPassword }),
};

// ---- boards / members / invites -------------------------------------------------------------
export const boardsApi = {
    list: () => fetchJson("/api/boards"),                                   // {boards:[{id,name,role}]}
    create: (name: string) => fetchJson("/api/boards/create", "POST", { name }),   // {name} | throws
    delete: (boardId: string) => postAck("/api/board/delete", { board_id: boardId }),
    members: (name: string) => fetchJson(`/api/board/${encodeURIComponent(name)}/members`),
    boardInvites: (name: string) => fetchJson(`/api/board/${encodeURIComponent(name)}/invites`),
    invite: (username: string) => postAck("/api/board/invite", { board_id: activeBoardId, username }),
    kick: (userId: string) => postAck("/api/board/kick", { board_id: activeBoardId, user_id: userId }),
    transfer: (newOwnerId: string) => postAck("/api/board/transfer", { board_id: activeBoardId, new_owner_id: newOwnerId }),
};

export const invitesApi = {
    mine: () => fetchJson("/api/invites"),                                  // {invites:[{id,board_name,inviter}]}
    accept: (inviteId: string) => postAck("/api/invite/accept", { invite_id: inviteId }),
    reject: (inviteId: string) => postAck("/api/invite/reject", { invite_id: inviteId }),
    withdraw: (inviteId: string) => postAck("/api/invite/withdraw", { invite_id: inviteId }),
};

// ---- board content (carry the active board id) ----------------------------------------------
export const taskApi = {
    create: (projectCode: string, title: string, description: string, tags: string[], assignees: string[], deadline: string | null) =>
        postAck("/api/task/create", { board_id: activeBoardId, project_code: projectCode, title, description, tags, assignees, deadline }),
    update: (taskId: string, title: string, description: string, tags: string[], assignees: string[], deadline: string | null) =>
        postAck("/api/task/update", { board_id: activeBoardId, task_id: taskId, title, description, tags, assignees, deadline }),
    delete: (taskId: string) => postAck("/api/task/delete", { board_id: activeBoardId, task_id: taskId }),
    // afterTaskId = the visible task to drop after (null = top of the column); filter-safe ordering.
    move: (taskId: string, statusId: string, afterTaskId: string | null) =>
        postAck("/api/task/move", { board_id: activeBoardId, task_id: taskId, status_id: statusId, after_task_id: afterTaskId }),
};

export const columnApi = {
    create: (name: string) => postAck("/api/column/create", { board_id: activeBoardId, name }),
    rename: (columnId: string, name: string) => postAck("/api/column/rename", { board_id: activeBoardId, column_id: columnId, name }),
    move: (columnId: string, direction: "left" | "right") => postAck("/api/column/move", { board_id: activeBoardId, column_id: columnId, direction }),
    delete: (columnId: string) => postAck("/api/column/delete", { board_id: activeBoardId, column_id: columnId }),
};

export const tagApi = {
    create: (name: string, color: string) => postAck("/api/tag/create", { board_id: activeBoardId, name, color }),
    update: (tagId: string, name: string, color: string) => postAck("/api/tag/update", { board_id: activeBoardId, tag_id: tagId, name, color }),
    delete: (tagId: string) => postAck("/api/tag/delete", { board_id: activeBoardId, tag_id: tagId }),
};

export const projectApi = {
    create: (code: string, color?: string) => postAck("/api/project/create", { board_id: activeBoardId, code, color }),
    rename: (code: string, newCode: string) => postAck("/api/project/rename", { board_id: activeBoardId, code, new_code: newCode }),
    setColor: (code: string, color: string) => postAck("/api/project/set_color", { board_id: activeBoardId, code, color }),
    delete: (code: string) => postAck("/api/project/delete", { board_id: activeBoardId, code }),
};

// per-user filter view (assignee / tags / projects) — persisted per board, synced via the mirror
export const viewApi = {
    set: (assignees: string[], tags: string[], projects: string[]) =>
        postAck("/api/view/set", { board_id: activeBoardId, assignees, tags, projects }),
};
