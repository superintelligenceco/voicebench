# Changelog

All notable changes to this project are documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-30

### Added

- Package published on PyPI as [`voicebench`](https://pypi.org/project/voicebench/). Install it with `pip install voicebench`.
- Install script: `curl -fsSL https://raw.githubusercontent.com/superintelligenceco/voicebench/main/install.sh | sh` downloads the executable for your platform and checks it against `SHA256SUMS`.
- Standalone `voicebench` executables for Linux x86-64, Linux ARM64, macOS on Apple silicon, and Windows x86-64, attached to each GitHub Release with a `SHA256SUMS` file. The executables need no Python install.
- Multi-arch container image (`linux/amd64`, `linux/arm64`) at `ghcr.io/superintelligenceco/voicebench`, tagged `:X.Y.Z` and `:latest` on releases and `:edge` on manual workflow runs.
- Wheel and sdist attached to each GitHub Release.
- `voicebench example` command that lists the bundled example scenarios and prints or saves one, so you can run the demo without a clone.
- Supply chain: SPDX SBOMs for the source and the image, build provenance attestations for every release file and the image, cosign keyless signatures on the image, and a Trivy gate that fails the release on CRITICAL vulnerabilities.
- Documentation site at [superintelligenceco.github.io/voicebench](https://superintelligenceco.github.io/voicebench/) with an architecture diagram, CLI and Python API reference, an FAQ, and decision records.
- Docker Compose quickstart that runs the mock agent in one container and benchmarks it from another.
- Property-based tests, a test that runs the README commands, benchmarks with a 2x regression gate, a nightly workflow, and weekly mutation testing.
- Developer setup: Makefile, pre-commit hooks, a dev container, VS Code settings, `CITATION.cff`, and `llms.txt`.

### Changed

- Releases now come from pushing a `vX.Y.Z` tag instead of release-please. See `CONTRIBUTING.md`.

## [0.1.0] - 2026-09-30

The first release of voicebench, a benchmark harness for real-time voice agents.

### Added

- `voicebench run`, `validate`, `mock-server`, and `synth` commands.
- YAML scenario format with start anchors on agent speech (`agent_speech_start`, `agent_speech_end`), per-turn expectations (`respond`, `stop`, `ignore`), synthetic or WAV audio, and an `assert` block that sets the exit code.
- Energy-based streaming VAD with hysteresis, hangover, and backdated boundaries.
- Metrics: response latency, time to first audio, missed responses, barge-in stop time and success rate, false barge-ins, spurious responses, talk-over, overlap, and word error rate.
- JSON (schema version 1), Markdown, and HTML reports. The HTML report includes a speech timeline.
- Adapter interface with `module:Class` loading for custom transports.
- `mock` adapter: a deterministic mock agent on a virtual clock.
- `websocket` adapter: raw PCM16 over a WebSocket, with JSON `clear` and `transcript` messages.
- Experimental `livekit` and `pipecat` adapters, installed with the `livekit` and `pipecat` extras.
- Examples for each adapter and a custom echo adapter.

### Release notes

- voicebench measures agents from the outside, at the audio. Latency numbers include the network and any client buffering between voicebench and the agent.
- The `mock` and `websocket` adapters are covered by the test suite, including an end-to-end run of the mock agent over a local socket. The `livekit` and `pipecat` adapters are real implementations that the test suite does not run against live services, so they are marked experimental.
- Synthetic `speech` signals work with the mock agent and energy detectors only. Use recorded prompts with production agents.
- Known limits: the VAD is energy-based, so loud background noise in the agent track counts as speech, and real-clock timings have the resolution of one scenario frame (20 ms by default).

[Unreleased]: https://github.com/superintelligenceco/voicebench/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/superintelligenceco/voicebench/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/superintelligenceco/voicebench/releases/tag/v0.1.0
