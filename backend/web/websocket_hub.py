"""The websocket hub — ONE shared socket per client, multiplexing many derived-dict subscriptions.

    -> {op:"subscribe",   sub_id, derived_dict:<enum name>, key_path}
    <- {op:"subscribed",  sub_id, value, seq}                          # initial snapshot
    <- {op:"update",      sub_id, key_path, value|"__DELETED__", seq}  # live change
    -> {op:"unsubscribe", sub_id}
    <- {op:"error",       sub_id, message}

Derived-dict callbacks fire on the watchdog observer thread; each frame hops onto the event loop via
``loop.call_soon_threadsafe`` feeding a per-connection asyncio queue drained by one sender task. The
hub adds no seq logic: it forwards the derived dict's in-order, seq-stamped stream verbatim.

Ordering caveat (client contract): an ``update`` CAN arrive before its ``subscribed`` frame — a
publish racing the subscribe gets queued first. The client buffers updates for a sub_id it hasn't
seen ``subscribed`` for, then applies them seq-filtered. (Ported from eventCamera's WebsocketHub.)
"""

import asyncio
from typing import Any, Dict, Tuple

from fastapi import WebSocket, WebSocketDisconnect

from backend.derived.pub_sub_derived_dict import APubSubDerivedDict, SubHandle, Update
from backend.util.logs import warn
from backend.web.registry import DerivedDictsRegistry


class WebsocketHub:

    def __init__(self, registry: DerivedDictsRegistry) -> None:
        self._registry = registry

    async def handle_connection(self, websocket: WebSocket) -> None:
        await websocket.accept()
        event_loop = asyncio.get_running_loop()
        outbound_frames: asyncio.Queue = asyncio.Queue()
        # sub_id -> (derived dict, its SubHandle), for replace-on-resubscribe + disconnect cleanup.
        live_subscriptions: Dict[str, Tuple[APubSubDerivedDict, SubHandle]] = {}

        async def sender_loop() -> None:
            while True:
                frame = await outbound_frames.get()
                await websocket.send_json(frame)

        sender_task = asyncio.create_task(sender_loop())
        try:
            while True:
                message = await websocket.receive_json()
                operation = message.get("op")
                if operation == "subscribe":
                    self._handle_subscribe(message, live_subscriptions, outbound_frames, event_loop)
                elif operation == "unsubscribe":
                    self._handle_unsubscribe(message, live_subscriptions)
                else:
                    outbound_frames.put_nowait({"op": "error", "sub_id": message.get("sub_id"),
                                                "message": f"Unknown op {operation!r}."})
        except WebSocketDisconnect:
            pass
        except Exception as error:                          # malformed json etc. — drop the socket
            warn(f"Websocket connection failed: {error!r}")
        finally:
            sender_task.cancel()
            for derived_dict, handle in live_subscriptions.values():
                derived_dict.unsubscribe(handle)
            live_subscriptions.clear()

    def _handle_subscribe(self, message: Dict[str, Any],
                          live_subscriptions: Dict[str, Tuple[APubSubDerivedDict, SubHandle]],
                          outbound_frames: asyncio.Queue,
                          event_loop: asyncio.AbstractEventLoop) -> None:
        sub_id = message.get("sub_id")
        key_path = message.get("key_path", "")
        try:
            derived_dict = self._registry.get_derived_dict(message.get("derived_dict"))
        except ValueError as error:
            outbound_frames.put_nowait({"op": "error", "sub_id": sub_id, "message": str(error)})
            return
        if sub_id in live_subscriptions:                    # a 2nd sub() replaces the subscription
            old_dict, old_handle = live_subscriptions.pop(sub_id)
            old_dict.unsubscribe(old_handle)

        def forward_update(update: Update, forward_sub_id=sub_id) -> None:
            """Runs on the publisher's (watchdog) thread — hop the frame onto the event loop."""
            frame = {"op": "update", "sub_id": forward_sub_id, "key_path": update.key_path,
                     "value": update.value, "seq": update.seq}
            event_loop.call_soon_threadsafe(outbound_frames.put_nowait, frame)

        handle = derived_dict.subscribe(key_path, forward_update)
        live_subscriptions[sub_id] = (derived_dict, handle)
        outbound_frames.put_nowait({"op": "subscribed", "sub_id": sub_id,
                                    "value": handle.initial_value, "seq": handle.initial_seq})

    @staticmethod
    def _handle_unsubscribe(message: Dict[str, Any],
                            live_subscriptions: Dict[str, Tuple[APubSubDerivedDict, SubHandle]]
                            ) -> None:
        subscription = live_subscriptions.pop(message.get("sub_id"), None)
        if subscription is not None:
            derived_dict, handle = subscription
            derived_dict.unsubscribe(handle)
