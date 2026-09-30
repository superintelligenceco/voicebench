"""The generic WebSocket adapter against the mock agent server on localhost."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

from voicebench import audio as au
from voicebench.adapters import AdapterError, create_adapter
from voicebench.adapters.base import AgentAudio, AgentClear, SessionInfo, Transcript
from voicebench.adapters.websocket import WebSocketAdapter, _redact_url
from voicebench.bench import run_benchmark
from voicebench.clock import RealClock
from voicebench.mock_server import start_server
from voicebench.scenario import parse_scenario

pytestmark = pytest.mark.realtime


def _session(sr: int = 16000) -> SessionInfo:
    return SessionInfo(sample_rate=sr, frame_ms=20, clock=RealClock(), scenario_name="t")


def test_session_against_mock_server() -> None:
    scenario = parse_scenario(
        {
            "name": "ws",
            "tail_ms": 500,
            "adapter": {"type": "websocket"},
            "turns": [
                {
                    "id": "q",
                    "audio": {"synth": "speech", "duration_ms": 700},
                    "start": {"delay_ms": 100},
                    "text": "what time is it",
                },
                {
                    "id": "b",
                    "audio": {"synth": "speech", "duration_ms": 700, "seed": 1},
                    "start": {"after": "agent_speech_start", "delay_ms": 400},
                    "expect": "stop",
                },
            ],
        }
    )

    async def go() -> Any:
        server = await start_server(
            port=0,
            options={
                "response_ms": 2000,
                "barge_in_min_ms": 100,
                "interrupt_reaction_ms": 100,
                "transcripts": ["what time is it"],
            },
        )
        port = server.sockets[0].getsockname()[1]
        try:
            return await run_benchmark(scenario, options={"url": f"ws://127.0.0.1:{port}"})
        finally:
            server.close()
            await server.wait_closed()

    result = asyncio.run(go())
    q, b = result.sessions[0].turns
    assert result.report["clock"] == "real"
    assert q.responded
    assert q.response_latency_ms is not None
    assert 600 <= q.response_latency_ms <= 1200
    assert q.ttfa_ms is not None
    assert q.wer == 0.0
    assert b.stopped
    assert b.stop_latency_ms is not None
    assert 150 <= b.stop_latency_ms <= 700


def test_protocol_messages_and_start_message() -> None:
    received: list[Any] = []

    async def handler(ws: ServerConnection) -> None:
        received.append(await ws.recv())
        await ws.send(au.to_pcm16(au.tone(20, 8000)))
        await ws.send(json.dumps({"type": "clear"}))
        await ws.send(json.dumps({"type": "transcript", "role": "user", "text": "hi"}))
        await ws.send("not json")
        await ws.send(json.dumps(["not", "a", "dict"]))
        received.append(await ws.recv())

    async def go() -> list[Any]:
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            adapter = WebSocketAdapter(
                url=f"ws://127.0.0.1:{port}",
                agent_sample_rate=8000,
                start_message={"type": "start"},
            )
            await adapter.start(_session())
            await adapter.send_audio(au.silence(20, 16000))
            await asyncio.sleep(0.3)
            await adapter.close()
            return adapter.drain()

    events = asyncio.run(go())
    assert json.loads(received[0]) == {"sample_rate": 16000, "type": "start"}
    assert isinstance(received[1], bytes)
    assert len(received[1]) == 640
    kinds = [type(e) for e in events]
    assert kinds == [AgentAudio, AgentClear, Transcript]
    audio = events[0]
    assert isinstance(audio, AgentAudio)
    assert audio.pcm.size == 320  # 20 ms at 8 kHz resampled to 16 kHz


def test_connect_failure_raises_adapter_error() -> None:
    adapter = create_adapter("websocket", {"url": "ws://127.0.0.1:9", "connect_timeout_s": 2})
    with pytest.raises(AdapterError, match="cannot connect"):
        asyncio.run(adapter.start(_session()))


def test_redact_url() -> None:
    assert _redact_url("wss://user:pw@example.com/agent?token=abc") == "wss://example.com/agent"
    assert _redact_url("ws://127.0.0.1:8765") == "ws://127.0.0.1:8765"
