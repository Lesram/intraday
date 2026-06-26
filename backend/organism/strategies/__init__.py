"""Intra 2.0 — strategy framework (Phase 1).

Every strategy implements the shared `Strategy` contract (base.py) and emits the
strategy-agnostic `Candidate`, so the live engine and the backtester can run any
strategy through the identical candidate -> gate -> size -> exit path. The
framework is flag-gated and behavior-preserving for the live momentum book until
parity is proven (Section 9 of the Phase 1 plan).
"""
from backend.organism.strategies.base import Candidate, FeatureFrame, Strategy
from backend.organism.strategies.registry import (
    build_strategy,
    get_strategy_class,
    register,
    registered_names,
)

__all__ = [
    "Strategy",
    "Candidate",
    "FeatureFrame",
    "register",
    "get_strategy_class",
    "build_strategy",
    "registered_names",
]
