"""Command line entry point.

nestris-ltm                 run with the tray/GUI shell (default)
nestris-ltm --headless      run the core without any GUI
nestris-ltm migrate         create/upgrade the database and exit
nestris-ltm config-path     print the config file location
nestris-ltm configure ...   change settings in config.toml (used by the installer)
nestris-ltm check           check database, MQTT broker and HTTP port
nestris-ltm autostart on|off|status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

from nestris_ltm import __version__, setup_cli
from nestris_ltm.config import Settings, default_config_path, load_settings
from nestris_ltm.logging_setup import configure_logging
from nestris_ltm.runtime import run_async

log = structlog.get_logger("nestris_ltm")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nestris-ltm", description="NestrisLTM host application")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        help="config file (default: %(default)s)",
        default=default_config_path(),
    )
    parser.add_argument("--headless", action="store_true", help="run without the GUI shell")
    parser.add_argument(
        "--minimized", action="store_true", help="start hidden in the tray (used by autostart)"
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("migrate", help="create/upgrade the database schema and exit")
    sub.add_parser("config-path", help="print the config file location and exit")
    admin = sub.add_parser(
        "set-admin-password", help="create an admin account or reset its password (asks for it)"
    )
    admin.add_argument("username")
    setup_cli.add_parsers(sub)
    sim = sub.add_parser("simulate", help="replay NGF recordings as MQTT stations")
    sim.add_argument("files", nargs="+", type=Path, help=".ngf / .ngf.gz recordings")
    sim.add_argument(
        "--stations",
        default="station-sim",
        help="comma-separated station ids, one simulator each (default: %(default)s)",
    )
    sim.add_argument(
        "--names", default="", help="comma-separated card names per station (empty = no card)"
    )
    sim.add_argument("--speed", type=float, default=1.0, help="playback speed factor")
    sim.add_argument("--live-hz", type=float, default=60.0, help="live messages per second")
    sim.add_argument("--loop", action="store_true", help="repeat the games forever")
    return parser


async def _migrate(settings: Settings) -> None:
    from nestris_ltm.db.bootstrap import bootstrap
    from nestris_ltm.db.session import create_engine

    engine = create_engine(settings.database)
    try:
        await bootstrap(settings.database, engine)
    finally:
        await engine.dispose()


def _run_headless(settings: Settings) -> None:
    from nestris_ltm.runtime import Runtime

    runtime = Runtime(settings)
    run_async(runtime.serve())


async def _set_admin_password(settings: Settings, username: str, password: str) -> bool:
    """Returns True if the account was created, False if its password was reset."""
    from sqlalchemy import func, select

    from nestris_ltm.db.bootstrap import bootstrap
    from nestris_ltm.db.models import AdminUser
    from nestris_ltm.db.session import create_engine, create_session_factory
    from nestris_ltm.services import audit
    from nestris_ltm.services.auth import hash_password

    engine = create_engine(settings.database)
    try:
        await bootstrap(settings.database, engine)
        async with create_session_factory(engine)() as session, session.begin():
            user = await session.scalar(
                select(AdminUser).where(func.lower(AdminUser.username) == username.lower())
            )
            created = user is None
            if user is None:
                user = AdminUser(username=username, password_hash=hash_password(password))
                session.add(user)
                await session.flush()
            else:
                user.password_hash = hash_password(password)
            await audit.record(
                session,
                actor="cli",
                action="create" if created else "password",
                entity="admin",
                entity_id=user.id,
            )
        return created
    finally:
        await engine.dispose()


async def _simulate(settings: Settings, args: argparse.Namespace) -> None:
    import asyncio

    from nestris_ltm.ingest.simulator import StationSimulator, load_games

    games = load_games(args.files)
    if not games:
        raise SystemExit("no playable games found in the given files")
    stations = [s.strip() for s in args.stations.split(",") if s.strip()]
    names = [n.strip() or None for n in args.names.split(",")] if args.names else []
    sims = []
    for i, station in enumerate(stations):
        # Each station starts with a different game so their scores differ.
        rotated = games[i % len(games) :] + games[: i % len(games)]
        name = names[i] if i < len(names) else None
        sim = StationSimulator(
            settings.mqtt, station, card_name=name, speed=args.speed, live_hz=args.live_hz
        )
        sims.append(sim.run(rotated, loop=args.loop))
    await asyncio.gather(*sims)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "config-path":
        print(args.config)
        return 0
    if args.command == "configure":
        return setup_cli.configure(args)
    if args.command == "check":
        return setup_cli.check(args)
    if args.command == "autostart":
        return setup_cli.autostart_cmd(args)

    settings = load_settings(args.config)
    configure_logging(settings)
    log.info(
        "starting", version=__version__, config=str(args.config), config_found=args.config.is_file()
    )

    if args.command == "set-admin-password":
        import getpass

        password = getpass.getpass(f"New password for {args.username}: ")
        if len(password) < 8:
            print("The password must have at least 8 characters.", file=sys.stderr)
            return 2
        if getpass.getpass("Repeat: ") != password:
            print("The passwords do not match.", file=sys.stderr)
            return 2
        created = run_async(_set_admin_password(settings, args.username, password))
        print("Admin account created." if created else "Password changed.")
        return 0

    if args.command == "simulate":
        run_async(_simulate(settings, args))
        return 0

    if args.command == "migrate":
        run_async(_migrate(settings))
        return 0

    if args.headless:
        _run_headless(settings)
        return 0

    try:
        from nestris_ltm.shell.app import run_shell
    except ImportError as exc:  # e.g. PySide6 missing on a server install
        log.warning("GUI shell unavailable, running headless", error=str(exc))
        _run_headless(settings)
        return 0
    return run_shell(settings, args.config, minimized=args.minimized)


if __name__ == "__main__":
    sys.exit(main())
