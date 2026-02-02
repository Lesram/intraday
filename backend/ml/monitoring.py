from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrainDecision:
    should_retrain: bool
    reasons: list[str]


def decide_retrain(
    *,
    recent_total_return: float,
    reference_total_return: float | None,
    psi_score: float | None,
    min_return_drop: float = 0.02,
    psi_threshold: float = 0.15,
) -> RetrainDecision:
    reasons: list[str] = []

    if psi_score is not None and float(psi_score) >= float(psi_threshold):
        reasons.append(f"drift psi {psi_score:.3f} >= {psi_threshold:.3f}")

    if reference_total_return is not None:
        if float(recent_total_return) <= float(reference_total_return) - float(min_return_drop):
            reasons.append(
                f"performance drop recent {recent_total_return:.4f} <= reference {reference_total_return:.4f} - {min_return_drop:.4f}"
            )
    # Fallback: if the recent window is losing money, retrain.
    elif float(recent_total_return) < 0.0:
        reasons.append(f"negative recent total_return {recent_total_return:.4f}")

    return RetrainDecision(should_retrain=bool(reasons), reasons=reasons)
