// SyncedClientFrame: a READ-ONLY live mirror of one backend derived dict (at an optional key-path
// root) over the shared websocket. The ws sync layer is its only writer. (Ported from eventCamera,
// minus the decorated-node path — Dzhira's DB mirror is a plain dict tree.)
//
// Seq protocol: the "subscribed" snapshot seeds the mirror and the seq baseline; each update applies
// iff update.seq > lastSeq, then advances. Backend update paths are ABSOLUTE — they get re-rooted to
// this frame's subscription root before applying. Reconnects re-subscribe (fresh snapshot resets the
// baseline, so replays and server restarts are both safe).

import { AClientFrame } from "./a_client_frame";
import {
    DELETED,
    deleteAtPath,
    isAtOrBelow,
    relativeKeyPath,
    setAtPath,
    splitKeyPath,
    type TTreeValue,
} from "../key_paths";
import { sharedSocket } from "../ws/socket";

export class SyncedClientFrame extends AClientFrame {
    private lastSeq = -1;
    private unsubscribeFromSocket: (() => void) | null = null;
    private subscriptionRootPath = "";

    constructor() {
        super({});
    }

    /** Mirror the connection's board dict at `keyPath`. A second sub() replaces the subscription. */
    sub(keyPath: string = ""): void {
        this.unsub();
        this.subscriptionRootPath = keyPath;
        this.unsubscribeFromSocket = sharedSocket.subscribe(keyPath, {
            onSnapshot: (value, seq) => {
                this.lastSeq = seq;                         // fresh baseline (reconnect-safe)
                this.swapState(value === DELETED ? {} : value);
                this.fireChange("", value);
            },
            onUpdate: (absoluteKeyPath, value, seq) => {
                if (seq <= this.lastSeq) return;            // already inside the snapshot
                this.lastSeq = seq;
                this.applyUpdate(absoluteKeyPath, value);
            },
        });
    }

    unsub(): void {
        if (this.unsubscribeFromSocket !== null) {
            this.unsubscribeFromSocket();
            this.unsubscribeFromSocket = null;
        }
    }

    private applyUpdate(absoluteKeyPath: string, value: TTreeValue): void {
        if (!isAtOrBelow(absoluteKeyPath, this.subscriptionRootPath)) return;   // defensive
        const frameRelativePath = relativeKeyPath(absoluteKeyPath, this.subscriptionRootPath);
        if (frameRelativePath === "") {                     // the whole mirror root changed
            this.swapState(value === DELETED ? {} : value);
            this.fireChange("", value);
            return;
        }
        const state = this.currentState();
        const steps = splitKeyPath(frameRelativePath);
        if (value === DELETED) deleteAtPath(state, steps);
        else setAtPath(state, steps, value);
        this.swapState(state);                              // same object; Store notifies anyway
        this.fireChange(frameRelativePath, value);
    }
}
