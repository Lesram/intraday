"""ML lifecycle runner.

Implements:
- Daily monitoring snapshots (performance + drift)
- Weekly retrain trigger
- Monthly promotion review (optional promotion)

Notes:
- This is an in-process implementation intended for dev / single-worker setups.
- For production, prefer an external scheduler + worker queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import ModelLifecycleEvent, ModelMonitoringSnapshot, ModelRegistry


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _is_test_mode() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("DISABLE_MARKET_DATA_FETCH", "0") == "1"


@dataclass(frozen=True)
class LifecycleJobResult:
    ok: bool
    message: str
    details: dict[str, Any]


async def _log_event(
    db: AsyncSession,
    *,
    event_type: str,
    model_id: Any | None,
    model_name: str | None,
    model_version: str | None,
    payload: dict[str, Any],
) -> None:
    row = ModelLifecycleEvent(
        model_id=model_id,
        model_name=model_name or "",
        model_version=model_version,
        event_type=event_type,
        payload=payload,
        created_at=_utcnow(),
    )
    db.add(row)


async def get_active_models(db: AsyncSession) -> list[ModelRegistry]:
    res = await db.execute(
        select(ModelRegistry).where(ModelRegistry.active.is_(True)).order_by(desc(ModelRegistry.updated_at))
    )
    return list(res.scalars().all())


async def run_monitoring_snapshot(
    db: AsyncSession,
    *,
    db_model: ModelRegistry,
    lookback_days: int,
) -> ModelMonitoringSnapshot | None:
    """Create and persist a monitoring snapshot for a model."""

    # Import helpers from the existing route module to avoid duplicating feature engineering logic.
    # TODO: refactor these helpers into a dedicated module.
    from backend.api.routes.models import _align_features, _build_monitor_frame  # noqa: PLC0415

    metrics_data = db_model.metrics or {}
    symbols = list(metrics_data.get("symbols") or [])
    feature_columns = list(metrics_data.get("feature_columns") or [])
    target_kind = str(metrics_data.get("target_kind") or "direction_up")
    drift_baseline = (metrics_data.get("custom_metrics") or {}).get("drift_baseline") or {}

    if _is_test_mode():
        await _log_event(
            db,
            event_type="monitoring_skipped",
            model_id=db_model.id,
            model_name=db_model.name,
            model_version=db_model.version,
            payload={"reason": "test_mode", "lookback_days": int(lookback_days)},
        )
        return None

    if not symbols or not feature_columns:
        await _log_event(
            db,
            event_type="monitoring_failed",
            model_id=db_model.id,
            model_name=db_model.name,
            model_version=db_model.version,
            payload={"reason": "missing_symbols_or_feature_columns"},
        )
        return None

    from backend.ml.drift import compute_drift  # noqa: PLC0415
    from backend.ml.model_selection import (  # noqa: PLC0415
        evaluate_baseline_buy_and_hold,
        evaluate_model_on_ohlcv,
    )
    from backend.utils.secure_pickle import secure_load_from_path  # noqa: PLC0415

    X_raw, close, next_close = _build_monitor_frame(symbols, int(lookback_days))
    X_eval = _align_features(X_raw, feature_columns)

    if getattr(X_eval, "empty", False):
        await _log_event(
            db,
            event_type="monitoring_failed",
            model_id=db_model.id,
            model_name=db_model.name,
            model_version=db_model.version,
            payload={"reason": "insufficient_market_data", "lookback_days": int(lookback_days)},
        )
        return None

    drift = compute_drift(drift_baseline, X_eval)
    perf = evaluate_model_on_ohlcv(
        model=secure_load_from_path(str(db_model.path)),
        X_eval=X_eval,
        close_eval=close,
        next_close_eval=next_close,
        target_kind=target_kind,  # type: ignore[arg-type]
        transaction_cost_bps=float(os.getenv("MODEL_EVAL_TX_COST_BPS", "1.0")),
    )
    baseline = evaluate_baseline_buy_and_hold(close_eval=close, next_close_eval=next_close)

    window_start = close.index.min().to_pydatetime() if hasattr(close.index, "min") else _utcnow()
    window_end = close.index.max().to_pydatetime() if hasattr(close.index, "max") else _utcnow()

    snapshot = ModelMonitoringSnapshot(
        model_id=db_model.id,
        model_name=db_model.name,
        model_version=db_model.version,
        window_start=window_start,
        window_end=window_end,
        metrics={
            "total_return": perf.total_return,
            "cagr": perf.cagr,
            "sharpe": perf.sharpe,
            "max_drawdown": perf.max_drawdown,
            "baseline_buy_hold_total_return": baseline.total_return,
            "n": perf.n_samples,
        },
        drift={
            "psi_score": drift.psi_score,
            "affected_features": drift.affected_features,
        },
        created_at=_utcnow(),
    )
    db.add(snapshot)

    await _log_event(
        db,
        event_type="monitoring_snapshot",
        model_id=db_model.id,
        model_name=db_model.name,
        model_version=db_model.version,
        payload={
            "lookback_days": int(lookback_days),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "metrics": snapshot.metrics,
            "drift": snapshot.drift,
        },
    )

    return snapshot


async def run_daily_monitoring(
    db: AsyncSession,
    *,
    lookback_days: int,
) -> LifecycleJobResult:
    models = await get_active_models(db)
    created = 0
    skipped = 0
    for m in models:
        snap = await run_monitoring_snapshot(db, db_model=m, lookback_days=int(lookback_days))
        if snap is None:
            skipped += 1
        else:
            created += 1

    await db.commit()
    return LifecycleJobResult(
        ok=True,
        message=f"Daily monitoring completed: {created} snapshots, {skipped} skipped",
        details={"created": created, "skipped": skipped, "models": len(models)},
    )


async def run_weekly_retrain(
    db: AsyncSession,
    *,
    lookback_days: int,
    min_return_drop: float,
    psi_threshold: float,
) -> LifecycleJobResult:
    from backend.api.routes.models import _enqueue_training_job  # noqa: PLC0415
    from backend.ml.monitoring import decide_retrain  # noqa: PLC0415
    from backend.models.ml_models import ModelTrainingRequest, ModelType  # noqa: PLC0415

    models = await get_active_models(db)
    triggered = 0
    evaluated = 0

    for m in models:
        snap = await run_monitoring_snapshot(db, db_model=m, lookback_days=int(lookback_days))
        if snap is None:
            continue

        evaluated += 1

        metrics_data = m.metrics or {}
        selection = ((metrics_data.get("custom_metrics") or {}).get("selection") or {}).get("new") or {}
        reference_total_return = selection.get("total_return")

        decision = decide_retrain(
            recent_total_return=float((snap.metrics or {}).get("total_return", 0.0)),
            reference_total_return=float(reference_total_return) if reference_total_return is not None else None,
            psi_score=float((snap.drift or {}).get("psi_score")) if (snap.drift or {}).get("psi_score") is not None else None,
            min_return_drop=float(min_return_drop),
            psi_threshold=float(psi_threshold),
        )

        training_id: str | None = None
        if decision.should_retrain:
            symbols = list(metrics_data.get("symbols") or [])
            features = list(metrics_data.get("features") or [])
            target_kind = str(metrics_data.get("target_kind") or "direction_up")
            model_type = ModelType.REGRESSION if target_kind == "next_close" else ModelType.CLASSIFICATION

            train_cfg = ModelTrainingRequest(
                model_type=model_type,
                model_name=m.name,
                features=features,
                symbols=symbols,
                lookback_days=int(lookback_days),
                test_size=float(os.getenv("MODEL_TRAIN_TEST_SIZE", "0.2")),
                hyperparameters=metrics_data.get("hyperparameters") or {},
                retrain=True,
            )
            resp = _enqueue_training_job(train_cfg)
            training_id = resp.training_id
            triggered += 1

        await _log_event(
            db,
            event_type="retrain_decision",
            model_id=m.id,
            model_name=m.name,
            model_version=m.version,
            payload={
                "should_retrain": bool(decision.should_retrain),
                "reasons": list(decision.reasons),
                "training_id": training_id,
                "lookback_days": int(lookback_days),
                "min_return_drop": float(min_return_drop),
                "psi_threshold": float(psi_threshold),
            },
        )

    await db.commit()
    return LifecycleJobResult(
        ok=True,
        message=f"Weekly retrain run completed: {triggered} retrains triggered",
        details={"triggered": triggered, "evaluated": evaluated, "models": len(models)},
    )


async def run_monthly_promotion_review(
    db: AsyncSession,
    *,
    promote_mode: str | None = None,
) -> LifecycleJobResult:
    """Review candidates and optionally promote the best one.

    promote_mode:
      - "immediate": no-op (training already promoted)
      - "monthly_review": promote best candidate if better
    """

    promote_mode = (promote_mode or os.getenv("ML_PROMOTION_MODE", "immediate")).strip().lower()

    res = await db.execute(select(ModelRegistry.name).distinct())
    names = [r[0] for r in res.all() if r and r[0]]

    promotions = 0
    reviewed = 0

    from backend.ml.active_model_pointer import write_active_model_pointer  # noqa: PLC0415

    for name in names:
        reviewed += 1
        r = await db.execute(select(ModelRegistry).where(ModelRegistry.name == name))
        models = list(r.scalars().all())
        champion = next((m for m in models if m.active), None)
        candidates = [m for m in models if not m.active]

        def score(m: ModelRegistry) -> float:
            try:
                sel = ((m.metrics or {}).get("custom_metrics") or {}).get("selection") or {}
                new = sel.get("new") or {}
                return float(new.get("total_return", float("-inf")))
            except Exception:
                return float("-inf")

        best = max(candidates, key=score, default=None)
        best_score = score(best) if best else None
        champ_score = score(champion) if champion else None

        promoted_id = None
        if promote_mode == "monthly_review" and best and (champion is None or (best_score is not None and champ_score is not None and best_score > champ_score)):
            if champion:
                champion.active = False
            best.active = True
            best.updated_at = _utcnow()
            promotions += 1
            promoted_id = str(best.id)

            # Update active pointer for live inference
            try:
                fc = list((best.metrics or {}).get("feature_columns") or [])
                target_kind = str((best.metrics or {}).get("target_kind") or "direction_up")
                write_active_model_pointer(
                    model_name=best.name,
                    model_path=str(best.path),
                    version=str(best.version),
                    trained_at=best.trained_at,
                    target_kind=target_kind,
                    feature_columns=fc,
                    extra={"promotion_mode": promote_mode},
                )
            except Exception:
                # Don't fail review on pointer write.
                pass

        await _log_event(
            db,
            event_type="promotion_review",
            model_id=champion.id if champion else None,
            model_name=name,
            model_version=champion.version if champion else None,
            payload={
                "mode": promote_mode,
                "champion": {"id": str(champion.id), "version": champion.version, "score": champ_score} if champion else None,
                "best_candidate": {"id": str(best.id), "version": best.version, "score": best_score} if best else None,
                "promoted_id": promoted_id,
            },
        )

    await db.commit()
    return LifecycleJobResult(
        ok=True,
        message=f"Monthly promotion review completed: {promotions} promotions",
        details={"reviewed_names": reviewed, "promotions": promotions, "mode": promote_mode},
    )
