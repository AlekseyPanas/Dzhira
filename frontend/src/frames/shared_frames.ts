// The shared frame singletons — the cross-component reference surface.
//   - dbFrame:  a SyncedClientFrame mirroring the whole backend DB derived dict (the read side).
//   - uiFrame:  frontend-only UI state — which popout is open (and its params). One writer at a
//               time by convention (the button that opened it / the popout itself).
// (Drag state is NOT a frame — the drag controller manipulates the DOM directly and commits once on
// drop, so it stays out of the Nano render cycle. See frontend/src/drag_controller.ts.)

import { DerivedDicts } from "../derived_dicts";
import { LocalClientFrame } from "./local_client_frame";
import { SyncedClientFrame } from "./synced_client_frame";

export const dbFrame = new SyncedClientFrame();     // <- DB (meta/projects/tags/columns/tasks)

// popup:   null | { kind: "task", taskId?: string } | { kind: "tags" } | { kind: "projects" }
//                | { kind: "assignee" }
// confirm: null | { message, confirmLabel?, action: () => void }   (action is a live closure)
export const uiFrame = new LocalClientFrame({ popup: null, confirm: null });

/** Wire the synced frame to its dict. Called once from the entrypoint (subscriptions flow on open). */
export function subscribeSharedFrames(): void {
    dbFrame.sub(DerivedDicts.DB);
}
