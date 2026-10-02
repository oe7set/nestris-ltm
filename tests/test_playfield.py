from __future__ import annotations

import pytest

from nestris_ltm.core import playfield


def test_rows_pack_roundtrip() -> None:
    rows = ["0" * 10] * 18 + ["0000000110", "2221103311"]
    packed = playfield.pack_rows(rows)
    assert len(packed) == 50
    assert playfield.rows_from_cells(playfield.unpack(packed)) == rows


def test_first_cell_in_high_bits() -> None:
    cells = [3, 0, 0, 1] + [0] * 196
    assert playfield.pack(cells)[0] == 0b11_00_00_01


@pytest.mark.parametrize(
    "rows",
    [
        ["0" * 10] * 19,
        ["0" * 10] * 19 + ["0" * 9],
        ["0" * 10] * 19 + ["000000000x"],
        ["0" * 10] * 19 + ["0000000004"],
    ],
)
def test_invalid_rows(rows: list[str]) -> None:
    with pytest.raises(playfield.PlayfieldError):
        playfield.cells_from_rows(rows)
