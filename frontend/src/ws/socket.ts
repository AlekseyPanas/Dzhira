// The ONE shared, reconnecting, multiplexed websocket. Frames (SyncedClientFrame) register
// subscriptions here; this module owns the socket lifecycle. (Ported from eventCamera's socket.ts.)
//
//   - subscribe(derivedDict, keyPath, handlers) -> unsubscribe fn. Survives reconnects: on every
//     (re)open the socket re-sends subscribe for all live subscriptions — each yields a FRESH
//     "subscribed" snapshot, and the handler resets its seq baseline from it (safe across server
//     restarts, where seq starts over).
//   - Ordering caveat (see backend/web/websocket_hub.py): an "update" CAN arrive before its
//     "subscribed" frame. Updates for a sub_id whose snapshot hasn't landed since the last
//     (re)subscribe are BUFFERED and replayed (seq-filtered by the frame) after the snapshot.

import type { TDerivedDictName } from "../derived_dicts";
import type { TTreeValue } from "../key_paths";

export interface SubscriptionHandlers {
    onSnapshot(value: TTreeValue, seq: number): void;
    onUpdate(keyPath: string, value: TTreeValue, seq: number): void;
    onError?(message: string): void;
}

interface LiveSubscription {
    subId: string;
    derivedDict: TDerivedDictName;
    keyPath: string;
    handlers: SubscriptionHandlers;
    snapshotReceived: boolean;
    bufferedUpdates: Array<{ keyPath: string; value: TTreeValue; seq: number }>;
}

const RECONNECT_MIN_DELAY_MS = 500;
const RECONNECT_MAX_DELAY_MS = 5000;

class MultiplexedSocket {
    private websocket: WebSocket | null = null;
    private subscriptions = new Map<string, LiveSubscription>();
    private nextSubNumber = 1;
    private reconnectDelayMs = RECONNECT_MIN_DELAY_MS;

    connect(): void {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        this.websocket = new WebSocket(`${protocol}//${location.host}/ws`);
        this.websocket.onopen = () => {
            this.reconnectDelayMs = RECONNECT_MIN_DELAY_MS;
            for (const subscription of this.subscriptions.values()) {
                subscription.snapshotReceived = false;      // expect a fresh snapshot
                subscription.bufferedUpdates = [];
                this.sendSubscribe(subscription);
            }
        };
        this.websocket.onmessage = (event) => this.handleFrame(JSON.parse(event.data));
        this.websocket.onerror = () => console.warn("[socket] error");
        this.websocket.onclose = () => {
            this.websocket = null;
            setTimeout(() => this.connect(), this.reconnectDelayMs);
            this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, RECONNECT_MAX_DELAY_MS);
        };
    }

    subscribe(derivedDict: TDerivedDictName, keyPath: string,
              handlers: SubscriptionHandlers): () => void {
        const subId = `sub_${this.nextSubNumber++}`;
        const subscription: LiveSubscription = {
            subId, derivedDict, keyPath, handlers, snapshotReceived: false, bufferedUpdates: [],
        };
        this.subscriptions.set(subId, subscription);
        this.sendSubscribe(subscription);                   // no-op when closed; onopen resends
        return () => {
            this.subscriptions.delete(subId);
            this.sendIfOpen({ op: "unsubscribe", sub_id: subId });
        };
    }

    private sendSubscribe(subscription: LiveSubscription): void {
        this.sendIfOpen({ op: "subscribe", sub_id: subscription.subId,
                          derived_dict: subscription.derivedDict, key_path: subscription.keyPath });
    }

    private sendIfOpen(frame: object): void {
        if (this.websocket !== null && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(frame));
        }
    }

    private handleFrame(frame: any): void {
        const subscription = this.subscriptions.get(frame.sub_id);
        if (subscription === undefined) return;             // late frame for an unsubscribed id
        if (frame.op === "subscribed") {
            subscription.snapshotReceived = true;
            subscription.handlers.onSnapshot(frame.value, frame.seq);
            for (const buffered of subscription.bufferedUpdates) {   // replay; frame seq-filters
                subscription.handlers.onUpdate(buffered.keyPath, buffered.value, buffered.seq);
            }
            subscription.bufferedUpdates = [];
        } else if (frame.op === "update") {
            if (!subscription.snapshotReceived) {
                subscription.bufferedUpdates.push(
                    { keyPath: frame.key_path, value: frame.value, seq: frame.seq });
            } else {
                subscription.handlers.onUpdate(frame.key_path, frame.value, frame.seq);
            }
        } else if (frame.op === "error") {
            console.error(`[socket] ${frame.sub_id}: ${frame.message}`);
            subscription.handlers.onError?.(frame.message);
        }
    }
}

// The app-wide singleton (one socket, many subscriptions).
export const sharedSocket = new MultiplexedSocket();
