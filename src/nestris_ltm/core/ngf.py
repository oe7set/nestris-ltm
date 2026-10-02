"""NestrisChamps NGF codec (frame versions 1-3 read, version 3 written).

A Python port of ``nestris-core/crates/nestris-ngf/src/codec.rs``; see
``nestris-core/docs/NGF.md`` for the format. Files are a plain
concatenation of fixed-size frames, optionally gzip-compressed as a whole
(detected by the ``1f 8b`` magic, not the file name).
"""

from __future__ import annotations

import gzip
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from nestris_ltm.core import playfield

PIECES = "TJZOSLI"  # NGF piece codes 0..6; 7 = none/unknown
FRAME_SIZES = {1: 71, 2: 72, 3: 73}
MAX_CTIME_MS = (1 << 28) - 1

_SENTINEL_SCORE = {1: 0x1FFFFF, 2: 0xFFFFFF}
_SENTINEL_LINES = {1: 0x1FF, 2: 0xFFF}
_SENTINEL_LEVEL = {1: 0x3F, 2: 0xFF}
_SENTINEL_COUNT = {1: 0xFF, 2: 0x1FF, 3: 0x3FF}
_SENTINEL_DAS = 0x1F
_PIECE_NONE = 7


class NgfError(ValueError):
    pass


@dataclass(slots=True)
class NgfFrame:
    version: int = 3
    game_type: int = 1
    player_num: int = 0
    gameid: int = 0
    ctime_ms: int = 0
    score: int | None = None
    lines: int | None = None
    level: int | None = None
    instant_das: int | None = None
    cur_piece_das: int | None = None
    preview: str | None = None
    cur_piece: str | None = None
    # Piece counts in order T J Z O S L I.
    counts: list[int | None] = field(default_factory=lambda: [None] * 7)
    # 200 cell ids, row-major from the top-left.
    field: list[int] = field(default_factory=lambda: [0] * playfield.CELLS)


def _piece(code: int) -> str | None:
    return PIECES[code] if code < len(PIECES) else None


def _code(piece: str | None) -> int:
    if piece is None:
        return _PIECE_NONE
    index = PIECES.find(piece)
    return index if index >= 0 else _PIECE_NONE


def _or_none(value: int, sentinel: int) -> int | None:
    return None if value == sentinel else value


def decode_frame(buf: bytes | memoryview, offset: int = 0) -> tuple[NgfFrame, int]:
    """Decode the frame at ``offset``. Returns the frame and its size."""
    if offset >= len(buf):
        raise NgfError("truncated: no frame header")
    version = (buf[offset] & 0b1110_0000) >> 5
    size = FRAME_SIZES.get(version)
    if size is None:
        raise NgfError(f"unknown frame version {version} at offset {offset}")
    if len(buf) - offset < size:
        raise NgfError(f"truncated frame at offset {offset}: need {size} bytes")
    f = bytes(buf[offset : offset + size])

    frame = NgfFrame(
        version=version,
        game_type=(f[0] & 0b0001_1000) >> 3,
        player_num=f[0] & 0b111,
        gameid=f[1] << 8 | f[2],
        ctime_ms=f[3] << 20 | f[4] << 12 | f[5] << 4 | (f[6] & 0xF0) >> 4,
    )

    if version >= 2:
        frame.lines = _or_none((f[6] & 0x0F) << 8 | f[7], _SENTINEL_LINES[2])
        frame.level = _or_none(f[8], _SENTINEL_LEVEL[2])
        frame.score = _or_none(f[9] << 16 | f[10] << 8 | f[11], _SENTINEL_SCORE[2])
        frame.counts = [_or_none(c, _SENTINEL_COUNT[version]) for c in _counts(f, version)]
        field_start = 23 if version == 3 else 22
    else:
        score = (f[7] & 0x0F) << 17 | f[8] << 9 | f[9] << 1 | (f[10] & 0x80) >> 7
        frame.score = _or_none(score, _SENTINEL_SCORE[1])
        frame.lines = _or_none((f[10] & 0x7F) << 2 | (f[11] & 0xC0) >> 6, _SENTINEL_LINES[1])
        frame.level = _or_none(f[11] & 0x3F, _SENTINEL_LEVEL[1])
        frame.counts = [_or_none(f[14 + i], _SENTINEL_COUNT[1]) for i in range(7)]
        field_start = 21

    frame.instant_das = _or_none((f[12] & 0b1111_1000) >> 3, _SENTINEL_DAS)
    frame.preview = _piece(f[12] & 0b111)
    frame.cur_piece_das = _or_none((f[13] & 0b1111_1000) >> 3, _SENTINEL_DAS)
    frame.cur_piece = _piece(f[13] & 0b111)
    frame.field = playfield.unpack(f[field_start : field_start + playfield.PACKED_SIZE])
    return frame, size


def _counts(f: bytes, version: int) -> list[int]:
    """Unpack the seven piece counters (10 bits each in v3, 9 bits in v2)."""
    width = 10 if version == 3 else 9
    acc = int.from_bytes(f[14:23] if version == 3 else f[14:22], "big")
    total_bits = (9 if version == 3 else 8) * 8
    return [(acc >> (total_bits - width * (i + 1))) & ((1 << width) - 1) for i in range(7)]


def encode_frame(frame: NgfFrame) -> bytes:
    """Encode as a version-3 frame (73 bytes)."""
    ctime = min(max(frame.ctime_ms, 0), MAX_CTIME_MS)
    lines = _SENTINEL_LINES[2] if frame.lines is None else frame.lines & 0xFFF
    level = _SENTINEL_LEVEL[2] if frame.level is None else frame.level & 0xFF
    score = _SENTINEL_SCORE[2] if frame.score is None else min(frame.score, 0xFFFFFE)
    das = _SENTINEL_DAS if frame.instant_das is None else frame.instant_das & 0x1F
    cur_das = _SENTINEL_DAS if frame.cur_piece_das is None else frame.cur_piece_das & 0x1F

    out = bytearray()
    out.append(3 << 5 | (frame.game_type & 0b11) << 3 | (frame.player_num & 0b111))
    out += (frame.gameid & 0xFFFF).to_bytes(2, "big")
    out += bytes(
        [
            ctime >> 20 & 0xFF,
            ctime >> 12 & 0xFF,
            ctime >> 4 & 0xFF,
            (ctime & 0x0F) << 4 | lines >> 8,
        ]
    )
    out += bytes([lines & 0xFF, level])
    out += score.to_bytes(3, "big")
    out.append(das << 3 | _code(frame.preview))
    out.append(cur_das << 3 | _code(frame.cur_piece))

    acc = 0
    for c in frame.counts:
        acc = acc << 10 | (_SENTINEL_COUNT[3] if c is None else min(c, 0x3FE))
    out += (acc << 2).to_bytes(9, "big")  # 70 bits + 2 bits padding
    out += playfield.pack(frame.field)
    assert len(out) == FRAME_SIZES[3]
    return bytes(out)


def decompress(data: bytes) -> bytes:
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def iter_frames(data: bytes) -> Iterator[NgfFrame]:
    """Decode every frame of an NGF file (raw or gzip)."""
    raw = memoryview(decompress(data))
    offset = 0
    while offset < len(raw):
        frame, size = decode_frame(raw, offset)
        offset += size
        yield frame


def encode_file(frames: Sequence[NgfFrame], *, compress: bool = True) -> bytes:
    raw = b"".join(encode_frame(f) for f in frames)
    return gzip.compress(raw, mtime=0) if compress else raw


def split_games(frames: Sequence[NgfFrame]) -> list[list[NgfFrame]]:
    """Split a recording into games: a new gameid or a ctime reset starts a game."""
    games: list[list[NgfFrame]] = []
    for frame in frames:
        if (
            not games
            or frame.gameid != games[-1][-1].gameid
            or frame.ctime_ms < games[-1][-1].ctime_ms
        ):
            games.append([])
        games[-1].append(frame)
    return games
