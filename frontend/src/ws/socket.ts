// The board websocket: one reconnecting socket bound to ONE board at a time (/ws?board=<name>).
// Switching boards = connect(otherName), which closes the old socket and opens a new one; live
// subscriptions (the board frame) re-subscribe on open and get a fresh snapshot. A connection-level
// error ("unauthorized" / "no-access", sent with no sub_id) is surfaced to a handler so the app can
// redirect (to login, or to a board you can actually see).

import type { TTreeValue } from "../key_paths";

export interface SubscriptionHandlers {
    onSnapshot(value: TTreeValue, seq: number): void;
    onUpdate(keyPath: string, value: TTreeValue, seq: number): void;
}

interface LiveSubscription {
    subId: string;
    keyPath: string;
    handlers: SubscriptionHandlers;
    snapshotReceived: boolean;
    bufferedUpdates: Array<{ keyPath: string; value: TTreeValue; seq: number }>;
}

const RECONNECT_MIN_DELAY_MS = 500;
const RECONNECT_MAX_DELAY_MS = 5000;

class BoardSocket {
    private websocket: WebSocket | null = null;
    private boardName = "";
    private subscriptions = new Map<string, LiveSubscription>();
    private nextSubNumber = 1;
    private reconnectDelayMs = RECONNECT_MIN_DELAY_MS;
    private connectionErrorHandler: (message: string) => void = () => {};

    setConnectionErrorHandler(handler: (message: string) => void): void {
        this.connectionErrorHandler = handler;
    }

    /** (Re)connect bound to `boardName`. Idempotent for the same board while open. */
    connect(boardName: string): void {
        if (boardName === this.boardName && this.websocket
            && this.websocket.readyState <= WebSocket.OPEN) return;
        this.boardName = boardName;
        this.close();
        this.open();
    }

    private open(): void {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${protocol}//${location.host}/ws?board=${encodeURIComponent(this.boardName)}`);
        this.websocket = ws;
        ws.onopen = () => {
            this.reconnectDelayMs = RECONNECT_MIN_DELAY_MS;
            for (const subscription of this.subscriptions.values()) {
                subscription.snapshotReceived = false;
                subscription.bufferedUpdates = [];
                this.sendSubscribe(subscription);
            }
        };
        ws.onmessage = (event) => this.handleFrame(JSON.parse(event.data));
        ws.onerror = () => console.warn("[socket] error");
        ws.onclose = () => {
            if (this.websocket !== ws) return;              // superseded by a board switch
            this.websocket = null;
            setTimeout(() => { if (this.boardName) this.open(); }, this.reconnectDelayMs);
            this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, RECONNECT_MAX_DELAY_MS);
        };
    }

    close(): void {
        if (this.websocket) {
            const dying = this.websocket;
            this.websocket = null;
            dying.onclose = null;                           // don't schedule a reconnect for a swap
            dying.close();
        }
    }

    subscribe(keyPath: string, handlers: SubscriptionHandlers): () => void {
        const subId = `sub_${this.nextSubNumber++}`;
        const subscription: LiveSubscription = { subId, keyPath, handlers, snapshotReceived: false, bufferedUpdates: [] };
        this.subscriptions.set(subId, subscription);
        this.sendSubscribe(subscription);
        return () => {
            this.subscriptions.delete(subId);
            this.sendIfOpen({ op: "unsubscribe", sub_id: subId });
        };
    }

    private sendSubscribe(subscription: LiveSubscription): void {
        this.sendIfOpen({ op: "subscribe", sub_id: subscription.subId, key_path: subscription.keyPath });
    }

    private sendIfOpen(frame: object): void {
        if (this.websocket !== null && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(frame));
        }
    }

    private handleFrame(frame: any): void {
        if (frame.op === "error" && frame.sub_id === undefined) {
            this.connectionErrorHandler(frame.message);     // unauthorized / no-access
            return;
        }
        const subscription = this.subscriptions.get(frame.sub_id);
        if (subscription === undefined) return;
        if (frame.op === "subscribed") {
            subscription.snapshotReceived = true;
            subscription.handlers.onSnapshot(frame.value, frame.seq);
            for (const buffered of subscription.bufferedUpdates) {
                subscription.handlers.onUpdate(buffered.keyPath, buffered.value, buffered.seq);
            }
            subscription.bufferedUpdates = [];
        } else if (frame.op === "update") {
            if (!subscription.snapshotReceived) {
                subscription.bufferedUpdates.push({ keyPath: frame.key_path, value: frame.value, seq: frame.seq });
            } else {
                subscription.handlers.onUpdate(frame.key_path, frame.value, frame.seq);
            }
        } else if (frame.op === "error") {
            console.error(`[socket] ${frame.sub_id}: ${frame.message}`);
        }
    }
}

export const sharedSocket = new BoardSocket();
