"""MkDocs hook that renders the `voicebench` help text into docs/reference/cli.md."""

from __future__ import annotations

import argparse
import os
from typing import Any

MARKER = "<!-- cli-reference -->"


def _render() -> str:
    os.environ.setdefault("COLUMNS", "100")
    from voicebench.cli import build_parser

    parser = build_parser()
    parts = ["## voicebench", "", "```text", parser.format_help().rstrip(), "```", ""]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                parts += [f"## voicebench {name}", "", "```text", sub.format_help().rstrip()]
                parts += ["```", ""]
    return "\n".join(parts)


def on_page_markdown(markdown: str, **kwargs: Any) -> str:
    if MARKER in markdown:
        return markdown.replace(MARKER, _render())
    return markdown
