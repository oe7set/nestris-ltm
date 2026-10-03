"""Versus rounds: binding games to slots, freezing results, deciding outcomes.

A scene has numbered slots, each watching one station. In a round every slot
plays one game:

1. The first game seen on a slot's station is bound to the slot.
2. When that game ends its score/lines/level are frozen. The overlay keeps
   showing them, so the difference to the players still playing stays right.
3. Further games on a finished slot are ignored until the next round
   (optionally a new round starts automatically once every slot finished).

Modes decide who advances. ``K`` players advance (top2: 2, winner_only: 1,
worst_out: all but one); an outcome is set as soon as it is *certain*:

- a finished player is **advanced** when fewer than ``K`` players can still
  end above them (finished players with a higher score + everybody still
  playing, since a running score can always grow);
- a finished player is **eliminated** when at least ``K`` players are
  certainly above: finished players with a higher score, or running players
  already past them (a running score never goes down);
- a running player is **advanced** early when fewer than ``K`` players can
  end above them even if they stop now; they are never eliminated early.

Ties never decide early; they are resolved by slot order once everybody
finished.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from nestris_ltm.core import scoring

Mode = Literal["none", "top2_advance", "worst_out", "winner_only"]
Outcome = Literal["advanced", "eliminated", "winner"]
SlotStatus = Literal["empty", "waiting", "playing", "finished"]


@dataclass
class Entry:
    """One slot in the current round."""

    slot: int
    game_id: str | None = None  # the station's game id (external id)
    player_name: str | None = None
    score: int | None = None
    lines: int | None = None
    level: int | None = None
    start_level: int | None = None
    finished_at: datetime | None = None
    outcome: Outcome | None = None

    @property
    def finished(self) -> bool:
        return self.finished_at is not None


@dataclass
class RoundState:
    number: int = 1
    entries: dict[int, Entry] = field(default_factory=dict)

    def entry(self, slot: int) -> Entry:
        if slot not in self.entries:
            self.entries[slot] = Entry(slot=slot)
        return self.entries[slot]

    def accepts(self, slot: int, game_id: str) -> bool:
        """Is ``game_id`` the game this slot plays (binding it if free)?"""
        e = self.entry(slot)
        if e.game_id == game_id:
            return True
        if e.finished:
            return False  # one game per slot and round
        # Free slot, or the bound game never finished (station restarted).
        e.game_id = game_id
        e.score = e.lines = e.level = None
        e.start_level = None
        return True

    def finish(
        self,
        slot: int,
        game_id: str,
        *,
        score: int | None,
        lines: int | None,
        level: int | None,
        start_level: int | None,
        at: datetime | None = None,
    ) -> bool:
        """Freeze the result of the bound game. Returns True if it was frozen."""
        e = self.entry(slot)
        if e.game_id != game_id or e.finished:
            return False
        e.score = score if score is not None else e.score
        e.lines = lines if lines is not None else e.lines
        e.level = level if level is not None else e.level
        e.start_level = start_level if start_level is not None else e.start_level
        e.finished_at = at or datetime.now(UTC)
        return True

    def all_finished(self, slots: list[int]) -> bool:
        return bool(slots) and all(self.entry(s).finished for s in slots)

    def unfreeze(self, slot: int) -> None:
        """Let a slot play again in this round (e.g. a game bound by mistake)."""
        self.entries[slot] = Entry(slot=slot)


def advancing_count(mode: Mode, players: int) -> int | None:
    if mode == "top2_advance":
        return min(2, players)
    if mode == "winner_only":
        return 1
    if mode == "worst_out":
        return max(players - 1, 0)
    return None


@dataclass(frozen=True, slots=True)
class Standing:
    slot: int
    score: int
    finished: bool


def decide_outcomes(mode: Mode, standings: list[Standing]) -> dict[int, Outcome]:
    """Outcomes that are already certain (see module docstring)."""
    k = advancing_count(mode, len(standings))
    if k is None or not standings:
        return {}
    winner_label: Outcome = "winner" if k == 1 else "advanced"
    outcomes: dict[int, Outcome] = {}
    for s in standings:
        others = [o for o in standings if o.slot != s.slot]
        # Who could still end at or above s ...
        could_be_above = sum(1 for o in others if not o.finished or o.score >= s.score)
        # ... and who is certainly above s already.
        surely_above = sum(1 for o in others if o.score > s.score)
        if could_be_above < k:
            outcomes[s.slot] = winner_label
        elif s.finished and surely_above >= k:
            outcomes[s.slot] = "eliminated"
    if all(s.finished for s in standings):
        # Everybody done: rank strictly (ties broken by slot order).
        ranked = sorted(standings, key=lambda s: (-s.score, s.slot))
        for i, s in enumerate(ranked):
            outcomes[s.slot] = winner_label if i < k else "eliminated"
    return outcomes


def score_to_beat(mode: Mode, standings: list[Standing], slot: int) -> int | None:
    """Score a running player must exceed to be safe (``K``-th best finished)."""
    k = advancing_count(mode, len(standings))
    if not k:  # no mode, or nobody playing yet
        return None
    finished = sorted((o.score for o in standings if o.slot != slot and o.finished), reverse=True)
    if len(finished) < k:
        return None
    return finished[k - 1]


@dataclass(frozen=True, slots=True)
class Gap:
    """How far a player is from a reference score."""

    points: int  # positive = behind
    tetrises: float  # at the player's level
    tetrises_needed: int  # whole tetrises to strictly pass (0 when ahead)


def gap(score: int, reference: int, level: int | None) -> Gap:
    deficit = reference - score
    return Gap(
        points=deficit,
        tetrises=round(scoring.tetrises_behind(deficit, level), 2),
        tetrises_needed=scoring.tetrises_needed(deficit, level) if deficit >= 0 else 0,
    )
