// Tiny imperative helpers over uiFrame for opening/closing the popouts and the confirm modal.
// Keeping them in one place means every component opens a popup the same way.

import { uiFrame } from "./frames/shared_frames";

export type PopupState =
    | null
    | { kind: "task"; taskId?: string }
    | { kind: "tags" }
    | { kind: "projects" }
    | { kind: "assignee" };

export function openPopup(popup: Exclude<PopupState, null>): void {
    uiFrame.write("popup", popup);
}

export function closePopup(): void {
    uiFrame.write("popup", null);
}

export interface ConfirmRequest {
    message: string;
    confirmLabel?: string;
    action: () => void;
}

/** Pop the "are you sure?!" modal; `action` runs only if the user confirms. */
export function askConfirm(request: ConfirmRequest): void {
    uiFrame.write("confirm", request);
}

export function clearConfirm(): void {
    uiFrame.write("confirm", null);
}
