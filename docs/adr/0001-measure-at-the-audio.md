# 0001: Measure at the audio

**Status:** Accepted

## Context

Voice agent frameworks expose timing events: end of user speech from the STT, first token from the LLM, first byte from the TTS. Each framework names and places these events differently, and none of them covers the network, the client jitter buffer, or the codec. A caller hears none of those events. A caller hears audio.

## Decision

voicebench treats the agent as a black box. It records the audio that it sends and the audio that it receives, and derives every metric from those two tracks with a voice activity detector. Adapters move audio and a few optional events (`clear`, `transcript`), and never report timings.

## Consequences

- The same scenario gives comparable numbers across frameworks, transports, and vendors.
- A new transport needs only an adapter that sends and receives PCM, not a timing integration.
- Latency includes everything between voicebench and the agent. Users who want the agent alone must run voicebench close to it.
- Metric accuracy depends on the VAD. See [0003](0003-energy-vad-over-a-model.md).
