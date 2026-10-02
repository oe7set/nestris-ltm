from __future__ import annotations

import random
from pathlib import Path

import pytest

from nestris_ltm.core import playfield
from nestris_ltm.core.ngf import (
    NgfError,
    NgfFrame,
    decode_frame,
    encode_file,
    encode_frame,
    iter_frames,
    split_games,
)

SAMPLES = sorted(Path(__file__).resolve().parents[2].glob("*.ngf"))


def _frame(ctime: int, gameid: int = 1, **kw: object) -> NgfFrame:
    rng = random.Random(ctime)
    return NgfFrame(
        gameid=gameid,
        ctime_ms=ctime,
        score=kw.get("score", 123456),  # type: ignore[arg-type]
        lines=kw.get("lines", 42),  # type: ignore[arg-type]
        level=kw.get("level", 18),  # type: ignore[arg-type]
        preview="I",
        cur_piece="T",
        counts=[1, 2, 3, 4, 5, 6, 1023 - 1],
        field=[rng.randint(0, 3) for _ in range(playfield.CELLS)],
    )


def test_v3_roundtrip() -> None:
    frame = _frame(0x0ABCDEF)
    data = encode_frame(frame)
    assert len(data) == 73
    decoded, size = decode_frame(data)
    assert size == 73
    assert decoded == frame


def test_unknown_values_use_sentinels() -> None:
    frame = NgfFrame(ctime_ms=5)  # everything unknown
    decoded, _ = decode_frame(encode_frame(frame))
    assert decoded.score is None and decoded.lines is None and decoded.level is None
    assert decoded.preview is None and decoded.cur_piece is None
    assert decoded.counts == [None] * 7


def test_file_roundtrip_gzip_and_split() -> None:
    frames = [_frame(t, gameid=1) for t in range(0, 500, 100)]
    frames += [_frame(t, gameid=2) for t in range(0, 300, 100)]
    for compress in (True, False):
        decoded = list(iter_frames(encode_file(frames, compress=compress)))
        assert decoded == frames
        assert [len(g) for g in split_games(decoded)] == [5, 3]


def test_truncated_and_unknown_version() -> None:
    data = encode_frame(_frame(1))
    with pytest.raises(NgfError):
        decode_frame(data[:40])
    with pytest.raises(NgfError):
        decode_frame(bytes([0b111 << 5]) + data[1:])


@pytest.mark.skipif(not SAMPLES, reason="no sample .ngf files in the workspace root")
def test_sample_recordings_decode() -> None:
    for path in SAMPLES:
        frames = list(iter_frames(path.read_bytes()))
        assert frames
        last = frames[-1]
        assert last.score is not None and last.score > 0
        assert all(f.version == frames[0].version for f in frames)
