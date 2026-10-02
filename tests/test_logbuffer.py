from __future__ import annotations

import logging

from nestris_ltm.diagnostics.logbuffer import RingBufferHandler


def _logger(handler: logging.Handler) -> logging.Logger:
    logger = logging.getLogger(f"test.ring.{id(handler)}")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


def test_keeps_only_capacity_entries() -> None:
    handler = RingBufferHandler(capacity=3)
    logger = _logger(handler)
    for i in range(5):
        logger.info("msg %d", i)

    entries = handler.entries()
    assert [e.message for e in entries] == ["msg 2", "msg 3", "msg 4"]


def test_filters_by_id_and_level() -> None:
    handler = RingBufferHandler(capacity=10)
    logger = _logger(handler)
    logger.debug("a")
    logger.warning("b")
    logger.error("c")

    first = handler.entries()[0]
    assert [e.message for e in handler.entries(after_id=first.id)] == ["b", "c"]
    assert [e.message for e in handler.entries(min_level=logging.ERROR)] == ["c"]
