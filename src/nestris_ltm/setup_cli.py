"""Setup commands used by the installer and for maintenance.

- ``configure``: change single settings in ``config.toml`` (other keys and
  values already in the file are kept).
- ``check``: can NestrisLTM reach PostgreSQL and the MQTT broker, and is its
  HTTP port free (or already served by a running NestrisLTM)?
- ``autostart``: the per-user Windows autostart entry.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

import tomli_w

from nestris_ltm.config import Settings, load_settings


def add_parsers(sub: Any) -> None:
    conf = sub.add_parser("configure", help="change settings in config.toml (used by installers)")
    conf.add_argument("--db-host")
    conf.add_argument("--db-port", type=int)
    conf.add_argument("--db-user")
    conf.add_argument("--db-password", help="PostgreSQL password ('' clears it)")
    conf.add_argument("--db-name")
    conf.add_argument("--mqtt-host")
    conf.add_argument("--mqtt-port", type=int)
    conf.add_argument("--http-port", type=int)

    check = sub.add_parser("check", help="check database, MQTT broker and HTTP port")
    check.add_argument("--json", action="store_true", help="machine-readable output")

    auto = sub.add_parser("autostart", help="start NestrisLTM in the tray when this user signs in")
    auto.add_argument("state", choices=["on", "off", "status"])


# ---------------------------------------------------------------- configure

_KEYS = {
    "db_host": ("database", "host"),
    "db_port": ("database", "port"),
    "db_user": ("database", "user"),
    "db_password": ("database", "password"),
    "db_name": ("database", "name"),
    "mqtt_host": ("mqtt", "host"),
    "mqtt_port": ("mqtt", "port"),
    "http_port": ("http", "port"),
}


def configure(args: argparse.Namespace) -> int:
    path: Path = args.config
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    changed = []
    for attr, (section, key) in _KEYS.items():
        value = getattr(args, attr)
        if value is None:
            continue
        data.setdefault(section, {})[key] = value.strip() if isinstance(value, str) else value
        changed.append(f"{section}.{key}")
    # Validate before writing: a typo must not leave a broken config behind.
    Settings.config_file = None
    try:
        Settings.model_validate(data)
    except ValueError as exc:
        print(f"Invalid settings: {exc}", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
    print(f"Saved {', '.join(changed) or 'nothing'} to {path}")
    return 0


# ---------------------------------------------------------------- check


async def _check_db(settings: Settings) -> dict[str, Any]:
    import asyncpg

    db = settings.database
    try:
        conn = await asyncpg.connect(
            host=db.host,
            port=db.port,
            user=db.user,
            password=db.password.get_secret_value() or None,
            database="postgres",
            timeout=db.connect_timeout_s,
        )
    except Exception as exc:
        where = f"{db.user}@{db.host}:{db.port}"
        return {"ok": False, "detail": f"{where}: {type(exc).__name__}: {exc}"}
    try:
        version = await conn.fetchval("SHOW server_version")
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db.name)
    finally:
        await conn.close()
    note = "exists" if exists else "will be created on first start"
    detail = f"PostgreSQL {version} at {db.host}:{db.port}; '{db.name}' {note}"
    return {"ok": True, "detail": detail}


async def _check_mqtt(settings: Settings) -> dict[str, Any]:
    import aiomqtt

    m = settings.mqtt
    if not m.enabled:
        return {"ok": True, "detail": "MQTT disabled in the config"}
    try:
        # Its own client id: reusing the host's id would disconnect a running NestrisLTM.
        async with (
            asyncio.timeout(8),
            aiomqtt.Client(
                m.host,
                m.port,
                identifier="nestris-ltm-check",
                username=m.username,
                password=m.password.get_secret_value() if m.password else None,
            ),
        ):
            pass
    except Exception as exc:
        return {"ok": False, "detail": f"{m.host}:{m.port}: {type(exc).__name__}: {exc}"}
    return {"ok": True, "detail": f"broker at {m.host}:{m.port} accepts connections"}


def _check_http(settings: Settings) -> dict[str, Any]:
    port = settings.http.port
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as r:
            body = json.loads(r.read())
        running = f"NestrisLTM {body.get('version', '?')} is running"
        return {"ok": True, "detail": f"port {port}: {running}"}
    except Exception:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return {"ok": False, "detail": f"port {port} is used by another program"}
    return {"ok": True, "detail": f"port {port} is free"}


async def _check_all(settings: Settings) -> dict[str, dict[str, Any]]:
    db, mqtt = await asyncio.gather(_check_db(settings), _check_mqtt(settings))
    return {"database": db, "mqtt": mqtt, "http": _check_http(settings)}


def check(args: argparse.Namespace) -> int:
    from nestris_ltm.runtime import run_async

    settings = load_settings(args.config)
    results = run_async(_check_all(settings))
    ok = all(r["ok"] for r in results.values())
    if args.json:
        print(json.dumps({"ok": ok, "config": str(args.config), **results}, indent=2))
    else:
        print(f"Config: {args.config}{'' if args.config.is_file() else ' (not found, defaults)'}")
        for name, r in results.items():
            print(f"[{'OK' if r['ok'] else 'FAIL'}] {name}: {r['detail']}")
    return 0 if ok else 1


# ---------------------------------------------------------------- autostart


def autostart_cmd(args: argparse.Namespace) -> int:
    from nestris_ltm.shell import autostart

    if not autostart.is_supported():
        print("Autostart is only supported on Windows.", file=sys.stderr)
        return 2
    if args.state != "status":
        autostart.set_enabled(args.state == "on")
    print("on" if autostart.is_enabled() else "off")
    return 0
