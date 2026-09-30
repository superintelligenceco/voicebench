from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from voicebench import audio as au


def test_ms_sample_round_trip(sr: int) -> None:
    assert au.ms_to_samples(20, sr) == 320
    assert au.samples_to_ms(320, sr) == pytest.approx(20.0)


def test_pcm16_round_trip() -> None:
    x = np.linspace(-1.0, 0.99, 1000, dtype=np.float32)
    y = au.from_pcm16(au.to_pcm16(x))
    assert y.dtype == np.float32
    assert np.max(np.abs(x - y)) < 1e-4


def test_pcm16_clips_out_of_range() -> None:
    y = au.from_pcm16(au.to_pcm16(np.array([2.0, -2.0], dtype=np.float32)))
    assert y[0] == pytest.approx(1.0, abs=1e-4)
    assert y[1] == pytest.approx(-1.0)


def test_pcm16_rejects_odd_length() -> None:
    with pytest.raises(ValueError, match="even"):
        au.from_pcm16(b"\x00\x00\x00")


@pytest.mark.parametrize("level", [-10.0, -20.0, -35.0])
def test_tone_level_matches_request(sr: int, level: float) -> None:
    x = au.tone(1000, sr, 440.0, level)
    # Ignore the 5 ms fades at each end.
    body = x[au.ms_to_samples(10, sr) : -au.ms_to_samples(10, sr)]
    assert au.rms_dbfs(body) == pytest.approx(level, abs=0.2)


def test_speech_like_level_and_determinism(sr: int) -> None:
    a = au.speech_like(1500, sr, level_db=-20.0, seed=3)
    b = au.speech_like(1500, sr, level_db=-20.0, seed=3)
    c = au.speech_like(1500, sr, level_db=-20.0, seed=4)
    assert a.size == au.ms_to_samples(1500, sr)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert au.rms_dbfs(a) == pytest.approx(-20.0, abs=0.5)


def test_silence_and_rms_floor(sr: int) -> None:
    assert au.rms_dbfs(au.silence(100, sr)) == -120.0
    assert au.rms_dbfs(np.zeros(0, dtype=np.float32)) == -120.0


def test_resample_preserves_duration() -> None:
    x = au.tone(500, 48000)
    y = au.resample(x, 48000, 16000)
    assert y.size == 8000
    assert au.resample(x, 16000, 16000) is not None


def test_wav_round_trip_with_resample(tmp_path: Path) -> None:
    path = tmp_path / "t.wav"
    x = au.tone(250, 8000, level_db=-12)
    au.write_wav(path, x, 8000)
    back = au.read_wav(path, 16000)
    assert back.size == 4000
    assert au.rms_dbfs(back) == pytest.approx(au.rms_dbfs(x), abs=0.5)
