"""How well ``live`` messages reach this host, per station.

The station numbers its ``live`` messages (``seq``, station 0.3.0+) and
reports how old the frame was when it published (``frame_age_ms``). From
that the host measures, without synchronized clocks, the received rate and
the messages lost on the way (MQTT QoS 0). The transport delay needs the
station's clock (``ts``); it is only shown when the clocks agree well enough
to be meaningful.

Note: the station sends ``live`` only on change, so the rate follows the
game (a slow level changes less often) and is not a health signal on its
own; losses and delays are.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

from nestris_ltm.ingest.payloads import LivePayload, StatusPayload

# Window for the received rate.
RATE_WINDOW_S = 5.0
# Transport delays beyond this mean the clocks differ (no NTP), not a slow
# network: the delay is then reported as unknown with a clock warning.
CLOCK_SKEW_S = 1.0
# Samples kept for the transport-delay median.
DELAY_SAMPLES = 200
# Performance history: one point per status (every 10 s): 15 minutes.
HISTORY_POINTS = 90


@dataclass
class LinkStats:
    received: int = 0
    lost: int = 0
    # Station restarts seen through a falling sequence number.
    restarts: int = 0
    last_seq: int | None = None
    _arrivals: deque[float] = field(default_factory=deque)
    _delays_ms: deque[float] = field(default_factory=lambda: deque(maxlen=DELAY_SAMPLES))
    _ages_ms: deque[float] = field(default_factory=lambda: deque(maxlen=DELAY_SAMPLES))

    def record(self, payload: LivePayload, now: datetime) -> None:
        self.received += 1
        t = now.timestamp()
        self._arrivals.append(t)
        while self._arrivals and t - self._arrivals[0] > RATE_WINDOW_S:
            self._arrivals.popleft()
        seq = payload.seq
        if seq is not None:
            if self.last_seq is not None:
                if seq > self.last_seq + 1:
                    self.lost += seq - self.last_seq - 1
                elif seq <= self.last_seq:
                    # The station restarted (or a duplicate): start over.
                    self.restarts += seq < self.last_seq
            self.last_seq = seq
        self._delays_ms.append((now - payload.ts).total_seconds() * 1000.0)
        if payload.frame_age_ms is not None:
            self._ages_ms.append(payload.frame_age_ms)

    def rate_hz(self, now: datetime) -> float:
        t = now.timestamp()
        recent = [a for a in self._arrivals if t - a <= RATE_WINDOW_S]
        return round(len(recent) / RATE_WINDOW_S, 1)

    def snapshot(self, now: datetime) -> dict[str, Any]:
        delay = median(self._delays_ms) if self._delays_ms else None
        clock_ok = delay is not None and -CLOCK_SKEW_S * 1000 < delay < CLOCK_SKEW_S * 1000
        sent = self.received + self.lost
        return {
            "rx_hz": self.rate_hz(now),
            "received": self.received,
            "lost": self.lost,
            "loss_rate": round(self.lost / sent, 4) if sent else 0.0,
            "restarts": self.restarts,
            "sequenced": self.last_seq is not None,
            "frame_age_ms": round(median(self._ages_ms), 1) if self._ages_ms else None,
            # Station clock -> here; None when the clocks are too far apart.
            "transport_ms": round(delay, 1) if clock_ok and delay is not None else None,
            "clock_skew": delay is not None and not clock_ok,
        }


@dataclass
class PerfHistory:
    """One point per status message, for the admin sparkline."""

    points: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=HISTORY_POINTS))

    def add(self, status: StatusPayload, link: LinkStats, now: datetime) -> None:
        perf = status.perf
        if status.state != "online" or (perf is None and status.fps is None):
            return
        self.points.append(
            {
                "t": now.isoformat(),
                "fps": perf.fps if perf else status.fps,
                "capture_fps": perf.capture_fps if perf else None,
                "target_fps": perf.target_fps if perf else None,
                "drop_rate": perf.drop_rate if perf else None,
                "missing": perf.missing if perf else None,
                "engine_ms_p95": perf.engine_ms_p95 if perf else None,
                "cpu_pct": perf.cpu_pct if perf else None,
                "rx_hz": link.rate_hz(now),
                "lost": link.lost,
            }
        )
