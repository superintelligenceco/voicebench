from __future__ import annotations

import numpy as np
import pytest

from voicebench import audio as au
from voicebench.vad import Segment, StreamingVad, VadConfig, detect_segments


def _cat(*parts: au.FloatArray) -> au.FloatArray:
    return np.concatenate(parts).astype(np.float32)


def test_detects_single_tone_burst(sr: int) -> None:
    x = _cat(au.silence(500, sr), au.tone(800, sr), au.silence(700, sr))
    segs = detect_segments(x, sr)
    assert len(segs) == 1
    assert segs[0].start == pytest.approx(0.5, abs=0.011)
    assert segs[0].end == pytest.approx(1.3, abs=0.011)


def test_onset_is_backdated_past_min_speech(sr: int) -> None:
    cfg = VadConfig(min_speech_ms=200)
    x = _cat(au.silence(300, sr), au.speech_like(1000, sr), au.silence(500, sr))
    segs = detect_segments(x, sr, cfg)
    assert segs[0].start == pytest.approx(0.3, abs=0.011)


def test_short_blip_is_rejected(sr: int) -> None:
    x = _cat(au.silence(300, sr), au.tone(30, sr), au.silence(300, sr))
    assert detect_segments(x, sr, VadConfig(min_speech_ms=50)) == []


def test_short_gap_is_bridged_long_gap_splits(sr: int) -> None:
    cfg = VadConfig(min_silence_ms=250)
    short = _cat(au.tone(400, sr), au.silence(150, sr), au.tone(400, sr), au.silence(400, sr))
    assert len(detect_segments(short, sr, cfg)) == 1
    long = _cat(au.tone(400, sr), au.silence(400, sr), au.tone(400, sr), au.silence(400, sr))
    segs = detect_segments(long, sr, cfg)
    assert len(segs) == 2
    assert segs[1].start == pytest.approx(0.8, abs=0.011)


def test_quiet_signal_below_threshold_is_silence(sr: int) -> None:
    x = au.noise(1000, sr, level_db=-60)
    assert detect_segments(x, sr, VadConfig(threshold_db=-45)) == []


def test_hysteresis_keeps_fading_tail(sr: int) -> None:
    # Drops 4 dB below the threshold: inside the 6 dB hysteresis band.
    cfg = VadConfig(threshold_db=-40, hysteresis_db=6)
    x = _cat(au.tone(400, sr, level_db=-30), au.tone(400, sr, level_db=-44), au.silence(400, sr))
    segs = detect_segments(x, sr, cfg)
    assert len(segs) == 1
    assert segs[0].end == pytest.approx(0.8, abs=0.021)


def test_open_segment_closes_on_flush(sr: int) -> None:
    x = _cat(au.silence(200, sr), au.tone(500, sr))
    segs = detect_segments(x, sr)
    assert len(segs) == 1
    assert segs[0].end == pytest.approx(0.7, abs=0.011)


def test_streaming_matches_batch_with_odd_chunks(sr: int) -> None:
    x = _cat(au.silence(300, sr), au.speech_like(900, sr), au.silence(600, sr), au.tone(300, sr))
    vad = StreamingVad(sr)
    events = []
    rng = np.random.default_rng(0)
    pos = 0
    while pos < x.size:
        n = int(rng.integers(1, 700))
        events += vad.push(x[pos : pos + n])
        pos += n
    events += vad.flush()
    batch = detect_segments(x, sr)
    stream = [e.time for e in events]
    assert stream == [t for s in batch for t in (s.start, s.end)]


def test_segment_overlap() -> None:
    a, b = Segment(1.0, 2.0), Segment(1.5, 3.0)
    assert a.overlaps(b) == pytest.approx(0.5)
    assert a.overlaps(Segment(2.5, 3.0)) == 0.0
    assert a.duration == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"frame_ms": 0}, "frame_ms"),
        ({"min_speech_ms": -1}, "non-negative"),
        ({"hysteresis_db": -1}, "hysteresis_db"),
    ],
)
def test_config_validation(kwargs: dict[str, float], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        VadConfig(**kwargs)
