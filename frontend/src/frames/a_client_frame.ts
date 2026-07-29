// Frontend frames: a frame wraps a Nano JSX Store (the state holder) and adds the key-path-granular
// subscription surface that components and derived logic use. Nano's own Store listeners fire on
// whole-state swaps with no path info, so the frame keeps its own listener registry and its mutation
// paths report exactly which key path changed. (Ported from eventCamera's a_client_frame.ts.)

import { Store } from "nano-jsx";
import {
    DELETED,
    getAtPath,
    pathsIntersect,
    splitKeyPath,
    type TPathStep,
    type TTreeValue,
} from "../key_paths";

export interface FrameChange {
    keyPath: string;                                        // frame-relative path that changed
    value: TTreeValue;                                      // new value, or DELETED
}

export type TFrameListener = (change: FrameChange) => void;
export type TUnsubscribe = () => void;

export abstract class AClientFrame {
    protected store: Store;
    private listeners = new Map<number, { keyPath: string; listener: TFrameListener }>();
    private nextListenerId = 1;

    protected constructor(initialState: TTreeValue) {
        this.store = new Store(initialState ?? {});
    }

    /** Value at `keyPath` ("" = the whole frame state); DELETED when absent. */
    read(keyPath: string = ""): TTreeValue {
        const { found, value } = getAtPath(this.store.state, splitKeyPath(keyPath));
        return found ? value : DELETED;
    }

    /** Fire `listener` for every change intersecting `keyPath`. Returns the unsubscribe. */
    subscribe(keyPath: string, listener: TFrameListener): TUnsubscribe {
        const listenerId = this.nextListenerId++;
        this.listeners.set(listenerId, { keyPath, listener });
        return () => this.listeners.delete(listenerId);
    }

    protected swapState(newState: TTreeValue): void {
        this.store.setState(newState);
    }

    protected currentState(): TTreeValue {
        return this.store.state;
    }

    /** Notify every listener whose key path intersects `changedKeyPath`. */
    protected fireChange(changedKeyPath: string, value: TTreeValue): void {
        for (const { keyPath, listener } of [...this.listeners.values()]) {
            if (pathsIntersect(changedKeyPath, keyPath)) {
                try {
                    listener({ keyPath: changedKeyPath, value });
                } catch (error) {
                    console.error("[frame] listener failed:", error);
                }
            }
        }
    }
}
