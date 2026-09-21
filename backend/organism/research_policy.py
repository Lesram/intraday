"""Explicit policy for the reviewed paper research baseline.

Inherited trade counts and profitable telemetry are not promotion authority.
Unlocking this policy requires a reviewed code/configuration release and a new
evaluation boundary; there is deliberately no environment-variable override.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

RESEARCH_POLICY_ID = "paper_research_locked_v1"
RESEARCH_POLICY_LOCKED = True
RESEARCH_POLICY_REASON = "reviewed_paper_baseline_requires_explicit_promotion"
BOOKKEEPING_FIELDS = frozenset({
    "symbol_fitness", "symbol_trade_counts", "short_win_rate", "short_avg_pnl",
    "short_trade_count", "evolution_generation", "total_adaptations",
})


def effective_policy_params(evolved_params: Any) -> dict:
    """Project actual retained parameter values, without rounding or defaults."""
    values = evolved_params if isinstance(evolved_params, dict) else vars(evolved_params)
    return copy.deepcopy({key: value for key, value in values.items()
                          if key not in BOOKKEEPING_FIELDS and not key.startswith("_")})


def effective_policy_hash(evolved_params: Any) -> str:
    data = json.dumps(effective_policy_params(evolved_params), sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def policy_status(raw_trade_count: int | None = None, *, evolved_params: Any = None) -> dict:
    """Report observed count honestly without inventing qualified evidence."""
    return {
        "id": RESEARCH_POLICY_ID,
        "locked": RESEARCH_POLICY_LOCKED,
        "reason": RESEARCH_POLICY_REASON if RESEARCH_POLICY_LOCKED else "",
        "raw_strategy_trade_count": raw_trade_count,
        "qualified_trade_count": None,
        "qualification_status": "unverified",
        "automatic_promotion_enabled": not RESEARCH_POLICY_LOCKED,
        "frozen_models": RESEARCH_POLICY_LOCKED,
        "ml_reversal_exit_policy": "retained_saved_model_baseline",
        "effective_policy_params": effective_policy_params(evolved_params) if evolved_params is not None else None,
        "effective_policy_hash": effective_policy_hash(evolved_params) if evolved_params is not None else None,
    }
