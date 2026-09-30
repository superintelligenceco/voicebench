from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"

SR = 16000


@pytest.fixture
def sr() -> int:
    return SR


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES
