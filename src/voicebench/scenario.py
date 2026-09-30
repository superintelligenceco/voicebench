"""Scenario files: YAML descriptions of a scripted conversation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from voicebench import audio as au
from voicebench.vad import VadConfig

Anchor = Literal["session_start", "previous_turn_end", "agent_speech_start", "agent_speech_end"]
Expectation = Literal["respond", "stop", "ignore"]

ANCHORS: tuple[str, ...] = (
    "session_start",
    "previous_turn_end",
    "agent_speech_start",
    "agent_speech_end",
)
EXPECTATIONS: tuple[str, ...] = ("respond", "stop", "ignore")
SYNTH_KINDS: tuple[str, ...] = ("speech", "tone", "noise", "silence")
ASSERT_KEYS: tuple[str, ...] = (
    "max_response_latency_ms",
    "p50_response_latency_ms",
    "p90_response_latency_ms",
    "p50_ttfa_ms",
    "max_barge_in_stop_ms",
    "min_barge_in_success_rate",
    "max_false_barge_ins",
    "max_missed_responses",
    "max_wer",
)


class ScenarioError(ValueError):
    """Raised when a scenario file is invalid. The message names the offending key."""


@dataclass(frozen=True)
class AudioSpec:
    """Where a turn's audio comes from: a WAV file or a synthesized signal."""

    file: Path | None = None
    synth: str | None = None
    duration_ms: float = 1000.0
    level_db: float = -20.0
    freq_hz: float = 440.0
    seed: int = 0

    def render(self, sample_rate: int) -> au.FloatArray:
        if self.file is not None:
            return au.read_wav(self.file, sample_rate)
        if self.synth == "speech":
            return au.speech_like(self.duration_ms, sample_rate, self.level_db, seed=self.seed)
        if self.synth == "tone":
            return au.tone(self.duration_ms, sample_rate, self.freq_hz, self.level_db)
        if self.synth == "noise":
            return au.noise(self.duration_ms, sample_rate, self.level_db, seed=self.seed)
        return au.silence(self.duration_ms, sample_rate)


@dataclass(frozen=True)
class StartRule:
    """When a turn starts: ``delay_ms`` after ``after``, or after ``timeout_ms`` regardless."""

    after: Anchor = "agent_speech_end"
    delay_ms: float = 0.0
    timeout_ms: float = 10000.0


@dataclass(frozen=True)
class Turn:
    """One scripted user utterance and what the agent should do about it."""

    id: str
    audio: AudioSpec
    start: StartRule
    expect: Expectation = "respond"
    text: str | None = None
    response_timeout_ms: float = 5000.0
    max_stop_ms: float = 1000.0


@dataclass(frozen=True)
class AdapterSpec:
    type: str = "mock"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    """A parsed and validated scenario."""

    name: str
    turns: tuple[Turn, ...]
    description: str = ""
    sample_rate: int = 16000
    frame_ms: float = 20.0
    tail_ms: float = 3000.0
    max_duration_ms: float = 120000.0
    user_vad: VadConfig = field(default_factory=VadConfig)
    agent_vad: VadConfig = field(default_factory=VadConfig)
    adapter: AdapterSpec = field(default_factory=AdapterSpec)
    assertions: dict[str, float] = field(default_factory=dict)
    source: Path | None = None


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario from a YAML file."""
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{p}: invalid YAML: {exc}") from exc
    return parse_scenario(data, base_dir=p.parent, source=p)


def parse_scenario(data: Any, base_dir: Path | None = None, source: Path | None = None) -> Scenario:
    """Validate a scenario from already-parsed YAML data."""
    root = _mapping(data, "scenario")
    _check_keys(
        root,
        "scenario",
        {
            "name",
            "description",
            "sample_rate",
            "frame_ms",
            "tail_ms",
            "max_duration_ms",
            "vad",
            "adapter",
            "defaults",
            "turns",
            "assert",
        },
    )
    name = _str(root.get("name"), "name")
    sample_rate = int(_num(root.get("sample_rate", 16000), "sample_rate", minimum=8000))
    frame_ms = _num(root.get("frame_ms", 20), "frame_ms", minimum=5)
    defaults = _mapping(root.get("defaults", {}), "defaults")
    _check_keys(defaults, "defaults", {"response_timeout_ms", "max_stop_ms"})

    raw_turns = root.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ScenarioError("turns: must be a non-empty list")
    turns: list[Turn] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_turns):
        turn = _parse_turn(raw, f"turns[{i}]", i, defaults, base_dir)
        if turn.id in seen:
            raise ScenarioError(f"turns[{i}].id: duplicate id {turn.id!r}")
        seen.add(turn.id)
        turns.append(turn)

    vad = _mapping(root.get("vad", {}), "vad")
    _check_keys(vad, "vad", {"user", "agent"})

    adapter_raw = _mapping(root.get("adapter", {}), "adapter")
    _check_keys(adapter_raw, "adapter", {"type", "options"})
    adapter = AdapterSpec(
        type=_str(adapter_raw.get("type", "mock"), "adapter.type"),
        options=dict(_mapping(adapter_raw.get("options", {}), "adapter.options")),
    )

    assertions_raw = _mapping(root.get("assert", {}), "assert")
    _check_keys(assertions_raw, "assert", set(ASSERT_KEYS))
    assertions = {k: _num(v, f"assert.{k}") for k, v in assertions_raw.items()}

    return Scenario(
        name=name,
        description=str(root.get("description", "")),
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        tail_ms=_num(root.get("tail_ms", 3000), "tail_ms", minimum=0),
        max_duration_ms=_num(root.get("max_duration_ms", 120000), "max_duration_ms", minimum=1),
        turns=tuple(turns),
        user_vad=_parse_vad(vad.get("user", {}), "vad.user"),
        agent_vad=_parse_vad(vad.get("agent", {}), "vad.agent"),
        adapter=adapter,
        assertions=assertions,
        source=source,
    )


def _parse_turn(
    raw: Any, where: str, index: int, defaults: dict[str, Any], base_dir: Path | None
) -> Turn:
    m = _mapping(raw, where)
    _check_keys(
        m,
        where,
        {"id", "audio", "start", "expect", "text", "response_timeout_ms", "max_stop_ms"},
    )
    turn_id = _str(m.get("id", f"turn-{index + 1}"), f"{where}.id")
    expect = m.get("expect", "respond")
    if expect not in EXPECTATIONS:
        raise ScenarioError(f"{where}.expect: must be one of {', '.join(EXPECTATIONS)}")

    start_raw = _mapping(m.get("start", {}), f"{where}.start")
    _check_keys(start_raw, f"{where}.start", {"after", "delay_ms", "timeout_ms"})
    default_anchor = "session_start" if index == 0 else "agent_speech_end"
    after = start_raw.get("after", default_anchor)
    if after not in ANCHORS:
        raise ScenarioError(f"{where}.start.after: must be one of {', '.join(ANCHORS)}")
    start = StartRule(
        after=cast(Anchor, after),
        delay_ms=_num(
            start_raw.get("delay_ms", 500 if index == 0 else 0), f"{where}.start.delay_ms"
        ),
        timeout_ms=_num(start_raw.get("timeout_ms", 10000), f"{where}.start.timeout_ms", minimum=0),
    )

    text = m.get("text")
    if text is not None and not isinstance(text, str):
        raise ScenarioError(f"{where}.text: must be a string")

    return Turn(
        id=turn_id,
        audio=_parse_audio(m.get("audio"), f"{where}.audio", base_dir),
        start=start,
        expect=cast(Expectation, expect),
        text=text,
        response_timeout_ms=_num(
            m.get("response_timeout_ms", defaults.get("response_timeout_ms", 5000)),
            f"{where}.response_timeout_ms",
            minimum=0,
        ),
        max_stop_ms=_num(
            m.get("max_stop_ms", defaults.get("max_stop_ms", 1000)),
            f"{where}.max_stop_ms",
            minimum=0,
        ),
    )


def _parse_audio(raw: Any, where: str, base_dir: Path | None) -> AudioSpec:
    m = _mapping(raw, where)
    _check_keys(m, where, {"file", "synth", "duration_ms", "level_db", "freq_hz", "seed"})
    has_file = "file" in m
    has_synth = "synth" in m
    if has_file == has_synth:
        raise ScenarioError(f"{where}: set exactly one of 'file' or 'synth'")
    if has_file:
        path = Path(_str(m["file"], f"{where}.file"))
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        if not path.is_file():
            raise ScenarioError(f"{where}.file: {path} does not exist")
        return AudioSpec(file=path)
    synth = m["synth"]
    if synth not in SYNTH_KINDS:
        raise ScenarioError(f"{where}.synth: must be one of {', '.join(SYNTH_KINDS)}")
    return AudioSpec(
        synth=synth,
        duration_ms=_num(m.get("duration_ms", 1000), f"{where}.duration_ms", minimum=1),
        level_db=_num(m.get("level_db", -20), f"{where}.level_db"),
        freq_hz=_num(m.get("freq_hz", 440), f"{where}.freq_hz", minimum=1),
        seed=int(_num(m.get("seed", 0), f"{where}.seed")),
    )


def _parse_vad(raw: Any, where: str) -> VadConfig:
    m = _mapping(raw, where)
    allowed = {"threshold_db", "hysteresis_db", "frame_ms", "min_speech_ms", "min_silence_ms"}
    _check_keys(m, where, allowed)
    try:
        return VadConfig(**{k: _num(v, f"{where}.{k}") for k, v in m.items()})
    except ValueError as exc:
        raise ScenarioError(f"{where}: {exc}") from exc


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScenarioError(f"{where}: must be a mapping")
    return value


def _check_keys(m: dict[str, Any], where: str, allowed: set[str]) -> None:
    unknown = sorted(set(m) - allowed)
    if unknown:
        raise ScenarioError(f"{where}: unknown key(s) {', '.join(unknown)}")


def _str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{where}: must be a non-empty string")
    return value


def _num(value: Any, where: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ScenarioError(f"{where}: must be a number")
    if minimum is not None and value < minimum:
        raise ScenarioError(f"{where}: must be >= {minimum:g}")
    return float(value)
