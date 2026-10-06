"""Appearance settings of an overlay scene (``scenes.settings``), validated.

Everything an admin can set is checked here, so the database only holds
values the overlay understands, and an imported file cannot smuggle in
anything else. The NES style is the default.

``replay`` is internal: only ``POST /api/scenes/<slug>/replay`` sets it, it is
never accepted from a client and never exported.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Style = Literal["nes", "modern"]
HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
DEFAULT_STYLE: Style = "nes"

# Colours of the overlay a scene may override (CSS variables of the stage).
THEME_KEYS = ("accent", "frame", "inner", "panel", "text", "good", "bad")
# Blocks of the built-in layouts that can be switched off.
SHOW_KEYS = ("header", "diff_graph", "versus", "pace", "burn", "hearts", "next")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Theme(_Strict):
    accent: str | None = Field(default=None, pattern=HEX_COLOR)
    frame: str | None = Field(default=None, pattern=HEX_COLOR)
    inner: str | None = Field(default=None, pattern=HEX_COLOR)
    panel: str | None = Field(default=None, pattern=HEX_COLOR)
    text: str | None = Field(default=None, pattern=HEX_COLOR)
    good: str | None = Field(default=None, pattern=HEX_COLOR)
    bad: str | None = Field(default=None, pattern=HEX_COLOR)


class Show(_Strict):
    header: bool = True
    diff_graph: bool = True
    versus: bool = True
    pace: bool = True
    burn: bool = True
    hearts: bool = True
    next: bool = True


class SceneSettings(_Strict):
    style: Style = DEFAULT_STYLE
    lang: Literal["de", "en"] = "de"
    background: Literal["transparent", "dark"] = "transparent"
    camera_frames: bool = False
    title: str | None = Field(default=None, max_length=64)
    theme: Theme = Field(default_factory=Theme)
    show: Show = Field(default_factory=Show)
    # Internal (set by the replay endpoint only).
    replay: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    def stored(self) -> dict[str, Any]:
        """What goes into ``scenes.settings`` (no empty optional values)."""
        data = self.model_dump(exclude_none=True)
        data["theme"] = self.theme.model_dump(exclude_none=True)
        return data

    def appearance(self) -> dict[str, Any]:
        """The exportable part: everything but the internal replay state."""
        data = self.stored()
        data.pop("replay", None)
        return data


def from_client(
    raw: dict[str, Any] | None, keep_replay: dict[str, Any] | None = None
) -> SceneSettings:
    """Validate settings sent by the admin UI or an import (strict).

    A client never sets ``replay``; the scene's current replay (if any) is kept.
    Raises ``ValueError`` (pydantic ``ValidationError``) on anything unknown or invalid.
    """
    data = dict(raw or {})
    data.pop("replay", None)
    settings = SceneSettings.model_validate(data)
    if keep_replay is not None:
        settings.replay = keep_replay
    return settings


def normalize(raw: Any) -> tuple[SceneSettings, list[str]]:
    """Stored settings of any age -> valid settings + what was dropped.

    Unknown keys and invalid values are dropped one by one (falling back to the
    default), so an old or hand-edited row never breaks a scene.
    """
    data = dict(raw) if isinstance(raw, dict) else {}
    dropped: list[str] = []
    for key in list(data):
        if key not in SceneSettings.model_fields:
            dropped.append(key)
            del data[key]
    for nested, model in (("theme", Theme), ("show", Show)):
        value = data.get(nested)
        if value is None:
            continue
        if not isinstance(value, dict):
            dropped.append(nested)
            del data[nested]
            continue
        clean = {}
        for key, item in value.items():
            try:
                model.model_validate({key: item})
            except ValidationError:
                dropped.append(f"{nested}.{key}")
                continue
            clean[key] = item
        data[nested] = clean
    for key in list(data):
        if key in ("theme", "show"):
            continue
        try:
            SceneSettings.model_validate({key: data[key]})
        except ValidationError:
            dropped.append(key)
            del data[key]
    return SceneSettings.model_validate(data), dropped
