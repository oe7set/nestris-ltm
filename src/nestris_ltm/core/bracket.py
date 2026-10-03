"""Single-elimination tournament bracket (ported from TournamentHigscore).

The bracket is a pure function of ``(seeds, active_count, manual_winners,
disabled)``; see :func:`derive_bracket`. :class:`BracketState` holds that
authoritative state and implements the admin operations without any I/O, so
``services/tournament.py`` only adds persistence and broadcasting.

Ported verbatim from ``TournamentHigscore/src/models/{player,bracket}.py`` and
``src/services/bracket_manager.py`` (derivation); only the persistence moved.
``user_id`` is NestrisLTM's ``players.id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

# --- Original module notes ---------------------------------------------------
# Bracket data structures.
#
# The bracket is a single single-elimination tree whose **capacity** (number of
# seed slots) is the next power of two ≥ the configured tournament size N, e.g.
#
#     N=12 -> capacity 16: Round of 16 (8) -> QF (4) -> SF (2) -> Final (1)
#     N=4  -> capacity 4 : Semifinals (2) -> Final (1)
#     N=64 -> capacity 64: 6 rounds
#
# plus a separate third-place match fed by the two semifinal losers (only when
# capacity ≥ 4). Seeds 1..N actively compete; positions N+1..capacity are empty
# and become byes for the top seeds.
#
# These are *output* models: the authoritative state is ``(seeds, active_count,
# manual_winners)`` held by :class:`~src.services.bracket_manager.BracketManager`,
# and a fully resolved :class:`Bracket` is *derived* from it on every change. The
# view renders this derived structure directly.
#
# Bracket state management and derivation.
#
# Design principle: the bracket displayed to clients is a **pure function** of
# three inputs —
#
#     * ``seeds``           : the frozen snapshot of up to 16 players (or ``None``)
#     * ``active_count`` (N): how many of the top seeds actively compete
#     * ``manual_winners``  : ``{match_id: user_id}`` winners the admin has set
#
# On every change we re-derive the whole bracket from these inputs rather than
# mutating a bracket object in place. This eliminates state drift: downstream
# matches whose participants change (because an upstream winner changed) are
# recomputed automatically, and any manual winner that no longer refers to a
# player present in its match is simply ignored. That makes "set winner",
# "correct winner" and "clear downstream" fall out for free.
#
# The novel part is **bye propagation**. With an active count N < 16 the seeds
# above N are treated as automatic losses, so their opponents advance without
# playing (a *bye*). Byes propagate forward recursively: a player can advance
# through several rounds of empty opposition. The tricky bit is distinguishing an
# empty slot that is *permanently* empty (its feeder match was DEAD — both
# participants auto-lost) from one that is merely *pending* (its feeder is a real,
# not-yet-decided match). Only the former grants the opponent a bye; the latter
# must block, so nobody advances past a real match that has not been played.


class SlotStatus(StrEnum):
    """Status of a player occupying a bracket slot.

    - ``ACTIVE``: the seed is within the active count and a real player exists.
      The player can win matches.
    - ``AUTO_LOST``: the seed is outside the active count (seed > N) or no player
      was captured for that seed when the bracket was frozen. Rendered greyed-out;
      treated as an automatic loss so their opponent advances by a bye.
    """

    ACTIVE = "ACTIVE"
    AUTO_LOST = "AUTO_LOST"


class Player(BaseModel):
    """A single competitor.

    For the live leaderboard, ``seed`` and ``status`` are unset / ignored. When a
    player occupies a frozen bracket slot, ``seed`` (1..16) and ``status`` describe
    their position and whether they actively compete.
    """

    user_id: int
    nickname: str
    highscore: int = 0

    # Extra live-game stats (best game of the player). Optional so the same model
    # can represent a bare bracket seed snapshot too.
    level: int | None = None
    lines: int | None = None
    tetris_rate: float | None = None

    # Bracket-only fields (populated when the player sits in a bracket slot).
    seed: int | None = None
    status: SlotStatus = SlotStatus.ACTIVE


class LeaderboardEntry(BaseModel):
    """One row of the live highscore list (left column)."""

    rank: int
    user_id: int
    nickname: str
    score: int
    level: int | None = None
    lines: int | None = None
    tetris_rate: float | None = None
    # True when this player's shown best game is an in-progress run (playing live
    # and already beating their previous best). Drives the live indicator dot.
    is_live: bool = False
    # NestrisLTM: the game behind this entry (replays from the terminal).
    game_id: int | None = None


class Stats(BaseModel):
    """Aggregate tournament statistics (left column)."""

    total_games: int = 0
    active_players: int = 0
    total_score: int = 0
    avg_score: float = 0.0
    highest_score: int = 0
    highest_level: int = 0


class ScoreTrain(BaseModel):
    """Milestone progress of the cumulative total score (left column)."""

    total_score: int = 0
    current_milestone: int = 0
    next_milestone: int | None = None
    # Progress 0.0..1.0 within the current milestone segment.
    progress: float = 0.0
    milestones: list[int] = []


# Smallest and largest tournament sizes the app supports.
MIN_SIZE = 2
MAX_SIZE = 64

# Stable match id for the third-place match.
THIRD_PLACE_ID = "third_place"


def next_pow2(n: int) -> int:
    """Smallest power of two ≥ ``n`` (with a floor of 2)."""
    n = max(MIN_SIZE, int(n))
    return 1 << (n - 1).bit_length()


def num_rounds(capacity: int) -> int:
    """Number of rounds for a power-of-two ``capacity`` (e.g. 16 -> 4)."""
    return capacity.bit_length() - 1


def matches_per_round(capacity: int) -> list[int]:
    """Matches in each round, index 0 == first round (e.g. 16 -> [8, 4, 2, 1])."""
    return [capacity >> (r + 1) for r in range(num_rounds(capacity))]


def seed_order(capacity: int) -> list[int]:
    """Standard single-elimination seed order for a power-of-two ``capacity``.

    Built recursively: start with ``[1]`` and repeatedly expand each seed ``s``
    in a round of length ``L`` into ``[s, L + 1 - s]``. This is the canonical
    bracket order — seeds 1 and 2 can only meet in the final, and in every round
    the strongest faces the weakest remaining (so byes fall to the top seeds).
    """
    order = [1]
    while len(order) < capacity:
        length = len(order) * 2
        order = [v for s in order for v in (s, length + 1 - s)]
    return order


def seeding_pairs(capacity: int) -> list[tuple[int, int]]:
    """Round-1 pairings as ``(seedA, seedB)`` (1-indexed) for ``capacity`` slots."""
    order = seed_order(capacity)
    return [(order[i], order[i + 1]) for i in range(0, capacity, 2)]


def round_name(player_count: int) -> str:
    """Human name for a round given how many players enter it."""
    if player_count == 2:
        return "Final"
    if player_count == 4:
        return "Semifinals"
    if player_count == 8:
        return "Quarterfinals"
    return f"Round of {player_count}"


def round_names(capacity: int) -> list[str]:
    """Round names for every round of a ``capacity``-slot bracket."""
    return [round_name(m * 2) for m in matches_per_round(capacity)]


class MatchKind(StrEnum):
    """Classification of a match, derived from its two slots.

    - ``REAL``:   both slots hold active players — the admin decides the winner.
    - ``BYE``:    exactly one active player — that player auto-advances.
    - ``DEAD``:   no active player — nobody advances (both auto-lost / empty).
    - ``PENDING``: at least one slot is still waiting on an upstream REAL match
                   that has not been decided yet (the player is "TBD").
    """

    REAL = "REAL"
    BYE = "BYE"
    DEAD = "DEAD"
    PENDING = "PENDING"


def match_id(round_idx: int, match_idx: int) -> str:
    """Stable id for a match, e.g. ``r1_m1`` (1-indexed for humans)."""
    return f"r{round_idx + 1}_m{match_idx + 1}"


class Match(BaseModel):
    """A single match between (up to) two players."""

    match_id: str
    round: int  # 1..4 (4 == final); third-place match uses 0
    match_index: int  # 0-based index within the round
    kind: MatchKind = MatchKind.PENDING
    # Hidden round-1 padding matches: a seed position beyond the tournament size
    # N (capacity - N of them). Their top seed silently starts a round later.
    # Purely cosmetic — the box keeps its layout space; bye-advance is unaffected.
    hidden: bool = False
    player1: Player | None = None
    player2: Player | None = None
    # Winner explicitly set by the admin (only meaningful for REAL matches).
    winner: Player | None = None
    # Winner implied by a bye (no admin action required).
    auto_winner: Player | None = None

    @property
    def effective_winner(self) -> Player | None:
        """The winner that advances: manual winner takes priority over a bye."""
        return self.winner or self.auto_winner


class Round(BaseModel):
    """One round of the bracket."""

    round_number: int  # 1-based
    name: str
    matches: list[Match]


class Bracket(BaseModel):
    """A fully resolved, ready-to-render bracket plus its meta state."""

    rounds: list[Round]
    third_place_match: Match
    # Meta describing how the bracket was produced.
    is_seeded: bool = False
    active_count: int = 16
    seeded_at: str | None = None
    # User ids the admin has disabled (excluded from the tournament). Carried in
    # the meta so the admin UI can mark them; they remain on the live highscore.
    disabled_user_ids: list[int] = []

    @property
    def champion(self) -> Player | None:
        """Winner of the final match, if decided."""
        return self.rounds[-1].matches[0].effective_winner

    @property
    def runner_up(self) -> Player | None:
        """Loser of the final match, if the final is decided."""
        final = self.rounds[-1].matches[0]
        winner = final.effective_winner
        if winner is None:
            return None
        if final.player1 and final.player1.user_id == winner.user_id:
            return final.player2
        if final.player2 and final.player2.user_id == winner.user_id:
            return final.player1
        return None

    @property
    def third_place(self) -> Player | None:
        """Winner of the third-place match, if decided."""
        return self.third_place_match.effective_winner


# Per-slot derivation reason used during forward propagation.
_PLAYER = "PLAYER"  # slot holds a concrete advancing player
_GONE = "GONE"  # slot is permanently empty (auto-lost seed / dead feeder)
_PENDING = "PENDING"  # slot waits on an upstream real match not yet decided
_FORFEIT = "FORFEIT"  # a disabled player carried forward, shown struck-through;
# never advances — the opponent at the frontier gets the bye


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _seeded_slot(
    player: Player | None,
    seed_num: int,
    active_count: int,
    disabled_user_ids: frozenset[int],
) -> Player | None:
    """Return a round-1 slot player tagged with seed + active/auto-lost status.

    ``seed_num`` is 1-based. A player is ACTIVE only when their seed is within
    the active count **and** they are not disabled; otherwise they are auto-lost.
    A missing seed (no player captured at freeze time) yields ``None`` and is
    treated as auto-lost. Disabling acts as a safety net even on a frozen
    bracket (the player becomes a bye) — in live mode disabled players never
    receive a seed in the first place.
    """
    if player is None:
        return None
    active = seed_num <= active_count and player.user_id not in disabled_user_ids
    status = SlotStatus.ACTIVE if active else SlotStatus.AUTO_LOST
    return player.model_copy(update={"seed": seed_num, "status": status})


def _resolve_manual_winner(match: Match, manual_winners: dict[str, int]) -> Player | None:
    """Return the manual winner of ``match`` if it refers to a present player."""
    uid = manual_winners.get(match.match_id)
    if uid is None:
        return None
    if match.player1 and match.player1.user_id == uid:
        return match.player1
    if match.player2 and match.player2.user_id == uid:
        return match.player2
    # Stale winner (player no longer in this match) — ignore.
    return None


def _classify(
    match: Match,
    reason1: str,
    reason2: str,
    manual_winners: dict[str, int],
) -> tuple[str, Player | None]:
    """Classify a match and return what advances from it.

    Sets ``match.kind`` / ``match.winner`` / ``match.auto_winner`` as a side
    effect and returns ``(advance_reason, advance_player)`` where
    ``advance_reason`` is one of ``_PLAYER`` / ``_GONE`` / ``_PENDING``.
    """
    has1, has2 = reason1 == _PLAYER, reason2 == _PLAYER
    pend1, pend2 = reason1 == _PENDING, reason2 == _PENDING
    forf1, forf2 = reason1 == _FORFEIT, reason2 == _FORFEIT

    # Both slots hold real players -> a real match the admin must decide.
    if has1 and has2:
        match.kind = MatchKind.REAL
        winner = _resolve_manual_winner(match, manual_winners)
        match.winner = winner
        return (_PLAYER, winner) if winner else (_PENDING, None)

    # One real player vs a permanently empty / forfeited slot -> bye, that player
    # advances (a forfeited opponent stays visible, struck-through, in its slot).
    if has1 and not has2 and not pend2:
        match.kind = MatchKind.BYE
        match.auto_winner = match.player1
        return (_PLAYER, match.player1)
    if has2 and not has1 and not pend1:
        match.kind = MatchKind.BYE
        match.auto_winner = match.player2
        return (_PLAYER, match.player2)

    # No active player from here on. A carried forfeit (disabled player) stays
    # visible in its slot; what the match contributes depends on the other slot.
    if forf1 or forf2:
        # Against a not-yet-decided upstream real match -> output is TBD.
        if pend1 or pend2:
            match.kind = MatchKind.PENDING
            return (_PENDING, None)
        # Two forfeits -> both struck-through, nobody advances.
        if forf1 and forf2:
            match.kind = MatchKind.DEAD
            return (_GONE, None)
        # Forfeit vs a permanently empty slot -> carry the ghost forward so it
        # stays visible up to the round where a real opponent appears.
        match.kind = MatchKind.DEAD
        return (_FORFEIT, match.player1 if forf1 else match.player2)

    # No player and nothing pending -> dead match, nobody advances.
    if not has1 and not has2 and not pend1 and not pend2:
        match.kind = MatchKind.DEAD
        return (_GONE, None)

    # Anything else involves a pending slot -> the match (and its output) is TBD.
    match.kind = MatchKind.PENDING
    return (_PENDING, None)


def derive_bracket(
    seeds: list[Player | None],
    active_count: int,
    manual_winners: dict[str, int],
    *,
    is_seeded: bool,
    seeded_at: str | None,
    disabled_user_ids: frozenset[int] | set[int] | None = None,
) -> Bracket:
    """Build a fully resolved bracket from the authoritative state.

    The tree capacity is the next power of two ≥ ``active_count`` (the tournament
    size N). Seeds 1..N compete; positions N+1..capacity are empty and become
    byes for the top seeds. The number of rounds, matches-per-round, seeding and
    round names are all derived from the capacity, so the same code handles a
    4-, 16- or 64-slot bracket.
    """
    disabled = frozenset(disabled_user_ids or ())
    capacity = next_pow2(active_count)
    mpr = matches_per_round(capacity)
    names = round_names(capacity)
    last_round = len(mpr) - 1

    # --- Build empty rounds + third-place match. ---------------------------
    rounds: list[Round] = []
    for r_idx, num in enumerate(mpr):
        matches = [
            Match(match_id=match_id(r_idx, m), round=r_idx + 1, match_index=m) for m in range(num)
        ]
        rounds.append(Round(round_number=r_idx + 1, name=names[r_idx], matches=matches))
    third = Match(match_id=THIRD_PLACE_ID, round=0, match_index=0)

    # --- Fill round 1 from the seeding pairing. ----------------------------
    # A round-1 match is "hidden" iff one of its seed positions is beyond the
    # tournament size N (the capacity-N padding byes for the top seeds). This is
    # based purely on the seed numbers vs N — NOT on whether a player is present
    # — so the visible tree structure depends only on N, not the player count.
    for m_idx, (sa, sb) in enumerate(seeding_pairs(capacity)):
        pa = seeds[sa - 1] if sa - 1 < len(seeds) else None
        pb = seeds[sb - 1] if sb - 1 < len(seeds) else None
        match = rounds[0].matches[m_idx]
        match.player1 = _seeded_slot(pa, sa, active_count, disabled)
        match.player2 = _seeded_slot(pb, sb, active_count, disabled)
        match.hidden = sa > active_count or sb > active_count

    # --- Per-slot reasons, round by round. ---------------------------------
    # reasons[r][m] = [reason_p1, reason_p2]; round 1 is read from the players.
    reasons: list[list[list[str]]] = [[[_GONE, _GONE] for _ in range(num)] for num in mpr]
    for m_idx, m in enumerate(rounds[0].matches):
        reasons[0][m_idx][0] = _slot_reason(m.player1, disabled)
        reasons[0][m_idx][1] = _slot_reason(m.player2, disabled)

    # --- Forward propagation through every round. --------------------------
    for r_idx, num in enumerate(mpr):
        for m_idx in range(num):
            match = rounds[r_idx].matches[m_idx]
            r1, r2 = reasons[r_idx][m_idx]
            adv_reason, adv_player = _classify(match, r1, r2, manual_winners)

            # Push the result into the next round (unless this is the final).
            if r_idx < last_round:
                next_m = m_idx // 2
                pos = 0 if m_idx % 2 == 0 else 1  # even feeder -> p1, odd -> p2
                reasons[r_idx + 1][next_m][pos] = adv_reason
                if adv_reason in (_PLAYER, _FORFEIT) and adv_player is not None:
                    nm = rounds[r_idx + 1].matches[next_m]
                    if pos == 0:
                        nm.player1 = adv_player
                    else:
                        nm.player2 = adv_player

    # --- Third-place match: fed by the two semifinal losers. ---------------
    # Only exists when there is a semifinal round (capacity >= 4). Otherwise it
    # stays an empty DEAD placeholder so the model/clients need no null checks.
    if capacity >= 4:
        semi_idx = last_round - 1  # round with exactly 2 matches
        third_reasons = [_GONE, _GONE]
        for m_idx in range(2):
            semi = rounds[semi_idx].matches[m_idx]
            loser, reason = _semifinal_loser(semi)
            third_reasons[m_idx] = reason
            if reason == _PLAYER:
                if m_idx == 0:
                    third.player1 = loser
                else:
                    third.player2 = loser
        _classify(third, third_reasons[0], third_reasons[1], manual_winners)
    else:
        third.kind = MatchKind.DEAD

    return Bracket(
        rounds=rounds,
        third_place_match=third,
        is_seeded=is_seeded,
        active_count=active_count,
        seeded_at=seeded_at,
        disabled_user_ids=sorted(disabled),
    )


def _is_active(player: Player | None) -> bool:
    """True when the slot holds a real, actively-competing player."""
    return player is not None and player.status == SlotStatus.ACTIVE


def _slot_reason(player: Player | None, disabled: frozenset[int]) -> str:
    """Round-1 derivation reason for a seeded slot.

    A present-but-disabled player is carried forward as ``_FORFEIT`` so it stays
    visible (struck-through) up to the round where a real opponent appears; an
    empty/padding/missing slot is ``_GONE``; otherwise the active player advances.
    """
    if player is not None and player.user_id in disabled:
        return _FORFEIT
    return _PLAYER if _is_active(player) else _GONE


def _semifinal_loser(semi: Match) -> tuple[Player | None, str]:
    """Return (loser, reason) contributed by a semifinal to the third-place match."""
    # Only a *real*, decided semifinal produces a genuine loser.
    if semi.kind == MatchKind.REAL:
        winner = semi.effective_winner
        if winner is None:
            return (None, _PENDING)  # real match, loser still TBD
        if semi.player1 and semi.player1.user_id == winner.user_id:
            return (semi.player2, _PLAYER)
        return (semi.player1, _PLAYER)
    if semi.kind == MatchKind.PENDING:
        return (None, _PENDING)
    # BYE or DEAD: no real opponent to drop to third place.
    return (None, _GONE)


@dataclass
class BracketState:
    """Authoritative tournament state plus the admin operations (no I/O).

    Mirrors TournamentHigscore's ``BracketManager`` minus SQLite and locking.
    ``live_pool`` is the current leaderboard (best first); before the bracket
    is fixed the seeds follow it live.
    """

    active_count: int = 16
    is_seeded: bool = False
    seeded_at: str | None = None
    frozen_seeds: list[Player | None] = field(default_factory=list)
    manual_winners: dict[str, int] = field(default_factory=dict)
    disabled: set[int] = field(default_factory=set)
    live_pool: list[Player] = field(default_factory=list)

    # --- seeds ------------------------------------------------------------

    def live_seeds(self) -> list[Player | None]:
        """Top seeds from the live pool, excluding disabled players (64 slots)."""
        eligible = [p for p in self.live_pool if p.user_id not in self.disabled]
        seeds: list[Player | None] = []
        for idx in range(MAX_SIZE):
            if idx < len(eligible):
                seeds.append(eligible[idx].model_copy(update={"seed": idx + 1}))
            else:
                seeds.append(None)
        return seeds

    def seeds(self) -> list[Player | None]:
        return self.frozen_seeds if self.is_seeded else self.live_seeds()

    def bracket(self) -> Bracket:
        return derive_bracket(
            self.seeds(),
            self.active_count,
            self.manual_winners,
            is_seeded=self.is_seeded,
            seeded_at=self.seeded_at,
            disabled_user_ids=self.disabled,
        )

    # --- operations ---------------------------------------------------------

    def set_active_count(self, count: int) -> None:
        """Set N; a capacity change on a fixed bracket clears the winners."""
        new_count = max(MIN_SIZE, min(MAX_SIZE, count))
        if self.is_seeded and next_pow2(new_count) != next_pow2(self.active_count):
            self.manual_winners = {}
        self.active_count = new_count

    def fix(self) -> None:
        """Freeze the current live seeds and (re)start the tournament."""
        self.frozen_seeds = self.live_seeds()
        self.manual_winners = {}
        self.is_seeded = True
        self.seeded_at = _now_iso()

    def set_winner(self, match_id_: str, user_id: int) -> None:
        if not self.is_seeded:
            raise ValueError("Fix the bracket before setting winners")
        match = find_match(self.bracket(), match_id_)
        if match is None:
            raise ValueError(f"Unknown match: {match_id_}")
        if match.kind != MatchKind.REAL:
            raise ValueError("Winner can only be set on a real (contested) match")
        if not (
            (match.player1 and match.player1.user_id == user_id)
            or (match.player2 and match.player2.user_id == user_id)
        ):
            raise ValueError("Player is not part of this match")
        self.manual_winners[match_id_] = user_id

    def clear_winner(self, match_id_: str) -> None:
        self.manual_winners.pop(match_id_, None)

    def reset(self) -> None:
        """Clear all winners, keep the seeds."""
        self.manual_winners = {}

    def unseed(self) -> None:
        """Back to live auto-fill (disabled players are kept)."""
        self.frozen_seeds = []
        self.manual_winners = {}
        self.is_seeded = False
        self.seeded_at = None
        self.active_count = 16

    # --- persistence helpers (JSON-safe) -------------------------------------

    def seeds_json(self) -> list[dict[str, Any] | None]:
        return [p.model_dump(mode="json") if p else None for p in self.frozen_seeds]

    @staticmethod
    def seeds_from_json(data: list[Any]) -> list[Player | None]:
        return [Player(**p) if p else None for p in data]


def find_match(bracket: Bracket, match_id_: str) -> Match | None:
    if bracket.third_place_match.match_id == match_id_:
        return bracket.third_place_match
    for rnd in bracket.rounds:
        for m in rnd.matches:
            if m.match_id == match_id_:
                return m
    return None
