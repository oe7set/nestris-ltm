"""Ported from TournamentHigscore/tests/test_bracket.py.

Tests for the bracket derivation and the dynamic-capacity seeding.

These pin down: the standard-seeding generators for any power-of-two capacity,
the dynamic tree size (capacity = next power of two ≥ N), byes for the top seeds
(no DEAD matches with a full pool), the third-place feed, manual winners +
corrections, disabled players, and the winner-reset on a capacity change.
"""

from nestris_ltm.core.bracket import (
    MatchKind,
    Player,
    SlotStatus,
    derive_bracket,
    match_id,
    matches_per_round,
    next_pow2,
    seed_order,
    seeding_pairs,
)


def make_seeds(n: int = 16) -> list[Player | None]:
    """16 seeds with deterministic ids/nicknames (seed s -> user_id s)."""
    seeds: list[Player | None] = []
    for s in range(1, 17):
        if s <= n:
            seeds.append(Player(user_id=s, nickname=f"P{s}", highscore=1000 * (17 - s)))
        else:
            seeds.append(None)
    return seeds


def derive(seeds, active_count, winners=None, disabled=None):
    return derive_bracket(
        seeds,
        active_count,
        winners or {},
        is_seeded=True,
        seeded_at=None,
        disabled_user_ids=disabled,
    )


def kinds(bracket, round_idx):
    return [m.kind for m in bracket.rounds[round_idx].matches]


# --- N = 16: full bracket, no byes ---------------------------------------- #


def test_n16_all_real_no_byes():
    b = derive(make_seeds(16), 16)
    assert all(k == MatchKind.REAL for k in kinds(b, 0))
    # No round-1 match has an auto winner.
    assert all(m.auto_winner is None for m in b.rounds[0].matches)
    # Round 1 seeding: match 0 is seed1 vs seed16.
    m0 = b.rounds[0].matches[0]
    assert m0.player1.seed == 1 and m0.player2.seed == 16
    assert m0.player1.status == SlotStatus.ACTIVE


# --- N = 15: exactly one bye ---------------------------------------------- #


def test_n15_one_bye():
    b = derive(make_seeds(16), 15)
    r1 = kinds(b, 0)
    assert r1.count(MatchKind.BYE) == 1
    assert r1.count(MatchKind.REAL) == 7
    # Seed 16 is auto-lost; seed 1 advances by bye into round 2 slot 0.
    m0 = b.rounds[0].matches[0]
    assert m0.kind == MatchKind.BYE
    assert m0.auto_winner.seed == 1
    assert b.rounds[1].matches[0].player1.seed == 1


# --- Dynamic capacity: the tree shrinks to next_pow2(N) ------------------- #


def test_size8_is_a_clean_8_tree():
    # N=8 -> capacity 8: three rounds, all real, no byes.
    b = derive(make_seeds(16), 8)
    assert [r.name for r in b.rounds] == ["Quarterfinals", "Semifinals", "Final"]
    assert all(k == MatchKind.REAL for k in kinds(b, 0))
    assert all(m.auto_winner is None for m in b.rounds[0].matches)


def test_size7_one_bye_in_8_tree():
    # N=7 -> capacity 8; seed 8 is outside the size -> pair (1,8) is a bye.
    b = derive(make_seeds(16), 7)
    assert len(b.rounds) == 3
    r1 = kinds(b, 0)
    assert r1.count(MatchKind.BYE) == 1
    assert r1.count(MatchKind.DEAD) == 0  # full pool -> never dead
    m0 = b.rounds[0].matches[0]
    assert m0.kind == MatchKind.BYE and m0.auto_winner.seed == 1
    assert b.rounds[1].matches[0].player1.seed == 1


def test_size6_two_byes_in_8_tree():
    # N=6 -> capacity 8; seeds 7,8 outside -> pairs (1,8) and (2,7) are byes.
    b = derive(make_seeds(16), 6)
    r1 = kinds(b, 0)
    assert r1.count(MatchKind.BYE) == 2
    assert r1.count(MatchKind.REAL) == 2
    assert r1.count(MatchKind.DEAD) == 0
    # Seeds 1 and 2 advance by byes into the semifinals (round 2).
    assert b.rounds[1].matches[0].player1.seed == 1
    assert b.rounds[1].matches[1].player1.seed == 2


def test_size2_single_final_no_third_place():
    b = derive(make_seeds(16), 2)  # capacity 2
    assert len(b.rounds) == 1 and b.rounds[0].name == "Final"
    assert b.rounds[0].matches[0].kind == MatchKind.REAL
    # No semifinals -> no third-place match.
    assert b.third_place_match.kind == MatchKind.DEAD


def test_size12_is_a_16_tree_with_four_byes():
    # N=12 -> capacity 16; the four top seeds (1..4) get byes and start in R2.
    b = derive(make_seeds(16), 12)
    assert [r.name for r in b.rounds] == [
        "Round of 16",
        "Quarterfinals",
        "Semifinals",
        "Final",
    ]
    assert kinds(b, 0).count(MatchKind.BYE) == 4
    assert kinds(b, 0).count(MatchKind.DEAD) == 0
    # The four bye winners are seeds 1..4, present in round 2.
    r2_seeds = {
        s.seed for m in b.rounds[1].matches for s in (m.player1, m.player2) if s is not None
    }
    assert {1, 2, 3, 4}.issubset(r2_seeds)


def test_size64_has_six_rounds():
    seeds = [Player(user_id=i, nickname=f"P{i}", highscore=1000 * (70 - i)) for i in range(1, 65)]
    b = derive(seeds, 64)
    assert len(b.rounds) == 6
    assert len(b.rounds[0].matches) == 32
    assert b.rounds[0].name == "Round of 64"


def test_walkover_single_real_player():
    # Only seed 1 is a real player in a size-2 tree -> bye -> champion.
    b = derive(make_seeds(1), 2)
    assert b.champion is not None and b.champion.seed == 1


def test_no_dead_matches_with_full_pool():
    # Invariant: with capacity = next_pow2(N) and enough real players, no round-1
    # match is DEAD — only the top seeds get byes.
    full = [Player(user_id=i, nickname=f"P{i}", highscore=1000 * (70 - i)) for i in range(1, 65)]
    for size in range(2, 65):
        b = derive(full, size)
        assert kinds(b, 0).count(MatchKind.DEAD) == 0, f"DEAD at size {size}"


# --- PENDING blocks false byes -------------------------------------------- #


def test_pending_does_not_grant_false_bye():
    # N=16: round-2 match 0 is fed by two REAL, undecided round-1 matches.
    b = derive(make_seeds(16), 16)
    r2m0 = b.rounds[1].matches[0]
    assert r2m0.kind == MatchKind.PENDING
    assert r2m0.player1 is None and r2m0.player2 is None
    assert r2m0.auto_winner is None  # nobody advances past unplayed real matches


# --- Manual winners advance correctly ------------------------------------- #


def test_manual_winner_advances():
    seeds = make_seeds(16)
    # Seed 16 (user_id 16) beats seed 1 in round-1 match 0.
    winners = {match_id(0, 0): 16}
    b = derive(seeds, 16, winners)
    m0 = b.rounds[0].matches[0]
    assert m0.winner.user_id == 16
    # Winner advances to round-2 match 0, position 1 (even feeder index).
    assert b.rounds[1].matches[0].player1.user_id == 16


def test_correcting_winner_redirects_downstream():
    seeds = make_seeds(16)
    # First seed 1 wins, then we change it to seed 16.
    b1 = derive(seeds, 16, {match_id(0, 0): 1})
    assert b1.rounds[1].matches[0].player1.user_id == 1
    b2 = derive(seeds, 16, {match_id(0, 0): 16})
    # Re-derivation drops seed 1 downstream and inserts seed 16 instead.
    assert b2.rounds[1].matches[0].player1.user_id == 16


def test_stale_winner_is_ignored():
    seeds = make_seeds(16)
    # user_id 99 is not in match 0 -> ignored, match stays undecided.
    b = derive(seeds, 16, {match_id(0, 0): 99})
    assert b.rounds[0].matches[0].winner is None


# --- Third-place match fed by semifinal losers ---------------------------- #


def _play_out(seeds, size, pick):
    """Resolve a full bracket by repeatedly setting winners until decided.

    ``pick(p1, p2)`` chooses a winner user_id for a REAL match. Re-derives after
    each pick so downstream pairings exist before we decide them.
    """
    winners: dict[str, int] = {}
    for _ in range(50):  # generous upper bound; each pass decides >=1 match
        b = derive(seeds, size, winners)
        changed = False
        for rnd in b.rounds:
            for m in rnd.matches:
                if m.kind == MatchKind.REAL and m.match_id not in winners:
                    winners[m.match_id] = pick(m.player1, m.player2)
                    changed = True
        if not changed:
            return b, winners
    raise AssertionError("bracket did not converge")


def test_third_place_from_semifinal_losers():
    seeds = make_seeds(16)

    # The stronger seed (lower number) always wins.
    def pick(p1, p2):
        return p1.user_id if p1.seed < p2.seed else p2.user_id

    # Decide everything except the third-place match itself.
    b, _winners = _play_out(seeds, 16, pick)
    tpm = b.third_place_match
    assert tpm.kind == MatchKind.REAL
    # The two semifinal losers feed the third-place match.
    semi = b.rounds[2].matches
    losers = set()
    for m in semi:
        w = m.effective_winner
        loser = m.player1 if m.player2.user_id == w.user_id else m.player2
        losers.add(loser.user_id)
    assert {tpm.player1.user_id, tpm.player2.user_id} == losers
    # The final is seeds 1 and 2 (top seeds meet only in the final).
    final = b.rounds[3].matches[0]
    assert {final.player1.seed, final.player2.seed} == {1, 2}


# --- Fewer than 16 captured seeds (None padding) treated as auto-lost ------ #


def test_missing_seeds_are_auto_lost():
    seeds = make_seeds(10)  # seeds 11..16 are None
    b = derive(seeds, 16, {})  # even with N=16, missing seeds can't compete
    # Match 0 is seed1 vs seed16(None) -> bye for seed 1.
    assert b.rounds[0].matches[0].kind == MatchKind.BYE
    assert b.rounds[0].matches[0].auto_winner.seed == 1


# --- Disabled players are auto-lost regardless of seed -------------------- #


def test_disabled_player_becomes_auto_lost():
    seeds = make_seeds(16)
    # Disable seed 16 (user_id 16) -> match 0 (1 vs 16) becomes a bye for seed 1.
    b = derive(seeds, 16, {}, disabled={16})
    m0 = b.rounds[0].matches[0]
    assert m0.kind == MatchKind.BYE
    assert m0.auto_winner.seed == 1
    # The disabled player's slot is marked auto-lost.
    assert m0.player2.status == SlotStatus.AUTO_LOST
    # disabled_user_ids is surfaced on the bracket meta.
    assert b.disabled_user_ids == [16]


def test_disabling_a_top_seed_creates_a_bye_for_their_opponent():
    seeds = make_seeds(16)
    # Disable seed 1 -> their round-1 opponent (seed 16) advances by bye.
    b = derive(seeds, 16, {}, disabled={1})
    m0 = b.rounds[0].matches[0]
    assert m0.kind == MatchKind.BYE
    assert m0.auto_winner.seed == 16
    assert m0.player1.status == SlotStatus.AUTO_LOST


def test_default_no_disabled_matches_full_bracket():
    seeds = make_seeds(16)
    b = derive(seeds, 16, {})  # disabled defaults to empty
    assert b.disabled_user_ids == []
    assert all(k == MatchKind.REAL for k in kinds(b, 0))


# --- Hidden flag: full N-tree visible, only >N padding hidden ------------- #


def _full_pool(n=64):
    return [Player(user_id=i, nickname=f"P{i}", highscore=1000 * (70 - i)) for i in range(1, n + 1)]


def test_hidden_count_equals_capacity_minus_n():
    # Exactly capacity - N round-1 matches are hidden (the padding byes).
    for size in (2, 8, 11, 12, 16, 20, 32, 50, 64):
        b = derive(_full_pool(), size)
        cap = next_pow2(size)
        hidden = sum(1 for m in b.rounds[0].matches if m.hidden)
        assert hidden == cap - size, f"size {size}: {hidden} != {cap - size}"


def test_later_and_third_place_never_hidden():
    b = derive(_full_pool(), 12)  # capacity 16
    for rnd in b.rounds[1:]:
        assert all(not m.hidden for m in rnd.matches)
    assert b.third_place_match.hidden is False


def test_power_of_two_size_hides_nothing():
    for size in (2, 4, 8, 16, 32, 64):
        b = derive(_full_pool(), size)
        assert all(not m.hidden for m in b.rounds[0].matches)


def test_disabled_after_fix_keeps_match_visible():
    # Frozen full pool: disabling a player turns their match into a BYE but it
    # stays VISIBLE (both seed positions <= N) — the structure does not change.
    seeds = make_seeds(16)
    b = derive(seeds, 16, {}, disabled={4})
    match = next(
        m
        for m in b.rounds[0].matches
        if (m.player1 and m.player1.user_id == 4) or (m.player2 and m.player2.user_id == 4)
    )
    assert match.kind == MatchKind.BYE
    assert match.hidden is False  # the bug fix: box stays on screen


# --- Disable renumbering before fix vs. fixed position after fix ---------- #


def _live_seed_map(pool, disabled):
    """Mimic BracketManager._live_seeds: drop disabled, renumber 1..P."""
    eligible = [p for p in pool if p.user_id not in disabled]
    return [p.model_copy(update={"seed": i + 1}) for i, p in enumerate(eligible)]


def test_disable_before_fix_renumbers():
    pool = _full_pool(16)
    # Disable user_id 4 (currently seed 4) -> everyone below moves up one seed.
    seeds = _live_seed_map(pool, {4})
    b = derive(seeds, 16, {}, disabled={4})
    by_seed = {
        s.seed: s.user_id
        for m in b.rounds[0].matches
        for s in (m.player1, m.player2)
        if s is not None
    }
    # user 4 is gone; user 5 took seed 4, user 6 took seed 5, ...
    assert 4 not in by_seed.values()
    assert by_seed[4] == 5
    assert by_seed[5] == 6


def test_disable_after_fix_keeps_position():
    # Frozen snapshot keeps user 4 at seed 4, just auto-lost (no renumber).
    seeds = make_seeds(16)
    b = derive(seeds, 16, {}, disabled={4})
    seat = {
        s.seed: (s.user_id, s.status)
        for m in b.rounds[0].matches
        for s in (m.player1, m.player2)
        if s is not None
    }
    assert seat[4][0] == 4  # still in seat 4
    assert seat[4][1] == SlotStatus.AUTO_LOST
    assert seat[5][0] == 5  # neighbours unchanged


# --- Disabled bye player stays visible (struck-through) in higher rounds --- #


def test_disabled_bye_player_stays_visible_in_higher_round():
    # N=12 -> capacity 16: seed 1 has a round-1 bye and starts in round 2. After
    # disabling seed 1, it must NOT collapse to a blank TBD in round 2 — it stays
    # in its slot, auto-lost, and the real round-1 winner gets the bye there.
    seeds = make_seeds(16)
    # Decide seed 1's round-2 opponent: the match feeding round-2 match 0 slot 1.
    # Round-1 matches 0,1 feed round-2 match 0; match 0 is seed 1's (hidden) bye,
    # match 1 is a real match (seeds 8 vs 9). Let seed 8 win it.
    b = derive(seeds, 12, {match_id(0, 1): 8}, disabled={1})

    r2m0 = b.rounds[1].matches[0]
    # Seed 1 is still shown (struck-through), not TBD.
    forfeiter = r2m0.player1 if (r2m0.player1 and r2m0.player1.user_id == 1) else r2m0.player2
    assert forfeiter is not None and forfeiter.user_id == 1
    assert forfeiter.status == SlotStatus.AUTO_LOST
    # The match is a BYE won by the real round-1 winner (seed 8), not seed 1.
    assert r2m0.kind == MatchKind.BYE
    assert r2m0.auto_winner is not None and r2m0.auto_winner.user_id == 8


def test_forfeit_stops_at_real_opponent_and_grants_no_false_advance():
    # The disabled player never advances past the round where it meets a real
    # opponent: seed 1 (auto-lost) loses its round-2 bye to seed 8, so round 3
    # carries seed 8, and seed 1 appears in no slot beyond round 2.
    seeds = make_seeds(16)
    b = derive(seeds, 12, {match_id(0, 1): 8}, disabled={1})

    r3m0 = b.rounds[2].matches[0]
    slots_r3 = [s for s in (r3m0.player1, r3m0.player2) if s is not None]
    assert any(s.user_id == 8 for s in slots_r3)
    # Seed 1 (user 1) shows ONLY up to round 2 — never in round 3 or the final.
    for rnd in b.rounds[2:]:
        for m in rnd.matches:
            for s in (m.player1, m.player2):
                assert s is None or s.user_id != 1


def test_disabled_top_seed_carries_through_bye_chain():
    # N=12, disable seed 1 but leave its round-2 opponent undecided: seed 1 still
    # must appear in round 2 (carried via _FORFEIT), shown auto-lost, with the
    # match PENDING on the real round-1 feeder — still no blank TBD for seed 1.
    seeds = make_seeds(16)
    b = derive(seeds, 12, {}, disabled={1})
    r2m0 = b.rounds[1].matches[0]
    seat = r2m0.player1 if (r2m0.player1 and r2m0.player1.user_id == 1) else r2m0.player2
    assert seat is not None and seat.user_id == 1
    assert seat.status == SlotStatus.AUTO_LOST


# --- Seeding generators --------------------------------------------------- #


def test_next_pow2():
    assert [next_pow2(n) for n in (1, 2, 3, 4, 5, 12, 16, 17, 33, 64)] == [
        2,
        2,
        4,
        4,
        8,
        16,
        16,
        32,
        64,
        64,
    ]


def test_seed_order_is_a_permutation():
    for cap in (2, 4, 8, 16, 32, 64):
        order = seed_order(cap)
        assert sorted(order) == list(range(1, cap + 1))


def test_seeding_pairs_sum_to_capacity_plus_one():
    # In standard seeding every round-1 pair sums to capacity + 1.
    for cap in (2, 4, 8, 16, 32, 64):
        for a, b in seeding_pairs(cap):
            assert a + b == cap + 1


def test_matches_per_round_halves_each_round():
    assert matches_per_round(16) == [8, 4, 2, 1]
    assert matches_per_round(64) == [32, 16, 8, 4, 2, 1]
    assert matches_per_round(2) == [1]


# --- Manager: changing size resets winners only on a capacity change ------- #


def _pool():
    return [Player(user_id=i, nickname=f"P{i}", highscore=1000 * (70 - i)) for i in range(1, 65)]


# Manager tests (originally against BracketManager + SQLite) are ported to
# the pure BracketState in test_bracket_state.py.
