# AGENTS.md

Instructions for coding agents that work in this repository. Human contributors can read [CONTRIBUTING.md](CONTRIBUTING.md) instead.

## Project

voicebench is a Python 3.11+ package that benchmarks real-time voice agents. It plays a scripted conversation into an agent through an adapter, records both sides, and computes metrics from the recorded audio.

## Layout

| Path | Contents |
| --- | --- |
| `src/voicebench/audio.py` | PCM conversion, WAV I/O, resampling, and test signal synthesis. |
| `src/voicebench/vad.py` | Streaming energy VAD. Boundaries are backdated to the first and last active frame. |
| `src/voicebench/scenario.py` | YAML parsing and validation. Unknown keys are errors. |
| `src/voicebench/runner.py` | The session loop: frame pacing, start anchors, and track recording. |
| `src/voicebench/metrics.py` | Turn and session metrics, summaries, and assertions. |
| `src/voicebench/report.py` | JSON, Markdown, HTML, and console output. |
| `src/voicebench/adapters/` | Adapter base class, registry, and built-in adapters. |
| `src/voicebench/mock_agent.py` | The deterministic mock agent state machine. |
| `tests/` | pytest suite. `realtime` marks tests that use the wall clock. |
| `examples/` | Scenarios and a custom adapter. |
| `docs/` | Metric definitions, scenario reference, and adapter guide. |

## Commands

```sh
python -m pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy
pytest --cov
voicebench run examples/mock-conversation.yaml --no-write
```

All four checks must pass before you finish a change.

## Rules

- Keep `mypy --strict` clean. Do not add `type: ignore` without a reason in the same line.
- Tests must run offline. Build test audio with `voicebench.audio` helpers so expected values are exact.
- A metric change must keep the definitions in `docs/metrics.md` and `README.md` accurate. Update them in the same change.
- Never write real-product benchmark numbers into docs or examples. Any sample output must come from running the mock agent.
- Never put credentials in reports. `describe()` output goes into `report.json`.
- The `livekit` and `pipecat` adapters import optional packages at module import. Keep those imports out of every other module.
- Use Conventional Commit messages.
- Docs use second person, present tense, active voice, and sentence-case headings, with no em-dashes.
