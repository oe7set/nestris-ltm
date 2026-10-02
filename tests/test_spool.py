from __future__ import annotations

from pathlib import Path

from nestris_ltm.ingest.spool import EventSpool


def test_append_load_complete_in_order(tmp_path: Path) -> None:
    spool = EventSpool(tmp_path)
    first = spool.append("station-1", "event/game_start", '{"a":1}')
    second = spool.append("station-1", "event/game_end", '{"b":2}')

    assert spool.pending() == [first, second]
    event = spool.load(first)
    assert (event.station, event.kind, event.payload) == (
        "station-1",
        "event/game_start",
        '{"a":1}',
    )

    spool.complete(first)
    assert spool.pending() == [second]


def test_fail_moves_file_with_reason(tmp_path: Path) -> None:
    spool = EventSpool(tmp_path)
    path = spool.append("s", "event/game_end", "{}")
    target = spool.fail(path, "bad payload")
    assert spool.pending() == []
    assert spool.failed() == [target]
    assert target.with_suffix(".reason.txt").read_text(encoding="utf-8") == "bad payload"


def test_cleanup_temp(tmp_path: Path) -> None:
    spool = EventSpool(tmp_path)
    (tmp_path / "x.tmp").write_text("half", encoding="utf-8")
    spool.cleanup_temp()
    assert not (tmp_path / "x.tmp").exists()
