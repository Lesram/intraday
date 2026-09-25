"""Bounded observational telemetry; never used to admit or size an order."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import math
import time


class PipelineDiagnostics:
    """Measure nonoverlapping wall-time segments independently of replay time.

    Counters describe one tick's alpha candidate-build phase. Accepted here
    means it survived that phase, not that sizing/submission later accepted it.
    No raw market rows, exception bodies, credentials or account IDs are kept.
    """

    def __init__(self, clock=None):
        self._clock = clock or time.perf_counter
        self._last = self._read()
        self._stage = "stream_health"
        self._finished = False
        self.seconds = Counter()
        self.alpha_terminal = Counter()
        self.alpha_scanned = 0
        self.alpha_considered = 0

    def _read(self):
        try:
            value = float(self._clock())
            return value if math.isfinite(value) else None
        except Exception:  # noqa: BLE001 -- an observational clock must never abort a trading tick
            return None

    def stage(self, name):
        if self._finished:
            return
        now = self._read()
        if now is not None and self._last is not None and now >= self._last:
            self.seconds[self._stage] += now - self._last
        self._last, self._stage = now, name

    def finish(self):
        self.stage("finished")
        self._finished = True

    def snapshot(self):
        terminal = dict(sorted(self.alpha_terminal.items()))
        return {
            "schema": "paper_pipeline_diagnostics_v1",
            "stage_seconds": {k: round(v, 6) for k, v in sorted(self.seconds.items())},
            "alpha_scanned": self.alpha_scanned,
            "alpha_considered": self.alpha_considered,
            "alpha_terminal": terminal,
            "alpha_unaccounted": self.alpha_considered - sum(terminal.values()),
            "scope": "alpha_candidate_build_before_combined_ranking_sizing_submission",
        }


def finite_age(value):
    """Unknown/unsubscribed infinity is explicitly null in structured evidence."""
    try:
        number = float(value)
        return round(number, 6) if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def entry_frame_age(engine, symbol, direction):
    """Observe the exact shared-gate frame; this does not replace admission."""
    try:
        receipt = engine._entry_evidence_frames[(symbol, float(direction))]
        stamp = datetime.fromisoformat(receipt["last_bar_at"].replace("Z", "+00:00"))
        return finite_age((engine._now_fn() - stamp).total_seconds())
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None


def subscription_state(provider, symbol):
    names = getattr(provider, "_subscribed_symbols", None)
    return symbol in names if isinstance(names, (set, frozenset)) else None
