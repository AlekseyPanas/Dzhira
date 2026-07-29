"""``APubSubDerivedDict`` — the core abstraction (ported from eventCamera §4).

An abstract, READ-ONLY, observable dictionary that is a pure function of some external state (here:
the JSON DB folder). It delivers VALUES plus a per-instance monotonic sequence number. Nothing
downstream can tell whether the value came off disk or was computed — the dict IS the interface.

Threading / delivery model (worth reading twice):

  * All state (the derived tree, the seq counter, the subscription table) lives under ONE
    ``_state_lock``. Mutation + seq increment + update-queueing are atomic under it, so
    ``read`` / ``snapshot`` / ``subscribe`` never observe a half-applied multi-key change, and
    ``subscribe``'s snapshot-and-register is atomic.

  * Callbacks are NOT fired under the state lock. ``_publish`` only appends to a FIFO queue; the
    mutator then calls ``_drain_pending_updates()`` AFTER releasing the state lock, serialized by a
    separate ``_dispatch_lock``. This keeps delivery IN SEQ ORDER even with concurrent publishers
    and avoids deadlocks from firing a callback while holding the state lock.

  * Each subscription is seq-filtered at delivery: updates with ``seq <=`` the subscription's
    snapshot seq are skipped (already inside the snapshot the subscriber got). Every subscriber sees
    exactly-once, in-order, post-snapshot updates.

  * An update whose path is an ANCESTOR of a subscription's path is PROJECTED: the subscriber
    receives ``Update(sub.key_path, <current value there, or DELETED>, seq)`` so its stream stays
    self-contained at its own root. Descendant-or-equal updates forward verbatim (absolute paths).

  * Delivered / returned values are deep copies — subscribers can never mutate internal state.
"""

import copy
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Tuple

from backend.derived.key_paths import get_at_path, paths_intersect, split_key_path
from backend.derived.node_types import TNodeValue
from backend.util.logs import warn

# The deletion sentinel — deliberately the literal wire value, so backend publishes, websocket
# frames and frontend frames all compare against the SAME constant.
DELETED = "__DELETED__"


@dataclass(frozen=True)
class Update:
    """One published change: the granularity that changed, its new value (or DELETED), and the
    publishing dict's seq at that change."""
    key_path: str
    value: TNodeValue                                       # new value, or the DELETED sentinel
    seq: int


@dataclass
class SubHandle:
    """Returned by ``subscribe``: the unsubscribe token, carrying the atomic initial snapshot."""
    subscription_id: int
    key_path: str
    callback: Callable[[Update], None] = field(repr=False)
    initial_value: TNodeValue = None                        # value at key_path when registered
    initial_seq: int = 0                                    # seq that initial_value reflects


class APubSubDerivedDict(ABC):
    """See the module docstring for the threading/delivery model."""

    def __init__(self) -> None:
        self._state_lock = threading.RLock()
        self._seq = 0
        self._next_subscription_id = 0
        self._subscriptions: Dict[int, SubHandle] = {}
        self._pending_updates: Deque[Update] = deque()
        self._dispatch_lock = threading.Lock()

    # ------------------------------------------------------------------ derivation (subclasses)
    @abstractmethod
    def _current_full(self) -> Dict[str, TNodeValue]:
        """Return the CURRENT full derived tree. Caller holds ``_state_lock``; no copying here."""

    # ------------------------------------------------------------------ read side
    def read(self, key_path: str = "") -> TNodeValue:
        """Value at ``key_path`` ("" = whole tree); the DELETED sentinel when the path is absent."""
        return self.snapshot(key_path)[0]

    def snapshot(self, key_path: str = "") -> Tuple[TNodeValue, int]:
        """Atomic ``(value, seq)`` — the value at ``key_path`` and the seq it reflects."""
        with self._state_lock:
            return self._value_at_locked(key_path), self._seq

    def subscribe(self, key_path: str, callback: Callable[[Update], None]) -> SubHandle:
        """Atomically snapshot ``key_path`` AND register ``callback`` for every intersecting change.
        The returned handle carries ``initial_value`` / ``initial_seq``; ``callback`` only ever
        receives updates with ``seq > initial_seq``."""
        with self._state_lock:
            handle = SubHandle(
                subscription_id=self._next_subscription_id,
                key_path=key_path,
                callback=callback,
                initial_value=self._value_at_locked(key_path),
                initial_seq=self._seq)
            self._next_subscription_id += 1
            self._subscriptions[handle.subscription_id] = handle
            return handle

    def unsubscribe(self, handle: SubHandle) -> None:
        with self._state_lock:
            self._subscriptions.pop(handle.subscription_id, None)

    def _navigate(self, tree: TNodeValue, steps: List[Any]) -> Tuple[bool, TNodeValue]:
        """How a key path walks THIS dict's tree. Default = plain dict/list navigation (a hook only
        so a decorated flavor could override it — Dzhira never needs to)."""
        return get_at_path(tree, steps)

    def _value_at_locked(self, key_path: str) -> TNodeValue:
        """Deep-copied value at ``key_path`` (DELETED when absent). Caller holds ``_state_lock``."""
        found, value = self._navigate(self._current_full(), split_key_path(key_path))
        return copy.deepcopy(value) if found else DELETED

    # ------------------------------------------------------------------ publish side
    def _publish(self, key_path: str, value_or_deleted: TNodeValue) -> None:
        """Queue one change for delivery. Caller MUST hold ``_state_lock``, MUST have already applied
        the change to the derived state, and MUST call ``_drain_pending_updates()`` after releasing
        the lock (the folder mirror does all of this for you)."""
        self._seq += 1
        self._pending_updates.append(
            Update(key_path=key_path, value=copy.deepcopy(value_or_deleted), seq=self._seq))

    def _drain_pending_updates(self) -> None:
        """Deliver queued updates, in seq order, outside the state lock. Safe from any thread;
        concurrent callers serialize on the dispatch lock and one of them does the work."""
        with self._dispatch_lock:
            while True:
                with self._state_lock:
                    if not self._pending_updates:
                        return
                    update = self._pending_updates.popleft()
                    subscriptions = list(self._subscriptions.values())
                for handle in subscriptions:
                    if update.seq <= handle.initial_seq:            # already inside its snapshot
                        continue
                    if not paths_intersect(update.key_path, handle.key_path):
                        continue
                    delivery = self._project_update_for(handle, update)
                    try:
                        handle.callback(delivery)
                    except Exception as error:                      # a bad subscriber must never
                        warn(f"Subscriber callback for '{handle.key_path}' raised: {error!r}. "
                             f"Continuing delivery.")                # break delivery to the others

    def _project_update_for(self, handle: SubHandle, update: Update) -> Update:
        """Verbatim for descendant-or-equal changes; re-read at the subscription root when the
        change happened at an ANCESTOR path (keeps the subscriber's stream rooted at its own path)."""
        update_steps = split_key_path(update.key_path)
        sub_steps = split_key_path(handle.key_path)
        if update_steps[:len(sub_steps)] == sub_steps:      # equal or descendant of the sub root
            return update
        with self._state_lock:                              # ancestor changed -> project to root
            return Update(key_path=handle.key_path,
                          value=self._value_at_locked(handle.key_path),
                          seq=update.seq)
