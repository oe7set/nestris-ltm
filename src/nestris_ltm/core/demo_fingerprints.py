"""Attract-mode demo fingerprints: a copy of
``nestris-core/crates/nestris-engine/assets/demo/fingerprints.json``.

Keep it in step with nestris-core (``tests/test_demo.py`` compares the two
when the sibling checkout is present). Each step is (score, lines, level,
next piece or None) as the demo shows it after a piece locked.
"""

from typing import Final

# (score, lines, level, next piece)
Step = tuple[int, int, int, str | None]

FINGERPRINTS: Final[list[dict[str, str | list[Step]]]] = [
    {
        "id": "nes-ntsc-event",
        "rom": "NES Tetris (NTSC), Retroverse event ROM; demo recorded by the stations 2026-11",
        "steps": [
            (0, 0, 0, "J"),
            (11, 0, 0, "T"),
            (23, 0, 0, "S"),
            (35, 0, 0, "Z"),
            (45, 0, 0, "J"),
            (96, 1, 0, "T"),
            (100, 1, 0, "S"),
            (111, 1, 0, "Z"),
            (120, 1, 0, "J"),
            (171, 2, 0, "S"),
            (182, 2, 0, "Z"),
            (190, 2, 0, "L"),
            (200, 2, 0, "Z"),
            (215, 2, 0, "J"),
            (325, 4, 0, "T"),
            (336, 4, 0, "T"),
            (385, 5, 0, "S"),
            (395, 5, 0, "I"),
            (400, 5, 0, None),
            (411, 5, 0, "O"),
            (424, 5, 0, "J"),
            (434, 5, 0, "S"),
            (443, 5, 0, "Z"),
            (451, 5, 0, "L"),
            (458, 5, 0, "Z"),
            (466, 5, 0, "L"),
            (473, 5, 0, "I"),
            (485, 5, 0, "O"),
            (1696, 9, 0, "L"),
            (1700, 9, 0, "Z"),
            (1715, 9, 0, "L"),
            (1724, 9, 0, "I"),
            (1732, 9, 0, "O"),
            (1943, 11, 1, "J"),
            (1953, 11, 1, "T"),
            (2164, 13, 1, "S"),
            (2175, 13, 1, "I"),
            (2185, 13, 1, "T"),
        ],
    },
]
