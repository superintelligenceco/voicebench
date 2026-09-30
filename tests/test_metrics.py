"""Metric tests on hand-built recordings, so each number is known in advance."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from voicebench import audio as au
from voicebench.adapters.base import Transcript
from voicebench.metrics import (
    analyze,
    check_assertions,
    percentile,
    summarize,
)
from voicebench.runner import Packet, SessionRecord, TurnWindow
from voicebench.scenario import parse_scenario

SR = 16000


def _track(total_s: float, spans: list[tuple[float, float]], kind: str = "speech") -> au.FloatArray:
    out = np.zeros(round(total_s * SR), dtype=np.float32)
    for start, end in spans:
        a = round(start * SR)
        dur_ms = (end - start) * 1000
        sig = au.speech_like(dur_ms, SR) if kind == "speech" else au.noise(dur_ms, SR, -25)
        out[a : a + sig.size] = sig
    return out


def _record(
    turns: list[dict[str, Any]],
    user_spans: list[tuple[float, float]],
    agent_spans: list[tuple[float, float]],
    total_s: float = 10.0,
    transcripts: list[Transcript] | None = None,
    user_kind: str = "speech",
) -> SessionRecord:
    sc = parse_scenario(
        {"name": "t", "turns": [{"audio": {"synth": "speech"}, **t} for t in turns]}
    )
    windows = [
        TurnWindow(turn, s, e, "anchor") for turn, (s, e) in zip(sc.turns, user_spans, strict=True)
    ]
    packets = [
        Packet(round(t, 2), -20.0, 0.02) for s, e in agent_spans for t in np.arange(s, e, 0.02)
    ]
    return SessionRecord(
        scenario=sc,
        adapter={"type": "test"},
        clock="virtual",
        user_track=_track(total_s, user_spans, user_kind),
        agent_track=_track(total_s, agent_spans),
        windows=windows,
        packets=packets,
        transcripts=transcripts or [],
    )


def test_response_latency_and_ttfa() -> None:
    rec = _record([{"id": "q"}], [(1.0, 2.0)], [(2.6, 4.0)])
    m = analyze(rec)
    t = m.turns[0]
    assert t.passed
    assert t.responded
    assert t.response_latency_ms == pytest.approx(600, abs=11)
    assert t.ttfa_ms == pytest.approx(600, abs=11)
    assert not t.talk_over
    assert m.overlap_ms == 0


def test_missed_response() -> None:
    rec = _record([{"id": "q", "response_timeout_ms": 1000}], [(1.0, 2.0)], [(4.0, 5.0)])
    t = analyze(rec).turns[0]
    assert t.responded is False
    assert not t.passed
    assert t.response_latency_ms is None
    assert any("no agent speech" in n for n in t.notes)


def test_talk_over_is_flagged() -> None:
    rec = _record([{"id": "q"}], [(1.0, 2.0)], [(1.5, 3.0)])
    m = analyze(rec)
    t = m.turns[0]
    assert t.talk_over
    assert t.response_latency_ms is not None
    assert t.response_latency_ms < 0
    assert t.ttfa_ms is None
    assert m.talk_over_ms == pytest.approx(500, abs=21)


def test_barge_in_stop_latency() -> None:
    turns = [{"id": "q"}, {"id": "b", "expect": "stop", "max_stop_ms": 500}]
    rec = _record(turns, [(0.5, 1.0), (2.5, 3.5)], [(1.5, 2.8)])
    t = analyze(rec).turns[1]
    assert t.stopped
    assert t.passed
    assert t.stop_latency_ms == pytest.approx(300, abs=21)


def test_barge_in_too_slow_fails() -> None:
    turns = [{"id": "q"}, {"id": "b", "expect": "stop", "max_stop_ms": 200}]
    rec = _record(turns, [(0.5, 1.0), (2.5, 3.5)], [(1.5, 3.2)])
    t = analyze(rec).turns[1]
    assert t.stopped is False
    assert not t.passed
    assert t.stop_latency_ms == pytest.approx(700, abs=21)


def test_barge_in_agent_never_stops() -> None:
    turns = [{"id": "q"}, {"id": "b", "expect": "stop"}]
    rec = _record(turns, [(0.5, 1.0), (2.5, 3.5)], [(1.5, 10.0)], total_s=10.0)
    t = analyze(rec).turns[1]
    assert t.stopped is False
    assert t.stop_latency_ms is None


def test_false_barge_in_on_noise() -> None:
    turns = [{"id": "q"}, {"id": "n", "expect": "ignore", "max_stop_ms": 500}]
    rec = _record(turns, [(0.5, 1.0), (2.5, 2.7)], [(1.5, 2.8)])
    t = analyze(rec).turns[1]
    assert t.false_barge_in
    assert not t.passed


def test_noise_ignored_correctly() -> None:
    turns = [{"id": "q"}, {"id": "n", "expect": "ignore", "max_stop_ms": 500}]
    rec = _record(turns, [(0.5, 1.0), (2.5, 2.7)], [(1.5, 5.0)])
    t = analyze(rec).turns[1]
    assert t.false_barge_in is False
    assert t.spurious_response is False
    assert t.passed
    assert t.response_latency_ms is None


def test_spurious_response_to_noise() -> None:
    rec = _record([{"id": "n", "expect": "ignore"}], [(1.0, 1.2)], [(1.8, 3.0)])
    t = analyze(rec).turns[0]
    assert t.spurious_response
    assert not t.passed


def test_wer_from_transcripts() -> None:
    rec = _record(
        [{"id": "q", "text": "book a table for two"}],
        [(1.0, 2.0)],
        [(2.5, 3.0)],
        transcripts=[Transcript("user", "book a table for you", 2.3)],
    )
    assert analyze(rec).turns[0].wer == pytest.approx(0.2)


def test_missing_transcript_is_noted() -> None:
    rec = _record([{"id": "q", "text": "hello"}], [(1.0, 2.0)], [(2.5, 3.0)])
    t = analyze(rec).turns[0]
    assert t.wer is None
    assert any("no user transcript" in n for n in t.notes)


def test_unplayed_turns_are_reported() -> None:
    sc = parse_scenario(
        {"name": "t", "turns": [{"audio": {"synth": "speech"}}, {"audio": {"synth": "speech"}}]}
    )
    rec = SessionRecord(
        scenario=sc,
        adapter={"type": "test"},
        clock="virtual",
        user_track=np.zeros(SR, dtype=np.float32),
        agent_track=np.zeros(SR, dtype=np.float32),
        truncated=True,
    )
    m = analyze(rec)
    assert [t.trigger for t in m.turns] == ["not_played", "not_played"]
    assert m.truncated


def test_percentile() -> None:
    assert percentile([], 50) is None
    assert percentile([100.0, 200.0, 300.0], 50) == 200.0
    assert percentile([100.0, 200.0], 90) == 190.0


def test_summarize_and_assertions() -> None:
    turns = [{"id": "q"}, {"id": "b", "expect": "stop", "max_stop_ms": 500}]
    rec = _record(turns, [(0.5, 1.0), (2.5, 3.5)], [(1.5, 2.8), (4.2, 5.0)])
    s = summarize([analyze(rec)])
    assert s["turns"] == 2
    assert s["turns_passed"] == 2
    assert s["barge_in_success_rate"] == 1.0
    assert s["response_latency_ms"]["count"] == 1
    results = check_assertions(
        s,
        {
            "max_response_latency_ms": 600,
            "min_barge_in_success_rate": 1.0,
            "max_barge_in_stop_ms": 100,
            "max_wer": 0.5,
        },
    )
    by_key = {r.key: r for r in results}
    assert by_key["max_response_latency_ms"].passed
    assert by_key["min_barge_in_success_rate"].passed
    assert not by_key["max_barge_in_stop_ms"].passed
    # No transcripts means no WER, and a limit on a missing value fails.
    assert by_key["max_wer"].actual is None
    assert not by_key["max_wer"].passed
