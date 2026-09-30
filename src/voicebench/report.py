"""Report writers: JSON, Markdown, HTML, and a plain-text console summary."""

from __future__ import annotations

import html
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from voicebench import __version__
from voicebench.metrics import AssertionResult, SessionMetrics
from voicebench.runner import SessionRecord

SCHEMA_VERSION = 1


def build_report(
    records: list[SessionRecord],
    sessions: list[SessionMetrics],
    summary: dict[str, Any],
    assertions: list[AssertionResult],
) -> dict[str, Any]:
    """Assemble the JSON-serializable report."""
    sc = records[0].scenario
    return {
        "schema_version": SCHEMA_VERSION,
        "voicebench_version": __version__,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "scenario": {
            "name": sc.name,
            "description": sc.description,
            "sample_rate": sc.sample_rate,
            "frame_ms": sc.frame_ms,
            "turns": len(sc.turns),
        },
        "adapter": records[0].adapter,
        "clock": records[0].clock,
        "summary": summary,
        "assertions": [
            {"key": a.key, "limit": a.limit, "actual": a.actual, "passed": a.passed}
            for a in assertions
        ],
        "passed": all(a.passed for a in assertions),
        "sessions": [s.to_dict() for s in sessions],
    }


def write_json(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".") if abs(value) < 10 else f"{value:.0f}"
        return f"{text}{unit}"
    return f"{value}{unit}"


def summary_rows(summary: dict[str, Any]) -> list[tuple[str, str]]:
    """Human-readable (metric, value) pairs for the summary table."""
    lat = summary["response_latency_ms"]
    ttfa = summary["ttfa_ms"]
    stop = summary["barge_in_stop_ms"]
    rate = summary["barge_in_success_rate"]
    rows = [
        ("Turns passed", f"{summary['turns_passed']}/{summary['turns']}"),
        ("Response latency p50 / p90", f"{_fmt(lat['p50'], ' ms')} / {_fmt(lat['p90'], ' ms')}"),
        (
            "Time to first audio p50 / p90",
            f"{_fmt(ttfa['p50'], ' ms')} / {_fmt(ttfa['p90'], ' ms')}",
        ),
        ("Missed responses", str(summary["missed_responses"])),
        (
            "Barge-in success",
            "-" if rate is None else f"{rate * 100:.0f}% of {summary['barge_in_turns']}",
        ),
        (
            "Barge-in stop time p50 / max",
            f"{_fmt(stop['p50'], ' ms')} / {_fmt(stop['max'], ' ms')}",
        ),
        ("False barge-ins", f"{summary['false_barge_ins']} of {summary['noise_turns']}"),
        ("Spurious responses", str(summary["spurious_responses"])),
        ("Agent talk-over", _fmt(summary["talk_over_ms"], " ms")),
        ("Mean WER", _fmt(summary["mean_wer"])),
    ]
    return rows


def turn_rows(session: SessionMetrics) -> list[list[str]]:
    rows = []
    for t in session.turns:
        rows.append(
            [
                t.id,
                t.expect,
                _fmt(t.response_latency_ms, " ms"),
                _fmt(t.ttfa_ms, " ms"),
                _fmt(t.stop_latency_ms, " ms"),
                _fmt(t.wer),
                "pass" if t.passed else "FAIL",
            ]
        )
    return rows


TURN_HEADER = ["Turn", "Expect", "Response", "TTFA", "Stop", "WER", "Result"]


def render_console(report: dict[str, Any], sessions: list[SessionMetrics]) -> str:
    """Plain-text summary for the terminal."""
    sc = report["scenario"]
    lines = [
        f"voicebench {report['voicebench_version']}  scenario={sc['name']}  "
        f"adapter={report['adapter']['type']}  clock={report['clock']}  "
        f"sessions={report['summary']['sessions']}",
        "",
    ]
    if len(sessions) == 1:
        lines += _text_table(TURN_HEADER, turn_rows(sessions[0]))
        lines.append("")
    rows = summary_rows(report["summary"])
    width = max(len(k) for k, _ in rows)
    lines += [f"{k.ljust(width)}  {v}" for k, v in rows]
    if report["assertions"]:
        lines.append("")
        for a in report["assertions"]:
            status = "PASS" if a["passed"] else "FAIL"
            op = ">=" if a["key"].startswith("min_") else "<="
            lines.append(
                f"{status}  {a['key']} {op} {_fmt(a['limit'])} (actual {_fmt(a['actual'])})"
            )
    notes = [(t.id, n) for s in sessions for t in s.turns for n in t.notes]
    if notes:
        lines.append("")
        lines += [f"note: {tid}: {n}" for tid, n in notes[:10]]
    return "\n".join(lines)


def _text_table(header: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]

    def line(cells: list[str]) -> str:
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths, strict=True)).rstrip()

    return [line(header), line(["-" * w for w in widths]), *[line(r) for r in rows]]


def render_markdown(report: dict[str, Any], sessions: list[SessionMetrics]) -> str:
    sc = report["scenario"]
    out = [
        f"# voicebench report: {sc['name']}",
        "",
        f"- Adapter: `{report['adapter']['type']}`",
        f"- Clock: {report['clock']}",
        f"- Sessions: {report['summary']['sessions']}",
        f"- voicebench {report['voicebench_version']}, created {report['created_at']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    out += [f"| {k} | {v} |" for k, v in summary_rows(report["summary"])]
    if report["assertions"]:
        out += [
            "",
            "## Assertions",
            "",
            "| Check | Limit | Actual | Result |",
            "| --- | --- | --- | --- |",
        ]
        out += [
            f"| `{a['key']}` | {_fmt(a['limit'])} | {_fmt(a['actual'])} | "
            f"{'pass' if a['passed'] else 'FAIL'} |"
            for a in report["assertions"]
        ]
    for n, s in enumerate(sessions, start=1):
        out += ["", f"## Session {n} turns", ""]
        out.append("| " + " | ".join(TURN_HEADER) + " |")
        out.append("|" + " --- |" * len(TURN_HEADER))
        out += ["| " + " | ".join(r) + " |" for r in turn_rows(s)]
        notes = [f"- `{t.id}`: {note}" for t in s.turns for note in t.notes]
        if notes:
            out += ["", *notes]
    return "\n".join(out) + "\n"


def _timeline_svg(session: SessionMetrics, width: int = 960) -> str:
    dur = max(session.duration_s, 1e-6)
    scale = (width - 80) / dur
    rows = [
        ("user", session.user_segments, "#2f6fdf"),
        ("agent", session.agent_segments, "#d9822b"),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="92" '
        'role="img" aria-label="Speech timeline">'
    ]
    for r, (label, segs, color) in enumerate(rows):
        y = 10 + r * 30
        parts.append(f'<text x="0" y="{y + 15}" font-size="12">{label}</text>')
        parts.append(f'<rect x="60" y="{y}" width="{width - 80}" height="20" fill="#f1f1f1"/>')
        for seg in segs:
            x = 60 + seg.start * scale
            w = max(1.0, seg.duration * scale)
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="20" fill="{color}">'
                f"<title>{label} {seg.start:.2f}-{seg.end:.2f} s</title></rect>"
            )
    for t in session.turns:
        x = 60 + t.start_s * scale
        parts.append(
            f'<line x1="{x:.1f}" y1="4" x2="{x:.1f}" y2="72" stroke="#888" stroke-dasharray="2,2"/>'
        )
        parts.append(f'<text x="{x + 2:.1f}" y="86" font-size="10">{html.escape(t.id)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def render_html(report: dict[str, Any], sessions: list[SessionMetrics]) -> str:
    sc = report["scenario"]
    esc = html.escape

    def table(header: list[str], rows: list[list[str]]) -> str:
        head = "".join(f"<th>{esc(h)}</th>" for h in header)
        body = "".join(
            "<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    sections = [
        f"<h1>voicebench report: {esc(sc['name'])}</h1>",
        f"<p>Adapter <code>{esc(report['adapter']['type'])}</code>, "
        f"clock {esc(report['clock'])}, {report['summary']['sessions']} session(s), "
        f"voicebench {esc(report['voicebench_version'])}, created {esc(report['created_at'])}.</p>",
        "<h2>Summary</h2>",
        table(["Metric", "Value"], [list(r) for r in summary_rows(report["summary"])]),
    ]
    if report["assertions"]:
        sections.append("<h2>Assertions</h2>")
        sections.append(
            table(
                ["Check", "Limit", "Actual", "Result"],
                [
                    [
                        a["key"],
                        _fmt(a["limit"]),
                        _fmt(a["actual"]),
                        "pass" if a["passed"] else "FAIL",
                    ]
                    for a in report["assertions"]
                ],
            )
        )
    for n, s in enumerate(sessions, start=1):
        sections.append(f"<h2>Session {n}</h2>")
        sections.append(_timeline_svg(s))
        sections.append(table(TURN_HEADER, turn_rows(s)))
        notes = [
            f"<li><code>{esc(t.id)}</code>: {esc(note)}</li>" for t in s.turns for note in t.notes
        ]
        if notes:
            sections.append("<ul>" + "".join(notes) + "</ul>")
    style = (
        "body{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;"
        "color:#1b1b1b}table{border-collapse:collapse;margin:1rem 0}td,th{border:1px solid #ccc;"
        "padding:4px 10px;text-align:left}th{background:#f5f5f5}"
        "code{background:#f3f3f3;padding:1px 4px}"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>voicebench: {esc(sc['name'])}</title><style>{style}</style></head><body>"
        + "".join(sections)
        + "</body></html>\n"
    )
