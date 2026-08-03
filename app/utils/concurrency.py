"""Process-local async locks for critical sections (single-worker safe)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_MAX_LOCKS = 2048
_locks: dict[str, asyncio.Lock] = {}
_registry_lock = asyncio.Lock()


def _prune_unlocked_locks() -> None:
    """Drop idle lock entries when the registry grows too large."""
    if len(_locks) < _MAX_LOCKS:
        return
    stale = [key for key, lock in _locks.items() if not lock.locked()]
    # Keep some headroom; never delete a lock that is currently held.
    drop_count = max(1, len(stale) // 2)
    for key in stale[:drop_count]:
        del _locks[key]


async def _lock_for(key: str) -> asyncio.Lock:
    async with _registry_lock:
        lock = _locks.get(key)
        if lock is None:
            _prune_unlocked_locks()
            lock = asyncio.Lock()
            _locks[key] = lock
        return lock


@asynccontextmanager
async def keyed_lock(key: str) -> AsyncIterator[None]:
    """
    Serialize coroutines that share ``key``.

    Suitable for MemoryStorage / single bot process. Combine with DB row locks
    for checkout so a second worker still cannot double-order.
    """
    lock = await _lock_for(key)
    async with lock:
        yield
