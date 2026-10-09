"""Remote station configuration: the pure parts.

A station's remote config is the template for all stations deep-merged with
the station's own overrides. It is sent complete (``station_config`` /
``set``) with a revision that is a hash of the values, so equal values always
carry the same revision and the station can tell a repeat from a change.

The allowlist mirrors ``ALLOWED`` in nestris-core
``crates/nestris-station/src/remote.rs``; the station has the last word.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

# Remote-settable keys: exact paths, or prefixes ending in ".".
ALLOWED: tuple[str, ...] = (
    "station.name",
    "capture.",
    "rfid.enabled",
    "rfid.port",
    "mqtt.live_max_hz",
    "mqtt.live_playfield",
    "mqtt.status_interval_s",
    "recording.enabled",
    "recording.gzip",
    "recording.keep_days",
    "recording.max_gb",
    "session.",
    "integrity.",
    "engine.",
    "log.level",
)


class ConfigError(ValueError):
    """Values that can never be sent (not a table, keys not settable)."""


def leaf_paths(values: dict[str, Any], prefix: str = "") -> list[str]:
    """Dotted paths of every leaf (an empty table is a leaf)."""
    out: list[str] = []
    for key, value in values.items():
        here = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and value:
            out.extend(leaf_paths(value, here))
        else:
            out.append(here)
    return out


def is_allowed(key: str, allowed: tuple[str, ...] | list[str] = ALLOWED) -> bool:
    for pattern in allowed:
        if pattern.endswith("."):
            if key.startswith(pattern) and len(key) > len(pattern):
                return True
        elif key == pattern:
            return True
    return False


def check(values: Any, allowed: tuple[str, ...] | list[str] = ALLOWED) -> dict[str, Any]:
    """The values as a table, or :class:`ConfigError` naming the bad keys."""
    if not isinstance(values, dict):
        raise ConfigError("config values must be a table")
    denied = [k for k in leaf_paths(values) if not is_allowed(k, allowed)]
    if denied:
        raise ConfigError("not settable remotely: " + ", ".join(sorted(denied)))
    return values


def prune(values: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` leaves and tables left empty (a removed override)."""
    out: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            sub = prune(value)
            if sub:
                out[key] = sub
        elif value is not None:
            out[key] = value
    return out


def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep merge: tables merge, everything else replaces."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def revision(values: dict[str, Any]) -> int:
    """A stable revision of the values (48 bits: exact in JSON numbers)."""
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(canonical.encode()).digest()[:6], "big")


def get_path(values: dict[str, Any], path: str) -> Any:
    node: Any = values
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def needs_send(desired_rev: int, reported_rev: int | None, reported_state: str | None) -> bool:
    """Whether the station still has to get the desired set.

    A set the station already holds, is about to apply, or rejected (same
    revision: it would only reject it again) is not resent.
    """
    if reported_rev != desired_rev:
        return True
    return reported_state not in ("applied", "pending", "restarting", "rejected")
