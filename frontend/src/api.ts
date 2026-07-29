// The HTTP write API: every mutation is a plain POST returning a bare ack; the REAL result arrives
// over the websocket via the DB derived dict. postAck resolves to null on success and to the error
// message string on failure (callers surface it) — no optimistic updates anywhere.
// (Ported from eventCamera's api.ts, pointed at Dzhira's /api/* routes.)

async function postAck(url: string, body?: object): Promise<string | null> {
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body ?? {}),
        });
        if (response.ok) return null;
        const payload = await response.json().catch(() => null);
        return payload?.detail ?? `HTTP ${response.status}`;
    } catch (error) {
        return `Request failed: ${error}`;
    }
}

export const taskApi = {
    create: (projectCode: string, title: string, description: string, tags: string[]) =>
        postAck("/api/task/create", { project_code: projectCode, title, description, tags }),
    update: (taskId: string, title: string, description: string, tags: string[]) =>
        postAck("/api/task/update", { task_id: taskId, title, description, tags }),
    delete: (taskId: string) => postAck("/api/task/delete", { task_id: taskId }),
    move: (taskId: string, statusId: string, index: number) =>
        postAck("/api/task/move", { task_id: taskId, status_id: statusId, index }),
};

export const columnApi = {
    create: (name: string) => postAck("/api/column/create", { name }),
    rename: (columnId: string, name: string) => postAck("/api/column/rename", { column_id: columnId, name }),
    move: (columnId: string, direction: "left" | "right") =>
        postAck("/api/column/move", { column_id: columnId, direction }),
    delete: (columnId: string) => postAck("/api/column/delete", { column_id: columnId }),
};

export const tagApi = {
    create: (name: string, color: string) => postAck("/api/tag/create", { name, color }),
    update: (tagId: string, name: string, color: string) =>
        postAck("/api/tag/update", { tag_id: tagId, name, color }),
    delete: (tagId: string) => postAck("/api/tag/delete", { tag_id: tagId }),
};

export const projectApi = {
    create: (code: string) => postAck("/api/project/create", { code }),
    rename: (code: string, newCode: string) => postAck("/api/project/rename", { code, new_code: newCode }),
    delete: (code: string) => postAck("/api/project/delete", { code }),
};

export const assigneeApi = {
    set: (name: string, color: string) => postAck("/api/assignee/set", { name, color }),
};
