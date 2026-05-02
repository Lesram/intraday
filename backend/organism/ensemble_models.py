"""
Phase 4.4 — Ensemble Model Expansion.

Wraps the existing XGBoost classifier + regressor with additional
models (Random Forest, optionally LightGBM) and averages their
direction / magnitude predictions for improved robustness.

The ensemble uses a **soft-vote** strategy:
    • Each model produces P(up) and predicted_return.
    • Final P(up) = weighted average of all models' P(up).
    • Final return = weighted average of all models' predicted_return.
    • Weights start equal and can be adapted by the EvolutionEngine
      based on per-model accuracy tracking.

Usage::

    from backend.organism.ensemble_models import EnsemblePredictor

    ensemble = EnsemblePredictor()
    ensemble.train(X_train, y_dir, y_ret)
    p_up, pred_ret = ensemble.predict(X_test)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional model imports ───────────────────────────────────────

_HAS_XGB = False
try:
    from xgboost import XGBClassifier, XGBRegressor
    _HAS_XGB = True
except ImportError:
    pass

_HAS_SKLEARN = False
try:
    from sklearn.ensemble import (
        GradientBoostingClassifier,
        GradientBoostingRegressor,
        RandomForestClassifier,
        RandomForestRegressor,
    )
    _HAS_SKLEARN = True
except ImportError:
    pass

_HAS_LGB = False
try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    pass

RANDOM_SEED = 42


class EnsemblePredictor:
    """Multi-model ensemble for direction + magnitude prediction.

    Models included (based on availability):
        1. XGBoost (primary — always present)
        2. Random Forest (sklearn)
        3. LightGBM (optional)

    Each model produces P(up) and predicted_return.  The ensemble
    combines them via weighted soft-vote.
    """

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 5,
        learning_rate: float = 0.05,
    ) -> None:
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._lr = learning_rate

        # Model pairs: (classifier, regressor, name, weight)
        self._models: list[tuple[Any, Any, str, float]] = []
        self._is_trained = False

        self._build_models()

    def _build_models(self) -> None:
        """Instantiate all available model pairs."""
        self._models.clear()

        # 1. XGBoost
        if _HAS_XGB:
            clf = XGBClassifier(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth,
                learning_rate=self._lr,
                eval_metric="logloss",
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=RANDOM_SEED,
                verbosity=0,
            )
            reg = XGBRegressor(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth,
                learning_rate=self._lr,
                objective="reg:squarederror",
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=RANDOM_SEED,
                verbosity=0,
            )
            self._models.append((clf, reg, "xgb", 0.45))
        elif _HAS_SKLEARN:
            clf = GradientBoostingClassifier(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth,
                learning_rate=self._lr,
                subsample=0.8,
                random_state=RANDOM_SEED,
            )
            reg = GradientBoostingRegressor(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth,
                learning_rate=self._lr,
                subsample=0.8,
                random_state=RANDOM_SEED,
            )
            self._models.append((clf, reg, "gbm", 0.45))

        # 2. Random Forest
        if _HAS_SKLEARN:
            rf_clf = RandomForestClassifier(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth + 2,  # RF can go slightly deeper
                min_samples_leaf=5,
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )
            rf_reg = RandomForestRegressor(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth + 2,
                min_samples_leaf=5,
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )
            self._models.append((rf_clf, rf_reg, "rf", 0.30))

        # 3. LightGBM (optional)
        if _HAS_LGB:
            lgb_clf = lgb.LGBMClassifier(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth,
                learning_rate=self._lr,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=RANDOM_SEED,
                verbose=-1,
            )
            lgb_reg = lgb.LGBMRegressor(
                n_estimators=self._n_estimators,
                max_depth=self._max_depth,
                learning_rate=self._lr,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=RANDOM_SEED,
                verbose=-1,
            )
            self._models.append((lgb_clf, lgb_reg, "lgbm", 0.25))

        # Normalise weights
        total_w = sum(w for _, _, _, w in self._models)
        if total_w > 0:
            self._models = [
                (c, r, n, w / total_w) for c, r, n, w in self._models
            ]

        logger.info(
            "EnsemblePredictor: %d models [%s]",
            len(self._models),
            ", ".join(n for _, _, n, _ in self._models),
        )

    # ── Training ─────────────────────────────────────────────────

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def model_names(self) -> list[str]:
        return [name for _, _, name, _ in self._models]

    def train(
        self,
        X: np.ndarray,
        y_direction: np.ndarray,
        y_return: np.ndarray,
    ) -> dict[str, bool]:
        """Train all models in the ensemble.

        Parameters
        ----------
        X : Feature matrix (n_samples, n_features)
        y_direction : Binary targets (0/1) for direction
        y_return : Continuous targets for return magnitude

        Returns
        -------
        {model_name: success_bool}
        """
        results: dict[str, bool] = {}
        any_trained = False

        for clf, reg, name, _w in self._models:
            try:
                clf.fit(X, y_direction)
                reg.fit(X, y_return)
                results[name] = True
                any_trained = True
                logger.debug("Ensemble model '%s' trained successfully", name)
            except Exception as e:
                results[name] = False
                logger.warning("Ensemble model '%s' training failed: %s", name, e)

        self._is_trained = any_trained
        return results

    # ── Prediction ───────────────────────────────────────────────

    def predict(self, X: np.ndarray) -> tuple[float, float]:
        """Weighted ensemble prediction.

        Parameters
        ----------
        X : Feature vector (1, n_features) — single sample.

        Returns
        -------
        (p_up, predicted_return) — both soft-vote averaged.
        """
        if not self._is_trained:
            return 0.5, 0.0

        p_up_total = 0.0
        ret_total = 0.0
        weight_total = 0.0

        for clf, reg, name, weight in self._models:
            try:
                proba = clf.predict_proba(X)[0]
                p_up = proba[1] if len(proba) > 1 else proba[0]
                pred_ret = float(reg.predict(X)[0])

                p_up_total += weight * p_up
                ret_total += weight * pred_ret
                weight_total += weight
            except Exception as e:
                logger.debug("Ensemble predict '%s' failed: %s", name, e)

        if weight_total > 0:
            return p_up_total / weight_total, ret_total / weight_total
        return 0.5, 0.0

    def predict_proba_all(self, X: np.ndarray) -> dict[str, float]:
        """Per-model P(up) for transparency / attribution."""
        results: dict[str, float] = {}
        for clf, _reg, name, _w in self._models:
            try:
                proba = clf.predict_proba(X)[0]
                results[name] = float(proba[1]) if len(proba) > 1 else float(proba[0])
            except Exception:
                results[name] = 0.5
        return results

    # ── Persistence ──────────────────────────────────────────────

    def save(self, target_dir: Any) -> bool:
        """Save all ensemble model pairs + weights to a directory.

        Audit-C concern 1 (2026-05-02): closes axis-8 parity bug.
        Without persistence, post-restart predict() ran XGB-only until
        the next retrain, producing different outputs for the same input
        (0.349 raw-confidence swing observed). Each (clf, reg, name, weight)
        tuple is serialized to ``ensemble_<name>_clf.joblib``,
        ``ensemble_<name>_reg.joblib``, plus a manifest of names+weights.

        Returns True iff at least one model pair was saved.
        """
        from pathlib import Path
        from backend.utils.secure_pickle import secure_dump_to_path
        import json

        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        if not self._is_trained:
            return False

        manifest: list[dict[str, Any]] = []
        for clf, reg, name, weight in self._models:
            try:
                clf_path = target / f"ensemble_{name}_clf.joblib"
                reg_path = target / f"ensemble_{name}_reg.joblib"
                secure_dump_to_path(clf, clf_path)
                secure_dump_to_path(reg, reg_path)
                manifest.append({"name": name, "weight": float(weight)})
            except Exception as e:
                logger.warning(
                    "EnsemblePredictor.save: failed to persist %s: %s",
                    name, e,
                )

        if not manifest:
            return False

        with open(target / "ensemble_manifest.json", "w") as f:
            json.dump({
                "n_estimators": self._n_estimators,
                "max_depth": self._max_depth,
                "learning_rate": self._lr,
                "models": manifest,
            }, f, indent=2)

        logger.info(
            "EnsemblePredictor saved: %d model pairs (%s)",
            len(manifest),
            ", ".join(m["name"] for m in manifest),
        )
        return True

    def load(self, source_dir: Any) -> bool:
        """Load all ensemble model pairs from a directory.

        Returns True iff at least one model pair was restored. Sets
        ``_is_trained=True`` if any pairs loaded — same semantics as
        post-train state.
        """
        from pathlib import Path
        from backend.utils.secure_pickle import (
            secure_load_from_path, is_signed_pickle,
        )
        import joblib
        import json

        source = Path(source_dir)
        manifest_path = source / "ensemble_manifest.json"
        if not manifest_path.is_file():
            return False

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception as e:
            logger.warning("EnsemblePredictor.load: manifest read failed: %s", e)
            return False

        loaded: list[tuple[Any, Any, str, float]] = []
        for entry in manifest.get("models", []):
            name = entry.get("name")
            weight = float(entry.get("weight", 0.0))
            clf_path = source / f"ensemble_{name}_clf.joblib"
            reg_path = source / f"ensemble_{name}_reg.joblib"
            if not (clf_path.is_file() and reg_path.is_file()):
                continue
            try:
                def _safe_load(p: Path) -> Any:
                    raw = p.read_bytes()
                    if is_signed_pickle(raw):
                        return secure_load_from_path(p)
                    return joblib.load(p)
                clf = _safe_load(clf_path)
                reg = _safe_load(reg_path)
                loaded.append((clf, reg, name, weight))
            except Exception as e:
                logger.warning(
                    "EnsemblePredictor.load: failed for %s: %s", name, e,
                )

        if not loaded:
            return False

        self._models = loaded
        self._is_trained = True
        logger.info(
            "EnsemblePredictor restored: %d model pairs",
            len(loaded),
        )
        return True

    # ── Weight adaptation ────────────────────────────────────────

    def update_weights(self, accuracy_by_model: dict[str, float]) -> None:
        """Re-weight models based on recent directional accuracy.

        Called by EvolutionEngine after evaluating each model's
        accuracy over recent trades.
        """
        updated: list[tuple[Any, Any, str, float]] = []
        for clf, reg, name, old_w in self._models:
            acc = accuracy_by_model.get(name, 0.5)
            # Map accuracy [0.4, 0.7] → weight [0.1, 1.0]
            new_w = max(0.1, min((acc - 0.3) * 2.5, 1.0))
            # EMA blend with previous weight
            blended = 0.7 * old_w + 0.3 * new_w
            updated.append((clf, reg, name, blended))

        # Normalise
        total = sum(w for _, _, _, w in updated)
        if total > 0:
            self._models = [(c, r, n, w / total) for c, r, n, w in updated]

        logger.info(
            "Ensemble weights updated: %s",
            {n: f"{w:.3f}" for _, _, n, w in self._models},
        )

    # ── Serialisation ────────────────────────────────────────────

    def get_weights(self) -> dict[str, float]:
        """Return current model weights for persistence."""
        return {name: w for _, _, name, w in self._models}

    def set_weights(self, weights: dict[str, float]) -> None:
        """Restore model weights from persistence."""
        updated = []
        for clf, reg, name, old_w in self._models:
            updated.append((clf, reg, name, weights.get(name, old_w)))
        # Normalise
        total = sum(w for _, _, _, w in updated)
        if total > 0:
            self._models = [(c, r, n, w / total) for c, r, n, w in updated]
