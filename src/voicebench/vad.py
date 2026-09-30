"""Energy-based voice activity detection with hysteresis and hangover.

The detector works on fixed analysis frames. A segment opens when the frame
level stays at or above ``threshold_db`` for ``min_speech_ms``, and closes when
the level stays below ``threshold_db - hysteresis_db`` for ``min_silence_ms``.
Reported onsets and offsets are backdated to the first and last active frame,
so the confirmation delay does not bias latency numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from voicebench.audio import FloatArray, ms_to_samples, rms_dbfs


@dataclass(frozen=True)
class VadConfig:
    """Tuning parameters for :class:`StreamingVad`."""

    threshold_db: float = -45.0
    hysteresis_db: float = 6.0
    frame_ms: float = 10.0
    min_speech_ms: float = 50.0
    min_silence_ms: float = 250.0

    def __post_init__(self) -> None:
        if self.frame_ms <= 0:
            raise ValueError("frame_ms must be positive")
        if self.min_speech_ms < 0 or self.min_silence_ms < 0:
            raise ValueError("min_speech_ms and min_silence_ms must be non-negative")
        if self.hysteresis_db < 0:
            raise ValueError("hysteresis_db must be non-negative")


@dataclass(frozen=True)
class VadEvent:
    """A confirmed speech boundary. ``time`` is in seconds from the stream origin."""

    kind: Literal["onset", "offset"]
    time: float


@dataclass(frozen=True)
class Segment:
    """A span of detected speech, in seconds."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: Segment) -> float:
        """Return the overlap with ``other`` in seconds (0 if disjoint)."""
        return max(0.0, min(self.end, other.end) - max(self.start, other.start))


class StreamingVad:
    """Incremental detector. Feed audio with :meth:`push`, then call :meth:`flush`."""

    def __init__(self, sample_rate: int, config: VadConfig | None = None) -> None:
        self.sample_rate = sample_rate
        self.config = config or VadConfig()
        self._frame_len = max(1, ms_to_samples(self.config.frame_ms, sample_rate))
        self._frame_s = self._frame_len / sample_rate
        self._buf = np.zeros(0, dtype=np.float32)
        self._frames_seen = 0
        self._speaking = False
        self._cand_start: float | None = None
        self._cand_len = 0.0
        self._last_active_end = 0.0

    @property
    def speaking(self) -> bool:
        """True while a confirmed segment is open."""
        return self._speaking

    @property
    def position(self) -> float:
        """Seconds of audio consumed into complete analysis frames."""
        return self._frames_seen * self._frame_s

    def push(self, audio: FloatArray) -> list[VadEvent]:
        """Consume ``audio`` and return any boundaries confirmed by it."""
        if audio.size:
            self._buf = np.concatenate([self._buf, audio.astype(np.float32, copy=False)])
        events: list[VadEvent] = []
        n_frames = self._buf.size // self._frame_len
        for i in range(n_frames):
            frame = self._buf[i * self._frame_len : (i + 1) * self._frame_len]
            event = self._step(rms_dbfs(frame))
            if event is not None:
                events.append(event)
        self._buf = self._buf[n_frames * self._frame_len :]
        return events

    def flush(self) -> list[VadEvent]:
        """Close an open segment at the end of the stream."""
        if self._speaking:
            self._speaking = False
            return [VadEvent("offset", self._last_active_end)]
        return []

    def _step(self, level: float) -> VadEvent | None:
        cfg = self.config
        start = self._frames_seen * self._frame_s
        end = start + self._frame_s
        self._frames_seen += 1
        if not self._speaking:
            if level >= cfg.threshold_db:
                if self._cand_start is None:
                    self._cand_start = start
                    self._cand_len = 0.0
                self._cand_len += self._frame_s
                if self._cand_len + 1e-9 >= cfg.min_speech_ms / 1000.0:
                    self._speaking = True
                    self._last_active_end = end
                    onset = self._cand_start
                    self._cand_start = None
                    return VadEvent("onset", onset)
            else:
                self._cand_start = None
            return None
        if level >= cfg.threshold_db - cfg.hysteresis_db:
            self._last_active_end = end
        elif end - self._last_active_end + 1e-9 >= cfg.min_silence_ms / 1000.0:
            self._speaking = False
            return VadEvent("offset", self._last_active_end)
        return None


def events_to_segments(events: list[VadEvent]) -> list[Segment]:
    """Pair onset and offset events into segments."""
    segments: list[Segment] = []
    onset: float | None = None
    for ev in events:
        if ev.kind == "onset":
            onset = ev.time
        elif onset is not None:
            segments.append(Segment(onset, ev.time))
            onset = None
    return segments


def detect_segments(
    audio: FloatArray, sample_rate: int, config: VadConfig | None = None
) -> list[Segment]:
    """Run the detector over a whole buffer and return the speech segments."""
    vad = StreamingVad(sample_rate, config)
    events = vad.push(audio)
    events += vad.flush()
    return events_to_segments(events)
