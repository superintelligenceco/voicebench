from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from voicebench import audio as au
from voicebench.scenario import ScenarioError, load_scenario, parse_scenario


def _minimal(**extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"name": "t", "turns": [{"audio": {"synth": "speech"}}]}
    data.update(extra)
    return data


def test_defaults() -> None:
    sc = parse_scenario(_minimal())
    assert sc.sample_rate == 16000
    assert sc.adapter.type == "mock"
    turn = sc.turns[0]
    assert turn.id == "turn-1"
    assert turn.expect == "respond"
    assert turn.start.after == "session_start"
    assert turn.start.delay_ms == 500


def test_later_turns_default_to_agent_speech_end() -> None:
    sc = parse_scenario(
        {"name": "t", "turns": [{"audio": {"synth": "speech"}}, {"audio": {"synth": "tone"}}]}
    )
    assert sc.turns[1].start.after == "agent_speech_end"
    assert sc.turns[1].start.delay_ms == 0


def test_defaults_block_applies_to_turns() -> None:
    sc = parse_scenario(_minimal(defaults={"response_timeout_ms": 900, "max_stop_ms": 300}))
    assert sc.turns[0].response_timeout_ms == 900
    assert sc.turns[0].max_stop_ms == 300


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"turns": [{"audio": {"synth": "speech"}}]}, "name"),
        ({"name": "t", "turns": []}, "turns"),
        (_minimal(bogus=1), "unknown key"),
        ({"name": "t", "turns": [{"audio": {}}]}, "exactly one"),
        ({"name": "t", "turns": [{"audio": {"synth": "music"}}]}, "synth"),
        ({"name": "t", "turns": [{"audio": {"synth": "speech"}, "expect": "maybe"}]}, "expect"),
        (
            {"name": "t", "turns": [{"audio": {"synth": "speech"}, "start": {"after": "later"}}]},
            "after",
        ),
        (_minimal(sample_rate=4000), "sample_rate"),
        (_minimal(frame_ms="20"), "number"),
        (_minimal(frame_ms=True), "number"),
        (_minimal(**{"assert": {"max_latency": 1}}), "unknown key"),
        (_minimal(vad={"user": {"frame_ms": 0}}), "vad.user"),
        (
            {
                "name": "t",
                "turns": [
                    {"id": "a", "audio": {"synth": "speech"}},
                    {"id": "a", "audio": {"synth": "speech"}},
                ],
            },
            "duplicate",
        ),
        ("just a string", "mapping"),
    ],
)
def test_invalid_scenarios(data: Any, match: str) -> None:
    with pytest.raises(ScenarioError, match=match):
        parse_scenario(data)


def test_wav_file_relative_to_scenario(tmp_path: Path, sr: int) -> None:
    au.write_wav(tmp_path / "hello.wav", au.tone(300, sr), sr)
    (tmp_path / "s.yaml").write_text(
        "name: wav\nturns:\n  - audio: {file: hello.wav}\n", encoding="utf-8"
    )
    sc = load_scenario(tmp_path / "s.yaml")
    assert sc.turns[0].audio.file == tmp_path / "hello.wav"
    assert sc.turns[0].audio.render(sr).size == au.ms_to_samples(300, sr)


def test_missing_wav_file(tmp_path: Path) -> None:
    (tmp_path / "s.yaml").write_text(
        "name: wav\nturns:\n  - audio: {file: nope.wav}\n", encoding="utf-8"
    )
    with pytest.raises(ScenarioError, match="does not exist"):
        load_scenario(tmp_path / "s.yaml")


def test_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "s.yaml").write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(ScenarioError, match="invalid YAML"):
        load_scenario(tmp_path / "s.yaml")


def test_all_examples_load(examples_dir: Path, tmp_path: Path, sr: int) -> None:
    # Some examples reference recordings you supply yourself; stand in for them.
    (tmp_path / "audio").mkdir()
    for name in ("hello", "question", "interrupt"):
        au.write_wav(tmp_path / "audio" / f"{name}.wav", au.speech_like(500, sr), sr)
    files = sorted(examples_dir.glob("*.yaml"))
    assert len(files) >= 4
    for path in files:
        copy = tmp_path / path.name
        copy.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        assert load_scenario(copy).turns
