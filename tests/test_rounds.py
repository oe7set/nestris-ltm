from __future__ import annotations

from nestris_ltm.core.rounds import RoundState, Standing, decide_outcomes, gap, score_to_beat


def S(slot: int, score: int, finished: bool = True) -> Standing:
    return Standing(slot, score, finished)


def test_binding_freezing_and_ignoring_later_games() -> None:
    r = RoundState()
    assert r.accepts(0, "g1")
    assert r.accepts(0, "g1")
    assert r.finish(0, "g1", score=100, lines=10, level=18, start_level=18)
    assert not r.accepts(0, "g2")  # second game in the same round is ignored
    assert not r.finish(0, "g2", score=999, lines=1, level=1, start_level=1)
    assert r.entry(0).score == 100
    assert r.all_finished([0])
    assert not r.all_finished([0, 1])
    r.unfreeze(0)
    assert r.accepts(0, "g2")


def test_unfinished_game_is_replaced_by_a_new_one() -> None:
    r = RoundState()
    r.accepts(0, "g1")
    assert r.accepts(0, "g2")  # station restarted without game_end
    assert r.entry(0).game_id == "g2"


def test_top2_early_decisions() -> None:
    # A finished at 300k, B finished at 100k, C and D still playing.
    st = [S(0, 300_000), S(1, 100_000), S(2, 50_000, False), S(3, 20_000, False)]
    assert decide_outcomes("top2_advance", st) == {}  # C and D could still pass A and B
    # C finishes at 200k: A is safe (only D can still pass); B is out (A and C above).
    st[2] = S(2, 200_000)
    assert decide_outcomes("top2_advance", st) == {0: "advanced", 1: "eliminated"}
    # D finishes at 10k: final ranking.
    st[3] = S(3, 10_000)
    assert decide_outcomes("top2_advance", st) == {
        0: "advanced", 2: "advanced", 1: "eliminated", 3: "eliminated"
    }  # fmt: skip


def test_finished_player_eliminated_early() -> None:
    st = [S(0, 300_000), S(1, 250_000), S(2, 100_000), S(3, 5_000, False)]
    out = decide_outcomes("top2_advance", st)
    assert out[2] == "eliminated"  # two finished players are already above
    assert 3 not in out


def test_worst_out_and_winner_only() -> None:
    st = [S(0, 300_000), S(1, 250_000), S(2, 100_000, False), S(3, 120_000)]
    # worst_out (K=3): A and B finished above 3 players' reach? A: 0 finished above,
    # 1 running -> 1 < 3 -> advanced. D (120k): A, B above + C running = 3 -> open.
    out = decide_outcomes("worst_out", st)
    assert out[0] == "advanced" and out[1] == "advanced" and 3 not in out
    win = decide_outcomes("winner_only", [S(0, 300_000), S(1, 100_000)])
    assert win == {0: "winner", 1: "eliminated"}


def test_running_leader_advances_early() -> None:
    # 1v1-style winner_only: B finished at 100k, A still playing at 150k -> A wins.
    out = decide_outcomes("winner_only", [S(0, 150_000, False), S(1, 100_000)])
    assert out == {0: "winner", 1: "eliminated"}


def test_score_to_beat_and_gap() -> None:
    st = [S(0, 300_000), S(1, 250_000), S(2, 100_000, False)]
    assert score_to_beat("top2_advance", st, 2) == 250_000
    assert score_to_beat("none", st, 2) is None
    assert score_to_beat("top2_advance", [], 0) is None
    g = gap(100_000, 250_000, 19)
    assert g.points == 150_000 and g.tetrises_needed == 7
    assert gap(300_000, 250_000, 19).tetrises_needed == 0
