"""Attract-mode demo detection on the host (core/demo.py)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from nestris_ltm.core import demo
from nestris_ltm.core.ngf import iter_frames

DATA = Path(__file__).parent / "data" / "demo"
CORE_FINGERPRINTS = (
    Path(__file__).parents[2] / "nestris-core/crates/nestris-engine/assets/demo/fingerprints.json"
)


def samples(name: str) -> list[demo.Sample]:
    frames = iter_frames((DATA / name).read_bytes())
    return [demo.Sample(f.ctime_ms, f.score, f.lines, f.level) for f in frames]


@pytest.mark.parametrize("name", ["game-1078.ngf.gz", "game-2524.ngf.gz"])
def test_recorded_demo_is_detected(name: str) -> None:
    match = demo.classify_frames(samples(name), start_level=0, end_reason="reset")
    assert match is not None
    assert match.fingerprint == "nes-ntsc-event"
    assert match.steps >= 30
    assert match.reason.startswith("frames:nes-ntsc-event:")


@pytest.mark.parametrize("cut_ms", [6_000, 12_000, 30_000])
def test_aborted_demo_is_detected(cut_ms: int) -> None:
    s = [x for x in samples("game-1078.ngf.gz") if x.t_ms <= cut_ms]
    assert demo.classify_frames(s, start_level=0, end_reason="reset") is not None


def test_very_short_demo_stays_a_game() -> None:
    # Two seconds: only the start value, no evidence.
    s = [x for x in samples("game-1078.ngf.gz") if x.t_ms <= 3_000]
    assert demo.classify_frames(s, start_level=0, end_reason="reset") is None


def test_game_over_is_never_a_demo() -> None:
    assert (
        demo.classify_frames(samples("game-1078.ngf.gz"), start_level=0, end_reason="game_over")
        is None
    )


def test_other_start_level_is_never_a_demo() -> None:
    assert (
        demo.classify_frames(samples("game-1078.ngf.gz"), start_level=18, end_reason="reset")
        is None
    )


def test_diverging_score_is_real() -> None:
    s = samples("game-1078.ngf.gz")
    # The player scored 7 instead of 11 with the first piece.
    s = [replace(x, score=7) if x.score == 11 else x for x in s]
    assert demo.classify_frames(s, start_level=0, end_reason="reset") is None


def test_real_level_zero_game_is_real() -> None:
    # A level-0 game: soft drops give other points than the demo.
    s, t = [], 0
    for score, lines in [(0, 0), (6, 0), (18, 0), (25, 0), (65, 1), (80, 1), (92, 1), (140, 2)]:
        for _ in range(60):
            s.append(demo.Sample(t, score, lines, 0))
            t += 17
    assert demo.classify_frames(s, start_level=0, end_reason="reset") is None


def test_glitches_are_tolerated() -> None:
    s = samples("game-2524.ngf.gz")
    # One-frame misreads every 50 frames.
    s = [replace(x, score=(x.score or 0) + 8) if i % 50 == 25 else x for i, x in enumerate(s)]
    assert demo.classify_frames(s, start_level=0, end_reason="reset") is not None


def test_end_values() -> None:
    full = demo.classify_end_values(
        score=2185, lines=13, start_level=0, end_level=1, end_reason="reset"
    )
    assert full is not None and full.method == "end_values"
    # Early steps are too common to judge without frames.
    assert (
        demo.classify_end_values(score=45, lines=0, start_level=0, end_level=0, end_reason="reset")
        is None
    )
    assert (
        demo.classify_end_values(
            score=2185, lines=13, start_level=0, end_level=1, end_reason="game_over"
        )
        is None
    )


@pytest.mark.skipif(not CORE_FINGERPRINTS.is_file(), reason="nestris-core checkout not found")
def test_fingerprints_match_nestris_core() -> None:
    core = json.loads(CORE_FINGERPRINTS.read_text(encoding="utf-8"))
    ours = demo.builtin()
    assert [f["id"] for f in core] == [f.id for f in ours]
    for c, o in zip(core, ours, strict=True):
        assert [(s["score"], s["lines"], s["level"], s.get("next")) for s in c["steps"]] == [
            (s.score, s.lines, s.level, s.next) for s in o.steps
        ]
