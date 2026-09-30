"""Benchmarks for the analysis hot path. Run them with `make bench`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import numpy as np

from voicebench import audio as au
from voicebench.bench import run_benchmark
from voicebench.scenario import load_scenario
from voicebench.vad import detect_segments
from voicebench.wer import wer

SR = 16000
EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "mock-conversation.yaml"


def _track(seconds: int) -> au.FloatArray:
    parts = []
    for i in range(seconds // 2):
        parts += [au.speech_like(1200, SR, seed=i), au.silence(800, SR)]
    return np.concatenate(parts).astype(np.float32)


def test_vad_on_one_minute_of_audio(benchmark: Any) -> None:
    track = _track(60)
    segs = benchmark(detect_segments, track, SR)
    assert len(segs) == 30


def test_wer_on_a_long_transcript(benchmark: Any) -> None:
    ref = " ".join(f"word{i % 50}" for i in range(400))
    hyp = " ".join(f"word{i % 47}" for i in range(400))
    assert benchmark(wer, ref, hyp) > 0


def test_mock_conversation_end_to_end(benchmark: Any) -> None:
    scenario = load_scenario(EXAMPLE)
    result = benchmark(lambda: asyncio.run(run_benchmark(scenario)))
    assert result.passed
