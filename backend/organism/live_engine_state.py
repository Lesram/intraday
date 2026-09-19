"""Startup state-reconstruction helpers for the live engine.

Extracted from ``live_engine.py`` (2026-06-08 decomposition) as a mixin to
shrink the ``OrganismLiveEngine`` god-object. These two methods form a cohesive
"rebuild engine state from DB / broker on startup" responsibility and have no
intra-class method calls. ``OrganismLiveEngine`` inherits
``_StateReconstructionMixin`` so ``inspect.getsource`` on these methods still
resolves via the MRO, and every behavioural call site is unchanged.

backend.organism dependencies are imported lazily inside the methods (the same
deferred-import pattern the originals use for SQLAlchemy) to avoid any import
cycle with ``live_engine`` itself. Behaviour is otherwise byte-for-byte
identical to the prior inline methods.

Requires the host class to provide: ``_sessionmaker``, ``_all_trades``,
``_cumulative_pnl``, ``learner``, ``_positions_service``, ``_exit_levels``,
``_data_client``, ``exit_engine``, ``_pyramid_positions``, ``_entry_metadata``.
"""
from __future__ import annotations

import asyncio

import pandas as pd

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class _StateReconstructionMixin:
    """Rebuild trade history and open-position state on engine startup."""

    async def _reconstruct_trades_from_db(self) -> None:
        """Reconstruct trade history from filled organism orders in DB.

        Called on startup when brain has no trade records (e.g. after a
        Docker restart that wiped trade_history.csv before it was written).
        Pairs entry and exit orders per symbol to build TradeRecord objects.
        """
        from sqlalchemy import select, text as sa_text
        from backend.infra.schemas import Order
        from backend.organism.continuous_learner import TradeRecord
        from backend.organism.schema.candidate_signal import infer_strategy_id

        async with self._sessionmaker() as session:
            stmt = (
                select(Order)
                .where(
                    Order.status == "filled",
                    sa_text("attributes->>'source' = 'organism'"),
                )
                .order_by(Order.submitted_at.asc())
            )
            result = await session.execute(stmt)
            orders = list(result.scalars().all())

        if not orders:
            logger.info("No filled organism orders in DB — nothing to reconstruct")
            return

        # Separate entries and exits
        entry_reasons = {"entry", "pyramid", "ml_entry", "alpha_entry", "breakout_entry"}
        entries: dict[str, list] = {}  # symbol → [order, ...]
        exits: dict[str, list] = {}

        for o in orders:
            attrs = o.attributes or {}
            reason = (attrs.get("reason") or "").lower()
            sym = o.symbol

            is_entry = (
                any(r in reason for r in entry_reasons)
                or (o.side == "buy" and not reason)
            )
            if is_entry:
                entries.setdefault(sym, []).append(o)
            else:
                exits.setdefault(sym, []).append(o)

        # Pair exits to entries
        reconstructed: list[TradeRecord] = []
        entry_idx: dict[str, int] = {}  # symbol → next unmatched entry index

        for sym, exit_orders in exits.items():
            sym_entries = entries.get(sym, [])
            idx = entry_idx.get(sym, 0)

            for ex_order in exit_orders:
                if idx >= len(sym_entries):
                    break  # No more entries to match

                en_order = sym_entries[idx]
                idx += 1

                entry_price = float(en_order.avg_fill_price or 0)
                exit_price = float(ex_order.avg_fill_price or 0)
                shares = int(float(en_order.filled_qty or en_order.qty or 0))

                if entry_price <= 0 or exit_price <= 0 or shares <= 0:
                    continue

                pnl = (exit_price - entry_price) * shares
                actual_return = (exit_price - entry_price) / entry_price

                en_attrs = en_order.attributes or {}
                ex_attrs = ex_order.attributes or {}

                # Audit-G v2 GAP-5 (2026-05-02): derive
                # is_reconciliation_artifact from exit_reason so DB-restored
                # trades correctly skip learner.record_trade below.
                _ex_reason = ex_attrs.get("reason", "unknown")
                _is_recon = _ex_reason == "reconciliation_adjustment"

                # V5 B-T-1 / Wave-18 (2026-05-03): direction was hard-coded
                # to 1.0 (LONG_ONLY). If LONG_ONLY is ever flipped to False
                # (or STRONG_SHORT_ENABLED / inverse-ETF flow exits a short
                # via DB), every short trade restored from the DB would
                # carry direction=1.0, inverting `actual_return` and
                # `correct_direction` and poisoning the learner.
                # Resolve direction from the entry order's side instead;
                # buy → +1, sell → -1. Fall back to +1 only when the side
                # is missing AND LONG_ONLY is in force (preserving prior
                # behavior under the only configuration where it was safe).
                _en_side = (getattr(en_order, "side", "") or "").lower()
                if _en_side == "buy":
                    _direction = 1.0
                elif _en_side == "sell":
                    _direction = -1.0
                else:
                    _direction = 1.0  # legacy default; LONG_ONLY-safe.
                # Recompute pnl/actual_return so they match the resolved
                # direction (entry → exit price diff is signed by direction).
                if _direction < 0:
                    pnl = (entry_price - exit_price) * shares
                    actual_return = (entry_price - exit_price) / entry_price

                reconstructed.append(TradeRecord(
                    symbol=sym,
                    direction=_direction,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_bar=0,
                    exit_bar=0,
                    shares=shares,
                    pnl=pnl,
                    exit_reason=_ex_reason,
                    predicted_return=0.0,
                    actual_return=actual_return,
                    confidence=float(en_attrs.get("confidence", 0.0)),
                    is_reconciliation_artifact=_is_recon,
                    strategy_id=infer_strategy_id(
                        en_attrs.get("entry_source", ""),
                        en_attrs.get("strategy_id", ""),
                    ),
                    closed_at="",
                ))

            entry_idx[sym] = idx

        if not reconstructed:
            logger.info("No matched entry/exit pairs found in DB")
            return

        self._all_trades = reconstructed
        cumulative = 0.0
        for t in reconstructed:
            cumulative += t.pnl
        self._cumulative_pnl = cumulative
        # Do NOT populate _equity_curve from PnL — it should only contain
        # actual broker equity snapshots from _get_equity().

        # Feed reconstructed trades to learner so ML can train.
        # Audit-G v2 GAP-5: skip reconciliation artifacts.
        if hasattr(self, 'learner') and self.learner:
            for t in reconstructed:
                if getattr(t, "is_reconciliation_artifact", False):
                    continue
                try:
                    self.learner.record_trade(t)
                except Exception as e:
                    logger.warning("Failed to record reconstructed trade for %s: %s", t.symbol, e)
            logger.info(
                "Fed %d reconstructed trades to learner (total_trades=%d)",
                len(reconstructed), self.learner.state.total_trades,
            )

        logger.info(
            "Reconstructed %d trades from DB: cumulative PnL=$%.2f",
            len(reconstructed),
            cumulative,
        )

    async def _reconstruct_position_state(self) -> None:
        """On startup, reconstruct exit levels and pyramid state
        from live broker positions.

        This handles the case where the engine restarts mid-trade.
        """
        from backend.organism.live_engine import LIVE_TIMEFRAME, PREDICTION_HORIZON
        from backend.organism.pyramider import PyramidLevel, PyramidPosition
        from backend.organism.regime import RegimeLabel

        try:
            positions = await self._positions_service.get_all_positions()
        except Exception as e:
            logger.warning("Cannot reconstruct positions: %s", e)
            return

        if not positions:
            return

        for sym, pos_data in positions.items():
            qty = abs(float(pos_data.get("qty", 0)))
            avg_entry = float(pos_data.get("avg_entry_price", 0))
            side = pos_data.get("side", "long")
            direction = 1.0 if side == "long" else -1.0

            if qty <= 0 or avg_entry <= 0:
                continue

            # Skip symbols that already have exit levels restored from
            # the brain — those have richer state (trailing stop progress,
            # partial_tp_taken, stress_tightened) that would be lost if we
            # overwrite with fresh conservative defaults.
            if sym in self._exit_levels:
                logger.debug(
                    "Skipping reconstruction for %s — exit levels "
                    "already restored from brain",
                    sym,
                )
                continue

            # Create basic exit levels (conservative defaults)
            try:
                feat_df = None
                if hasattr(self._data_client, "get_historical_data"):
                    raw = await asyncio.to_thread(
                        self._data_client.get_historical_data,
                        sym, timeframe=LIVE_TIMEFRAME, limit=100,
                    )
                    if raw is not None and not raw.empty:
                        col_map = {
                            "Open": "open", "High": "high",
                            "Low": "low", "Close": "close",
                            "Volume": "volume",
                        }
                        feat_df = raw.rename(columns=col_map)

                if feat_df is not None and len(feat_df) > 10:
                    exit_lvl = self.exit_engine.create_exit_levels(
                        symbol=sym,
                        direction=direction,
                        entry_price=avg_entry,
                        predicted_return=0.02,
                        features_df=feat_df,
                        regime=RegimeLabel.UNKNOWN,
                        prediction_horizon=PREDICTION_HORIZON,
                    )
                else:
                    # Fallback: create exit levels with a 2% ATR estimate.
                    # Better than nothing — ensures max-loss safety net is
                    # enforced through normal check_exit() rather than only
                    # through the emergency safety net added in the tick loop.
                    fallback_atr = avg_entry * 0.02
                    fallback_df = pd.DataFrame({
                        "close": [avg_entry] * 20,
                        "high": [avg_entry * 1.01] * 20,
                        "low": [avg_entry * 0.99] * 20,
                    })
                    exit_lvl = self.exit_engine.create_exit_levels(
                        symbol=sym,
                        direction=direction,
                        entry_price=avg_entry,
                        predicted_return=0.02,
                        features_df=fallback_df,
                        regime=RegimeLabel.UNKNOWN,
                        prediction_horizon=PREDICTION_HORIZON,
                    )
                    logger.warning(
                        "Using fallback ATR ($%.2f) for %s — "
                        "no historical data available",
                        fallback_atr, sym,
                    )

                self._exit_levels[sym] = exit_lvl

                atr = exit_lvl.atr_at_entry
                self._pyramid_positions[sym] = PyramidPosition(
                    symbol=sym,
                    direction=direction,
                    layers=[
                        PyramidLevel(
                            shares=int(qty),
                            entry_price=avg_entry,
                            bar_added=0,
                            level=0,
                        )
                    ],
                    # V4 R-F-9 (2026-05-02): symmetry with in-tick orphan
                    # adoption (line ~5198). The previous startup path used
                    # `qty * 1.5` while the in-tick path uses `qty` flat,
                    # an asymmetry that meant a startup-adopted orphan
                    # would invite a pyramid add to reach 1.5×qty whereas
                    # the same position adopted in-tick would not. The
                    # pyramid-block guard (H-7) catches the actual add,
                    # but eliminating the asymmetry is defense in depth
                    # and matches the H-7 fix at the in-tick site.
                    target_total_shares=int(qty),
                    atr_at_entry=atr,
                    initial_stop=exit_lvl.stop_loss,
                    current_stop=exit_lvl.stop_loss,
                    highest_price=avg_entry,
                    lowest_price=avg_entry,
                )

                # Audit-G v2 GAP-1 (2026-05-02): tag startup-recovery orphan
                # adoptions identically to in-tick orphan adoption (Phase 4).
                # Otherwise post-restart orphan closes pollute learning.
                self._entry_metadata[sym] = {
                    "entry_price": avg_entry,
                    "entry_tick": 0,
                    "direction": direction,
                    "predicted_return": 0.02,
                    "confidence": 0.5,
                    "entry_source": "reconciliation_orphan",
                    "strategy_id": "reconciliation_artifact",
                }

                logger.info(
                    "Reconstructed position state for %s: "
                    "%d shares @ $%.2f",
                    sym,
                    int(qty),
                    avg_entry,
                )

            except Exception as e:
                logger.warning("Cannot reconstruct %s: %s", sym, e)
