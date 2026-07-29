// Small shared widgets: the boolean-attribute helper, a goofy modal shell, a confirm modal, and a
// text truncator.

import Nano, { Component, h } from "nano-jsx";

/** Boolean HTML attributes (checked/disabled/selected) under Nano JSX: a DEFINED prop is funneled
 *  through setAttribute, and for these attributes PRESENCE wins — `disabled={false}` still disables.
 *  Passing `undefined` makes Nano skip the attribute. So: `disabled={presentIf(x)}`, never `{x}`. */
export function presentIf(condition: boolean): true | undefined {
    return condition ? true : undefined;
}

/** Cut `text` to `max` chars, adding an ellipsis when trimmed. */
export function truncate(text: string, max: number): string {
    const clean = (text ?? "").trim();
    return clean.length > max ? clean.slice(0, max).trimEnd() + "…" : clean;
}

interface ModalProps {
    title: string;
    onClose: () => void;
    children?: any;
    wide?: boolean;
}

/** A draggy-crayon dialog. Click the backdrop (or the ✕) to close; clicks inside don't propagate. */
export const Modal = (props: ModalProps) => (
    <div class="modal-backdrop" onClick={() => props.onClose()}>
        <div class={props.wide ? "modal-box wide" : "modal-box"}
             onClick={(event: Event) => event.stopPropagation()}>
            <div class="modal-titlebar">
                <span class="modal-title">{props.title}</span>
                <button class="modal-x" title="close" onClick={() => props.onClose()}>✕</button>
            </div>
            <div class="modal-body">{props.children}</div>
        </div>
    </div>
);

interface ConfirmModalProps {
    message: string;
    confirmLabel?: string;
    onConfirm: () => void;
    onCancel: () => void;
}

/** The "are you sure?!" warning shown before every destructive action. */
export const ConfirmModal = (props: ConfirmModalProps) => (
    <div class="modal-backdrop" onClick={() => props.onCancel()}>
        <div class="modal-box confirm" onClick={(event: Event) => event.stopPropagation()}>
            <div class="confirm-bang">⚠️</div>
            <div class="confirm-message">{props.message}</div>
            <div class="modal-buttons">
                <button class="crayon-btn" onClick={() => props.onCancel()}>Nooo, cancel</button>
                <button class="crayon-btn danger" onClick={() => props.onConfirm()}>
                    {props.confirmLabel ?? "Yes, do it"}
                </button>
            </div>
        </div>
    </div>
);
