"""A minimal custom adapter: an "agent" that plays your audio back after a delay.

Use it as a template for your own transport. Run it with:

    PYTHONPATH=examples voicebench run examples/echo.yaml -a echo_adapter:EchoAdapter
"""

from __future__ import annotations

from collections import deque
from typing import Any, ClassVar

import numpy as np

from voicebench.adapters import Adapter, AgentAudio
from voicebench.audio import FloatArray, ms_to_samples


class EchoAdapter(Adapter):
    """Echoes user audio back ``delay_ms`` later, with ``gain_db`` applied."""

    name: ClassVar[str] = "echo"
    # This adapter never touches the network, so it can run on virtual time.
    supports_virtual_clock: ClassVar[bool] = True

    def __init__(self, delay_ms: float = 500.0, gain_db: float = 0.0, **options: Any) -> None:
        super().__init__(**options)
        self.delay_ms = float(delay_ms)
        self.gain = float(10.0 ** (gain_db / 20.0))
        self._queue: deque[FloatArray] = deque()
        self._delay_frames = 0

    async def connect(self) -> None:
        frame = ms_to_samples(self.session.frame_ms, self.session.sample_rate)
        self._delay_frames = max(1, ms_to_samples(self.delay_ms, self.session.sample_rate) // frame)
        self._queue.clear()

    async def send_audio(self, pcm: FloatArray) -> None:
        self._queue.append(pcm * self.gain)
        if len(self._queue) > self._delay_frames:
            out = self._queue.popleft()
            if np.any(out):
                self.emit(AgentAudio(out.astype(np.float32), self.session.clock.now()))

    async def close(self) -> None:
        self._queue.clear()

    def describe(self) -> dict[str, Any]:
        return {"type": self.name, "delay_ms": self.delay_ms}
