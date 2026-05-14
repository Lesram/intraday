"""Phase 9D evidence-only strategy portfolio construction.

This module turns strategy league rows into a conservative portfolio
construction verdict.  It does not place orders, mutate promotion state, or
change live sizing.  The intent is to make the future scaling decision explicit:
multiple independently validated strategy families must pass evidence,
concentration, beta, and correlation controls before any portfolio budget can be
recommended.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any, Iterable, Mapping


PORTFOLIO_ELIGIBLE_VERDICTS = frozenset({
    "micro_paper_eligible",
    "normal_paper_eligible",
    "paper_eligible",
    "live_eligible",
    "scale_eligible",
})
REPLAY_ONLY_VERDICTS = frozenset({"replay_eligible"})

STRATEGY_FAMILY_BY_ID: dict[str, str] = {
    "alpha_baseline": "legacy_baseline",
    "etf_intraday_momentum": "index_momentum",
    "gamma_flow_momentum": "index_momentum",
    "inverse_index_hedge": "index_momentum",
    "orb_sip_current": "stocks_in_play_continuation",
    "orb_sip_v2": "stocks_in_play_continuation",
    "catalyst_continuation": "stocks_in_play_continuation",
    "mean_reversion_current": "residual_reversion",
    "residual_mean_reversion": "residual_reversion",
    "pairs_stat_arb": "residual_reversion",
    "eod_momentum_current": "eod_reversal",
    "eod_reversal_shadow": "eod_reversal",
}


@dataclass(frozen=True)
class PortfolioConstructionConfig:
    min_validated_strategies: int = 2
    min_validated_families: int = 2
    min_samples: int = 100
    min_profit_factor: float = 1.20
    min_avg_r: float = 0.0
    min_alpha_bps: float = 0.0
    max_symbol_concentration: float = 0.30
    max_session_concentration: float = 0.25
    max_pairwise_correlation: float = 0.75
    max_abs_weighted_beta: float = 0.35
    max_total_risk_budget_bps: float = 25.0
    max_strategy_risk_budget_bps: float = 10.0


@dataclass(frozen=True)
class StrategyPortfolioCandidate:
    strategy_id: str
    family: str
    verdict: str
    n: int
    profit_factor: float
    avg_r: float
    avg_alpha_over_symbol_hold_bps: float | None = None
    avg_alpha_over_random_bps: float | None = None
    avg_alpha_over_delay_bps: float | None = None
    max_symbol_concentration: float = 0.0
    max_session_concentration: float = 0.0
    max_drawdown: float = 0.0
    beta_to_spy: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        row: Mapping[str, Any],
        *,
        betas: Mapping[str, float] | None = None,
    ) -> "StrategyPortfolioCandidate":
        strategy_id = str(row.get("strategy_id") or "").strip().lower()
        family = str(
            row.get("strategy_family")
            or row.get("family")
            or STRATEGY_FAMILY_BY_ID.get(strategy_id, strategy_id or "unknown")
        ).strip().lower()
        beta = _finite(
            row.get("beta_to_spy", (betas or {}).get(strategy_id, 0.0)),
            0.0,
        )
        return cls(
            strategy_id=strategy_id or "unknown",
            family=family or "unknown",
            verdict=str(row.get("verdict") or "").strip().lower(),
            n=int(_finite(row.get("n"), 0.0)),
            profit_factor=_profit_factor_value(row.get("profit_factor")),
            avg_r=_finite(row.get("avg_r"), 0.0),
            avg_alpha_over_symbol_hold_bps=_optional(
                row.get("avg_alpha_over_symbol_hold_bps")
            ),
            avg_alpha_over_random_bps=_optional(row.get("avg_alpha_over_random_bps")),
            avg_alpha_over_delay_bps=_optional(row.get("avg_alpha_over_delay_bps")),
            max_symbol_concentration=_finite(row.get("max_symbol_concentration"), 0.0),
            max_session_concentration=_finite(row.get("max_session_concentration"), 0.0),
            max_drawdown=_finite(row.get("max_drawdown"), 0.0),
            beta_to_spy=beta,
            metadata=dict(row),
        )

    @property
    def alpha_values(self) -> tuple[float | None, float | None, float | None]:
        return (
            self.avg_alpha_over_symbol_hold_bps,
            self.avg_alpha_over_random_bps,
            self.avg_alpha_over_delay_bps,
        )

    @property
    def quality_score(self) -> float:
        alphas = [value for value in self.alpha_values if value is not None]
        edge = max(0.0, fmean(alphas)) if alphas else 0.0
        pf_component = min(max(self.profit_factor, 0.0), 3.0) / 1.20
        r_component = 1.0 + max(self.avg_r, 0.0)
        sample_component = math.sqrt(max(self.n, 1))
        drawdown_penalty = 1.0 + abs(min(self.max_drawdown, 0.0)) / 100.0
        return edge * pf_component * r_component * sample_component / drawdown_penalty


def construct_strategy_portfolio(
    rows: Iterable[Mapping[str, Any] | StrategyPortfolioCandidate],
    *,
    config: PortfolioConstructionConfig | None = None,
    betas: Mapping[str, float] | None = None,
    correlations: Mapping[str | tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    """Build a Phase 9D portfolio verdict from strategy evidence rows."""
    cfg = config or PortfolioConstructionConfig()
    candidates = [
        row
        if isinstance(row, StrategyPortfolioCandidate)
        else StrategyPortfolioCandidate.from_mapping(row, betas=betas)
        for row in rows
    ]
    candidate_reports = [
        _candidate_report(candidate, cfg) for candidate in sorted(
            candidates, key=lambda item: item.strategy_id
        )
    ]
    eligible = [
        report for report in candidate_reports
        if report["eligible_for_portfolio"] is True
    ]

    correlation_blockers = _correlation_blockers(eligible, correlations or {}, cfg)
    for report in eligible:
        blockers = correlation_blockers.get(str(report["strategy_id"]), [])
        if blockers:
            report["blockers"].extend(blockers)
            report["eligible_for_portfolio"] = False

    eligible = [report for report in eligible if report["eligible_for_portfolio"] is True]
    families = sorted({str(report["family"]) for report in eligible})
    portfolio_blockers: list[str] = []
    if len(eligible) < cfg.min_validated_strategies:
        portfolio_blockers.append("not_enough_validated_strategies")
    if len(families) < cfg.min_validated_families:
        portfolio_blockers.append("not_enough_independent_strategy_families")

    allocations = _allocate_risk(eligible, cfg) if not portfolio_blockers else []
    beta_report = _weighted_beta_report(allocations, cfg)
    if beta_report["status"] == "blocked":
        portfolio_blockers.append("weighted_beta_exceeds_limit")
        allocations = []

    allocated_risk = round(sum(row["target_risk_budget_bps"] for row in allocations), 6)
    return {
        "scope": "phase9d_portfolio_construction_no_live_behavior_change",
        "portfolio_authorized": bool(allocations) and not portfolio_blockers,
        "promotion_authorized": False,
        "live_behavior": "unchanged",
        "config": _config_dict(cfg),
        "counts": {
            "input_rows": len(candidates),
            "eligible_strategies": len(eligible),
            "eligible_families": len(families),
            "allocations": len(allocations),
        },
        "portfolio_blockers": portfolio_blockers,
        "eligible_families": families,
        "allocated_risk_budget_bps": allocated_risk,
        "candidates": candidate_reports,
        "allocations": allocations,
        "controls": {
            "correlation": {
                "max_pairwise_correlation": cfg.max_pairwise_correlation,
                "blocked_strategy_ids": sorted(correlation_blockers),
            },
            "beta": beta_report,
            "exposure": {
                "max_total_risk_budget_bps": cfg.max_total_risk_budget_bps,
                "max_strategy_risk_budget_bps": cfg.max_strategy_risk_budget_bps,
                "allocated_risk_budget_bps": allocated_risk,
            },
        },
    }


def _candidate_report(
    candidate: StrategyPortfolioCandidate,
    config: PortfolioConstructionConfig,
) -> dict[str, Any]:
    blockers = _candidate_blockers(candidate, config)
    return {
        "strategy_id": candidate.strategy_id,
        "family": candidate.family,
        "verdict": candidate.verdict,
        "n": candidate.n,
        "profit_factor": _json_number(candidate.profit_factor),
        "avg_r": round(candidate.avg_r, 6),
        "avg_alpha_over_symbol_hold_bps": _round_optional(
            candidate.avg_alpha_over_symbol_hold_bps
        ),
        "avg_alpha_over_random_bps": _round_optional(
            candidate.avg_alpha_over_random_bps
        ),
        "avg_alpha_over_delay_bps": _round_optional(candidate.avg_alpha_over_delay_bps),
        "max_symbol_concentration": round(candidate.max_symbol_concentration, 6),
        "max_session_concentration": round(candidate.max_session_concentration, 6),
        "max_drawdown": round(candidate.max_drawdown, 6),
        "beta_to_spy": round(candidate.beta_to_spy, 6),
        "quality_score": round(candidate.quality_score, 6),
        "eligible_for_portfolio": not blockers,
        "blockers": blockers,
    }


def _candidate_blockers(
    candidate: StrategyPortfolioCandidate,
    config: PortfolioConstructionConfig,
) -> list[str]:
    blockers: list[str] = []
    if candidate.verdict in REPLAY_ONLY_VERDICTS:
        blockers.append("replay_only_not_portfolio_eligible")
    elif candidate.verdict not in PORTFOLIO_ELIGIBLE_VERDICTS:
        blockers.append("verdict_not_portfolio_eligible")
    if candidate.n < config.min_samples:
        blockers.append("sample_size_below_portfolio_minimum")
    if candidate.profit_factor < config.min_profit_factor:
        blockers.append("profit_factor_below_minimum")
    if candidate.avg_r <= config.min_avg_r:
        blockers.append("avg_r_not_positive")
    for name, value in (
        ("symbol_hold_alpha", candidate.avg_alpha_over_symbol_hold_bps),
        ("random_alpha", candidate.avg_alpha_over_random_bps),
        ("delay_alpha", candidate.avg_alpha_over_delay_bps),
    ):
        if value is None:
            blockers.append(f"{name}_missing")
        elif value <= config.min_alpha_bps:
            blockers.append(f"{name}_not_positive")
    if candidate.max_symbol_concentration > config.max_symbol_concentration:
        blockers.append("symbol_concentration_exceeds_limit")
    if candidate.max_session_concentration > config.max_session_concentration:
        blockers.append("session_concentration_exceeds_limit")
    return blockers


def _correlation_blockers(
    eligible_reports: list[dict[str, Any]],
    correlations: Mapping[str | tuple[str, str], float],
    config: PortfolioConstructionConfig,
) -> dict[str, list[str]]:
    if not eligible_reports:
        return {}
    by_id = {str(report["strategy_id"]): report for report in eligible_reports}
    blockers: dict[str, list[str]] = {}
    for left_id, left_report in sorted(by_id.items()):
        for right_id, right_report in sorted(by_id.items()):
            if left_id >= right_id:
                continue
            corr = _lookup_correlation(correlations, left_id, right_id)
            if corr is None or abs(corr) <= config.max_pairwise_correlation:
                continue
            left_score = float(left_report["quality_score"])
            right_score = float(right_report["quality_score"])
            loser = right_id if left_score >= right_score else left_id
            winner = left_id if loser == right_id else right_id
            blockers.setdefault(loser, []).append(
                f"pairwise_correlation_exceeds_limit:{winner}:{round(corr, 6)}"
            )
    return blockers


def _lookup_correlation(
    correlations: Mapping[str | tuple[str, str], float],
    left: str,
    right: str,
) -> float | None:
    keys: tuple[str | tuple[str, str], ...] = (
        (left, right),
        (right, left),
        f"{left}:{right}",
        f"{right}:{left}",
    )
    for key in keys:
        if key in correlations:
            return _finite(correlations[key], 0.0)
    return None


def _allocate_risk(
    eligible_reports: list[dict[str, Any]],
    config: PortfolioConstructionConfig,
) -> list[dict[str, Any]]:
    total_score = sum(float(report["quality_score"]) for report in eligible_reports)
    if total_score <= 0:
        return []
    allocations = []
    for report in eligible_reports:
        raw = (
            float(report["quality_score"])
            / total_score
            * config.max_total_risk_budget_bps
        )
        budget = min(raw, config.max_strategy_risk_budget_bps)
        allocations.append({
            "strategy_id": report["strategy_id"],
            "family": report["family"],
            "target_risk_budget_bps": round(budget, 6),
            "quality_score": report["quality_score"],
            "beta_to_spy": report["beta_to_spy"],
            "notes": "advisory_budget_only_no_live_sizing_change",
        })
    return allocations


def _weighted_beta_report(
    allocations: list[dict[str, Any]],
    config: PortfolioConstructionConfig,
) -> dict[str, Any]:
    total = sum(float(row["target_risk_budget_bps"]) for row in allocations)
    if total <= 0:
        return {
            "status": "not_applicable",
            "weighted_beta": 0.0,
            "max_abs_weighted_beta": config.max_abs_weighted_beta,
        }
    weighted = sum(
        float(row["target_risk_budget_bps"]) * float(row.get("beta_to_spy") or 0.0)
        for row in allocations
    ) / total
    return {
        "status": "pass" if abs(weighted) <= config.max_abs_weighted_beta else "blocked",
        "weighted_beta": round(weighted, 6),
        "max_abs_weighted_beta": config.max_abs_weighted_beta,
    }


def _finite(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _profit_factor_value(value: Any) -> float:
    if isinstance(value, str) and value.strip().lower() == "inf":
        return float("inf")
    return _finite(value, 0.0)


def _optional(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _json_number(value: float) -> float | str:
    if math.isinf(value):
        return "inf"
    return round(value, 6)


def _round_optional(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _config_dict(config: PortfolioConstructionConfig) -> dict[str, Any]:
    return {
        "min_validated_strategies": config.min_validated_strategies,
        "min_validated_families": config.min_validated_families,
        "min_samples": config.min_samples,
        "min_profit_factor": config.min_profit_factor,
        "min_avg_r": config.min_avg_r,
        "min_alpha_bps": config.min_alpha_bps,
        "max_symbol_concentration": config.max_symbol_concentration,
        "max_session_concentration": config.max_session_concentration,
        "max_pairwise_correlation": config.max_pairwise_correlation,
        "max_abs_weighted_beta": config.max_abs_weighted_beta,
        "max_total_risk_budget_bps": config.max_total_risk_budget_bps,
        "max_strategy_risk_budget_bps": config.max_strategy_risk_budget_bps,
    }
