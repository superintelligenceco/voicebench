from __future__ import annotations

import numpy as np
import pytest

from voicebench import audio as au
from voicebench.mock_agent import MockAgent, MockAgentConfig, MockOutput

FRAME_MS = 20.0


def _feed(
    agent: MockAgent, signal: au.FloatArray, t0: float = 0.0
) -> list[tuple[float, MockOutput]]:
    sr = agent.sample_rate
    n = au.ms_to_samples(FRAME_MS, sr)
    out = []
    for i in range(0, signal.size, n):
        t = t0 + i / sr
        out += [(t, o) for o in agent.process(signal[i : i + n], t)]
    return out


def _first(outputs: list[tuple[float, MockOutput]], kind: str) -> float | None:
    return next((t for t, o in outputs if o.kind == kind), None)


def test_responds_after_endpoint_plus_delay(sr: int) -> None:
    cfg = MockAgentConfig(endpoint_silence_ms=300, response_delay_ms=400, response_ms=500)
    agent = MockAgent(sr, cfg)
    sig = np.concatenate([au.speech_like(1000, sr), au.silence(2000, sr)])
    outs = _feed(agent, sig)
    first_audio = _first(outs, "audio")
    assert first_audio is not None
    # Speech ends at 1.0 s; endpoint confirmed at 1.3 s; reply at 1.7 s.
    assert first_audio == pytest.approx(1.7, abs=0.021)


def test_greeting_plays_first(sr: int) -> None:
    agent = MockAgent(sr, MockAgentConfig(greeting_ms=400))
    outs = _feed(agent, au.silence(600, sr))
    audio = [t for t, o in outs if o.kind == "audio"]
    assert audio[0] == 0.0
    assert len(audio) == 20


def test_barge_in_stops_speaking(sr: int) -> None:
    cfg = MockAgentConfig(greeting_ms=3000, barge_in_min_ms=100, interrupt_reaction_ms=150)
    agent = MockAgent(sr, cfg)
    sig = np.concatenate([au.silence(500, sr), au.speech_like(800, sr), au.silence(500, sr)])
    outs = _feed(agent, sig)
    clear = _first(outs, "clear")
    assert clear is not None
    # Barge-in starts at 0.5 s, is confirmed after 100 ms, and the agent stops 150 ms later.
    assert clear == pytest.approx(0.75, abs=0.021)
    assert not any(o.kind == "audio" and 0.77 < t < 1.3 for t, o in outs)


def test_non_interruptible_keeps_talking(sr: int) -> None:
    cfg = MockAgentConfig(greeting_ms=2000, interruptible=False)
    agent = MockAgent(sr, cfg)
    sig = np.concatenate([au.silence(300, sr), au.speech_like(800, sr), au.silence(900, sr)])
    outs = _feed(agent, sig)
    assert _first(outs, "clear") is None
    assert sum(o.kind == "audio" for _, o in outs) == 100


def test_noise_under_reply_is_not_a_turn(sr: int) -> None:
    cfg = MockAgentConfig(greeting_ms=1000, barge_in_min_ms=250, response_ms=500)
    agent = MockAgent(sr, cfg)
    sig = np.concatenate(
        [au.silence(300, sr), au.noise(150, sr, level_db=-25), au.silence(3000, sr)]
    )
    outs = _feed(agent, sig)
    audio = [t for t, o in outs if o.kind == "audio"]
    assert _first(outs, "clear") is None
    assert max(audio) < 1.0  # only the greeting, no reply to the noise


def test_transcripts_are_emitted_per_turn(sr: int) -> None:
    cfg = MockAgentConfig(transcripts=("one", "two"), response_ms=300)
    agent = MockAgent(sr, cfg)
    turn = np.concatenate([au.speech_like(500, sr), au.silence(1500, sr)])
    outs = _feed(agent, np.concatenate([turn, turn, turn]))
    assert [o.text for _, o in outs if o.kind == "transcript"] == ["one", "two"]


def test_jitter_is_seeded(sr: int) -> None:
    sig = np.concatenate([au.speech_like(500, sr), au.silence(2000, sr)])

    def first(seed: int) -> float | None:
        agent = MockAgent(sr, MockAgentConfig(jitter_ms=500, seed=seed))
        return _first(_feed(agent, sig), "audio")

    assert first(1) == first(1)


def test_from_options_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown option"):
        MockAgentConfig.from_options({"speed": 2})
    cfg = MockAgentConfig.from_options({"transcripts": ["a", 1]})
    assert cfg.transcripts == ("a", "1")
