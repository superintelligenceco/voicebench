"""The adapter interface between the runner and an agent under test."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from voicebench.audio import FloatArray
from voicebench.clock import Clock


@dataclass(frozen=True)
class AgentAudio:
    """Agent audio at the session sample rate, received at ``time`` seconds."""

    pcm: FloatArray
    time: float


@dataclass(frozen=True)
class AgentClear:
    """The agent asked the client to drop any audio it has not played yet."""

    time: float


Role = Literal["user", "agent"]


@dataclass(frozen=True)
class Transcript:
    """Text reported by the agent, for example its speech-to-text result."""

    role: Role
    text: str
    time: float
    final: bool = True


AgentEvent = AgentAudio | AgentClear | Transcript


@dataclass(frozen=True)
class SessionInfo:
    """What an adapter needs to know about the session it joins."""

    sample_rate: int
    frame_ms: float
    clock: Clock
    scenario_name: str


class AdapterError(RuntimeError):
    """Raised when an adapter cannot connect to or talk to the agent."""


class Adapter(abc.ABC):
    """Base class for transports.

    Subclasses implement :meth:`connect`, :meth:`send_audio`, and :meth:`close`,
    and report everything the agent sends through :meth:`emit`. The runner
    pulls reported events with :meth:`drain` once per frame.
    """

    #: Name used in reports and on the command line.
    name: ClassVar[str] = "base"
    #: True if the adapter can run on :class:`~voicebench.clock.VirtualClock`.
    supports_virtual_clock: ClassVar[bool] = False

    def __init__(self, **options: Any) -> None:
        self.options = options
        self._session: SessionInfo | None = None
        self._pending: list[AgentEvent] = []

    @property
    def session(self) -> SessionInfo:
        if self._session is None:
            raise AdapterError(f"{self.name}: not connected")
        return self._session

    async def start(self, session: SessionInfo) -> None:
        """Bind the session and connect. The runner calls this once."""
        self._session = session
        await self.connect()

    @abc.abstractmethod
    async def connect(self) -> None:
        """Open the connection to the agent."""

    @abc.abstractmethod
    async def send_audio(self, pcm: FloatArray) -> None:
        """Send one frame of user audio at the session sample rate."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Release all resources. Must be safe to call more than once."""

    def emit(self, event: AgentEvent) -> None:
        """Record an event from the agent."""
        self._pending.append(event)

    def drain(self) -> list[AgentEvent]:
        """Return and clear the events reported since the last call."""
        events, self._pending = self._pending, []
        return events

    def describe(self) -> dict[str, Any]:
        """Adapter details for the report. Never include secrets."""
        return {"type": self.name}
