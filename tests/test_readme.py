"""Check that the commands and code in README.md still work."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

import pytest

from voicebench.cli import build_parser, main

REPO = Path(__file__).resolve().parent.parent
README = (REPO / "README.md").read_text(encoding="utf-8")


def _blocks(lang: str) -> list[str]:
    return re.findall(rf"```{lang}\n(.*?)```", README, flags=re.DOTALL)


def _voicebench_commands() -> list[list[str]]:
    commands = []
    for block in _blocks("sh"):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("voicebench "):
                commands.append(shlex.split(line, comments=True)[1:])
    return commands


def test_readme_shows_voicebench_commands() -> None:
    assert len(_voicebench_commands()) >= 8


@pytest.mark.parametrize("argv", _voicebench_commands(), ids=lambda a: " ".join(a))
def test_every_readme_command_parses(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)
    assert args.command == argv[0]


def test_readme_quickstart_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["example", "mock-conversation", "-O", "demo.yaml"]) == 0
    assert main(["run", "demo.yaml"]) == 0
    (run_dir,) = (tmp_path / "voicebench-results").iterdir()
    for name in ("report.json", "report.md", "report.html"):
        assert (run_dir / name).is_file()


def test_readme_console_output_matches_a_real_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (console,) = _blocks("console")
    prompt, *expected = console.rstrip("\n").splitlines()
    argv = shlex.split(prompt.removeprefix("$ "))[1:]
    monkeypatch.chdir(REPO)
    assert main(argv) == 0
    actual = capsys.readouterr().out.rstrip("\n").splitlines()
    assert [line.rstrip() for line in actual] == [line.rstrip() for line in expected]


def test_readme_python_example_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    (code,) = _blocks("python")
    monkeypatch.chdir(REPO)
    exec(compile(code, "README.md", "exec"), {"__name__": "readme"})
    assert os.getcwd() == str(REPO)
