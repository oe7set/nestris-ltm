"""Starting points for the layout builder: the NES camera layouts as definitions.

They follow the built-in layouts (``1v1_cam``, ``2x1v1_cam``, ...) closely but
are plain element lists, so they can be changed freely in the builder. Every
template is a valid ``LayoutDefinition`` (``tests/test_studio.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nestris_ltm.core.overlay_layout import CANVAS_W

Element = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Template:
    id: str
    name_de: str
    name_en: str
    description_de: str
    description_en: str
    build: Callable[[], dict[str, Any]]

    def definition(self) -> dict[str, Any]:
        return self.build()


def _flip(x: int, w: int, mirror: bool, width: int = CANVAS_W, origin: int = 0) -> int:
    """x of a box mirrored inside [origin, origin + width) when asked."""
    return origin + width - (x - origin) - w if mirror else x


def _el(
    eid: str, kind: str, x: int, y: int, w: int, h: int,
    *, slot: int | None = None, pair: int | None = None, **props: Any,
) -> Element:  # fmt: skip
    el: Element = {"id": eid, "type": kind, "x": x, "y": y, "w": w, "h": h}
    if slot is not None:
        el["slot"] = slot
    if pair is not None:
        el["pair"] = pair
    if props:
        el["props"] = props
    return el


def _stat(eid: str, slot: int, field: str, x: int, y: int, w: int, h: int, align: str) -> Element:
    return _el(eid, "stat", x, y, w, h, slot=slot, field=field, align=align)


def _cam_side(slot: int, mirror: bool) -> list[Element]:
    """1 vs 1, one side: camera | stats | board (mirrored for the right player)."""

    def X(x: int, w: int) -> int:
        return _flip(x, w, mirror)

    s, align = f"s{slot}", ("right" if mirror else "left")
    return [
        _el(f"tag-{s}", "nametag", X(24, 296), 24, 296, 112, slot=slot, align=align),
        _el(f"cam-{s}", "camera", X(24, 296), 152, 296, 856, slot=slot),
        _stat(f"score-{s}", slot, "score", X(336, 264), 24, 264, 112, align),
        _stat(f"gap-{s}", slot, "gap", X(336, 264), 152, 264, 88, align),
        _stat(f"lines-{s}", slot, "lines", X(336, 128), 256, 128, 88, align),
        _stat(f"level-{s}", slot, "level", X(472, 128), 256, 128, 88, align),
        _el(f"next-{s}", "next", X(336, 264), 360, 264, 136, slot=slot),
        _stat(f"trt-{s}", slot, "trt", X(336, 128), 512, 128, 88, align),
        _stat(f"drought-{s}", slot, "drought", X(472, 128), 512, 128, 88, align),
        _stat(f"pace-{s}", slot, "pace", X(336, 264), 616, 264, 88, align),
        _el(f"board-{s}", "board", X(616, 336), 88, 336, 696, slot=slot),
    ]


def one_vs_one_cam() -> dict[str, Any]:
    return {
        "schema": 1,
        "slots": 2,
        "pairs": [[0, 1]],
        "elements": [
            *_cam_side(0, False),
            *_cam_side(1, True),
            _el("title", "title", 616, 16, 688, 56),
            _el("versus", "versus", 616, 800, 320, 256, pair=0),
            _el("graph", "diff_graph", 952, 800, 352, 184, pair=0),
            _el("round", "round", 952, 1000, 352, 56, pair=0),
        ],
    }


def _row_side(slot: int, top: int, mirror: bool) -> list[Element]:
    """2 x 1 vs 1, one player of a row (540 px high)."""

    def X(x: int, w: int) -> int:
        return _flip(x, w, mirror)

    s, align = f"s{slot}", ("right" if mirror else "left")
    return [
        _el(f"tag-{s}", "nametag", X(16, 280), top + 16, 280, 80, slot=slot, align=align),
        _el(f"cam-{s}", "camera", X(16, 280), top + 104, 280, 420, slot=slot),
        _stat(f"score-{s}", slot, "score", X(312, 264), top + 16, 264, 88, align),
        _stat(f"lines-{s}", slot, "lines", X(312, 128), top + 112, 128, 80, align),
        _stat(f"level-{s}", slot, "level", X(448, 128), top + 112, 128, 80, align),
        _el(f"next-{s}", "next", X(312, 264), top + 200, 264, 112, slot=slot),
        _stat(f"trt-{s}", slot, "trt", X(312, 128), top + 320, 128, 80, align),
        _stat(f"drought-{s}", slot, "drought", X(448, 128), top + 320, 128, 80, align),
        _stat(f"pace-{s}", slot, "pace", X(312, 264), top + 408, 264, 80, align),
        _el(f"board-{s}", "board", X(592, 256), top + 16, 256, 508, slot=slot),
    ]


def two_by_one_vs_one_cam() -> dict[str, Any]:
    elements: list[Element] = []
    for pair, top in ((0, 0), (1, 540)):
        a, b = 2 * pair, 2 * pair + 1
        elements += _row_side(a, top, False) + _row_side(b, top, True)
        elements += [
            _el(f"versus-p{pair}", "versus", 864, top + 16, 192, 232, pair=pair),
            _el(f"graph-p{pair}", "diff_graph", 864, top + 264, 192, 176, pair=pair),
            _el(f"round-p{pair}", "round", 864, top + 456, 192, 56, pair=pair),
        ]
    return {"schema": 1, "slots": 4, "pairs": [[0, 1], [2, 3]], "elements": elements}


def single_cam() -> dict[str, Any]:
    return {
        "schema": 1,
        "slots": 1,
        "pairs": [],
        "elements": [
            _el("tag", "nametag", 40, 40, 768, 112, slot=0),
            _el("cam", "camera", 40, 168, 768, 432, slot=0),
            _el("title", "title", 40, 616, 768, 64),
            _el("board", "board", 848, 40, 504, 1000, slot=0),
            _stat("score", 0, "score", 1392, 40, 488, 136, "left"),
            _stat("lines", 0, "lines", 1392, 192, 240, 112, "left"),
            _stat("level", 0, "level", 1640, 192, 240, 112, "left"),
            _el("next", "next", 1392, 320, 488, 200, slot=0),
            _stat("trt", 0, "trt", 1392, 536, 240, 112, "left"),
            _stat("drought", 0, "drought", 1640, 536, 240, 112, "left"),
            _stat("burn", 0, "burn", 1392, 664, 240, 112, "left"),
            _stat("pace", 0, "pace", 1640, 664, 240, 112, "left"),
        ],
    }


def four_players() -> dict[str, Any]:
    elements: list[Element] = []
    for slot in range(4):
        x, s = slot * 480, f"s{slot}"
        elements += [
            _el(f"tag-{s}", "nametag", x + 24, 16, 432, 88, slot=slot),
            _el(f"board-{s}", "board", x + 24, 120, 304, 616, slot=slot),
            _el(f"next-{s}", "next", x + 344, 120, 112, 112, slot=slot),
            _stat(f"level-{s}", slot, "level", x + 344, 248, 112, 88, "left"),
            _stat(f"score-{s}", slot, "score", x + 24, 752, 432, 104, "left"),
            _stat(f"lines-{s}", slot, "lines", x + 24, 872, 208, 88, "left"),
            _stat(f"trt-{s}", slot, "trt", x + 248, 872, 208, 88, "left"),
            _stat(f"drought-{s}", slot, "drought", x + 24, 976, 208, 88, "left"),
            _stat(f"pace-{s}", slot, "pace", x + 248, 976, 208, 88, "left"),
        ]
    return {"schema": 1, "slots": 4, "pairs": [], "elements": elements}


TEMPLATES: tuple[Template, ...] = (
    Template(
        "1v1_cam", "1 gegen 1 mit Kameras", "1 vs 1 with cameras",
        "Kamera | Werte | Spielfeld ‖ Spielfeld | Werte | Kamera, Differenz und Verlauf unten.",
        "Camera | stats | board ‖ board | stats | camera, difference and graph below.",
        one_vs_one_cam,
    ),
    Template(
        "2x1v1_cam", "2 × 1 gegen 1 mit Kameras", "2 × 1 vs 1 with cameras",  # noqa: RUF001
        "Zwei Paare übereinander, je Spieler Kamera, Werte und Spielfeld.",
        "Two pairs on top of each other, camera, stats and board per player.",
        two_by_one_vs_one_cam,
    ),
    Template(
        "single_cam", "Einzelspieler mit Kamera", "Single player with camera",
        "Große Kamera links, Spielfeld und alle Werte rechts.",
        "Large camera on the left, board and all stats on the right.",
        single_cam,
    ),
    Template(
        "4p", "4 Spieler", "4 players",
        "Vier Spalten ohne Paare: Name, Spielfeld und Werte je Spieler.",
        "Four columns without pairs: name, board and stats per player.",
        four_players,
    ),
)  # fmt: skip

BY_ID = {t.id: t for t in TEMPLATES}
