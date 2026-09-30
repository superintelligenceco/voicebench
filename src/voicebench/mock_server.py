"""WebSocket server that exposes the mock agent over the generic PCM protocol.

Use it to try the ``websocket`` adapter end to end without a real agent::

    voicebench mock-server --port 8765
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from voicebench import audio as au
from voicebench.mock_agent import MockAgent, MockAgentConfig


def make_handler(
    sample_rate: int, config: MockAgentConfig
) -> Callable[[ServerConnection], Awaitable[None]]:
    """Build a connection handler. Each connection gets a fresh mock agent."""

    async def handler(ws: ServerConnection) -> None:
        agent = MockAgent(sample_rate, config)
        origin = time.monotonic()
        with contextlib.suppress(ConnectionClosed):
            async for message in ws:
                if not isinstance(message, bytes):
                    continue  # the optional start message
                frame = au.from_pcm16(message)
                for out in agent.process(frame, time.monotonic() - origin):
                    if out.kind == "audio" and out.pcm is not None:
                        await ws.send(au.to_pcm16(out.pcm))
                    elif out.kind == "clear":
                        await ws.send(json.dumps({"type": "clear"}))
                    else:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "transcript",
                                    "role": "user",
                                    "text": out.text,
                                    "final": True,
                                }
                            )
                        )

    return handler


async def start_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    sample_rate: int = 16000,
    options: dict[str, Any] | None = None,
) -> Server:
    """Start the server and return it. Port 0 picks a free port."""
    config = MockAgentConfig.from_options(options or {})
    return await serve(make_handler(sample_rate, config), host, port, max_size=None)


async def serve_forever(host: str, port: int, sample_rate: int, options: dict[str, Any]) -> None:
    server = await start_server(host, port, sample_rate, options)
    for sock in server.sockets:
        name = sock.getsockname()
        print(f"mock agent listening on ws://{name[0]}:{name[1]} ({sample_rate} Hz PCM16)")
    await asyncio.Future()
