"""Clocks that drive a benchmark session.

Network adapters run on :class:`RealClock`. The in-process mock agent can run
on :class:`VirtualClock`, which makes a session deterministic and lets it
finish as fast as the CPU allows.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    """Session time in seconds since the session started."""

    realtime: bool

    def now(self) -> float: ...

    async def sleep_until(self, t: float) -> None: ...


class RealClock:
    """Wall-clock time from a monotonic source."""

    realtime = True

    def __init__(self) -> None:
        self._origin = time.monotonic()

    def now(self) -> float:
        return time.monotonic() - self._origin

    async def sleep_until(self, t: float) -> None:
        delay = t - self.now()
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0)


class VirtualClock:
    """Simulated time that jumps forward whenever the session waits."""

    realtime = False

    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    async def sleep_until(self, t: float) -> None:
        self._now = max(self._now, t)
        await asyncio.sleep(0)
