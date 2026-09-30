"""Plays a scenario into an adapter and records both sides of the conversation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from voicebench import audio as au
from voicebench.adapters.base import (
    Adapter,
    AgentAudio,
    AgentClear,
    AgentEvent,
    SessionInfo,
    Transcript,
)
from voicebench.clock import Clock, RealClock, VirtualClock
from voicebench.scenario import Scenario, Turn
from voicebench.vad import StreamingVad

_PACKET_FLOOR_DB = -70.0


@dataclass(frozen=True)
class TurnWindow:
    """When a turn's audio actually played, and what triggered it."""

    turn: Turn
    start: float
    end: float
    trigger: str


@dataclass(frozen=True)
class Packet:
    """One chunk of agent audio: when it arrived and how loud it was."""

    time: float
    level_db: float
    duration: float


@dataclass
class SessionRecord:
    """Everything the analysis needs from one run of a scenario."""

    scenario: Scenario
    adapter: dict[str, object]
    clock: str
    user_track: au.FloatArray
    agent_track: au.FloatArray
    windows: list[TurnWindow] = field(default_factory=list)
    packets: list[Packet] = field(default_factory=list)
    clears: list[float] = field(default_factory=list)
    transcripts: list[Transcript] = field(default_factory=list)
    truncated: bool = False

    @property
    def duration(self) -> float:
        return self.user_track.size / self.scenario.sample_rate


class _Track:
    """A growable mono buffer indexed by sample."""

    def __init__(self, initial: int) -> None:
        self.data = np.zeros(max(initial, 1), dtype=np.float32)

    def write(self, pos: int, pcm: au.FloatArray) -> None:
        end = pos + pcm.size
        if end > self.data.size:
            grown = np.zeros(max(end, self.data.size * 2), dtype=np.float32)
            grown[: self.data.size] = self.data
            self.data = grown
        self.data[pos:end] = pcm

    def clear(self, start: int, end: int) -> None:
        if end > start:
            self.data[start : min(end, self.data.size)] = 0.0


def default_clock(adapter: Adapter, realtime: bool = False) -> Clock:
    """Use virtual time when the adapter allows it, unless ``realtime`` is set."""
    if adapter.supports_virtual_clock and not realtime:
        return VirtualClock()
    return RealClock()


async def run_session(scenario: Scenario, adapter: Adapter, clock: Clock) -> SessionRecord:
    """Run one session and return the recorded tracks and events."""
    sr = scenario.sample_rate
    frame = au.ms_to_samples(scenario.frame_ms, sr)
    max_samples = au.ms_to_samples(scenario.max_duration_ms, sr)
    rendered = [turn.audio.render(sr) for turn in scenario.turns]

    user = _Track(max_samples + frame)
    agent = _Track(max_samples + frame)
    agent_vad = StreamingVad(sr, scenario.agent_vad)
    vad_pos = 0
    playout = 0
    onsets: list[float] = []
    offsets: list[float] = []
    record = SessionRecord(
        scenario=scenario,
        adapter=adapter.describe(),
        clock="virtual" if not clock.realtime else "real",
        user_track=np.zeros(0, dtype=np.float32),
        agent_track=np.zeros(0, dtype=np.float32),
    )

    def handle(event: AgentEvent) -> None:
        nonlocal playout
        if isinstance(event, AgentAudio):
            pos = max(au.ms_to_samples(event.time * 1000.0, sr), playout, vad_pos)
            agent.write(pos, event.pcm)
            playout = pos + event.pcm.size
            record.packets.append(Packet(event.time, au.rms_dbfs(event.pcm), event.pcm.size / sr))
        elif isinstance(event, AgentClear):
            cut = max(au.ms_to_samples(event.time * 1000.0, sr), vad_pos)
            agent.clear(cut, playout)
            playout = min(playout, cut)
            record.clears.append(event.time)
        else:
            record.transcripts.append(event)

    next_turn = 0
    prev_end = 0.0
    waiting_since = 0.0
    tail = scenario.tail_ms / 1000.0
    i = 0
    await adapter.start(
        SessionInfo(
            sample_rate=sr, frame_ms=scenario.frame_ms, clock=clock, scenario_name=scenario.name
        )
    )
    try:
        while True:
            pos = i * frame
            if pos >= max_samples:
                record.truncated = True
                break
            t = pos / sr
            await clock.sleep_until(t)

            for event in adapter.drain():
                handle(event)
            if pos > vad_pos:
                for ev in agent_vad.push(agent.data[vad_pos:pos]):
                    (onsets if ev.kind == "onset" else offsets).append(ev.time)
                vad_pos = pos

            if next_turn < len(scenario.turns) and t + 1e-9 >= prev_end:
                turn = scenario.turns[next_turn]
                anchor = _anchor_time(turn, prev_end, waiting_since, onsets, offsets)
                trigger = ""
                if anchor is not None and t + 1e-9 >= anchor + turn.start.delay_ms / 1000.0:
                    trigger = "anchor"
                elif t + 1e-9 >= waiting_since + turn.start.timeout_ms / 1000.0:
                    trigger = "timeout"
                if trigger:
                    clip = rendered[next_turn]
                    user.write(pos, clip)
                    prev_end = t + clip.size / sr
                    waiting_since = prev_end
                    record.windows.append(TurnWindow(turn, t, prev_end, trigger))
                    next_turn += 1

            await adapter.send_audio(user.data[pos : pos + frame].copy())

            done_turns = next_turn >= len(scenario.turns)
            if done_turns and t >= prev_end + tail and not agent_vad.speaking and playout <= pos:
                break
            i += 1
    finally:
        await adapter.close()
    for event in adapter.drain():
        handle(event)

    end = (i + 1) * frame
    record.user_track = user.data[:end].copy()
    record.agent_track = agent.data[:end].copy()
    record.packets = [p for p in record.packets if p.level_db > _PACKET_FLOOR_DB]
    return record


def _anchor_time(
    turn: Turn,
    prev_end: float,
    waiting_since: float,
    onsets: list[float],
    offsets: list[float],
) -> float | None:
    after = turn.start.after
    if after == "session_start":
        return 0.0
    if after == "previous_turn_end":
        return prev_end
    times = onsets if after == "agent_speech_start" else offsets
    for ts in times:
        if ts + 1e-9 >= waiting_since:
            return ts
    return None


async def run(scenario: Scenario, adapter: Adapter, realtime: bool = False) -> SessionRecord:
    """Run one session with the clock the adapter supports."""
    return await run_session(scenario, adapter, default_clock(adapter, realtime))
