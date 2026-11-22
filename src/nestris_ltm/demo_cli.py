"""``nestris-ltm demo-scan`` / ``demo-purge``: attract-mode demos in the database.

demo-scan                     list the stored games that are demos (dry run)
demo-scan --apply             flag them (hidden everywhere, one audit entry each)
demo-scan --suggest           groups of identical results: demos of ROMs
                              without a fingerprint yet
demo-scan --suggest --export DIR
                              also save up to 5 recordings per group as .ngf.gz,
                              for ``nestris demo learn`` (nestris-core)
demo-purge                    list the flagged demos (dry run)
demo-purge --yes              delete them with frames and recordings
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nestris_ltm.config import Settings


def add_parsers(sub: Any) -> None:
    scan = sub.add_parser("demo-scan", help="find attract-mode demo games in the database")
    scan.add_argument("--apply", action="store_true", help="flag the demos found (else dry run)")
    scan.add_argument(
        "--suggest", action="store_true", help="list groups of identical results (unknown demos)"
    )
    scan.add_argument("--min-count", type=int, default=5, help="group size for --suggest")
    scan.add_argument("--export", type=Path, help="with --suggest: save recordings here")
    purge = sub.add_parser("demo-purge", help="delete the games flagged as demos")
    purge.add_argument("--yes", action="store_true", help="really delete (else dry run)")


def _line(game: Any, reason: str) -> str:
    started = game.started_at.strftime("%Y-%m-%d %H:%M") if game.started_at else "-"
    return (
        f"  #{game.id:<6} {game.station_id or '-':<14} {started}  "
        f"score {game.score if game.score is not None else '-':>7}  "
        f"lines {game.lines if game.lines is not None else '-':>4}  {reason}"
    )


async def scan(settings: Settings, args: argparse.Namespace) -> int:
    from nestris_ltm.db.bootstrap import bootstrap
    from nestris_ltm.db.session import create_engine, create_session_factory
    from nestris_ltm.services import demo, recordings

    engine = create_engine(settings.database)
    try:
        await bootstrap(settings.database, engine)
        factory = create_session_factory(engine)
        if args.suggest:
            async with factory() as session:
                clusters = await demo.suggest(session, min_count=args.min_count)
                if not clusters:
                    print(f"No result occurs {args.min_count} times or more.")
                for c in clusters:
                    print(
                        f"{c.count:>5}x  score {c.score:>7}  lines {c.lines}  "
                        f"start level {c.start_level}  end level {c.end_level}  "
                        f"games {', '.join(str(i) for i in c.game_ids[:8])}"
                    )
                    if args.export is None:
                        continue
                    args.export.mkdir(parents=True, exist_ok=True)
                    for game_id in c.game_ids[:5]:
                        found = await recordings.recording_bytes(session, game_id)
                        if found is None:
                            continue
                        path = args.export / f"cluster-{c.score}-{c.lines}-game-{game_id}.ngf.gz"
                        path.write_bytes(found[0])
                        print(f"        saved {path}")
            return 0
        async with factory() as session, session.begin():
            hits = await demo.scan(session, apply=args.apply)
            for hit in hits:
                print(_line(hit.game, hit.match.reason))
            if not args.apply:
                await session.rollback()
        if args.apply:
            print(f"{len(hits)} games flagged as demo (hidden everywhere).")
            if hits:
                print(
                    "Check them in the admin UI (Games, filter Demo), then: nestris-ltm demo-purge"
                )
        else:
            print(f"{len(hits)} demo games found (dry run).")
            print("Flag them with: nestris-ltm demo-scan --apply")
        return 0
    finally:
        await engine.dispose()


async def purge(settings: Settings, args: argparse.Namespace) -> int:
    from nestris_ltm.db.bootstrap import bootstrap
    from nestris_ltm.db.session import create_engine, create_session_factory
    from nestris_ltm.services import demo

    engine = create_engine(settings.database)
    try:
        await bootstrap(settings.database, engine)
        async with create_session_factory(engine)() as session, session.begin():
            games = await demo.flagged(session)
            for game in games:
                print(_line(game, game.demo_reason or ""))
            if not args.yes:
                print(f"{len(games)} flagged demos (dry run).")
                print("Delete them with: nestris-ltm demo-purge --yes")
                await session.rollback()
                return 0
            count = await demo.purge(session)
        print(f"{count} demo games deleted.")
        return 0
    finally:
        await engine.dispose()
