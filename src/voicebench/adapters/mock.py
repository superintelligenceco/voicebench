"""In-process adapter for :class:`~voicebench.mock_agent.MockAgent`."""

from __future__ import annotations

from typing import Any, ClassVar

from voicebench.adapters.base import Adapter, AgentAudio, AgentClear, Transcript
from voicebench.audio import FloatArray
from voicebench.mock_agent import MockAgent, MockAgentConfig


class MockAdapter(Adapter):
    """Runs the mock agent in the same process, with no network in between."""

    name: ClassVar[str] = "mock"
    supports_virtual_clock: ClassVar[bool] = True

    def __init__(self, **options: Any) -> None:
        super().__init__(**options)
        self.config = MockAgentConfig.from_options(options)
        self._agent: MockAgent | None = None

    async def connect(self) -> None:
        self._agent = MockAgent(self.session.sample_rate, self.config)

    async def send_audio(self, pcm: FloatArray) -> None:
        if self._agent is None:
            raise RuntimeError("mock adapter is not connected")
        t = self.session.clock.now()
        for out in self._agent.process(pcm, t):
            if out.kind == "audio" and out.pcm is not None:
                self.emit(AgentAudio(out.pcm, t))
            elif out.kind == "clear":
                self.emit(AgentClear(t))
            elif out.kind == "transcript":
                self.emit(Transcript("user", out.text, t))

    async def close(self) -> None:
        self._agent = None

    def describe(self) -> dict[str, Any]:
        return {"type": self.name, "config": {**self.config.__dict__}}
