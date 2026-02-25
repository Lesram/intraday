"""
Module P4.7 — Inter-Run Transfer Learning.

Uses accumulated trade data and brain state across runs to warm-start
models when the organism restarts or encounters new market conditions.

Key capabilities:
    1. **Knowledge distillation** — extract regime-conditioned trade
       statistics, feature importance rankings, and model hyperparameters
       from all historical runs.  Persisted in `transfer_knowledge.json`.
    2. **Warm-start initialisation** — when the organism starts a new run,
       use the distilled knowledge to:
       (a) Seed initial EvolvedParams with values from the most relevant
           historical regime instead of defaults,
       (b) Prime feature weights from accumulated importance rankings,
       (c) Configure model capacity (XGB hyperparams) from what worked
           best in similar conditions.
    3. **Regime-guided model selection** — when multiple runs exist in the
       brain's history, select model weights from the run whose regime
       profile most closely matches the *current* detected regime.

Persistence: ``TransferKnowledge`` serialises to / from JSON and is
stored inside the brain directory as ``transfer_knowledge.json``.

Ref: docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md §Phase 4.7
"""

from __future__ import annotations

import json
import logging
import math
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

TRANSFER_FILE = "transfer_knowledge.json"

# Decay factor for older run snapshots (newer runs weigh more)
_RUN_DECAY = 0.85
# Max snapshots to keep
_MAX_SNAPSHOTS = 20


# ═════════════════════════════════════════════════════════════════
#  Data Structures
# ═════════════════════════════════════════════════════════════════

@dataclass
class RunSnapshot:
    """Condensed performance summary of a single run / epoch.

    Stored chronologically so the transfer engine can weight recent
    runs more heavily.
    """

    run_id: int = 0
    generation: int = 0
    regime: str = "unknown"
    # Overall performance
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    sharpe: float = 0.0
    direction_accuracy: float = 0.0
    # Best-known hyperparameters at end of run
    xgb_n_estimators: int = 200
    xgb_max_depth: int = 5
    xgb_learning_rate: float = 0.05
    xgb_subsample: float = 0.80
    xgb_colsample_bytree: float = 0.80
    # Top feature importances (name → weight)
    top_features: dict[str, float] = field(default_factory=dict)
    # Regime-specific metrics
    regime_pnl: dict[str, float] = field(default_factory=dict)
    # Evolved param snapshot (key scalars only)
    evolved_snapshot: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generation": self.generation,
            "regime": self.regime,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_pnl": round(self.avg_pnl, 2),
            "sharpe": round(self.sharpe, 4),
            "direction_accuracy": round(self.direction_accuracy, 4),
            "xgb_n_estimators": self.xgb_n_estimators,
            "xgb_max_depth": self.xgb_max_depth,
            "xgb_learning_rate": round(self.xgb_learning_rate, 6),
            "xgb_subsample": round(self.xgb_subsample, 4),
            "xgb_colsample_bytree": round(self.xgb_colsample_bytree, 4),
            "top_features": {k: round(v, 4) for k, v in self.top_features.items()},
            "regime_pnl": {k: round(v, 2) for k, v in self.regime_pnl.items()},
            "evolved_snapshot": {
                k: round(v, 4) if isinstance(v, float) else v
                for k, v in self.evolved_snapshot.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunSnapshot":
        snap = cls()
        for key in [
            "run_id", "generation", "regime", "total_trades",
            "win_rate", "avg_pnl", "sharpe", "direction_accuracy",
            "xgb_n_estimators", "xgb_max_depth", "xgb_learning_rate",
            "xgb_subsample", "xgb_colsample_bytree",
        ]:
            if key in d:
                setattr(snap, key, d[key])
        if "top_features" in d and isinstance(d["top_features"], dict):
            snap.top_features = d["top_features"]
        if "regime_pnl" in d and isinstance(d["regime_pnl"], dict):
            snap.regime_pnl = d["regime_pnl"]
        if "evolved_snapshot" in d and isinstance(d["evolved_snapshot"], dict):
            snap.evolved_snapshot = d["evolved_snapshot"]
        return snap


@dataclass
class TransferKnowledge:
    """Accumulated cross-run knowledge base.

    Grows over each brain save, enabling the organism to leverage
    all prior experience when restarting.
    """

    # Chronological list of run snapshots (newest last)
    snapshots: list[RunSnapshot] = field(default_factory=list)
    # Aggregated feature importance (EMA across all runs)
    global_feature_importance: dict[str, float] = field(default_factory=dict)
    # Best-ever Sharpe and the hyperparams that produced it
    best_sharpe: float = -math.inf
    best_sharpe_params: dict[str, Any] = field(default_factory=dict)
    # Per-regime best config — which params work best in each regime
    regime_best_config: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "global_feature_importance": {
                k: round(v, 4) for k, v in self.global_feature_importance.items()
            },
            "best_sharpe": round(self.best_sharpe, 4) if math.isfinite(self.best_sharpe) else None,
            "best_sharpe_params": self.best_sharpe_params,
            "regime_best_config": self.regime_best_config,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransferKnowledge":
        tk = cls()
        for sd in d.get("snapshots", []):
            tk.snapshots.append(RunSnapshot.from_dict(sd))
        if "global_feature_importance" in d:
            tk.global_feature_importance = d["global_feature_importance"]
        bs = d.get("best_sharpe")
        tk.best_sharpe = float(bs) if bs is not None else -math.inf
        tk.best_sharpe_params = d.get("best_sharpe_params", {})
        tk.regime_best_config = d.get("regime_best_config", {})
        return tk


# ═════════════════════════════════════════════════════════════════
#  Transfer Learning Engine
# ═════════════════════════════════════════════════════════════════

class TransferLearningEngine:
    """Cross-run knowledge distillation and warm-start engine.

    Lifecycle:
        1. On brain load:  ``load_knowledge()`` → ``warm_start_params()``
        2. On brain save:  ``record_run()`` → ``save_knowledge()``
    """

    def __init__(self, brain_dir: str | Path = "organism_brain"):
        self.brain_dir = Path(brain_dir).resolve()
        self.knowledge = TransferKnowledge()

    # ─────────────────────────────────────────────────────────────
    #  PERSISTENCE
    # ─────────────────────────────────────────────────────────────

    def load_knowledge(self) -> bool:
        """Load transfer knowledge from brain directory.

        Returns True if knowledge was loaded.
        """
        path = self.brain_dir / TRANSFER_FILE
        if not path.is_file():
            logger.info("No transfer knowledge found — starting fresh")
            return False

        try:
            with open(path) as f:
                data = json.load(f)
            self.knowledge = TransferKnowledge.from_dict(data)
            logger.info(
                "Transfer knowledge loaded: %d snapshots, best Sharpe=%.2f",
                len(self.knowledge.snapshots),
                self.knowledge.best_sharpe if math.isfinite(self.knowledge.best_sharpe) else 0,
            )
            return True
        except Exception as e:
            logger.warning("Failed to load transfer knowledge: %s", e)
            self.knowledge = TransferKnowledge()
            return False

    def save_knowledge(self) -> None:
        """Persist transfer knowledge to brain directory."""
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        path = self.brain_dir / TRANSFER_FILE
        try:
            with open(path, "w") as f:
                json.dump(self.knowledge.to_dict(), f, indent=2, default=str)
            logger.info(
                "Transfer knowledge saved: %d snapshots",
                len(self.knowledge.snapshots),
            )
        except Exception as e:
            logger.error("Failed to save transfer knowledge: %s", e)

    # ─────────────────────────────────────────────────────────────
    #  RECORD (called on every brain save)
    # ─────────────────────────────────────────────────────────────

    def record_run(
        self,
        evolved_params: Any,
        trades: list[Any],
        epoch_metrics: list[Any],
        feature_importances: dict[str, float] | None = None,
        regime: str = "unknown",
    ) -> None:
        """Record a run's outcome into the knowledge base.

        Parameters
        ----------
        evolved_params : EvolvedParams instance
        trades : recent TradeRecord list
        epoch_metrics : list of epoch performance dicts
        feature_importances : {feature: importance} from ML model
        regime : dominant regime for this run
        """
        if not trades:
            return

        # Build snapshot
        run_id = len(self.knowledge.snapshots)
        wins = sum(1 for t in trades if t.pnl > 0)
        wr = wins / len(trades) if trades else 0
        avg_pnl = float(np.mean([t.pnl for t in trades])) if trades else 0
        correct_dir = sum(
            1 for t in trades
            if (getattr(t, "predicted_direction", 1) > 0 and t.pnl > 0)
            or (getattr(t, "predicted_direction", 1) < 0 and t.pnl < 0)
        )
        dir_acc = correct_dir / len(trades) if trades else 0

        # Compute Sharpe from epoch metrics
        sharpe = 0.0
        if epoch_metrics:
            last = epoch_metrics[-1] if epoch_metrics else {}
            if isinstance(last, dict):
                sharpe = last.get("sharpe", 0.0)
            elif hasattr(last, "sharpe"):
                sharpe = getattr(last, "sharpe", 0.0)

        # Regime-conditioned PnL
        regime_pnl: dict[str, float] = {}
        for t in trades:
            r = getattr(t, "regime", regime)
            regime_pnl.setdefault(r, 0.0)
            regime_pnl[r] += t.pnl

        # Top features
        top_feats = {}
        if feature_importances:
            sorted_feats = sorted(
                feature_importances.items(), key=lambda x: x[1], reverse=True
            )
            top_feats = dict(sorted_feats[:30])  # keep top 30

        # Evolved params snapshot (key scalars)
        ep_snapshot = {}
        if hasattr(evolved_params, "to_dict"):
            ep_dict = evolved_params.to_dict()
            for key in [
                "alpha_weight_ml", "alpha_weight_volume",
                "alpha_weight_momentum", "alpha_weight_breakout",
                "direction_threshold_buy", "direction_threshold_sell",
                "stop_atr_scale", "trailing_distance_scale",
                "xgb_n_estimators", "xgb_max_depth", "xgb_learning_rate",
                "xgb_subsample", "xgb_colsample_bytree",
            ]:
                if key in ep_dict:
                    ep_snapshot[key] = ep_dict[key]

        snap = RunSnapshot(
            run_id=run_id,
            generation=getattr(evolved_params, "evolution_generation", 0),
            regime=regime,
            total_trades=len(trades),
            win_rate=wr,
            avg_pnl=avg_pnl,
            sharpe=sharpe,
            direction_accuracy=dir_acc,
            xgb_n_estimators=getattr(evolved_params, "xgb_n_estimators", 200),
            xgb_max_depth=getattr(evolved_params, "xgb_max_depth", 5),
            xgb_learning_rate=getattr(evolved_params, "xgb_learning_rate", 0.05),
            xgb_subsample=getattr(evolved_params, "xgb_subsample", 0.80),
            xgb_colsample_bytree=getattr(evolved_params, "xgb_colsample_bytree", 0.80),
            top_features=top_feats,
            regime_pnl=regime_pnl,
            evolved_snapshot=ep_snapshot,
        )

        self.knowledge.snapshots.append(snap)
        # Prune old snapshots
        if len(self.knowledge.snapshots) > _MAX_SNAPSHOTS:
            self.knowledge.snapshots = self.knowledge.snapshots[-_MAX_SNAPSHOTS:]

        # Update global feature importance (EMA)
        if feature_importances:
            alpha = 0.3
            for feat, imp in feature_importances.items():
                old = self.knowledge.global_feature_importance.get(feat, imp)
                self.knowledge.global_feature_importance[feat] = (
                    (1 - alpha) * old + alpha * imp
                )

        # Track best Sharpe
        if math.isfinite(sharpe) and sharpe > self.knowledge.best_sharpe:
            self.knowledge.best_sharpe = sharpe
            self.knowledge.best_sharpe_params = ep_snapshot.copy()

        # Update per-regime best config
        regime_best = self.knowledge.regime_best_config.get(regime)
        if regime_best is None or sharpe > regime_best.get("sharpe", -math.inf):
            self.knowledge.regime_best_config[regime] = {
                "sharpe": sharpe,
                "win_rate": wr,
                "params": ep_snapshot.copy(),
            }

        logger.info(
            "Transfer knowledge updated: run %d, regime=%s, WR=%.1f%%, Sharpe=%.2f",
            run_id, regime, wr * 100, sharpe,
        )

    # ─────────────────────────────────────────────────────────────
    #  WARM-START (called on organism initialization)
    # ─────────────────────────────────────────────────────────────

    def warm_start_params(
        self,
        evolved_params: Any,
        current_regime: str = "unknown",
    ) -> Any:
        """Apply transfer learning to warm-start evolved params.

        Uses accumulated knowledge to set better-than-default initial values
        on the EvolvedParams object.  Returns the modified params.

        Strategy:
        1. If we have regime-specific best config for the current regime,
           use that.
        2. Otherwise, compute a decay-weighted average of all snapshots.
        3. Seed feature weights from global feature importance.
        """
        if not self.knowledge.snapshots:
            logger.info("No transfer knowledge — using defaults")
            return evolved_params

        params = deepcopy(evolved_params)

        # 1. Try regime-specific best config
        regime_config = self.knowledge.regime_best_config.get(current_regime)
        if regime_config and regime_config.get("sharpe", 0) > 0:
            self._apply_snapshot_params(params, regime_config.get("params", {}))
            logger.info(
                "Warm-start from regime '%s' best (Sharpe=%.2f)",
                current_regime, regime_config["sharpe"],
            )
        else:
            # 2. Decay-weighted average across all snapshots
            self._apply_weighted_average(params)

        # 3. Always seed feature weights from global importance
        if self.knowledge.global_feature_importance:
            self._seed_feature_weights(params)

        logger.info(
            "Transfer learning warm-start applied (%d historical runs)",
            len(self.knowledge.snapshots),
        )
        return params

    def get_recommended_hyperparams(
        self,
        current_regime: str = "unknown",
    ) -> dict[str, Any]:
        """Get recommended XGB hyperparameters based on transfer knowledge.

        Returns dict with n_estimators, max_depth, learning_rate, etc.
        """
        defaults = {
            "n_estimators": 200,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.80,
            "colsample_bytree": 0.80,
        }

        if not self.knowledge.snapshots:
            return defaults

        # Prefer regime-specific if available
        regime_config = self.knowledge.regime_best_config.get(current_regime)
        if regime_config and regime_config.get("sharpe", 0) > 0:
            cfg = regime_config.get("params", {})
            return {
                "n_estimators": cfg.get("xgb_n_estimators", defaults["n_estimators"]),
                "max_depth": cfg.get("xgb_max_depth", defaults["max_depth"]),
                "learning_rate": cfg.get("xgb_learning_rate", defaults["learning_rate"]),
                "subsample": cfg.get("xgb_subsample", defaults["subsample"]),
                "colsample_bytree": cfg.get("xgb_colsample_bytree", defaults["colsample_bytree"]),
            }

        # Otherwise use best-ever params
        if self.knowledge.best_sharpe_params:
            bp = self.knowledge.best_sharpe_params
            return {
                "n_estimators": bp.get("xgb_n_estimators", defaults["n_estimators"]),
                "max_depth": bp.get("xgb_max_depth", defaults["max_depth"]),
                "learning_rate": bp.get("xgb_learning_rate", defaults["learning_rate"]),
                "subsample": bp.get("xgb_subsample", defaults["subsample"]),
                "colsample_bytree": bp.get("xgb_colsample_bytree", defaults["colsample_bytree"]),
            }

        return defaults

    def get_most_relevant_snapshot(
        self,
        current_regime: str = "unknown",
    ) -> RunSnapshot | None:
        """Find the historical run most relevant to the current regime.

        Returns the best-performing snapshot in the matching regime,
        or the overall best if no regime match exists.
        """
        if not self.knowledge.snapshots:
            return None

        # Look for same-regime snapshots
        regime_snaps = [
            s for s in self.knowledge.snapshots if s.regime == current_regime
        ]
        if regime_snaps:
            return max(regime_snaps, key=lambda s: s.sharpe)

        # Fallback: best overall
        return max(self.knowledge.snapshots, key=lambda s: s.sharpe)

    # ─────────────────────────────────────────────────────────────
    #  INTERNAL HELPERS
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_snapshot_params(params: Any, snapshot_params: dict[str, Any]) -> None:
        """Apply snapshot parameter values to an EvolvedParams instance."""
        for key, value in snapshot_params.items():
            if hasattr(params, key):
                setattr(params, key, value)

    def _apply_weighted_average(self, params: Any) -> None:
        """Compute decay-weighted average of all snapshots and apply.

        More recent snapshots (later index) get higher weight.
        Only apply for parameters where we have enough evidence (≥3 snapshots).
        """
        n = len(self.knowledge.snapshots)
        if n < 2:
            if n == 1:
                self._apply_snapshot_params(
                    params, self.knowledge.snapshots[0].evolved_snapshot,
                )
            return

        # Compute weights: newest snapshot gets weight 1.0, then _RUN_DECAY^1, etc.
        weights = [_RUN_DECAY ** (n - 1 - i) for i in range(n)]
        total_w = sum(weights)

        # Collect parameter keys from snapshots
        param_keys = set()
        for s in self.knowledge.snapshots:
            param_keys.update(s.evolved_snapshot.keys())

        for key in param_keys:
            values = []
            ws = []
            for i, snap in enumerate(self.knowledge.snapshots):
                if key in snap.evolved_snapshot:
                    val = snap.evolved_snapshot[key]
                    # Only average numeric values
                    if isinstance(val, (int, float)):
                        values.append(val)
                        ws.append(weights[i])

            if not values:
                continue

            # Weighted average
            w_total = sum(ws)
            if w_total > 0:
                avg = sum(v * w for v, w in zip(values, ws)) / w_total
                # Preserve type: int fields stay int
                if hasattr(params, key):
                    current = getattr(params, key)
                    if isinstance(current, int):
                        avg = int(round(avg))
                    setattr(params, key, avg)

    def _seed_feature_weights(self, params: Any) -> None:
        """Seed feature weights from accumulated global importance.

        Normalises global importance to [0.2, 2.0] range for feature
        selection weights.
        """
        if not self.knowledge.global_feature_importance:
            return

        imp = self.knowledge.global_feature_importance
        max_imp = max(imp.values()) if imp else 1.0
        if max_imp <= 0:
            return

        # Map to [0.2, 2.0]
        seeded = {}
        for feat, val in imp.items():
            normalised = val / max_imp  # 0..1
            seeded[feat] = 0.2 + normalised * 1.8  # [0.2, 2.0]

        # Merge: only set if not already set by brain restore
        if not params.feature_weights:
            params.feature_weights = seeded
        else:
            # Blend: 70% existing + 30% transferred
            for feat, tval in seeded.items():
                existing = params.feature_weights.get(feat)
                if existing is not None:
                    params.feature_weights[feat] = 0.7 * existing + 0.3 * tval
                else:
                    params.feature_weights[feat] = tval

    def summary(self) -> dict[str, Any]:
        """Return a summary dict for diagnostics / API responses."""
        return {
            "total_snapshots": len(self.knowledge.snapshots),
            "best_sharpe": (
                round(self.knowledge.best_sharpe, 4)
                if math.isfinite(self.knowledge.best_sharpe) else None
            ),
            "regimes_tracked": list(self.knowledge.regime_best_config.keys()),
            "feature_count": len(self.knowledge.global_feature_importance),
            "latest_runs": [
                {
                    "run_id": s.run_id,
                    "regime": s.regime,
                    "sharpe": round(s.sharpe, 2),
                    "win_rate": round(s.win_rate, 3),
                }
                for s in self.knowledge.snapshots[-5:]
            ],
        }
