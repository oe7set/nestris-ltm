"""Playfield encodings.

Cell ids: 0 empty, 1 white, 2/3 the level's two accent colors.

- *rows*: the MQTT ``live`` form, 20 strings of 10 digits, top row first.
- *cells*: 200 ints, row-major from the top-left.
- *packed*: 50 bytes, 4 cells per byte, first cell in the high bits; the
  NestrisChamps NGF playfield layout (identical bytes to NGF v3 frames).
"""

from __future__ import annotations

from collections.abc import Sequence

ROWS = 20
COLS = 10
CELLS = ROWS * COLS
PACKED_SIZE = CELLS // 4


class PlayfieldError(ValueError):
    pass


def cells_from_rows(rows: Sequence[str]) -> list[int]:
    if len(rows) != ROWS:
        raise PlayfieldError(f"expected {ROWS} rows, got {len(rows)}")
    cells: list[int] = []
    for row in rows:
        if len(row) != COLS:
            raise PlayfieldError(f"expected rows of {COLS} cells, got {row!r}")
        for ch in row:
            if ch not in "0123":
                raise PlayfieldError(f"invalid cell id {ch!r}")
            cells.append(ord(ch) - 48)
    return cells


def rows_from_cells(cells: Sequence[int]) -> list[str]:
    _check_cells(cells)
    return ["".join(str(c) for c in cells[r * COLS : (r + 1) * COLS]) for r in range(ROWS)]


def pack(cells: Sequence[int]) -> bytes:
    _check_cells(cells)
    out = bytearray(PACKED_SIZE)
    for i in range(PACKED_SIZE):
        a, b, c, d = cells[i * 4 : i * 4 + 4]
        out[i] = (a & 3) << 6 | (b & 3) << 4 | (c & 3) << 2 | (d & 3)
    return bytes(out)


def unpack(packed: bytes) -> list[int]:
    if len(packed) != PACKED_SIZE:
        raise PlayfieldError(f"expected {PACKED_SIZE} bytes, got {len(packed)}")
    cells: list[int] = []
    for byte in packed:
        cells.extend(((byte >> 6) & 3, (byte >> 4) & 3, (byte >> 2) & 3, byte & 3))
    return cells


def pack_rows(rows: Sequence[str]) -> bytes:
    return pack(cells_from_rows(rows))


def _check_cells(cells: Sequence[int]) -> None:
    if len(cells) != CELLS:
        raise PlayfieldError(f"expected {CELLS} cells, got {len(cells)}")
    if any(c not in (0, 1, 2, 3) for c in cells):
        raise PlayfieldError("cell ids must be 0..3")
