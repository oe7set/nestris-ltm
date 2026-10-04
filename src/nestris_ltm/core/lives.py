"""Hearts (lives) of a 1-vs-1 bracket match.

Once the bracket is fixed, every real match is played as a series: both
players start with ``max_lives`` hearts (tournament default 2, per match
adjustable), the loser of a round loses one, and a player at zero hearts has
lost the match.

The state is never stored as numbers: it is folded from an event log
(``lose`` / ``gain`` / ``set``), so undo, audit and restarts need nothing
extra. Pure functions, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Kind = Literal["lose", "gain", "set"]
Source = Literal["admin", "api", "auto"]
KINDS: tuple[str, ...] = ("lose", "gain", "set")
SOURCES: tuple[str, ...] = ("admin", "api", "auto")
MAX_LIVES = 9


@dataclass(frozen=True, slots=True)
class LifeEvent:
    player_id: int
    kind: Kind
    value: int | None = None  # only for "set"
    undone: bool = False


def clamp(value: int, max_lives: int) -> int:
    return max(0, min(max_lives, value))


def fold(events: Iterable[LifeEvent], max_lives: int, players: Iterable[int]) -> dict[int, int]:
    """Hearts per player after ``events`` (in order); undone events are skipped.

    Events of players outside ``players`` (e.g. from before a reseed) are
    ignored. Every step is clamped to ``0..max_lives``.
    """
    lives = dict.fromkeys(players, max_lives)
    for e in events:
        if e.undone or e.player_id not in lives:
            continue
        current = lives[e.player_id]
        if e.kind == "lose":
            current -= 1
        elif e.kind == "gain":
            current += 1
        elif e.kind == "set" and e.value is not None:
            current = e.value
        lives[e.player_id] = clamp(current, max_lives)
    return lives


def loser(lives: dict[int, int]) -> int | None:
    """The player who lost the match (zero hearts), if exactly one has none."""
    out = [p for p, n in lives.items() if n <= 0]
    return out[0] if len(out) == 1 else None


def loser_of_round(score_a: int | None, score_b: int | None) -> Literal[0, 1] | None:
    """Side (0 = a, 1 = b) that lost a round; ``None`` on a tie or a missing score."""
    if score_a is None or score_b is None or score_a == score_b:
        return None
    return 0 if score_a < score_b else 1


def cycle(current: int, max_lives: int) -> int:
    """Next value of a press-to-cycle button: max → … → 1 → 0 → max."""
    return max_lives if current <= 0 else current - 1
