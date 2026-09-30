"""Run the mock agent through whole scenarios, on virtual and real clocks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from voicebench.bench import run_benchmark
from voicebench.scenario import load_scenario, parse_scenario


def _run(scenario: Any, **kwargs: Any) -> Any:
    return asyncio.run(run_benchmark(scenario, **kwargs))


def test_example_conversation_passes(examples_dir: Path) -> None:
    sc = load_scenario(examples_dir / "mock-conversation.yaml")
    result = _run(sc)
    assert result.passed, result.report["assertions"]
    turns = {t.id: t for t in result.sessions[0].turns}
    assert all(t.passed for t in turns.values())
    # The mock waits 300 ms of silence plus a 350-500 ms delay, on 20 ms frames.
    for tid in ("opening", "answer-date", "confirm"):
        latency = turns[tid].response_latency_ms
        assert latency is not None
        assert 640 <= latency <= 900
    barge = turns["barge-in"]
    assert barge.stopped
    # 250 ms to confirm the barge-in plus 120 ms reaction, within a frame or two.
    assert barge.stop_latency_ms == pytest.approx(370, abs=41)
    assert turns["cough"].false_barge_in is False
    assert result.summary["mean_wer"] == 0.0
    assert result.report["clock"] == "virtual"


def test_virtual_clock_is_deterministic(examples_dir: Path) -> None:
    sc = load_scenario(examples_dir / "mock-conversation.yaml")
    a = _run(sc).summary
    b = _run(sc).summary
    assert a == b


def test_repeat_runs_fresh_sessions(examples_dir: Path) -> None:
    sc = load_scenario(examples_dir / "mock-conversation.yaml")
    result = _run(sc, repeat=3)
    assert result.summary["sessions"] == 3
    assert result.summary["turns"] == 15


def test_non_interruptible_agent_fails_barge_in(examples_dir: Path) -> None:
    sc = load_scenario(examples_dir / "mock-conversation.yaml")
    result = _run(sc, options={"interruptible": False})
    assert not result.passed
    assert result.summary["barge_in_success_rate"] == 0.0


def test_silent_agent_starts_turns_on_timeout() -> None:
    sc = parse_scenario(
        {
            "name": "silent",
            "adapter": {"type": "mock", "options": {"threshold_db": 10}},
            "tail_ms": 500,
            "turns": [
                {"id": "a", "audio": {"synth": "speech", "duration_ms": 500}},
                {
                    "id": "b",
                    "audio": {"synth": "speech", "duration_ms": 500},
                    "start": {"after": "agent_speech_end", "timeout_ms": 1500},
                },
            ],
            "assert": {"max_missed_responses": 0},
        }
    )
    result = _run(sc)
    turns = result.sessions[0].turns
    assert [t.trigger for t in turns] == ["anchor", "timeout"]
    assert result.summary["missed_responses"] == 2
    assert not result.passed


def test_max_duration_truncates() -> None:
    sc = parse_scenario(
        {
            "name": "long",
            "max_duration_ms": 1000,
            "turns": [{"audio": {"synth": "speech", "duration_ms": 3000}}],
        }
    )
    result = _run(sc)
    assert result.sessions[0].truncated


def test_greeting_anchor() -> None:
    sc = parse_scenario(
        {
            "name": "greet",
            "adapter": {"type": "mock", "options": {"greeting_ms": 1000}},
            "turns": [
                {
                    "id": "reply",
                    "audio": {"synth": "speech", "duration_ms": 800},
                    "start": {"after": "agent_speech_end", "delay_ms": 300},
                }
            ],
        }
    )
    result = _run(sc)
    t = result.sessions[0].turns[0]
    assert t.trigger == "anchor"
    assert t.start_s == pytest.approx(1.3, abs=0.03)
    assert t.passed


@pytest.mark.realtime
def test_mock_adapter_on_real_clock() -> None:
    sc = parse_scenario(
        {
            "name": "rt",
            "tail_ms": 1500,
            "turns": [
                {"audio": {"synth": "speech", "duration_ms": 600}, "start": {"delay_ms": 100}}
            ],
        }
    )
    result = _run(sc, realtime=True, options={"response_ms": 400})
    assert result.report["clock"] == "real"
    t = result.sessions[0].turns[0]
    assert t.responded
    assert t.response_latency_ms is not None
    assert 600 <= t.response_latency_ms <= 1100
