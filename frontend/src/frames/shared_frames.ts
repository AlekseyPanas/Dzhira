// The shared frame singletons.
//   - authFrame:      the logged-in user ({id,username,color}) or null — from /api/auth/me.
//   - routeFrame:     the current client-side path (see router.ts).
//   - boardFrame:     a SyncedClientFrame mirroring the CURRENT board's content over the websocket.
//   - boardMetaFrame: the current board's id/name + members (id→username/color/role) + my role —
//                     fetched via API (not the socket), refreshed on board load + membership change.
//   - uiFrame:        which popout / confirm is open.

import { LocalClientFrame } from "./local_client_frame";
import { SyncedClientFrame } from "./synced_client_frame";

export const authFrame = new LocalClientFrame({ user: null });
export const routeFrame = new LocalClientFrame({ path: location.pathname });
// The viewer's LOCAL "today" (YYYY-MM-DD), used to colour deadline chips. Ticked client-side (see
// client.tsx) so chips recolour across midnight without a refresh. Deliberately NOT backend-synced —
// each viewer compares against their own clock/timezone.
export const nowFrame = new LocalClientFrame({ today: "" });
export const boardFrame = new SyncedClientFrame();   // <- board.json + columns/tags/projects/tasks
export const boardMetaFrame = new LocalClientFrame({ name: "", id: "", members: [], myRole: null });

// popup:   null | { kind: "task", taskId? } | "tags" | "projects" | "profile" | "invite" | "boards"
// confirm: null | { message, confirmLabel?, action }
export const uiFrame = new LocalClientFrame({ popup: null, confirm: null });
