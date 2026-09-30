"""Command-line interface for voicebench: run, validate, example, mock-server, and synth."""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from voicebench import __version__
from voicebench import audio as au
from voicebench.adapters import BUILTIN, AdapterError
from voicebench.bench import run_benchmark
from voicebench.report import render_console, render_html, render_markdown, write_json
from voicebench.scenario import ScenarioError, load_scenario

EXIT_OK = 0
EXIT_ASSERTIONS = 1
EXIT_USAGE = 2
EXIT_ADAPTER = 3
FORMATS = ("json", "md", "html")


def _parse_options(pairs: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"--option expects key=value, got {pair!r}")
        options[key.strip()] = yaml.safe_load(value) if value else ""
    return options


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", text).strip("-") or "scenario"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voicebench",
        description="Benchmark real-time voice agents: latency, barge-in, and turn-taking.",
    )
    parser.add_argument("--version", action="version", version=f"voicebench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a scenario against an agent")
    run_p.add_argument("scenario", type=Path, help="path to a scenario YAML file")
    run_p.add_argument(
        "-a",
        "--adapter",
        help=f"adapter to use ({', '.join(BUILTIN)}, or module:Class); overrides the scenario",
    )
    run_p.add_argument("--url", help="agent URL (sets the adapter's 'url' option)")
    run_p.add_argument(
        "-o",
        "--option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="adapter option; VALUE is parsed as YAML (repeatable)",
    )
    run_p.add_argument("-n", "--repeat", type=int, default=1, help="number of sessions (default 1)")
    run_p.add_argument(
        "--realtime",
        action="store_true",
        help="run the mock adapter on the wall clock instead of virtual time",
    )
    run_p.add_argument(
        "--out",
        type=Path,
        help="output directory (default: voicebench-results/<scenario>-<timestamp>)",
    )
    run_p.add_argument(
        "--format",
        default="json,md,html",
        help="comma-separated report formats: json, md, html (default: all)",
    )
    run_p.add_argument("--no-write", action="store_true", help="print the summary only")
    run_p.add_argument("-q", "--quiet", action="store_true", help="do not print the summary")

    val_p = sub.add_parser("validate", help="check scenario files without running them")
    val_p.add_argument("scenarios", type=Path, nargs="+")

    ex_p = sub.add_parser(
        "example", help="print or save a bundled example scenario (omit NAME to list them)"
    )
    ex_p.add_argument("name", nargs="?", help="example name, for example mock-conversation")
    ex_p.add_argument("-O", "--output", type=Path, help="write the scenario to this file")

    mock_p = sub.add_parser("mock-server", help="serve the mock agent over the WebSocket protocol")
    mock_p.add_argument("--host", default="127.0.0.1")
    mock_p.add_argument("--port", type=int, default=8765)
    mock_p.add_argument("--sample-rate", type=int, default=16000)
    mock_p.add_argument("-o", "--option", action="append", default=[], metavar="KEY=VALUE")

    synth_p = sub.add_parser("synth", help="write a synthetic test signal to a WAV file")
    synth_p.add_argument("output", type=Path)
    synth_p.add_argument("--kind", choices=["speech", "tone", "noise", "silence"], default="speech")
    synth_p.add_argument("--duration-ms", type=float, default=1500.0)
    synth_p.add_argument("--level-db", type=float, default=-20.0)
    synth_p.add_argument("--sample-rate", type=int, default=16000)
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    bad = [f for f in formats if f not in FORMATS]
    if bad:
        print(f"error: unknown format(s): {', '.join(bad)}", file=sys.stderr)
        return EXIT_USAGE
    try:
        scenario = load_scenario(args.scenario)
        options = _parse_options(args.option)
    except (ScenarioError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.url:
        options["url"] = args.url
    try:
        result = asyncio.run(
            run_benchmark(
                scenario,
                adapter=args.adapter,
                options=options,
                repeat=args.repeat,
                realtime=args.realtime,
            )
        )
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ADAPTER
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not args.quiet:
        print(render_console(result.report, result.sessions))
    if not args.no_write:
        out: Path = args.out or Path("voicebench-results") / (
            f"{_slug(scenario.name)}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        out.mkdir(parents=True, exist_ok=True)
        if "json" in formats:
            write_json(result.report, out / "report.json")
        if "md" in formats:
            (out / "report.md").write_text(
                render_markdown(result.report, result.sessions), encoding="utf-8"
            )
        if "html" in formats:
            (out / "report.html").write_text(
                render_html(result.report, result.sessions), encoding="utf-8"
            )
        if not args.quiet:
            print(f"\nreports written to {out}")
    return EXIT_OK if result.passed else EXIT_ASSERTIONS


def _cmd_validate(args: argparse.Namespace) -> int:
    status = EXIT_OK
    for path in args.scenarios:
        try:
            sc = load_scenario(path)
        except (ScenarioError, OSError) as exc:
            print(f"FAIL  {path}: {exc}")
            status = EXIT_USAGE
        else:
            print(f"ok    {path}: {sc.name} ({len(sc.turns)} turns, adapter {sc.adapter.type})")
    return status


def bundled_examples() -> dict[str, str]:
    """Return the bundled example scenarios as ``{name: yaml_text}``."""
    root = resources.files("voicebench") / "examples"
    return {
        entry.name.removesuffix(".yaml"): entry.read_text(encoding="utf-8")
        for entry in sorted(root.iterdir(), key=lambda e: e.name)
        if entry.name.endswith(".yaml")
    }


def _cmd_example(args: argparse.Namespace) -> int:
    examples = bundled_examples()
    if not args.name:
        for name, text in examples.items():
            description = yaml.safe_load(text).get("description", "")
            print(f"{name:<20} {description}")
        return EXIT_OK
    if args.name not in examples:
        print(
            f"error: unknown example {args.name!r}; use one of {', '.join(examples)}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.output:
        args.output.write_text(examples[args.name], encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(examples[args.name])
    return EXIT_OK


def _cmd_mock_server(args: argparse.Namespace) -> int:
    from voicebench.mock_server import serve_forever

    try:
        options = _parse_options(args.option)
        asyncio.run(serve_forever(args.host, args.port, args.sample_rate, options))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def _cmd_synth(args: argparse.Namespace) -> int:
    sr = args.sample_rate
    if args.kind == "speech":
        signal = au.speech_like(args.duration_ms, sr, args.level_db)
    elif args.kind == "tone":
        signal = au.tone(args.duration_ms, sr, level_db=args.level_db)
    elif args.kind == "noise":
        signal = au.noise(args.duration_ms, sr, args.level_db)
    else:
        signal = au.silence(args.duration_ms, sr)
    au.write_wav(args.output, signal, sr)
    print(f"wrote {args.output} ({args.duration_ms:g} ms, {sr} Hz)")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "run": _cmd_run,
        "validate": _cmd_validate,
        "example": _cmd_example,
        "mock-server": _cmd_mock_server,
        "synth": _cmd_synth,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
