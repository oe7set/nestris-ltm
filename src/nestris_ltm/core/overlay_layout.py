"""Own overlay layouts built in the layout builder (``overlay_layouts``).

A definition places elements on the 1920x1080 stage. Elements of a player
refer to a *slot*, head-to-head elements (difference, diff graph) to a
*pair* of slots; the pairs also decide which slots play their rounds
together (``services/scenes.py``), exactly like the built-in layouts.

Everything is validated here (also what an import brings): known element
types, properties per type, unique ids, slots/pairs in range, rectangles on
the stage. ``migrate`` upgrades older schema versions.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from nestris_ltm.core.layouts import Layout

SCHEMA_VERSION = 1
CANVAS_W, CANVAS_H = 1920, 1080
MAX_SLOTS = 8
MAX_PAIRS = 4
MAX_ELEMENTS = 300
# Elements may stick out of the stage a little (shadows, bleed), not more.
MARGIN_W, MARGIN_H = CANVAS_W // 10, CANVAS_H // 10
MIN_SIZE = 8
HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
ID_PATTERN = r"^[A-Za-z0-9_-]{1,32}$"

Align = Literal["left", "center", "right"]
StatField = Literal[
    "score", "lines", "level", "start_level", "trt", "drought", "burn", "pace", "gap", "pieces"
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- element properties


class BoardProps(_Strict):
    pass


class NextProps(_Strict):
    show_label: bool = True


class StatProps(_Strict):
    field: StatField = "score"
    label: str | None = Field(default=None, max_length=24)  # None = the standard label
    show_label: bool = True
    align: Align = "left"
    color: str | None = Field(default=None, pattern=HEX_COLOR)


class NameProps(_Strict):
    align: Align = "left"
    show_rank: bool = False


class HeartsProps(_Strict):
    align: Align = "left"


class NametagProps(_Strict):
    align: Align = "center"
    show_round: bool = False


class CameraProps(_Strict):
    framed: bool = True


class PairProps(_Strict):
    pass


class TitleProps(_Strict):
    text: str | None = Field(default=None, max_length=64)  # None = scene title / round name
    align: Align = "center"


class RoundProps(_Strict):
    align: Align = "center"


class TextProps(_Strict):
    text: str = Field(min_length=1, max_length=200)
    align: Align = "left"
    size: int = Field(default=24, ge=8, le=160)
    color: str | None = Field(default=None, pattern=HEX_COLOR)


class FrameProps(_Strict):
    style: Literal["nes", "panel"] = "nes"


PROPS: dict[str, type[_Strict]] = {
    "board": BoardProps,
    "next": NextProps,
    "stat": StatProps,
    "name": NameProps,
    "hearts": HeartsProps,
    "nametag": NametagProps,
    "camera": CameraProps,
    "versus": PairProps,
    "diff_graph": PairProps,
    "title": TitleProps,
    "round": RoundProps,
    "text": TextProps,
    "frame": FrameProps,
}
SLOT_TYPES = frozenset({"board", "next", "stat", "name", "hearts", "nametag", "camera"})
PAIR_TYPES = frozenset({"versus", "diff_graph"})
# A round element may show the round of one pair (else the scene's first group).
OPTIONAL_PAIR_TYPES = frozenset({"round"})
ElementType = Literal[
    "board", "next", "stat", "name", "hearts", "nametag", "camera",
    "versus", "diff_graph", "title", "round", "text", "frame",
]  # fmt: skip


class Element(_Strict):
    id: str = Field(pattern=ID_PATTERN)
    type: ElementType
    slot: int | None = Field(default=None, ge=0, lt=MAX_SLOTS)
    pair: int | None = Field(default=None, ge=0, lt=MAX_PAIRS)
    x: int = Field(ge=-MARGIN_W, le=CANVAS_W + MARGIN_W)
    y: int = Field(ge=-MARGIN_H, le=CANVAS_H + MARGIN_H)
    w: int = Field(ge=MIN_SIZE, le=CANVAS_W + 2 * MARGIN_W)
    h: int = Field(ge=MIN_SIZE, le=CANVAS_H + 2 * MARGIN_H)
    z: int = Field(default=0, ge=-1000, le=1000)
    hidden: bool = False
    locked: bool = False
    props: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Element:
        if self.type in SLOT_TYPES:
            if self.slot is None:
                raise ValueError(f"{self.type} element {self.id!r} needs a slot")
            if self.pair is not None:
                raise ValueError(f"{self.type} element {self.id!r} takes a slot, not a pair")
        elif self.type in PAIR_TYPES:
            if self.pair is None:
                raise ValueError(f"{self.type} element {self.id!r} needs a pair")
            if self.slot is not None:
                raise ValueError(f"{self.type} element {self.id!r} takes a pair, not a slot")
        elif self.slot is not None or (
            self.pair is not None and self.type not in OPTIONAL_PAIR_TYPES
        ):
            raise ValueError(f"{self.type} element {self.id!r} takes no slot/pair")
        if self.x + self.w < -MARGIN_W or self.x > CANVAS_W + MARGIN_W:
            raise ValueError(f"element {self.id!r} lies outside the stage")
        if self.y + self.h < -MARGIN_H or self.y > CANVAS_H + MARGIN_H:
            raise ValueError(f"element {self.id!r} lies outside the stage")
        # Normalized properties (defaults filled in, unknown keys rejected).
        self.props = PROPS[self.type].model_validate(self.props).model_dump(exclude_none=True)
        return self


class Canvas(_Strict):
    w: Literal[1920] = 1920
    h: Literal[1080] = 1080


class LayoutDefinition(_Strict):
    schema_version: Literal[1] = Field(default=1, alias="schema")
    canvas: Canvas = Field(default_factory=Canvas)
    slots: int = Field(ge=1, le=MAX_SLOTS)
    pairs: list[tuple[int, int]] = Field(default_factory=list, max_length=MAX_PAIRS)
    elements: list[Element] = Field(default_factory=list, max_length=MAX_ELEMENTS)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("pairs")
    @classmethod
    def _pairs(cls, pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
        seen: set[int] = set()
        for a, b in pairs:
            if a == b or a in seen or b in seen:
                raise ValueError("every slot belongs to at most one pair, never twice")
            seen.update((a, b))
        return pairs

    @model_validator(mode="after")
    def _check(self) -> LayoutDefinition:
        for a, b in self.pairs:
            if not (0 <= a < self.slots and 0 <= b < self.slots):
                raise ValueError(f"pair ({a}, {b}) refers to a slot beyond {self.slots}")
        ids: set[str] = set()
        for i, e in enumerate(self.elements):
            # "elements[i]:" lets errors() point the builder at the element.
            if e.id in ids:
                raise ValueError(f"elements[{i}]: element id {e.id!r} is used twice")
            ids.add(e.id)
            if e.slot is not None and e.slot >= self.slots:
                raise ValueError(f"elements[{i}]: slot {e.slot + 1} does not exist")
            if e.pair is not None and e.pair >= len(self.pairs):
                raise ValueError(f"elements[{i}]: pair {e.pair + 1} does not exist")
        return self

    def dump(self) -> dict[str, Any]:
        """JSON-shaped (pairs as lists), exactly what the database stores."""
        return self.model_dump(by_alias=True, mode="json")


def migrate(raw: Any) -> dict[str, Any]:
    """Older schema versions -> the current one (only version 1 exists yet)."""
    if not isinstance(raw, dict):
        raise ValueError("a layout definition is a JSON object")
    version = raw.get("schema", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ValueError(f"layout schema {version!r} is not supported by this version")
    return raw


def parse(raw: Any) -> LayoutDefinition:
    """Validate a definition (from the builder, the database or an import)."""
    return LayoutDefinition.model_validate(migrate(raw))


_ELEMENT_REF = re.compile(r"elements\[(\d+)\]")


def errors(exc: ValidationError) -> list[dict[str, Any]]:
    """Validation errors for the builder: element index and message."""
    out = []
    for err in exc.errors():
        loc = err.get("loc", ())
        index = loc[1] if len(loc) > 1 and loc[0] == "elements" else None
        if index is None and (m := _ELEMENT_REF.search(str(err.get("msg", "")))):
            index = int(m[1])
        out.append(
            {"element": index, "field": ".".join(str(p) for p in loc), "message": err["msg"]}
        )
    return out


CUSTOM_PREFIX = "custom:"


def layout_key(layout_id: str) -> str:
    return f"{CUSTOM_PREFIX}{layout_id}"


def to_layout(layout_id: str, name: str, description: str, definition: LayoutDefinition) -> Layout:
    """The engine's view of an own layout (slots, pairs) like a built-in one."""
    return Layout(
        id=layout_key(layout_id),
        slots=definition.slots,
        title_de=name,
        title_en=name,
        description_de=description,
        description_en=description,
        pairs=tuple(tuple(p) for p in definition.pairs),  # type: ignore[misc]
        supports_modes=not definition.pairs and definition.slots > 2,
    )
