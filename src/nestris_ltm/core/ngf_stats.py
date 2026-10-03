"""Game statistics derived from NGF frames (simulator, NGF import).

Approximates what the station computes live: line clears from LINES steps,
burn, tetris rate, piece count and droughts from the OCR'd piece counters.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nestris_ltm.core.ngf import NgfFrame

COUNT_CONFIRM_FRAMES = 3
I_PIECE = 6  # index of I in the T J Z O S L I counter order


@dataclass
class GameTracker:
    """Derives the station's per-game statistics from NGF frames."""

    start_level: int | None = None
    score: int | None = None
    lines: int | None = None
    level: int | None = None
    clears: dict[str, int] = field(
        default_factory=lambda: {"single": 0, "double": 0, "triple": 0, "tetris": 0}
    )
    burn: int = 0
    pieces: int = 0
    drought: int = 0
    max_drought: int = 0
    _candidate: list[int | None] = field(default_factory=lambda: [None] * 7)
    _stable: list[int] = field(default_factory=lambda: [0] * 7)
    _confirmed: list[int | None] = field(default_factory=lambda: [None] * 7)

    def update(self, frame: NgfFrame) -> None:
        if self.start_level is None and frame.level is not None:
            self.start_level = frame.level
        if frame.lines is not None:
            if self.lines is not None and 0 < frame.lines - self.lines <= 4:
                kind = ("single", "double", "triple", "tetris")[frame.lines - self.lines - 1]
                self.clears[kind] += 1
                if kind != "tetris":
                    self.burn += frame.lines - self.lines
            self.lines = frame.lines
        if frame.score is not None:
            self.score = frame.score
        if frame.level is not None:
            self.level = frame.level

        # Piece counters are OCR'd and flicker (2 -> 9 -> 2). A counter value
        # only counts once it held for COUNT_CONFIRM_FRAMES and is a small
        # forward step from the confirmed value.
        for i, value in enumerate(frame.counts):
            if value is None:
                continue
            if value != self._candidate[i]:
                self._candidate[i], self._stable[i] = value, 1
                continue
            self._stable[i] += 1
            if self._stable[i] != COUNT_CONFIRM_FRAMES:
                continue
            confirmed = self._confirmed[i]
            if confirmed is None:
                self._confirmed[i] = value
            elif 0 < value - confirmed <= 2:
                step = value - confirmed
                self._confirmed[i] = value
                self.pieces += step
                if i == I_PIECE:
                    self.drought = 0
                else:
                    self.drought += step
                    self.max_drought = max(self.max_drought, self.drought)

    @property
    def tetris_rate(self) -> float | None:
        if not self.lines:
            return None
        return round(self.clears["tetris"] * 4 / self.lines, 4)
