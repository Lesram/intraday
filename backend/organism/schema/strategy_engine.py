"""Protocol for strategy-specific signal engines."""

from __future__ import annotations

from typing import Any, Iterable, Protocol

from backend.organism.schema.candidate_signal import CandidateSignal


class StrategyEngine(Protocol):
    """A strategy engine emits first-class CandidateSignal objects."""

    strategy_id: str
    engine_version: str
    shadow_only: bool

    def generate_signals(self, context: dict[str, Any]) -> Iterable[CandidateSignal]:
        """Return strategy-born candidate signals for the supplied context."""
