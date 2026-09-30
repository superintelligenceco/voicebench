"""Generic WebSocket adapter that streams raw 16-bit PCM in both directions.

Protocol:

* Client to agent: binary messages, each one frame of mono PCM16 little-endian
  audio at ``sample_rate``. If ``start_message`` is set, the adapter first sends
  it as a JSON text message.
* Agent to client: binary messages of mono PCM16 audio at ``agent_sample_rate``
  (defaults to ``sample_rate``), and optional JSON text messages:

  - ``{"type": "clear"}`` drops agent audio that has not played yet.
  - ``{"type": "transcript", "role": "user", "text": "...", "final": true}``
    reports what the agent heard, for WER.

Unknown text messages are ignored.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, ClassVar

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from voicebench import audio as au
from voicebench.adapters.base import (
    Adapter,
    AdapterError,
    AgentAudio,
    AgentClear,
    Role,
    Transcript,
)


class WebSocketAdapter(Adapter):
    """Streams PCM over a WebSocket. Runs on the real clock."""

    name: ClassVar[str] = "websocket"

    def __init__(
        self,
        url: str = "ws://127.0.0.1:8765",
        agent_sample_rate: int | None = None,
        start_message: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        connect_timeout_s: float = 10.0,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.url = url
        self.agent_sample_rate = agent_sample_rate
        self.start_message = start_message
        self.headers = headers or {}
        self.connect_timeout_s = connect_timeout_s
        self._ws: ClientConnection | None = None
        self._reader: asyncio.Task[None] | None = None
        self.receive_error: BaseException | None = None

    async def connect(self) -> None:
        try:
            self._ws = await asyncio.wait_for(
                connect(self.url, additional_headers=self.headers, max_size=None),
                timeout=self.connect_timeout_s,
            )
        except (OSError, TimeoutError) as exc:
            raise AdapterError(f"websocket: cannot connect to {self.url}: {exc}") from exc
        if self.start_message is not None:
            message = {"sample_rate": self.session.sample_rate, **self.start_message}
            await self._ws.send(json.dumps(message))
        self._reader = asyncio.create_task(self._read_loop(self._ws))

    async def _read_loop(self, ws: ClientConnection) -> None:
        clock = self.session.clock
        src_rate = self.agent_sample_rate or self.session.sample_rate
        try:
            async for message in ws:
                now = clock.now()
                if isinstance(message, bytes):
                    self.handle_binary(message, now, src_rate)
                else:
                    self.handle_text(message, now)
        except ConnectionClosed:
            pass
        except Exception as exc:  # surfaced to the caller on close
            self.receive_error = exc

    def handle_binary(self, message: bytes, now: float, src_rate: int) -> None:
        """Decode one binary message from the agent: raw PCM16 in this protocol."""
        pcm = au.resample(au.from_pcm16(message), src_rate, self.session.sample_rate)
        self.emit(AgentAudio(pcm, now))

    def encode_audio(self, pcm: au.FloatArray) -> bytes:
        """Encode one frame of user audio for the wire."""
        return au.to_pcm16(pcm)

    def handle_text(self, message: str, now: float) -> None:
        """Parse one JSON control message from the agent."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        if kind == "clear":
            self.emit(AgentClear(now))
        elif kind == "transcript" and isinstance(data.get("text"), str):
            role: Role = "agent" if data.get("role") == "agent" else "user"
            self.emit(Transcript(role, data["text"], now, bool(data.get("final", True))))

    async def send_audio(self, pcm: au.FloatArray) -> None:
        if self._ws is None:
            raise AdapterError("websocket: not connected")
        try:
            await self._ws.send(self.encode_audio(pcm))
        except ConnectionClosed as exc:
            raise AdapterError(f"websocket: agent closed the connection: {exc}") from exc

    async def close(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
        if self._reader is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._reader, timeout=2.0)
        self._ws = None
        self._reader = None
        if self.receive_error is not None:
            raise AdapterError(f"websocket: receive failed: {self.receive_error}")

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.name,
            "url": _redact_url(self.url),
            "agent_sample_rate": self.agent_sample_rate,
        }


def _redact_url(url: str) -> str:
    """Drop the query string and credentials, which often carry tokens."""
    base = url.split("?", 1)[0]
    if "@" in base:
        scheme, _, rest = base.partition("://")
        base = f"{scheme}://{rest.split('@', 1)[1]}"
    return base
