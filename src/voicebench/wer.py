"""Word error rate."""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s']", flags=re.UNICODE)


def normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation (keeping apostrophes), and split into words."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = _PUNCT.sub(" ", text)
    return [w.strip("'") for w in text.split() if w.strip("'")]


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein distance between two word sequences."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Return (substitutions + deletions + insertions) / reference words.

    An empty reference scores 0.0 against an empty hypothesis and 1.0 otherwise.
    """
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)
