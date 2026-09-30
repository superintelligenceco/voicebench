"""Pipecat adapter (experimental).

Connects to a Pipecat bot that uses a WebSocket transport with
``ProtobufFrameSerializer``, for example ``WebsocketServerTransport`` or
``FastAPIWebsocketTransport``. User audio goes out as ``AudioRawFrame``
messages. The adapter reads back:

* ``audio`` frames as agent audio (resampled to the session rate),
* ``interruption`` frames as a clear event,
* ``transcription`` frames as user transcripts, for WER. Pipecat only sends
  these if your pipeline forwards ``TranscriptionFrame`` to the output transport.

Requires ``pip install 'voicebench[pipecat]'`` for the protobuf definitions.
"""

from __future__ import annotations

from typing import Any, ClassVar

from voicebench import audio as au
from voicebench.adapters.base import AgentAudio, AgentClear, Transcript
from voicebench.adapters.websocket import WebSocketAdapter

try:
    from pipecat.frames.protobufs import frames_pb2  # type: ignore[attr-defined,unused-ignore]
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError("the pipecat adapter needs the 'pipecat-ai' package") from exc


class PipecatAdapter(WebSocketAdapter):
    """Speaks Pipecat's protobuf frame protocol over a WebSocket."""

    name: ClassVar[str] = "pipecat"

    def __init__(self, url: str = "ws://127.0.0.1:8765", **options: Any) -> None:
        options.pop("start_message", None)
        super().__init__(url=url, **options)

    def encode_audio(self, pcm: au.FloatArray) -> bytes:
        frame = frames_pb2.Frame()
        frame.audio.audio = au.to_pcm16(pcm)
        frame.audio.sample_rate = self.session.sample_rate
        frame.audio.num_channels = 1
        data: bytes = frame.SerializeToString()
        return data

    def handle_binary(self, message: bytes, now: float, src_rate: int) -> None:
        frame = frames_pb2.Frame.FromString(message)
        which = frame.WhichOneof("frame")
        if which == "audio":
            audio = frame.audio
            pcm = au.from_pcm16(audio.audio)
            if audio.num_channels > 1:
                pcm = pcm.reshape(-1, audio.num_channels).mean(axis=1).astype(pcm.dtype)
            rate = audio.sample_rate or src_rate
            self.emit(AgentAudio(au.resample(pcm, rate, self.session.sample_rate), now))
        elif which == "interruption":
            self.emit(AgentClear(now))
        elif which == "transcription" and frame.transcription.text:
            self.emit(Transcript("user", frame.transcription.text, now))

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "type": self.name, "experimental": True}
