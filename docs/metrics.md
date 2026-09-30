# Metrics

voicebench computes every metric after the session ends, from two recorded tracks at the session sample rate:

- The **user track** holds the scripted audio exactly as voicebench sent it.
- The **agent track** holds the agent's audio, placed at the time each packet arrived. When the agent sends a `clear` (barge-in) event, voicebench drops any audio it had buffered but not yet played, the same way a client playback buffer would.

## Speech detection

voicebench finds speech in each track with an energy detector (`voicebench.vad.StreamingVad`):

1. The detector splits the track into analysis frames of `frame_ms` (default 10 ms) and computes each frame's RMS level in dBFS.
2. A segment opens when the level stays at or above `threshold_db` (default -45 dBFS) for `min_speech_ms` (default 50 ms). This rejects clicks.
3. An open segment stays open while the level stays above `threshold_db - hysteresis_db` (default 6 dB), so fading word endings do not split a segment.
4. A segment closes after `min_silence_ms` (default 250 ms) below that lower threshold. Short pauses between words stay inside one segment.
5. Reported onsets and offsets are backdated to the first and last active frame, so the confirmation delays in steps 2 and 4 do not add to any latency.

Tune the detector per track with the scenario's `vad.user` and `vad.agent` blocks. Lower `vad.agent.threshold_db` if your agent speaks quietly, and raise `min_silence_ms` if the agent pauses between sentences and you want a single reply to count as one segment.

The detector measures energy, not speech. Background noise above the threshold counts as speech. For the agent track this is usually what you want, because a caller hears the noise too.

## Timing resolution

- VAD boundaries have the resolution of one analysis frame (10 ms by default).
- On the real clock, packet arrival times come from a monotonic clock, and the runner polls the adapter once per scenario frame (20 ms by default). Metrics can shift by up to one scenario frame.
- On the virtual clock (mock adapter only), the session is deterministic.
- Latency numbers include everything between voicebench and the agent: network, jitter buffers in client SDKs, and codec delay. That is intentional, since a caller experiences all of it. Run voicebench close to the agent if you want to isolate the agent itself.

## Turn metrics

A turn's window runs from the moment its audio starts until the next turn starts (or the session ends). Within that window, the user's speech onset and offset are the first and last detected user speech boundaries.

### Response latency

The time from the user's offset to the onset of the first agent speech segment that starts after the user's onset and no later than `response_timeout_ms` after the user's offset. A negative value means the agent started talking before the user finished, and the turn is flagged as talk-over.

### Time to first audio (TTFA)

The time from the user's offset to the arrival of the first agent packet above -70 dBFS that belongs to the reply. Packets from an earlier agent segment are excluded. TTFA is not reported for talk-over replies.

TTFA and response latency agree when the agent sends speech immediately. TTFA is lower when the agent sends leading silence or quiet audio first, and higher than you might expect when the transport delivers audio in large bursts.

### Barge-in (`expect: stop`)

For a turn that interrupts the agent, voicebench finds the agent segment that was playing at the user's onset. The **stop time** is the time from the user's onset to the end of that segment. The turn passes when the stop time is at most `max_stop_ms`. If the agent never stopped before the session ended, the stop time is not reported and the turn fails. If the agent was not talking at the user's onset, the turn fails with a note, because the scenario timing did not create a barge-in.

### Noise (`expect: ignore`)

For a turn that plays non-speech, such as a cough or a door slam:

- If the agent was talking and stopped within `max_stop_ms` of the noise, voicebench counts a **false barge-in**. An agent reply that happens to end naturally that close to the noise looks the same, so place noise turns early in a long reply.
- If the agent was silent and started talking within `response_timeout_ms`, voicebench counts a **spurious response**.

### Word error rate

If a turn sets `text` and the adapter reports user transcripts, voicebench joins the final user transcripts that arrived during the turn's window and computes WER against `text`. Both strings are Unicode-normalized, lowercased, and stripped of punctuation other than apostrophes. WER can exceed 1.0 when the transcript has many insertions.

## Session metrics

| Field | Meaning |
| --- | --- |
| `duration_s` | Length of the recorded session. |
| `user_speech_ms`, `agent_speech_ms` | Total detected speech per side. |
| `overlap_ms` | Total time both sides spoke at once. |
| `talk_over_ms` | Overlap during `respond` turns only, where the agent should have been listening. |
| `truncated` | True if the session hit `max_duration_ms` before all turns played. Turns that never played appear with trigger `not_played`. |

## Summary and assertions

The summary aggregates all turns across all sessions of a run. Latency distributions report `count`, `min`, `p50`, `p90`, `max`, and `mean`, with percentiles computed by linear interpolation. An assertion on a value that does not exist (for example, `max_wer` when no transcripts arrived) fails, so a broken transcript path cannot pass silently.
