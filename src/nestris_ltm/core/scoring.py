"""NES Tetris scoring math for the versus overlays.

- Line clears score 40/100/300/1200 x (level + 1).
- The first level-up happens after ``transition_lines(start)`` lines, then
  every 10 lines (NTSC rules), so start levels 15..19 reach level 29 at
  line 230.
- *Tetrises behind*: a deficit expressed in tetrises at the trailing
  player's current level, the usual broadcast metric (CTWC/NestrisChamps).
- *Pace*: projected score when reaching level 29, assuming the player keeps
  their tetris rate (same idea as nestris-core's ``pace_score``).
"""

from __future__ import annotations

import math

CLEAR_POINTS = {1: 40, 2: 100, 3: 300, 4: 1200}
KILLSCREEN_LEVEL = 29
DEFAULT_TETRIS_RATE = 0.4
# Average points per line of non-tetris clears (mix of singles/doubles/triples).
NON_TETRIS_POINTS_PER_LINE = (40 / 1 + 100 / 2 + 300 / 3) / 3


def tetris_value(level: int) -> int:
    return CLEAR_POINTS[4] * (max(level, 0) + 1)


def transition_lines(start_level: int) -> int:
    """Lines needed for the first level-up from ``start_level`` (NTSC)."""
    start_level = max(start_level, 0)
    return min(start_level * 10 + 10, max(100, start_level * 10 - 50))


def level_at(start_level: int, lines: int) -> int:
    """Level after ``lines`` cleared lines when starting at ``start_level``."""
    first = transition_lines(start_level)
    if lines < first:
        return start_level
    return start_level + 1 + (lines - first) // 10


def lines_to_level(start_level: int, target_level: int) -> int:
    """Total lines at which ``target_level`` is reached."""
    if target_level <= start_level:
        return 0
    return transition_lines(start_level) + 10 * (target_level - start_level - 1)


def tetrises_behind(deficit: int, level: int | None) -> float:
    """``deficit`` points as tetrises at ``level`` (0 when not behind)."""
    if deficit <= 0:
        return 0.0
    return deficit / tetris_value(level or 0)


def tetrises_needed(deficit: int, level: int | None) -> int:
    """Whole tetrises needed to strictly overtake a ``deficit`` (ignores level-ups)."""
    if deficit < 0:
        return 0
    return math.floor(deficit / tetris_value(level or 0)) + 1


def project_score(
    score: int,
    lines: int,
    start_level: int | None,
    tetris_rate: float | None = None,
    *,
    target_level: int = KILLSCREEN_LEVEL,
) -> int:
    """Projected score at ``target_level`` keeping the current tetris rate."""
    start = start_level if start_level is not None else 18
    end_lines = lines_to_level(start, target_level)
    if lines >= end_lines:
        return score
    rate = DEFAULT_TETRIS_RATE if tetris_rate is None or lines < 12 else tetris_rate
    rate = min(max(rate, 0.0), 1.0)
    per_line = rate * CLEAR_POINTS[4] / 4 + (1 - rate) * NON_TETRIS_POINTS_PER_LINE
    total = float(score)
    for line in range(lines, end_lines):
        total += per_line * (level_at(start, line) + 1)
    return round(total)
