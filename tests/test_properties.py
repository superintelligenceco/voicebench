"""Property-based tests for the pure core: WER, PCM conversion, the VAD, and percentiles."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from voicebench import audio as au
from voicebench.metrics import percentile
from voicebench.vad import StreamingVad, VadConfig, detect_segments, events_to_segments
from voicebench.wer import edit_distance, normalize, wer

SR = 16000
WORDS = st.lists(st.sampled_from(["yes", "no", "book", "a", "table", "for", "two"]), max_size=8)


@given(WORDS, WORDS)
def test_edit_distance_is_a_bounded_symmetric_metric(a: list[str], b: list[str]) -> None:
    d = edit_distance(a, b)
    assert d == edit_distance(b, a)
    assert abs(len(a) - len(b)) <= d <= max(len(a), len(b))
    assert (d == 0) == (a == b)


@given(WORDS, WORDS, WORDS)
def test_edit_distance_obeys_the_triangle_inequality(
    a: list[str], b: list[str], c: list[str]
) -> None:
    assert edit_distance(a, c) <= edit_distance(a, b) + edit_distance(b, c)


@given(st.text(max_size=60), st.text(max_size=60))
def test_wer_is_non_negative_and_zero_for_identical_text(ref: str, hyp: str) -> None:
    assert wer(ref, hyp) >= 0.0
    assert wer(ref, ref) == 0.0
    if normalize(ref):
        assert wer(ref, hyp) == edit_distance(normalize(ref), normalize(hyp)) / len(normalize(ref))


@given(st.lists(st.floats(-1.0, 1.0, width=32), max_size=200))
def test_pcm16_round_trip_error_is_below_one_step(values: list[float]) -> None:
    x = np.asarray(values, dtype=np.float32)
    y = au.from_pcm16(au.to_pcm16(x))
    assert y.shape == x.shape
    if x.size:
        assert float(np.max(np.abs(y - x))) <= 1.0 / 32768.0 + 1e-7


@given(
    st.integers(0, 2000),
    st.sampled_from([8000, 16000, 24000, 48000]),
    st.sampled_from([8000, 16000, 24000, 48000]),
)
def test_resample_keeps_the_duration(n: int, src: int, dst: int) -> None:
    x = np.zeros(n, dtype=np.float32)
    y = au.resample(x, src, dst)
    if n == 0:
        assert y.size == 0
    else:
        assert abs(y.size - n * dst / src) <= 1.0


@st.composite
def bursts(draw: st.DrawFn) -> au.FloatArray:
    """Alternate silence and tone bursts with random lengths and levels."""
    parts = [au.silence(draw(st.integers(0, 400)), SR)]
    for _ in range(draw(st.integers(0, 4))):
        parts.append(au.tone(draw(st.integers(10, 600)), SR, level_db=draw(st.floats(-60, -10))))
        parts.append(au.silence(draw(st.integers(0, 600)), SR))
    return np.concatenate(parts).astype(np.float32)


@settings(max_examples=60, deadline=None)
@given(bursts(), st.lists(st.integers(1, 4000), max_size=12))
def test_streaming_vad_ignores_how_the_audio_is_chunked(x: au.FloatArray, cuts: list[int]) -> None:
    whole = detect_segments(x, SR)
    vad = StreamingVad(SR)
    events = []
    pos = 0
    for size in cuts:
        events += vad.push(x[pos : pos + size])
        pos += size
    events += vad.push(x[pos:])
    events += vad.flush()
    assert events_to_segments(events) == whole


@settings(max_examples=60, deadline=None)
@given(bursts())
def test_vad_segments_are_ordered_disjoint_and_inside_the_audio(x: au.FloatArray) -> None:
    segs = detect_segments(x, SR)
    duration = x.size / SR
    for seg in segs:
        assert 0.0 <= seg.start < seg.end <= duration + 1e-9
    for prev, nxt in pairwise(segs):
        assert prev.end <= nxt.start


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 50), st.integers(8, 100), st.integers(30, 100))
def test_vad_finds_one_isolated_burst_within_one_frame(
    lead_frames: int, burst_frames: int, tail_frames: int
) -> None:
    cfg = VadConfig()
    frame_ms = cfg.frame_ms
    x = np.concatenate(
        [
            au.silence(lead_frames * frame_ms, SR),
            au.tone(burst_frames * frame_ms, SR),
            au.silence(tail_frames * frame_ms, SR),
        ]
    ).astype(np.float32)
    segs = detect_segments(x, SR, cfg)
    assert len(segs) == 1
    tol = frame_ms / 1000.0 + 1e-9
    assert abs(segs[0].start - lead_frames * frame_ms / 1000.0) <= tol
    assert abs(segs[0].end - (lead_frames + burst_frames) * frame_ms / 1000.0) <= tol


@given(st.lists(st.floats(-1e4, 1e4), min_size=1, max_size=50), st.floats(0, 100))
def test_percentile_stays_within_the_range(values: list[float], q: float) -> None:
    p = percentile(values, q)
    assert p is not None
    assert round(min(values), 1) - 0.1 <= p <= round(max(values), 1) + 0.1
    lo, hi = percentile(values, 0), percentile(values, 100)
    assert lo is not None
    assert hi is not None
    assert lo <= p <= hi
