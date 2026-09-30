# Adapters

An adapter connects voicebench to the agent under test. It sends user audio frames and reports what the agent sends back. Everything else, including timing, recording, and metrics, happens in the runner.

## Choose an adapter

| Adapter | Clock | Use it for |
| --- | --- | --- |
| `mock` | Virtual | Trying voicebench, testing scenarios, and CI checks of the harness itself. |
| `websocket` | Real | Any agent that can stream raw PCM over a WebSocket. Often the easiest integration: add a small endpoint to your agent. |
| `livekit` (experimental) | Real | Agents built on LiveKit Agents, or anything that joins a LiveKit room. |
| `pipecat` (experimental) | Real | Pipecat bots that use a WebSocket transport with `ProtobufFrameSerializer`. |
| `module:Class` | Either | Your own transport. |

## Mock agent

The mock agent detects the end of each user turn with an energy threshold, waits, and answers with a synthetic voice. All behavior comes from options:

| Option | Default | Description |
| --- | --- | --- |
| `endpoint_silence_ms` | `300` | Silence after user speech before the mock treats the turn as over. |
| `response_delay_ms` | `400` | Extra delay before the reply starts. |
| `jitter_ms` | `0` | Random extra delay per reply, drawn from `seed`. |
| `response_ms` | `1500` | Length of each reply. |
| `greeting_ms` | `0` | If set, the mock speaks first for this long. |
| `level_db` | `-20` | Reply level in dBFS. |
| `threshold_db` | `-45` | Level at which the mock hears user audio. |
| `interruptible` | `true` | Whether the mock yields to barge-in. |
| `barge_in_min_ms` | `100` | Overlapping user audio needed before the mock treats it as a barge-in. Shorter noise does not interrupt it. |
| `interrupt_reaction_ms` | `150` | How long the mock keeps talking after it detects a barge-in. |
| `transcripts` | `[]` | Fixture transcripts the mock reports, one per detected user turn. |
| `seed` | `0` | Seed for jitter and the synthetic voice. |

Pass `--realtime` to run the mock on the wall clock instead of virtual time.

## WebSocket protocol

The `websocket` adapter opens one connection per session.

**Client to agent**

- Binary messages: one frame of mono, 16-bit, little-endian PCM at the session sample rate. By default each message holds 20 ms of audio, sent every 20 ms, including silence.
- If you set the `start_message` option, the adapter first sends it as a JSON text message, with `sample_rate` added.

**Agent to client**

- Binary messages: mono 16-bit little-endian PCM at `agent_sample_rate` (defaults to the session rate). Any size is fine. voicebench places each message at its arrival time, or right after the previous message if that one has not finished playing.
- Text messages, all optional:
  - `{"type": "clear"}` means the agent was interrupted. voicebench drops any agent audio it received but has not played yet.
  - `{"type": "transcript", "role": "user", "text": "...", "final": true}` reports what the agent heard, for WER.

voicebench ignores other text messages.

| Option | Default | Description |
| --- | --- | --- |
| `url` | `ws://127.0.0.1:8765` | Agent URL. `--url` on the command line sets it. |
| `agent_sample_rate` | session rate | Sample rate of the agent's audio. |
| `start_message` | none | JSON object sent once before any audio. |
| `headers` | none | Extra HTTP headers for the handshake, for example an authorization header. |
| `connect_timeout_s` | `10` | Connection timeout. |

Reports include the URL without its query string or credentials.

Try the protocol end to end with the bundled server:

```sh
voicebench mock-server --port 8765
voicebench run examples/websocket.yaml
```

## LiveKit (experimental)

```sh
pip install 'voicebench[livekit]'
export LIVEKIT_URL=wss://your-project.livekit.cloud
export LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=...
voicebench run examples/livekit.yaml
```

The adapter creates a room (or joins `room`), optionally dispatches the worker named in `agent_name`, publishes the scripted audio as a microphone track, and records every remote audio track as agent audio. It waits up to `wait_for_agent_s` for the first agent track before the session starts.

It reads user transcripts from LiveKit Agents text streams on the `lk.transcription` topic and from legacy transcription events.

Limitations:

- LiveKit sends no explicit `clear` event, so barge-in timing comes from the audio the agent stops sending.
- Received timing includes the client SDK's jitter buffer.
- The test suite does not exercise this adapter against a LiveKit server.

## Pipecat (experimental)

```sh
pip install 'voicebench[pipecat]'
voicebench run examples/pipecat.yaml --url ws://127.0.0.1:8765
```

The adapter sends user audio as protobuf `AudioRawFrame` messages and reads back audio, interruption, and transcription frames. Your pipeline must forward `TranscriptionFrame` to the output transport for WER to work.

The test suite does not exercise this adapter against a running Pipecat bot.

## Write your own adapter

Subclass `voicebench.adapters.Adapter`:

```python
from typing import Any, ClassVar

from voicebench.adapters import Adapter, AgentAudio, AgentClear, Transcript
from voicebench.audio import FloatArray


class MyAdapter(Adapter):
    name: ClassVar[str] = "my-agent"

    def __init__(self, url: str, **options: Any) -> None:
        super().__init__(**options)
        self.url = url

    async def connect(self) -> None:
        # self.session has sample_rate, frame_ms, clock, and scenario_name.
        ...

    async def send_audio(self, pcm: FloatArray) -> None:
        # pcm is one frame of mono float32 audio in [-1, 1] at the session rate.
        ...

    async def close(self) -> None:
        # Release everything. The runner calls this when the session ends, even if it fails.
        ...
```

Report what the agent sends with `self.emit(...)`:

- `AgentAudio(pcm, time)` for agent audio, as float32 at the session sample rate.
- `AgentClear(time)` when the agent signals an interruption.
- `Transcript(role, text, time, final)` for transcripts.

Take `time` from `self.session.clock.now()` when the event arrives. The runner calls `drain()` once per frame to collect events.

Set `supports_virtual_clock = True` only if the adapter never waits on anything outside the process. Network adapters must run on the real clock.

Run it by module path:

```sh
PYTHONPATH=. voicebench run scenario.yaml -a my_module:MyAdapter -o url=wss://example.com/agent
```

[examples/echo_adapter.py](../examples/echo_adapter.py) is a complete adapter you can copy.

Keep secrets out of `describe()`, because its output goes into the report.
