"""A scene's flow: qualifying before FIX, rounds after (core/scene_flow.py)."""

from __future__ import annotations

import pytest

from nestris_ltm.core import scene_flow


@pytest.mark.parametrize(
    ("flow", "seeded", "expected"),
    [
        ("phase", False, "quali"),
        ("phase", True, "rounds"),
        ("quali", False, "quali"),
        ("quali", True, "quali"),
        ("rounds", False, "rounds"),
        ("rounds", True, "rounds"),
    ],
)
def test_effective_flow(flow: str, seeded: bool, expected: str) -> None:
    assert scene_flow.effective(flow, seeded) == expected


def test_auto_round_only_in_rounds_and_when_switched_on() -> None:
    assert scene_flow.auto_round("phase", True, "auto")
    assert not scene_flow.auto_round("phase", True, "manual")
    assert not scene_flow.auto_round("phase", False, "auto")  # qualifying: no rounds
    assert not scene_flow.auto_round("quali", True, "auto")
    assert scene_flow.auto_round("rounds", False, "auto")
