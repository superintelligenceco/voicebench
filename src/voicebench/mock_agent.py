"""A deterministic, frame-driven mock voice agent.

The mock stands in for a real agent in tests, demos, and CI. It detects the
end of a user turn with a simple energy threshold, waits a configurable delay,
and answers with a speech-like signal. It yields to barge-in after a
configurable reaction time, or ignores barge-in if you tell it to.

Its latency numbers are whatever you configure, so they say nothing about any
real product. The point is to check the harness itself end to end.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Literal

import numpy as np

from voicebench import audio as au


@dataclass(frozen=True)
class MockAgentConfig:
    """Behavior knobs for :class:`MockAgent`. Times are in milliseconds."""

    endpoint_silence_ms: float = 300.0
    response_delay_ms: float = 400.0
    jitter_ms: float = 0.0
    response_ms: float = 1500.0
    greeting_ms: float = 0.0
    level_db: float = -20.0
    threshold_db: float = -45.0
    interruptible: bool = True
    barge_in_min_ms: float = 100.0
    interrupt_reaction_ms: float = 150.0
    transcripts: tuple[str, ...] = ()
    seed: int = 0

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> MockAgentConfig:
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(options) - known)
        if unknown:
            raise ValueError(f"mock agent: unknown option(s) {', '.join(unknown)}")
        opts = dict(options)
        if "transcripts" in opts:
            opts["transcripts"] = tuple(str(t) for t in opts["transcripts"])
        return cls(**opts)


@dataclass(frozen=True)
class MockOutput:
    """What the mock produced for one input frame."""

    kind: Literal["audio", "clear", "transcript"]
    pcm: au.FloatArray | None = None
    text: str = ""


class MockAgent:
    """State machine that maps each input frame to zero or more outputs."""

    def __init__(self, sample_rate: int, config: MockAgentConfig | None = None) -> None:
        self.sample_rate = sample_rate
        self.config = config or MockAgentConfig()
        self._rng = np.random.default_rng(self.config.seed)
        self._state: Literal["listening", "waiting", "speaking"] = "listening"
        self._heard_speech = False
        self._silence_s = 0.0
        self._overlap_speech_s = 0.0
        self._respond_at = 0.0
        self._stop_at: float | None = None
        self._voice = np.zeros(0, dtype=np.float32)
        self._voice_pos = 0
        self._turns_heard = 0
        self._started = False

    @property
    def state(self) -> str:
        return self._state

    def process(self, frame: au.FloatArray, t: float) -> list[MockOutput]:
        """Consume the user frame that starts at ``t`` seconds."""
        cfg = self.config
        dur = frame.size / self.sample_rate
        out: list[MockOutput] = []
        if not self._started:
            self._started = True
            if cfg.greeting_ms > 0:
                self._begin_speaking(cfg.greeting_ms)

        user_active = au.rms_dbfs(frame) >= cfg.threshold_db
        if user_active:
            # Speech that overlaps the agent only counts as a new user turn once
            # it qualifies as a barge-in; a cough under a reply is not a turn.
            if self._state != "speaking":
                self._heard_speech = True
            self._silence_s = 0.0
        else:
            self._silence_s += dur

        endpoint = self._silence_s * 1000.0 + 1e-9 >= cfg.endpoint_silence_ms
        if self._state == "listening" and self._heard_speech and endpoint:
            self._heard_speech = False
            jitter = float(self._rng.uniform(0.0, cfg.jitter_ms)) if cfg.jitter_ms else 0.0
            self._respond_at = t + dur + (cfg.response_delay_ms + jitter) / 1000.0
            self._state = "waiting"
            if self._turns_heard < len(cfg.transcripts):
                out.append(MockOutput("transcript", text=cfg.transcripts[self._turns_heard]))
            self._turns_heard += 1

        if self._state == "waiting" and t + 1e-9 >= self._respond_at:
            self._begin_speaking(cfg.response_ms)

        if self._state == "speaking":
            if user_active:
                self._overlap_speech_s += dur
            else:
                self._overlap_speech_s = 0.0
            if (
                cfg.interruptible
                and self._stop_at is None
                and self._overlap_speech_s * 1000.0 + 1e-9 >= cfg.barge_in_min_ms
            ):
                self._stop_at = t + dur + cfg.interrupt_reaction_ms / 1000.0
                self._heard_speech = True
            if self._stop_at is not None and t + 1e-9 >= self._stop_at:
                self._state = "listening"
                self._stop_at = None
                out.append(MockOutput("clear"))
                return out
            chunk = self._voice[self._voice_pos : self._voice_pos + frame.size]
            self._voice_pos += frame.size
            if chunk.size < frame.size:
                chunk = np.concatenate([chunk, np.zeros(frame.size - chunk.size, np.float32)])
            out.append(MockOutput("audio", pcm=chunk))
            if self._voice_pos >= self._voice.size:
                self._state = "listening"
                self._stop_at = None
        return out

    def _begin_speaking(self, duration_ms: float) -> None:
        self._voice = au.speech_like(
            duration_ms,
            self.sample_rate,
            level_db=self.config.level_db,
            f0_hz=210.0,
            seed=self.config.seed + self._turns_heard,
        )
        self._voice_pos = 0
        self._overlap_speech_s = 0.0
        self._stop_at = None
        self._state = "speaking"
