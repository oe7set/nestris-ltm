# ruff: noqa: E501, RUF001  (UI texts read better unwrapped)
"""Overlay layouts: how many slots a scene has and who plays against whom.

The overlay app (frontend/apps/overlay) has one component per layout id;
adding a layout means a new entry here plus a component there.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Layout:
    id: str
    slots: int
    title_de: str
    title_en: str
    description_de: str
    description_en: str
    # Head-to-head pairs; the diff of a paired slot is shown against its partner.
    pairs: tuple[tuple[int, int], ...] = field(default_factory=tuple)
    # Elimination modes make sense only with more than two players.
    supports_modes: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def partner(self, slot: int) -> int | None:
        for a, b in self.pairs:
            if slot == a:
                return b
            if slot == b:
                return a
        return None


# fmt: off
LAYOUTS: dict[str, Layout] = {
    layout.id: layout
    for layout in (
        Layout("single", 1, "Einzelspieler", "Single player",
               "Großes Spielfeld mit allen Statistiken eines Spielers.",
               "Large playfield with all statistics of one player."),
        Layout("single_compact", 1, "Einzelspieler kompakt", "Single player compact",
               "Schmale Leiste mit Spielfeld und Werten, z. B. neben der Kamera.",
               "Narrow strip with playfield and values, e.g. next to the camera."),
        Layout("1v1", 2, "1 gegen 1", "1 vs 1",
               "Zwei Spielfelder, Score-Differenz, Vorsprung in Tetris, Pace, Diff-Verlauf.",
               "Two playfields, score difference, lead in tetrises, pace, diff graph.",
               pairs=((0, 1),)),
        Layout("2x1v1", 4, "2 × 1 gegen 1", "2 × 1 vs 1",
               "Zwei Paarungen gleichzeitig (Slot 1 vs 2, Slot 3 vs 4).",
               "Two matches at once (slot 1 vs 2, slot 3 vs 4).",
               pairs=((0, 1), (2, 3))),
        Layout("4p", 4, "4 Spieler", "4 players",
               "Alle gegen alle mit Rangliste; Modi: Top 2 weiter, Schlechtester raus, nur Sieger.",
               "Everyone against everyone with ranking; modes: top 2 advance, worst out, winner only.",
               supports_modes=True),
    )
}
# fmt: on
