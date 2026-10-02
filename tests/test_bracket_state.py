"""Ported from the BracketManager tests in TournamentHigscore/tests/test_bracket.py,
now against the pure BracketState (persistence lives in services/tournament.py)."""

from __future__ import annotations

import pytest

from nestris_ltm.core.bracket import BracketState, MatchKind, Player, SlotStatus, find_match


def _pool() -> list[Player]:
    return [Player(user_id=i, nickname=f"P{i}", highscore=1000 * (70 - i)) for i in range(1, 65)]


def _fixed(count: int = 16) -> BracketState:
    state = BracketState(live_pool=_pool())
    state.set_active_count(count)
    state.fix()
    return state


def test_size_change_within_capacity_keeps_winners() -> None:
    state = _fixed(16)
    b = state.bracket()
    match = next(
        m
        for m in b.rounds[0].matches
        if m.kind == MatchKind.REAL
        and m.player1 is not None
        and m.player2 is not None
        and (m.player1.seed or 99) <= 13
        and (m.player2.seed or 99) <= 13
    )
    assert match.player1 is not None
    state.set_winner(match.match_id, match.player1.user_id)
    state.set_active_count(13)  # same capacity (16)
    keep = find_match(state.bracket(), match.match_id)
    assert keep is not None and keep.winner is not None


def test_size_change_across_capacity_clears_winners() -> None:
    state = _fixed(16)
    first_real = next(m for m in state.bracket().rounds[0].matches if m.kind == MatchKind.REAL)
    assert first_real.player1 is not None
    state.set_winner(first_real.match_id, first_real.player1.user_id)
    state.set_active_count(8)  # capacity 16 -> 8
    assert all(m.winner is None for rnd in state.bracket().rounds for m in rnd.matches)


def test_winner_requires_seeded() -> None:
    state = BracketState(live_pool=_pool())
    with pytest.raises(ValueError):
        state.set_winner("r1_m1", 1)


def test_live_seeds_follow_pool_and_skip_disabled() -> None:
    state = BracketState(live_pool=_pool(), disabled={1})
    seeds = state.seeds()
    assert seeds[0] is not None and seeds[0].user_id == 2 and seeds[0].seed == 1


def test_disable_after_fix_forfeits_instead_of_reseeding() -> None:
    state = _fixed(16)
    state.disabled.add(1)
    first = state.bracket().rounds[0].matches[0]
    assert first.player1 is not None and first.player1.user_id == 1
    assert first.player1.status == SlotStatus.AUTO_LOST
    assert first.kind == MatchKind.BYE  # seed 16 advances


def test_state_roundtrips_through_json() -> None:
    state = _fixed(8)
    restored = BracketState.seeds_from_json(state.seeds_json())
    assert restored == state.frozen_seeds


def test_unseed_returns_to_live() -> None:
    state = _fixed(8)
    state.unseed()
    assert not state.is_seeded and state.active_count == 16 and state.manual_winners == {}
