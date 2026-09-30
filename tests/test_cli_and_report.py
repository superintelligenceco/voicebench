from __future__ import annotations

import json
from pathlib import Path

import pytest

from voicebench import audio as au
from voicebench.adapters import AdapterError, create_adapter, load_adapter_class
from voicebench.adapters.base import Adapter
from voicebench.cli import main


def test_run_writes_all_reports(
    examples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    code = main(["run", str(examples_dir / "mock-conversation.yaml"), "--out", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert "Turns passed" in printed
    assert "PASS  max_false_barge_ins" in printed
    report = json.loads((out / "report.json").read_text())
    assert report["schema_version"] == 1
    assert report["passed"] is True
    assert report["adapter"]["type"] == "mock"
    assert len(report["sessions"][0]["turns"]) == 5
    md = (out / "report.md").read_text()
    assert md.startswith("# voicebench report: mock-conversation")
    assert "| Metric | Value |" in md
    html = (out / "report.html").read_text()
    assert "<svg" in html
    assert "<table>" in html


def test_run_exit_code_on_failed_assertion(examples_dir: Path) -> None:
    code = main(
        [
            "run",
            str(examples_dir / "mock-conversation.yaml"),
            "--no-write",
            "-q",
            "-o",
            "interruptible=false",
        ]
    )
    assert code == 1


def test_run_single_format(examples_dir: Path, tmp_path: Path) -> None:
    code = main(
        [
            "run",
            str(examples_dir / "mock-conversation.yaml"),
            "--out",
            str(tmp_path),
            "-q",
            "--format",
            "md",
        ]
    )
    assert code == 0
    assert [p.name for p in tmp_path.iterdir()] == ["report.md"]


def test_run_usage_errors(tmp_path: Path, examples_dir: Path) -> None:
    assert main(["run", str(tmp_path / "missing.yaml")]) == 2
    scenario = str(examples_dir / "mock-conversation.yaml")
    assert main(["run", scenario, "--format", "pdf"]) == 2
    assert main(["run", scenario, "-o", "novalue"]) == 2
    assert main(["run", scenario, "--no-write", "-o", "speed=2"]) == 3
    assert main(["run", scenario, "-a", "nope"]) == 3


def test_validate(examples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n", encoding="utf-8")
    assert main(["validate", str(examples_dir / "mock-conversation.yaml")]) == 0
    assert main(["validate", str(bad)]) == 2
    out = capsys.readouterr().out
    assert "ok    " in out
    assert "FAIL  " in out


def test_synth(tmp_path: Path) -> None:
    path = tmp_path / "s.wav"
    assert main(["synth", str(path), "--kind", "tone", "--duration-ms", "250"]) == 0
    assert au.read_wav(path, 16000).size == 4000


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "voicebench 0.1.0" in capsys.readouterr().out


def test_adapter_registry() -> None:
    assert load_adapter_class("mock").name == "mock"
    with pytest.raises(AdapterError, match="unknown adapter"):
        load_adapter_class("carrier-pigeon")
    with pytest.raises(AdapterError, match="cannot load"):
        load_adapter_class("no_such_module:Thing")
    with pytest.raises(AdapterError, match="not a voicebench Adapter"):
        load_adapter_class("voicebench.audio:tone")
    with pytest.raises(AdapterError, match="bad options"):
        create_adapter("mock", {"speed": 2})


def test_custom_adapter_by_path(
    examples_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.syspath_prepend(str(examples_dir))
    cls = load_adapter_class("echo_adapter:EchoAdapter")
    assert issubclass(cls, Adapter)
    assert main(["run", str(examples_dir / "echo.yaml"), "--no-write"]) == 0
    out = capsys.readouterr().out
    assert "adapter=echo" in out
    assert "hello  respond  500 ms" in out


def test_optional_adapters_fail_cleanly_without_extras() -> None:
    import importlib.util

    for name, module in (("livekit", "livekit.rtc"), ("pipecat", "pipecat")):
        try:
            installed = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            installed = False
        if installed:
            continue
        with pytest.raises(AdapterError, match=rf"voicebench\[{name}\]"):
            load_adapter_class(name)
