"""How a scene runs: qualifying or rounds, derived from the tournament phase.

A scene's ``flow`` is one of

- ``phase``: follows the tournament. Before FIX (the bracket still fills
  live from the highscore) it is qualifying, after FIX it plays rounds;
- ``quali``: always qualifying (every slot shows the current game of its
  station, no rounds, no hearts);
- ``rounds``: always rounds (one game per slot and round).

Whether the next round starts by itself is one global setting
(``scenes.next_round``: ``manual`` or ``auto``) for all scenes in rounds.
"""

from __future__ import annotations

from typing import Literal

Flow = Literal["phase", "quali", "rounds"]
NextRound = Literal["manual", "auto"]
Effective = Literal["quali", "rounds"]

FLOWS: tuple[Flow, ...] = ("phase", "quali", "rounds")
NEXT_ROUNDS: tuple[NextRound, ...] = ("manual", "auto")
DEFAULT_FLOW: Flow = "phase"
DEFAULT_NEXT_ROUND: NextRound = "manual"


def effective(flow: str, seeded: bool) -> Effective:
    """What a scene does right now."""
    if flow == "quali" or (flow == "phase" and not seeded):
        return "quali"
    return "rounds"


def auto_round(flow: str, seeded: bool, next_round: str) -> bool:
    """Does the next round start by itself (everyone finished, someone starts again)?"""
    return effective(flow, seeded) == "rounds" and next_round == "auto"
