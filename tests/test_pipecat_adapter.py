"""Protocol tests for the experimental Pipecat adapter. Skipped without the extra."""

from __future__ import annotations

import pytest

frames_pb2 = pytest.importorskip("pipecat.frames.protobufs.frames_pb2")

from voicebench import audio as au  # noqa: E402
from voicebench.adapters.base import (  # noqa: E402
    AgentAudio,
    AgentClear,
    SessionInfo,
    Transcript,
)
from voicebench.adapters.pipecat import PipecatAdapter  # noqa: E402
from voicebench.clock import VirtualClock  # noqa: E402


def _adapter() -> PipecatAdapter:
    adapter = PipecatAdapter(url="ws://127.0.0.1:1")
    adapter._session = SessionInfo(16000, 20, VirtualClock(), "t")
    return adapter


def test_encode_audio_is_an_audio_raw_frame() -> None:
    pcm = au.tone(20, 16000)
    frame = frames_pb2.Frame.FromString(_adapter().encode_audio(pcm))
    assert frame.WhichOneof("frame") == "audio"
    assert frame.audio.sample_rate == 16000
    assert frame.audio.num_channels == 1
    assert frame.audio.audio == au.to_pcm16(pcm)


def test_decodes_audio_interruption_and_transcription() -> None:
    adapter = _adapter()
    audio = frames_pb2.Frame()
    audio.audio.audio = au.to_pcm16(au.tone(20, 24000))
    audio.audio.sample_rate = 24000
    audio.audio.num_channels = 1
    interruption = frames_pb2.Frame()
    interruption.interruption.SetInParent()
    transcription = frames_pb2.Frame()
    transcription.transcription.text = "hello there"

    for i, frame in enumerate((audio, interruption, transcription)):
        adapter.handle_binary(frame.SerializeToString(), float(i), 16000)
    events = adapter.drain()
    assert [type(e) for e in events] == [AgentAudio, AgentClear, Transcript]
    first = events[0]
    assert isinstance(first, AgentAudio)
    assert first.pcm.size == 320  # resampled from 24 kHz to 16 kHz
    last = events[2]
    assert isinstance(last, Transcript)
    assert last.text == "hello there"
