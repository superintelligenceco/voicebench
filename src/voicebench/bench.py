"""High-level API: run a scenario one or more times and build the report."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from voicebench.adapters import create_adapter
from voicebench.metrics import (
    AssertionResult,
    SessionMetrics,
    analyze,
    check_assertions,
    summarize,
)
from voicebench.report import build_report
from voicebench.runner import SessionRecord, run
from voicebench.scenario import Scenario


@dataclass
class BenchResult:
    records: list[SessionRecord]
    sessions: list[SessionMetrics]
    summary: dict[str, Any]
    assertions: list[AssertionResult]
    report: dict[str, Any]

    @property
    def passed(self) -> bool:
        return all(a.passed for a in self.assertions)


async def run_benchmark(
    scenario: Scenario,
    adapter: str | None = None,
    options: dict[str, Any] | None = None,
    repeat: int = 1,
    realtime: bool = False,
) -> BenchResult:
    """Run ``scenario`` ``repeat`` times, each with a fresh adapter instance.

    ``adapter`` and ``options`` override the scenario's ``adapter`` block. When
    ``adapter`` names a different type than the scenario, the scenario's
    options are not used.
    """
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    name = adapter or scenario.adapter.type
    merged: dict[str, Any] = dict(scenario.adapter.options) if name == scenario.adapter.type else {}
    merged.update(options or {})

    records: list[SessionRecord] = []
    for _ in range(repeat):
        instance = create_adapter(name, merged)
        records.append(await run(scenario, instance, realtime=realtime))
    sessions = [analyze(r) for r in records]
    summary = summarize(sessions)
    assertions = check_assertions(summary, scenario.assertions)
    report = build_report(records, sessions, summary, assertions)
    return BenchResult(records, sessions, summary, assertions, report)
