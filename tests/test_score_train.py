"""Tests for the pure score-train milestone computation (1,000,000 steps)."""

from nestris_ltm.core.score_train import STEP, compute_train


def test_step_is_one_million():
    assert STEP == 1_000_000


def test_zero():
    t = compute_train(0)
    assert t.current_milestone == 0
    assert t.next_milestone == 1_000_000
    assert t.progress == 0.0


def test_below_first_million():
    t = compute_train(400_000)
    assert t.current_milestone == 0
    assert t.next_milestone == 1_000_000
    assert abs(t.progress - 0.4) < 1e-6


def test_halfway_into_a_million():
    t = compute_train(1_500_000)
    assert t.current_milestone == 1_000_000
    assert t.next_milestone == 2_000_000
    assert abs(t.progress - 0.5) < 1e-6


def test_exactly_on_a_million():
    t = compute_train(2_000_000)
    assert t.current_milestone == 2_000_000
    assert t.next_milestone == 3_000_000
    assert t.progress == 0.0


def test_large_value_never_finishes():
    t = compute_train(42_750_000)
    assert t.current_milestone == 42_000_000
    assert t.next_milestone == 43_000_000
    assert abs(t.progress - 0.75) < 1e-6


def test_negative_is_clamped():
    t = compute_train(-5)
    assert t.current_milestone == 0
    assert t.next_milestone == 1_000_000
    assert t.progress == 0.0
