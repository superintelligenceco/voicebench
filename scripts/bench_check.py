"""Run the benchmarks and fail when one is more than 2x slower than the baseline.

Usage:
    python scripts/bench_check.py            # compare against benchmarks/baseline.json
    python scripts/bench_check.py --update   # rewrite the baseline from this machine

The baseline stores the median time of each benchmark in seconds, measured on a
GitHub-hosted ubuntu-latest runner, so compare on similar hardware.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "benchmarks" / "baseline.json"
MAX_RATIO = 2.0


def run_benchmarks() -> dict[str, float]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "bench.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/benchmarks",
                "--benchmark-enable",
                "--benchmark-only",
                f"--benchmark-json={out}",
                "-q",
            ],
            cwd=ROOT,
            check=True,
        )
        data = json.loads(out.read_text())
    return {b["name"]: b["stats"]["median"] for b in data["benchmarks"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args()

    current = run_benchmarks()
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"wrote {BASELINE.relative_to(ROOT)}")
        return 0

    baseline = json.loads(BASELINE.read_text())
    lines = [
        "| Benchmark | Baseline | Current | Ratio | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    failed = False
    for name, median in sorted(current.items()):
        base = baseline.get(name)
        if base is None:
            lines.append(f"| `{name}` | - | {median * 1000:.2f} ms | - | new |")
            continue
        ratio = median / base
        ok = ratio <= MAX_RATIO
        failed |= not ok
        lines.append(
            f"| `{name}` | {base * 1000:.2f} ms | {median * 1000:.2f} ms | {ratio:.2f}x | "
            f"{'pass' if ok else 'FAIL'} |"
        )
    table = "\n".join(lines)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Benchmarks (fail above {MAX_RATIO:g}x the baseline)\n\n{table}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
