from __future__ import annotations

import pytest

from voicebench.wer import edit_distance, normalize, wer


def test_normalize_strips_case_and_punctuation() -> None:
    assert normalize("Hi, there! It's   FINE.") == ["hi", "there", "it's", "fine"]


def test_exact_match_is_zero() -> None:
    assert wer("Yes, that works.", "yes that works") == 0.0


@pytest.mark.parametrize(
    ("ref", "hyp", "expected"),
    [
        ("a b c d", "a x c d", 0.25),  # substitution
        ("a b c d", "a c d", 0.25),  # deletion
        ("a b c d", "a b b c d", 0.25),  # insertion
        ("a b", "", 1.0),
        ("a", "b c d", 3.0),
    ],
)
def test_wer_cases(ref: str, hyp: str, expected: float) -> None:
    assert wer(ref, hyp) == pytest.approx(expected)


def test_empty_reference() -> None:
    assert wer("", "") == 0.0
    assert wer("", "noise") == 1.0


def test_edit_distance() -> None:
    assert edit_distance(list("kitten"), list("sitting")) == 3
