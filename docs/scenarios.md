# Scenario format

A scenario is a YAML file that describes one scripted conversation. Validate a file without running it:

```sh
voicebench validate my-scenario.yaml
```

Unknown keys are errors, so a typo never silently falls back to a default.

## Top-level keys

| Key | Default | Description |
| --- | --- | --- |
| `name` | required | Name used in reports and in the default output directory. |
| `description` | `""` | Free text, copied into the report. |
| `sample_rate` | `16000` | Sample rate in Hz for all audio in the session. Minimum 8000. |
| `frame_ms` | `20` | Size of each user audio frame sent to the agent. Minimum 5. |
| `tail_ms` | `3000` | How long to keep recording after the last turn ends. The session also waits for the agent to finish speaking. |
| `max_duration_ms` | `120000` | Hard limit on session length. |
| `vad` | | Detector settings: `user` and `agent` blocks, each with `threshold_db`, `hysteresis_db`, `frame_ms`, `min_speech_ms`, and `min_silence_ms`. See [metrics](metrics.md#speech-detection). |
| `adapter` | `{type: mock}` | `type` is a built-in adapter name or `module.path:ClassName`. `options` are passed to the adapter as keyword arguments. |
| `defaults` | | Default `response_timeout_ms` and `max_stop_ms` for every turn. |
| `turns` | required | Non-empty list of turns. |
| `assert` | | Pass or fail limits. See [assertions](#assertions). |

## Turns

| Key | Default | Description |
| --- | --- | --- |
| `id` | `turn-N` | Unique name for the turn. |
| `audio` | required | Exactly one of `file` or `synth`. See [audio](#audio). |
| `start` | see below | When the turn starts. See [start rules](#start-rules). |
| `expect` | `respond` | `respond`: the agent should answer. `stop`: the turn interrupts the agent, which should stop talking. `ignore`: the audio is noise, and the agent should neither stop nor answer. |
| `text` | | What the audio says. Enables WER when the agent reports transcripts. |
| `response_timeout_ms` | `5000` | How long after the user's speech ends to wait for a reply. |
| `max_stop_ms` | `1000` | For `stop`, the longest acceptable stop time. For `ignore`, stopping within this time counts as a false barge-in. |

## Audio

A file path is relative to the scenario file:

```yaml
audio: {file: audio/question.wav}
```

voicebench reads 8-, 16-, and 32-bit PCM WAV files, downmixes them to mono, and resamples them to the session rate.

A synthetic signal needs no file:

```yaml
audio: {synth: speech, duration_ms: 1500, level_db: -20, seed: 2}
```

| `synth` | Signal |
| --- | --- |
| `speech` | Harmonic complex on a wandering pitch, amplitude modulated at a syllable rate. Energy detectors treat it as speech. Speech-to-text engines and neural VADs do not. |
| `tone` | Sine tone at `freq_hz` (default 440). |
| `noise` | White noise. Useful for `ignore` turns. |
| `silence` | Digital silence. |

`level_db` sets the RMS level in dBFS (default -20). `seed` changes the random parts of `speech` and `noise`.

Use synthetic signals with the mock agent and for transport smoke tests. For a real agent, record your prompts, because a real agent runs speech recognition on them.

## Start rules

```yaml
start: {after: agent_speech_end, delay_ms: 400, timeout_ms: 10000}
```

A turn never starts before the previous turn's audio ends. After that, it starts `delay_ms` after its anchor:

| `after` | Anchor |
| --- | --- |
| `session_start` | The start of the session. Default for the first turn, with `delay_ms: 500`. |
| `previous_turn_end` | The end of the previous turn's audio. |
| `agent_speech_start` | The next agent speech onset after the previous turn ended. Use it for barge-in and noise turns. |
| `agent_speech_end` | The next agent speech offset after the previous turn ended. Default for later turns, with `delay_ms: 0`. |

The agent anchors come from a live VAD on the agent track, using the `vad.agent` settings. If the anchor never happens, the turn starts `timeout_ms` (default 10000) after the previous turn ended, and the report marks its trigger as `timeout`.

## Assertions

| Key | Passes when |
| --- | --- |
| `max_response_latency_ms` | Maximum response latency is at most the limit. |
| `p50_response_latency_ms` | Median response latency is at most the limit. |
| `p90_response_latency_ms` | 90th percentile response latency is at most the limit. |
| `p50_ttfa_ms` | Median time to first audio is at most the limit. |
| `max_barge_in_stop_ms` | Slowest barge-in stop time is at most the limit. |
| `min_barge_in_success_rate` | Barge-in success rate (0 to 1) is at least the limit. |
| `max_false_barge_ins` | Count of false barge-ins is at most the limit. |
| `max_missed_responses` | Count of missed responses is at most the limit. |
| `max_wer` | Mean WER is at most the limit. |

An assertion on a metric with no data fails. With `--repeat`, assertions apply to the pooled turns of all sessions.
