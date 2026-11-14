# ruff: noqa: E501, RUF001  (UI texts read better unwrapped)
"""Layout templates: every important built-in layout as an element definition.

A template is a plain element list on the 1920x1080 stage, so it can be
changed freely in the scene studio. ``builtin`` names the fixed layout
(``core/layouts.py``) a template reproduces: "adapting" a scene with a
built-in layout starts from that template (``services/overlay_layouts.fork``).

The coordinates were measured from the built-in overlay components rendered
at 1920x1080 in the NES style (``getBoundingClientRect`` of board well, next
box, stats panel and cells, camera, versus, graph), so a template looks like
its built-in layout. Every template is a valid ``LayoutDefinition``
(``tests/test_studio.py``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nestris_ltm.core.overlay_layout import CANVAS_W

Element = dict[str, Any]
Box = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Template:
    id: str
    name_de: str
    name_en: str
    description_de: str
    description_en: str
    build: Callable[[], dict[str, Any]]
    # The fixed layout this template reproduces (None: a template only).
    builtin: str | None = None
    # Player count, groups the "new scene" dialog (1, 2 or 4).
    players: int = 1
    # Shown first and highlighted in the "new scene" dialog.
    featured: bool = False

    def definition(self) -> dict[str, Any]:
        return self.build()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name_de": self.name_de, "name_en": self.name_en,
            "description_de": self.description_de, "description_en": self.description_en,
            "builtin": self.builtin, "players": self.players, "featured": self.featured,
            "definition": self.definition(),
        }  # fmt: skip


# ---------------------------------------------------------------- building blocks


def _el(
    eid: str, kind: str, box: Box,
    *, slot: int | None = None, pair: int | None = None, **props: Any,
) -> Element:  # fmt: skip
    x, y, w, h = box
    el: Element = {"id": eid, "type": kind, "x": x, "y": y, "w": w, "h": h}
    if slot is not None:
        el["slot"] = slot
    if pair is not None:
        el["pair"] = pair
    if props:
        el["props"] = props
    return el


def _mirror(box: Box, width: int = CANVAS_W, origin: int = 0) -> Box:
    """A box mirrored horizontally inside [origin, origin + width)."""
    x, y, w, h = box
    return (origin + width - (x - origin) - w, y, w, h)


def _shift(box: Box, dx: int = 0, dy: int = 0) -> Box:
    x, y, w, h = box
    return (x + dx, y + dy, w, h)


def _stat(eid: str, slot: int, field: str, box: Box, align: str, **props: Any) -> Element:
    return _el(eid, "stat", box, slot=slot, field=field, align=align, **props)


def _panel_stats(
    s: str, slot: int, panel: Box, name: Box, score: Box, cells: list[tuple[str, Box]],
    align: str, hearts: Box | None = None,
) -> list[Element]:  # fmt: skip
    """The stats panel of the built-in layouts: one frame, the values inside."""
    out = [
        _el(f"panel-{s}", "frame", panel),
        _el(f"name-{s}", "name", name, slot=slot, align=align, boxed=False, show_rank=True),
        _stat(f"score-{s}", slot, "score", score, align, boxed=False, show_label=False),
    ]
    if hearts is not None:
        out.append(_el(f"hearts-{s}", "hearts", hearts, slot=slot, align=align))
    out += [_stat(f"{f}-{s}", slot, f, box, align, boxed=False) for f, box in cells]
    return out


def _side_stats(s: str, slot: int, boxes: dict[str, Box], align: str) -> list[Element]:
    """The narrow stats column of the camera layouts (one box per value).

    Mirrored boxes swap the two halves of a row; the original keeps LINES and
    TRT on the left on both sides, so swap them back.
    """
    if align == "right":
        boxes = dict(boxes)
        for a, b in (("lines", "level"), ("trt", "drought")):
            if a in boxes and b in boxes:
                boxes[a], boxes[b] = boxes[b], boxes[a]
    score = boxes["score"]
    x, y, w, h = score
    out = [
        _el(f"scorebox-{s}", "frame", score),
        _stat(f"score-{s}", slot, "score", (x + 8, y + 4, w - 16, h * 3 // 5), align, boxed=False),
        _stat(f"gap-{s}", slot, "gap", (x + 8, y + h * 3 // 5, w - 16, h * 2 // 5 - 6), align,
              boxed=False, show_label=False),
    ]  # fmt: skip
    for field, box in boxes.items():
        if field == "score":
            continue
        if field == "next":
            out.append(_el(f"next-{s}", "next", box, slot=slot))
        else:
            out.append(_stat(f"{field}-{s}", slot, field, box, align))
    return out


def _definition(slots: int, pairs: list[list[int]], elements: list[Element]) -> dict[str, Any]:
    return {"schema": 1, "slots": slots, "pairs": pairs, "elements": elements}


# ---------------------------------------------------------------- 1 player


def single() -> dict[str, Any]:
    """Like ``Single.svelte``: camera space left, board and stats right."""
    return _definition(1, [], [
        _el("cam", "camera", (40, 40, 860, 484), slot=0, framed=False),
        _el("board", "board", (924, 40, 470, 910), slot=0),
        _el("next", "next", (1404, 40, 174, 116), slot=0),
        *_panel_stats("s0", 0, (1602, 220, 278, 278), (1624, 238, 234, 38), (1624, 286, 234, 38), [
            ("lines", (1624, 334, 109, 32)), ("level", (1749, 334, 109, 32)),
            ("trt", (1624, 372, 109, 32)), ("burn", (1749, 372, 109, 32)),
            ("drought", (1624, 410, 109, 32)), ("pace", (1624, 448, 234, 32)),
        ], "left"),
    ])  # fmt: skip


def single_compact() -> dict[str, Any]:
    """Like ``SingleCompact.svelte``: a narrow strip on the right."""
    return _definition(1, [], [
        *_panel_stats("s0", 0, (1470, 30, 431, 202), (1492, 48, 387, 38), (1492, 96, 387, 38), [
            ("lines", (1492, 144, 186, 32)), ("level", (1694, 144, 186, 32)),
            ("trt", (1492, 182, 186, 32)), ("drought", (1694, 182, 186, 32)),
        ], "left"),
        _el("board", "board", (1470, 248, 302, 582), slot=0),
        _el("next", "next", (1782, 248, 119, 92), slot=0),
    ])  # fmt: skip


def single_cam() -> dict[str, Any]:
    """Large camera on the left, board and every value on the right."""
    return _definition(1, [], [
        _el("tag", "nametag", (40, 40, 768, 112), slot=0),
        _el("cam", "camera", (40, 168, 768, 432), slot=0),
        _el("title", "title", (40, 616, 768, 64)),
        _el("board", "board", (848, 40, 504, 1000), slot=0),
        _stat("score", 0, "score", (1392, 40, 488, 136), "left"),
        _stat("lines", 0, "lines", (1392, 192, 240, 112), "left"),
        _stat("level", 0, "level", (1640, 192, 240, 112), "left"),
        _el("next", "next", (1392, 320, 488, 200), slot=0),
        _stat("trt", 0, "trt", (1392, 536, 240, 112), "left"),
        _stat("drought", 0, "drought", (1640, 536, 240, 112), "left"),
        _stat("burn", 0, "burn", (1392, 664, 240, 112), "left"),
        _stat("pace", 0, "pace", (1640, 664, 240, 112), "left"),
    ])  # fmt: skip


# ---------------------------------------------------------------- 2 players


def one_vs_one() -> dict[str, Any]:
    """Like ``OneVsOne.svelte``: boards outside, stats inside, versus centre."""
    width = 1940  # mirror axis 970: the right board ends at the stage edge

    def side(slot: int, right: bool) -> list[Element]:
        s, align = f"s{slot}", ("right" if right else "left")

        def at(box: Box) -> Box:
            return _mirror(box, width) if right else box

        def cell(box: Box) -> Box:
            # The cell grid is not mirrored, only moved to the other panel.
            return _shift(box, 552) if right else box

        return [
            _el(f"board-{s}", "board", at((20, 86, 365, 705)), slot=slot),
            _el(f"next-{s}", "next", at((395, 86, 140, 102)), slot=slot),
            _el(f"cam-{s}", "camera", at((549, 86, 290, 163)), slot=slot, framed=False),
            *_panel_stats(
                s, slot, at((549, 263, 290, 316)), at((571, 281, 246, 38)), at((571, 367, 246, 38)),
                [
                    ("lines", cell((571, 415, 115, 32))), ("level", cell((702, 415, 115, 32))),
                    ("trt", cell((571, 453, 115, 32))), ("burn", cell((702, 453, 115, 32))),
                    ("drought", cell((571, 491, 115, 32))), ("pace", cell((571, 529, 246, 32))),
                ],
                align, hearts=at((571, 327, 246, 30)),
            ),
        ]  # fmt: skip

    return _definition(2, [[0, 1]], [
        _el("title", "title", (788, 16, 216, 56)),
        _el("round", "round", (1014, 20, 152, 48)),
        *side(0, False),
        *side(1, True),
        _el("versus", "versus", (853, 126, 244, 235), pair=0),
        _el("graph", "diff_graph", (853, 375, 244, 154), pair=0),
    ])  # fmt: skip


def one_vs_one_cam() -> dict[str, Any]:
    """Like ``OneVsOneCam.svelte``: camera | stats | board ‖ board | stats | camera."""

    def side(slot: int, right: bool) -> list[Element]:
        s, align = f"s{slot}", ("right" if right else "left")

        def at(box: Box) -> Box:
            return _mirror(box) if right else box

        return [
            _el(f"tag-{s}", "nametag", at((20, 20, 290, 96)), slot=slot),
            _el(f"cam-{s}", "camera", at((20, 128, 290, 880)), slot=slot, framed=False),
            *_side_stats(s, slot, {
                "score": at((322, 20, 260, 109)),
                "lines": at((322, 139, 125, 70)), "level": at((457, 139, 125, 70)),
                "next": at((322, 219, 260, 94)),
                "trt": at((322, 323, 125, 70)), "drought": at((457, 323, 125, 70)),
                "pace": at((322, 403, 260, 70)), "burn": at((322, 483, 260, 70)),
            }, align),
            _el(f"board-{s}", "board", at((602, 84, 344, 664)), slot=slot),
        ]  # fmt: skip

    return _definition(2, [[0, 1]], [
        *side(0, False),
        *side(1, True),
        _el("title", "title", (738, 18, 284, 56)),
        _el("round", "round", (1032, 22, 152, 48), pair=0),
        _el("versus", "versus", (594, 760, 300, 235), pair=0),
        _el("graph", "diff_graph", (906, 760, 424, 174), pair=0),
    ])  # fmt: skip


# ---------------------------------------------------------------- 4 players


def _quadrant(slot: int, right: bool, top: int, gap_field: str) -> list[Element]:
    """One quadrant of the camera layouts: camera | stats | board, mirrored right."""
    s, align = f"s{slot}", ("right" if right else "left")

    def at(box: Box, mirrored: Box | None = None) -> Box:
        if right:
            box = mirrored if mirrored is not None else _mirror(box)
        return _shift(box, dy=top)

    side = _side_stats(s, slot, {
        "score": at((510, 8, 200, 75)),
        "lines": at((510, 89, 97, 48)), "level": at((613, 89, 97, 48)),
        "next": at((510, 143, 200, 64)),
        "trt": at((510, 213, 97, 48)), "drought": at((613, 213, 97, 48)),
    }, align)  # fmt: skip
    if gap_field != "gap":
        for el in side:
            if el["id"] == f"gap-{s}":
                el["props"]["field"] = gap_field
    return [
        _el(f"tag-{s}", "nametag", at((8, 8, 494, 78)), slot=slot, show_round=True),
        # The camera keeps its place at the outer edge in the right quadrant.
        _el(f"cam-{s}", "camera", at((8, 94, 460, 430), (1452, 94, 460, 430)), slot=slot, framed=False),
        *side,
        _el(f"board-{s}", "board", at((718, 8, 239, 459)), slot=slot),
    ]  # fmt: skip


def two_by_one_vs_one_cam() -> dict[str, Any]:
    """Like ``TwoByOneVsOneCam.svelte``: a quadrant per player, two pairs."""
    elements: list[Element] = []
    for row, top in enumerate((0, 540)):
        elements += _quadrant(2 * row, False, top, "gap") + _quadrant(2 * row + 1, True, top, "gap")
    return _definition(4, [[0, 1], [2, 3]], elements)


def four_players_quadrants() -> dict[str, Any]:
    """A quadrant per player, everyone against everyone, ranking in the middle."""
    elements: list[Element] = []
    for row, top in enumerate((0, 540)):
        elements += _quadrant(2 * row, False, top, "to_advance")
        elements += _quadrant(2 * row + 1, True, top, "to_advance")
    for el in elements:  # nametags show the rank instead of a round
        if el["type"] == "nametag":
            el["props"] = {"show_round": False}
    # Between the rows, between the cameras: names only, the scores are beside the boards.
    elements.append(_el("ranking", "ranking", (480, 474, 960, 68), show_points=False))
    return _definition(4, [], elements)


def two_by_one_vs_one() -> dict[str, Any]:
    """Like ``TwoByOneVsOne.svelte``: two matches side by side."""
    elements: list[Element] = [
        _el("title", "title", (741, 16, 216, 56)),
        _el("round", "round", (967, 20, 212, 48)),
    ]
    for pair, dx in ((0, 0), (1, 968)):
        for slot, right in ((2 * pair, False), (2 * pair + 1, True)):
            s, align = f"s{slot}", ("right" if right else "left")

            def at(box: Box, right: bool = right, dx: int = dx) -> Box:
                return _shift(_mirror(box, 968) if right else box, dx)

            def cell(box: Box, right: bool = right, dx: int = dx) -> Box:
                return _shift(box, dx + (560 if right else 0))

            elements += [
                _el(f"board-{s}", "board", at((16, 86, 260, 500)), slot=slot),
                _el(f"next-{s}", "next", at((286, 86, 106, 86)), slot=slot),
                *_panel_stats(
                    s, slot, at((16, 596, 376, 230)), cell((38, 614, 332, 38)), cell((38, 690, 332, 38)),
                    [
                        ("lines", cell((38, 738, 158, 32))), ("level", cell((212, 738, 158, 32))),
                        ("trt", cell((38, 776, 158, 32))), ("drought", cell((212, 776, 158, 32))),
                    ],
                    align, hearts=cell((38, 660, 332, 20)),
                ),
            ]  # fmt: skip
        elements += [
            _el(f"versus-p{pair}", "versus", _shift((386, 146, 232, 247), dx), pair=pair),
            _el(f"graph-p{pair}", "diff_graph", _shift((386, 403, 180, 114), dx), pair=pair),
        ]
    return _definition(4, [[0, 1], [2, 3]], elements)


def four_players() -> dict[str, Any]:
    """Like ``FourPlayers.svelte``: four columns, ranking at the bottom."""
    elements: list[Element] = [
        _el("title", "title", (594, 12, 216, 56)),
        _el("round", "round", (820, 16, 152, 48)),
        _el("ranking", "ranking", (20, 1016, 1880, 52)),
    ]
    for slot in range(4):
        dx, s = slot * 475, f"s{slot}"
        elements += [
            _el(f"board-{s}", "board", _shift((24, 84, 302, 582), dx), slot=slot),
            _el(f"next-{s}", "next", _shift((336, 84, 119, 92), dx), slot=slot),
            *_panel_stats(
                s, slot, _shift((24, 676, 449, 202), dx), _shift((46, 694, 405, 38), dx),
                _shift((46, 742, 405, 38), dx),
                [
                    ("lines", _shift((46, 790, 194, 32), dx)), ("level", _shift((256, 790, 194, 32), dx)),
                    ("trt", _shift((46, 828, 194, 32), dx)), ("drought", _shift((256, 828, 194, 32), dx)),
                ],
                "left",
            ),
            _stat(f"advance-{s}", slot, "to_advance", _shift((24, 888, 449, 64), dx), "center"),
        ]  # fmt: skip
    return _definition(4, [], elements)


# ---------------------------------------------------------------- catalogue

TEMPLATES: tuple[Template, ...] = (
    # 4 players
    Template(
        "2x1v1_cam", "4 Spieler: 2 × 1 gegen 1 (Viertel)", "4 players: 2 × 1 vs 1 (quadrants)",
        "Ein Viertel pro Spieler mit Kamera, Werten und Spielfeld; oben Slot 1 gegen 2, unten 3 gegen 4.",
        "A quadrant per player with camera, stats and board; top slot 1 vs 2, bottom 3 vs 4.",
        two_by_one_vs_one_cam, builtin="2x1v1_cam", players=4, featured=True,
    ),
    Template(
        "4p_quad", "4 Spieler: alle gegen alle (Viertel)", "4 players: everyone vs everyone (quadrants)",
        "Ein Viertel pro Spieler mit Kamera, ohne Paare; Rangliste in der Mitte, Modi wie Top 2 weiter.",
        "A quadrant per player with camera, no pairs; ranking in the middle, modes like top 2 advance.",
        four_players_quadrants, players=4, featured=True,
    ),
    Template(
        "4p", "4 Spieler: Spalten", "4 players: columns",
        "Vier Spalten ohne Paare: Spielfeld und Werte je Spieler, Rangliste unten.",
        "Four columns without pairs: board and stats per player, ranking at the bottom.",
        four_players, builtin="4p", players=4,
    ),
    Template(
        "2x1v1", "4 Spieler: 2 × 1 gegen 1", "4 players: 2 × 1 vs 1",
        "Zwei Paarungen nebeneinander, ohne Kameras.",
        "Two matches side by side, without cameras.",
        two_by_one_vs_one, builtin="2x1v1", players=4,
    ),
    # 2 players
    Template(
        "1v1", "2 Spieler: 1 gegen 1", "2 players: 1 vs 1",
        "Spielfelder außen, Werte innen, Differenz und Verlauf in der Mitte.",
        "Boards outside, stats inside, difference and graph in the middle.",
        one_vs_one, builtin="1v1", players=2, featured=True,
    ),
    Template(
        "1v1_cam", "2 Spieler: 1 gegen 1 mit Kameras", "2 players: 1 vs 1 with cameras",
        "Kamera | Werte | Spielfeld ‖ Spielfeld | Werte | Kamera, Differenz und Verlauf unten.",
        "Camera | stats | board ‖ board | stats | camera, difference and graph below.",
        one_vs_one_cam, builtin="1v1_cam", players=2,
    ),
    # 1 player
    Template(
        "single", "Einzelspieler", "Single player",
        "Kamerafläche links, großes Spielfeld und alle Werte rechts.",
        "Camera space on the left, large board and all stats on the right.",
        single, builtin="single", players=1, featured=True,
    ),
    Template(
        "single_cam", "Einzelspieler mit Kamera", "Single player with camera",
        "Große Kamera mit Namen links, Spielfeld und jeder Wert einzeln rechts.",
        "Large camera with name on the left, board and every value on the right.",
        single_cam, players=1,
    ),
    Template(
        "single_compact", "Einzelspieler kompakt", "Single player compact",
        "Schmale Leiste rechts mit Werten und Spielfeld, z. B. neben der Kamera.",
        "Narrow strip on the right with stats and board, e.g. next to the camera.",
        single_compact, builtin="single_compact", players=1,
    ),
)  # fmt: skip

BY_ID = {t.id: t for t in TEMPLATES}
BY_BUILTIN = {t.builtin: t for t in TEMPLATES if t.builtin}

# settings.show of a built-in layout -> element types/fields it hides when the
# scene is adapted (so the adapted scene looks the same).
SHOW_HIDES: dict[str, tuple[str, ...]] = {
    "header": ("title", "round"),
    "diff_graph": ("diff_graph",),
    "versus": ("versus",),
    "pace": ("stat:pace",),
    "burn": ("stat:burn",),
    "hearts": ("hearts",),
    "next": ("next",),
}


def apply_show(definition: dict[str, Any], show: dict[str, bool]) -> dict[str, Any]:
    """Hide the elements a built-in scene switched off (``settings.show``)."""
    off = {kind for key, kinds in SHOW_HIDES.items() if show.get(key) is False for kind in kinds}
    if not off:
        return definition
    for el in definition["elements"]:
        field = (el.get("props") or {}).get("field")
        if el["type"] in off or (el["type"] == "stat" and f"stat:{field}" in off):
            el["hidden"] = True
    return definition
