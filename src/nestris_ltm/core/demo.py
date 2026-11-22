"""Attract-mode demo detection on the host (pure logic).

Left on the title screen, NES Tetris plays a demo game that looks exactly like
a real one. Stations from 0.4.0 on drop demos themselves
(``nestris-core/docs/STATION.md``, "Demo detection"); this module recognizes
the demos older stations already sent, from a game's live frames or its NGF
recording.

The demo is deterministic, so it always shows the same SCORE/LINES values
after each piece (a fingerprint). A game is a demo only when every stable
SCORE/LINES value it showed is the next step of a fingerprint and the level
matches. One stable contradiction, a game over (the demo never tops out) or a
start level other than 0 make it real. Doubt always means real.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from nestris_ltm.core.demo_fingerprints import FINGERPRINTS

# A SCORE/LINES value must stay this long to count (OCR glitches are shorter;
# the demo shows each value for a second or more).
STABLE_MS = 100
# Fingerprint steps a value may skip (updates the OCR missed).
MAX_SKIP = 2
# Matched steps for a finished demo / for an aborted one (ended by reset).
MIN_STEPS = 6
MIN_STEPS_ABORTED = 3
# Without frames: the end values must be a step at least this far in.
MIN_END_STEP = 10


@dataclass(frozen=True)
class DemoStep:
    score: int
    lines: int
    level: int
    next: str | None


@dataclass(frozen=True)
class Fingerprint:
    id: str
    rom: str
    steps: tuple[DemoStep, ...]


@dataclass(frozen=True)
class Sample:
    """One frame of a game: milliseconds since its start and the readings."""

    t_ms: int
    score: int | None
    lines: int | None
    level: int | None


@dataclass(frozen=True)
class DemoMatch:
    fingerprint: str
    # "frames": the frame sequence matched; "end_values": no frames, only the
    # final SCORE/LINES lie on the demo.
    method: str
    steps: int

    @property
    def reason(self) -> str:
        return f"{self.method}:{self.fingerprint}:{self.steps}"


def builtin() -> list[Fingerprint]:
    out = []
    for raw in FINGERPRINTS:
        raw_steps = raw["steps"]
        assert isinstance(raw_steps, list)
        steps = tuple(DemoStep(s[0], s[1], s[2], s[3]) for s in raw_steps)
        out.append(Fingerprint(id=str(raw["id"]), rom=str(raw.get("rom", "")), steps=steps))
    return out


def _stable_runs(samples: Iterable[Sample]) -> list[tuple[int, int, int | None]]:
    """(score, lines, level) of every SCORE/LINES value that held STABLE_MS."""
    runs: list[tuple[tuple[int, int], int, int, Counter[int]]] = []
    for s in samples:
        if s.score is None or s.lines is None:
            continue
        pair = (s.score, s.lines)
        if runs and runs[-1][0] == pair:
            first, _, levels = runs[-1][1], runs[-1][2], runs[-1][3]
            runs[-1] = (pair, first, s.t_ms, levels)
        else:
            runs.append((pair, s.t_ms, s.t_ms, Counter()))
        if s.level is not None:
            runs[-1][3][s.level] += 1
    out: list[tuple[int, int, int | None]] = []
    for i, (pair, first, last, levels) in enumerate(runs):
        end = runs[i + 1][1] if i + 1 < len(runs) else last
        if end - first < STABLE_MS and i + 1 < len(runs):
            continue
        level = levels.most_common(1)[0][0] if levels else None
        if out and (out[-1][0], out[-1][1]) == pair:
            continue
        out.append((pair[0], pair[1], level))
    return out


def _near(steps: Sequence[DemoStep], pos: int) -> Sequence[DemoStep]:
    return steps[max(pos - 1, 0) : pos + 2]


def _mixed(a: DemoStep, b: DemoStep, score: int, lines: int) -> bool:
    """SCORE and LINES settle on different frames: a pair between two steps."""
    return score in (a.score, b.score) and lines in (a.lines, b.lines)


def _match(runs: list[tuple[int, int, int | None]], fp: Fingerprint) -> int | None:
    """Matched steps, or None on a contradiction."""
    steps = fp.steps
    pos: int | None = None
    matched = 0
    for score, lines, level in runs:

        def at(i: int, score: int = score, lines: int = lines) -> bool:
            return steps[i].score == score and steps[i].lines == lines

        if pos is None:
            found = next((i for i in range(len(steps)) if at(i)), None)
            if found is None:
                return None
            pos, matched = found, 1
        elif not at(pos):
            ahead = next(
                (i for i in range(pos + 1, min(pos + 2 + MAX_SKIP, len(steps))) if at(i)), None
            )
            if ahead is not None:
                pos, matched = ahead, matched + 1
            elif pos + 1 < len(steps) and _mixed(steps[pos], steps[pos + 1], score, lines):
                continue
            else:
                return None
        if level is not None and all(s.level != level for s in _near(steps, pos)):
            return None
    return matched


def classify_frames(
    samples: Iterable[Sample],
    *,
    start_level: int | None,
    end_reason: str | None,
    fingerprints: Sequence[Fingerprint] | None = None,
) -> DemoMatch | None:
    """The demo a game's frames show, or None for a real game."""
    if start_level not in (None, 0) or end_reason == "game_over":
        return None
    runs = _stable_runs(samples)
    if not runs:
        return None
    need = MIN_STEPS if end_reason is None else MIN_STEPS_ABORTED
    best: DemoMatch | None = None
    for fp in fingerprints if fingerprints is not None else builtin():
        matched = _match(runs, fp)
        if matched is not None and matched >= need and (best is None or matched > best.steps):
            best = DemoMatch(fingerprint=fp.id, method="frames", steps=matched)
    return best


def classify_end_values(
    *,
    score: int | None,
    lines: int | None,
    start_level: int | None,
    end_level: int | None,
    end_reason: str | None,
    fingerprints: Sequence[Fingerprint] | None = None,
) -> DemoMatch | None:
    """Without frames: the final SCORE/LINES are a late step of a demo."""
    if score is None or lines is None or start_level not in (None, 0) or end_reason == "game_over":
        return None
    for fp in fingerprints if fingerprints is not None else builtin():
        for i, step in enumerate(fp.steps):
            if (
                i >= MIN_END_STEP
                and (step.score, step.lines) == (score, lines)
                and end_level in (None, step.level)
            ):
                return DemoMatch(fingerprint=fp.id, method="end_values", steps=i + 1)
    return None
