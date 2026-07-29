// bindFrames: Nano JSX does NOT auto-re-render on state change — a component must subscribe to its
// frames and call this.update() itself. This helper wires that once: call it in the component
// CONSTRUCTOR; it wraps didMount/didUnmount so every listed frame's changes trigger update(), and
// every subscription is cleaned up on unmount. (Ported from eventCamera's bind_frames.ts.)

import type { Component } from "nano-jsx";
import type { AClientFrame, TUnsubscribe } from "./a_client_frame";

export function bindFrames(component: Component, frames: AClientFrame[]): void {
    const unsubscribers: TUnsubscribe[] = [];
    const originalDidMount = component.didMount?.bind(component);
    const originalDidUnmount = component.didUnmount?.bind(component);

    component.didMount = () => {
        for (const frame of frames) {
            unsubscribers.push(frame.subscribe("", () => component.update()));
        }
        originalDidMount?.();
    };
    component.didUnmount = () => {
        for (const unsubscribe of unsubscribers) unsubscribe();
        unsubscribers.length = 0;
        originalDidUnmount?.();
    };
}
