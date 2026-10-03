from __future__ import annotations

import pytest

from nestris_ltm.core import scoring


@pytest.mark.parametrize(
    ("start", "first"),
    [(0, 10), (9, 100), (12, 100), (15, 100), (16, 110), (18, 130), (19, 140)],
)
def test_transition_lines(start: int, first: int) -> None:
    assert scoring.transition_lines(start) == first


@pytest.mark.parametrize("start", [15, 16, 17, 18, 19])
def test_level_29_at_line_230(start: int) -> None:
    assert scoring.lines_to_level(start, 29) == 230
    assert scoring.level_at(start, 229) == 28
    assert scoring.level_at(start, 230) == 29


def test_tetris_math() -> None:
    assert scoring.tetris_value(18) == 22800
    assert scoring.tetrises_behind(50_000, 19) == pytest.approx(2.083, abs=0.001)
    assert scoring.tetrises_behind(-5, 19) == 0
    assert scoring.tetrises_needed(24_000, 19) == 2  # 1 tetris = 24 000, need to exceed
    assert scoring.tetrises_needed(23_999, 19) == 1


def test_projection() -> None:
    # Past level 29 nothing is projected.
    assert scoring.project_score(900_000, 240, 18, 0.6) == 900_000
    low = scoring.project_score(100_000, 60, 18, 0.2)
    high = scoring.project_score(100_000, 60, 18, 0.8)
    assert 100_000 < low < high
    # All tetrises from 18 to level 29: 130 x 300 x 19 + 3000 x (20 + ... + 29) = 1 476 000.
    assert scoring.project_score(0, 12, 18, 1.0) == 1_476_000 - 12 * 300 * 19
    # Too few lines for a meaningful rate: the default rate is used.
    assert scoring.project_score(0, 4, 18, 1.0) == scoring.project_score(0, 4, 18, 0.4)
