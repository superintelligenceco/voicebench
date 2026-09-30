"""Turn-level and session-level metrics computed from a recorded session."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from voicebench.runner import SessionRecord, TurnWindow
from voicebench.vad import Segment, detect_segments
from voicebench.wer import wer

_EPS = 1e-9


@dataclass
class TurnResult:
    """Measurements for one scripted turn. Times are ms unless the name says ``_s``."""

    id: str
    expect: str
    trigger: str
    start_s: float
    end_s: float
    user_onset_s: float | None = None
    user_offset_s: float | None = None
    responded: bool | None = None
    response_latency_ms: float | None = None
    ttfa_ms: float | None = None
    talk_over: bool = False
    stopped: bool | None = None
    stop_latency_ms: float | None = None
    false_barge_in: bool | None = None
    spurious_response: bool | None = None
    transcript: str | None = None
    wer: float | None = None
    passed: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class SessionMetrics:
    """Everything measured in one session."""

    turns: list[TurnResult]
    duration_s: float
    user_speech_ms: float
    agent_speech_ms: float
    overlap_ms: float
    talk_over_ms: float
    user_segments: list[Segment]
    agent_segments: list[Segment]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["user_segments"] = [[round(s.start, 4), round(s.end, 4)] for s in self.user_segments]
        out["agent_segments"] = [[round(s.start, 4), round(s.end, 4)] for s in self.agent_segments]
        return out


def analyze(record: SessionRecord) -> SessionMetrics:
    """Compute all metrics for a recorded session."""
    sc = record.scenario
    sr = sc.sample_rate
    user_segs = detect_segments(record.user_track, sr, sc.user_vad)
    agent_segs = detect_segments(record.agent_track, sr, sc.agent_vad)
    duration = record.duration

    results: list[TurnResult] = []
    talk_over_s = 0.0
    for k, win in enumerate(record.windows):
        next_start = record.windows[k + 1].start if k + 1 < len(record.windows) else duration
        res = _analyze_turn(record, win, next_start, user_segs, agent_segs, duration)
        if win.turn.expect == "respond":
            for us in _segments_in(user_segs, win.start, win.end):
                talk_over_s += sum(us.overlaps(a) for a in agent_segs)
        results.append(res)

    for turn in sc.turns[len(record.windows) :]:
        results.append(
            TurnResult(
                id=turn.id,
                expect=turn.expect,
                trigger="not_played",
                start_s=duration,
                end_s=duration,
                notes=["turn never started: the session hit max_duration_ms"],
            )
        )

    overlap = sum(u.overlaps(a) for u in user_segs for a in agent_segs)
    return SessionMetrics(
        turns=results,
        duration_s=round(duration, 4),
        user_speech_ms=_ms(sum(s.duration for s in user_segs)),
        agent_speech_ms=_ms(sum(s.duration for s in agent_segs)),
        overlap_ms=_ms(overlap),
        talk_over_ms=_ms(talk_over_s),
        user_segments=user_segs,
        agent_segments=agent_segs,
        truncated=record.truncated,
    )


def _analyze_turn(
    record: SessionRecord,
    win: TurnWindow,
    next_start: float,
    user_segs: list[Segment],
    agent_segs: list[Segment],
    duration: float,
) -> TurnResult:
    turn = win.turn
    res = TurnResult(
        id=turn.id,
        expect=turn.expect,
        trigger=win.trigger,
        start_s=round(win.start, 4),
        end_s=round(win.end, 4),
    )
    if win.trigger == "timeout":
        res.notes.append(f"start anchor {turn.start.after!r} never happened; started on timeout")

    mine = _segments_in(user_segs, win.start, win.end)
    if not mine:
        res.notes.append("no user speech detected in the turn audio; check vad.user.threshold_db")
        return res
    onset, offset = mine[0].start, mine[-1].end
    res.user_onset_s = round(onset, 4)
    res.user_offset_s = round(offset, 4)

    speaking_at_onset = next(
        (a for a in agent_segs if a.start <= onset + _EPS and a.end > onset + _EPS), None
    )

    # Response: the first agent onset after the user started, within the window.
    limit = min(next_start, offset + turn.response_timeout_ms / 1000.0)
    response = next(
        (a for a in agent_segs if a.start > onset + _EPS and a.start <= limit + _EPS), None
    )
    res.responded = response is not None
    if response is not None and turn.expect != "ignore":
        res.response_latency_ms = _ms(response.start - offset)
        res.talk_over = response.start < offset
        # Packets that belong to an earlier agent segment do not count as the reply.
        earlier = [a.end for a in agent_segs if a.end <= response.start + _EPS]
        floor = max([offset, *earlier])
        packet = next(
            (p for p in record.packets if p.time >= floor - _EPS and p.time <= limit + _EPS),
            None,
        )
        if packet is not None and not res.talk_over:
            res.ttfa_ms = _ms(packet.time - offset)

    if turn.expect == "respond":
        res.passed = bool(res.responded)
        if not res.responded:
            res.notes.append(
                f"no agent speech within {turn.response_timeout_ms:g} ms of the end of the turn"
            )
    elif turn.expect == "stop":
        if speaking_at_onset is None:
            res.notes.append("agent was not speaking when the barge-in started; nothing to stop")
        else:
            stop = speaking_at_onset.end - onset
            ran_to_end = speaking_at_onset.end >= duration - _EPS
            res.stop_latency_ms = None if ran_to_end else _ms(stop)
            res.stopped = not ran_to_end and stop * 1000.0 <= turn.max_stop_ms + _EPS
            res.passed = bool(res.stopped)
            if not res.stopped:
                res.notes.append(f"agent kept talking more than {turn.max_stop_ms:g} ms")
    else:  # ignore
        if speaking_at_onset is not None:
            stop = speaking_at_onset.end - onset
            res.false_barge_in = stop * 1000.0 <= turn.max_stop_ms + _EPS
            res.spurious_response = False
            if res.false_barge_in:
                res.notes.append(
                    f"agent stopped {_ms(stop):g} ms after non-speech input; counted as a false "
                    "barge-in (a natural end of the reply this close looks the same)"
                )
        else:
            res.false_barge_in = False
            res.spurious_response = bool(res.responded)
            if res.spurious_response:
                res.notes.append("agent started talking in response to non-speech input")
        res.passed = not res.false_barge_in and not res.spurious_response

    _attach_transcript(record, win, next_start, res)
    return res


def _attach_transcript(
    record: SessionRecord, win: TurnWindow, next_start: float, res: TurnResult
) -> None:
    texts = [
        tr.text
        for tr in record.transcripts
        if tr.role == "user" and tr.final and win.start - _EPS <= tr.time < next_start
    ]
    if texts:
        res.transcript = " ".join(texts)
    if win.turn.text is not None:
        if res.transcript is None:
            res.notes.append("expected text is set but the agent reported no user transcript")
        else:
            res.wer = round(wer(win.turn.text, res.transcript), 4)


def _segments_in(segs: list[Segment], start: float, end: float) -> list[Segment]:
    return [s for s in segs if s.end > start + _EPS and s.start < end - _EPS]


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 1)


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile, or None for an empty list."""
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype=np.float64), q)), 1)


def summarize(sessions: list[SessionMetrics]) -> dict[str, Any]:
    """Aggregate turn results across one or more sessions."""
    turns = [t for s in sessions for t in s.turns]
    respond = [t for t in turns if t.expect == "respond"]
    stops = [t for t in turns if t.expect == "stop"]
    ignores = [t for t in turns if t.expect == "ignore"]
    latencies = [t.response_latency_ms for t in respond if t.response_latency_ms is not None]
    ttfas = [t.ttfa_ms for t in respond if t.ttfa_ms is not None]
    stop_lat = [t.stop_latency_ms for t in stops if t.stop_latency_ms is not None]
    wers = [t.wer for t in turns if t.wer is not None]
    return {
        "sessions": len(sessions),
        "turns": len(turns),
        "turns_passed": sum(t.passed for t in turns),
        "response_latency_ms": _stats(latencies),
        "ttfa_ms": _stats(ttfas),
        "missed_responses": sum(1 for t in respond if not t.responded),
        "talk_overs": sum(1 for t in respond if t.talk_over),
        "barge_in_turns": len(stops),
        "barge_in_success_rate": (
            round(sum(bool(t.stopped) for t in stops) / len(stops), 4) if stops else None
        ),
        "barge_in_stop_ms": _stats(stop_lat),
        "noise_turns": len(ignores),
        "false_barge_ins": sum(bool(t.false_barge_in) for t in ignores),
        "spurious_responses": sum(bool(t.spurious_response) for t in ignores),
        "mean_wer": round(float(np.mean(wers)), 4) if wers else None,
        "overlap_ms": round(sum(s.overlap_ms for s in sessions), 1),
        "talk_over_ms": round(sum(s.talk_over_ms for s in sessions), 1),
    }


def _stats(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "min": round(min(values), 1) if values else None,
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "max": round(max(values), 1) if values else None,
        "mean": round(float(np.mean(values)), 1) if values else None,
    }


@dataclass(frozen=True)
class AssertionResult:
    key: str
    limit: float
    actual: float | None
    passed: bool


def check_assertions(
    summary: dict[str, Any], assertions: dict[str, float]
) -> list[AssertionResult]:
    """Compare the summary against the scenario's ``assert`` block."""
    lookup: dict[str, tuple[float | None, bool]] = {
        "max_response_latency_ms": (summary["response_latency_ms"]["max"], False),
        "p50_response_latency_ms": (summary["response_latency_ms"]["p50"], False),
        "p90_response_latency_ms": (summary["response_latency_ms"]["p90"], False),
        "p50_ttfa_ms": (summary["ttfa_ms"]["p50"], False),
        "max_barge_in_stop_ms": (summary["barge_in_stop_ms"]["max"], False),
        "min_barge_in_success_rate": (summary["barge_in_success_rate"], True),
        "max_false_barge_ins": (float(summary["false_barge_ins"]), False),
        "max_missed_responses": (float(summary["missed_responses"]), False),
        "max_wer": (summary["mean_wer"], False),
    }
    results = []
    for key, limit in assertions.items():
        actual, is_minimum = lookup[key]
        ok = actual is not None and (actual >= limit if is_minimum else actual <= limit)
        results.append(AssertionResult(key, limit, actual, ok))
    return results
