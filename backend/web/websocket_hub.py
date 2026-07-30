"""The websocket hub — now ONE derived dict PER CONNECTION, scoped to a single board.

A client connects to ``/ws?board=<name>``. The hub authenticates via the session cookie, checks the
user's access to that board, then spins up a ``JsonFolderDerivedDict`` mirroring ONLY that board's
folder and starts watching it. Every subscription on the connection maps to that one board dict (the
``derived_dict`` name in the message is ignored — a connection sees exactly one board). On disconnect
the dict is stopped and dropped, freeing its watcher. Switching boards = a fresh connection.

Wire protocol (unchanged from before, minus the registry):
    -> {op:"subscribe",   sub_id, key_path}
    <- {op:"subscribed",  sub_id, value, seq}
    <- {op:"update",      sub_id, key_path, value|"__DELETED__", seq}
    -> {op:"unsubscribe", sub_id}
    <- {op:"error",       sub_id?, message}
"""

import asyncio
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from backend.derived.json_folder_derived_dict import JsonFolderDerivedDict
from backend.derived.pub_sub_derived_dict import SubHandle, Update
from backend.services import AppServices
from backend.util.logs import warn
from backend.web.auth import COOKIE_NAME


class WebsocketHub:

    def __init__(self, services: AppServices) -> None:
        self._services = services

    async def handle_connection(self, websocket: WebSocket) -> None:
        await websocket.accept()

        user = self._services.user_for_session(websocket.cookies.get(COOKIE_NAME))
        if user is None:
            await websocket.send_json({"op": "error", "message": "unauthorized"})
            await websocket.close()
            return
        board = self._services.accessible_board_by_name(
            websocket.query_params.get("board", ""), user)
        if board is None:
            await websocket.send_json({"op": "error", "message": "no-access"})
            await websocket.close()
            return

        board_dict = self._services.acquire_board_mirror(board["id"])    # shared, ref-counted mirror

        event_loop = asyncio.get_running_loop()
        outbound_frames: asyncio.Queue = asyncio.Queue()
        live_subscriptions: Dict[str, SubHandle] = {}

        async def sender_loop() -> None:
            while True:
                await websocket.send_json(await outbound_frames.get())

        sender_task = asyncio.create_task(sender_loop())
        try:
            while True:
                message = await websocket.receive_json()
                operation = message.get("op")
                if operation == "subscribe":
                    self._subscribe(board_dict, message, live_subscriptions,
                                    outbound_frames, event_loop)
                elif operation == "unsubscribe":
                    handle = live_subscriptions.pop(message.get("sub_id"), None)
                    if handle is not None:
                        board_dict.unsubscribe(handle)
                else:
                    outbound_frames.put_nowait({"op": "error", "sub_id": message.get("sub_id"),
                                                "message": f"Unknown op {operation!r}."})
        except WebSocketDisconnect:
            pass
        except Exception as error:                          # malformed json etc. — drop the socket
            warn(f"Websocket connection failed: {error!r}")
        finally:
            sender_task.cancel()
            for handle in live_subscriptions.values():
                board_dict.unsubscribe(handle)
            self._services.release_board_mirror(board["id"])   # ref--; stops the watcher on the last

    @staticmethod
    def _subscribe(board_dict: JsonFolderDerivedDict, message: dict,
                   live_subscriptions: Dict[str, SubHandle], outbound_frames: asyncio.Queue,
                   event_loop: asyncio.AbstractEventLoop) -> None:
        sub_id = message.get("sub_id")
        key_path = message.get("key_path", "")
        if sub_id in live_subscriptions:                    # a 2nd sub() replaces the subscription
            board_dict.unsubscribe(live_subscriptions.pop(sub_id))

        def forward_update(update: Update, forward_sub_id=sub_id) -> None:
            frame = {"op": "update", "sub_id": forward_sub_id, "key_path": update.key_path,
                     "value": update.value, "seq": update.seq}
            event_loop.call_soon_threadsafe(outbound_frames.put_nowait, frame)

        handle = board_dict.subscribe(key_path, forward_update)
        live_subscriptions[sub_id] = handle
        outbound_frames.put_nowait({"op": "subscribed", "sub_id": sub_id,
                                    "value": handle.initial_value, "seq": handle.initial_seq})
