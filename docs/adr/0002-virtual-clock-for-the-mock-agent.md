# 0002: Run the mock agent on a virtual clock

**Status:** Accepted

## Context

The runner, the VAD, and the metrics need end-to-end tests. Tests against a wall clock are slow, because a conversation takes tens of seconds, and flaky, because CI machines stall. Users also need a demo that works offline without a real agent.

## Decision

The runner takes a `Clock`. Network adapters use `RealClock`. The in-process `mock` adapter uses `VirtualClock`, which advances time only when the runner sleeps, so a session runs as fast as the CPU allows and gives the same result every time.

## Consequences

- The full pipeline runs in milliseconds, so the test suite, the README check, and the benchmark gate cover it on every push.
- The demo output in the README is byte-for-byte reproducible, and a test compares it with a real run.
- Real-clock behavior still needs coverage. The `realtime` tests run the mock agent over a local WebSocket on the wall clock.
