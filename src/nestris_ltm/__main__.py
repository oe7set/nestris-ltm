"""Command line entry point.

nestris-ltm                 run with the tray/GUI shell (default)
nestris-ltm --headless      run the core without any GUI
nestris-ltm migrate         create/upgrade the database and exit
nestris-ltm config-path     print the config file location
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

from nestris_ltm import __version__
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
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("migrate", help="create/upgrade the database schema and exit")
    sub.add_parser("config-path", help="print the config file location and exit")
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
        sim = StationSimulator(settings.mqtt, station, card_name=name, speed=args.speed)
        sims.append(sim.run(rotated, loop=args.loop))
    await asyncio.gather(*sims)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "config-path":
        print(args.config)
        return 0

    settings = load_settings(args.config)
    configure_logging(settings)
    log.info(
        "starting", version=__version__, config=str(args.config), config_found=args.config.is_file()
    )

    if args.command == "simulate":
        run_async(_simulate(settings, args))
        return 0

    if args.command == "migrate":
        run_async(_migrate(settings))
        return 0

    if args.headless:
        _run_headless(settings)
        return 0

    # The Qt shell arrives in phase 3; until then fall back to headless.
    log.warning("GUI shell not available yet, running headless")
    _run_headless(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
