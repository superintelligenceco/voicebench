# 0003: Use an energy VAD instead of a model

**Status:** Accepted

## Context

voicebench needs to find speech in the user and agent tracks. Neural VADs are more robust to noise, but they add a large dependency, need model downloads, vary between versions, and make results harder to reproduce. The tracks that voicebench analyzes are mostly clean: synthetic or recorded user audio, and TTS output from the agent.

## Decision

voicebench uses a streaming energy detector with a start threshold, hysteresis, a minimum speech duration, and a hangover period. It backdates segment boundaries to the first and last active frame, so the confirmation delays do not add latency. Every parameter is configurable per track in the scenario.

## Consequences

- The core install needs only NumPy, PyYAML, and websockets, and runs anywhere, including the standalone executable.
- Results are deterministic and easy to explain.
- Background noise above the threshold counts as speech. Scenarios with noisy agents need a higher `threshold_db`.
- A pluggable model-based VAD remains possible later without changing the metrics.
