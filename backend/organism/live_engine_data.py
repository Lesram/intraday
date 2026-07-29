"""Market-data feeder helpers for the live engine.

Extracted from ``live_engine.py`` (2026-06-08 decomposition) as a mixin to
shrink the ``OrganismLiveEngine`` god-object. These two methods fetch bars and
compute per-symbol ML features; ``_fetch_and_compute_features`` calls
``_fetch_bars`` (both live here together). ``OrganismLiveEngine`` inherits
``_DataFeederMixin`` so ``inspect.getsource`` resolves via the MRO and the
common test pattern ``engine._fetch_and_compute_features = AsyncMock(...)``
(instance-attribute monkeypatch) is unaffected.

backend dependencies (``compute_ml_features``, ``add_multi_timeframe_features``
and the ``live_engine`` constants ``LIVE_LOOKBACK`` / ``LIVE_TIMEFRAME`` /
``MIN_BARS``) are imported lazily inside the methods — the constants in
particular must be deferred to avoid an import cycle with ``live_engine``.
Behaviour is otherwise byte-for-byte identical to the prior inline methods.

Requires the host class to provide: ``_streaming_provider``, ``_feature_store``,
``_bars_per_day``, ``_universe``, ``_positions_service``, ``_data_client``.
"""
from __future__ import annotations

import asyncio

import pandas as pd

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class _DataFeederMixin:
    """Fetch bars and compute ML features for the trading universe."""

    async def _fetch_and_compute_features(
        self,
    ) -> dict[str, pd.DataFrame]:
        """Fetch latest bars and compute ML features for the universe.

        Uses VersionedFeatureStore when available (Phase 3.3),
        falling back to raw compute_ml_features otherwise.
        Phase 5: Handles larger dynamic universe with concurrency control.
        """
        from backend.organism.live_engine import MIN_BARS
        from backend.organism.ml_features import compute_ml_features
        from backend.organism.multi_timeframe import add_multi_timeframe_features

        features_by_symbol: dict[str, pd.DataFrame] = {}
        spy_df = None
        _concurrency = asyncio.Semaphore(10)  # Max 10 parallel bar fetches
        _streaming_active = self._streaming_provider is not None

        # Fetch SPY first (needed for cross-asset features)
        # When streaming, SPY is already buffered so this is instant
        spy_df = await self._fetch_bars("SPY")

        def _compute_features_sync(
            raw_df: pd.DataFrame, sym: str, spy_ref: pd.DataFrame | None,
        ) -> pd.DataFrame:
            """CPU-bound feature computation — runs in thread when streaming."""
            if self._feature_store is not None:
                feats, _snapshot = self._feature_store.compute_features(
                    raw_df, symbol=sym,
                )
                feats_ml = compute_ml_features(
                    raw_df,
                    spy_df=spy_ref if sym != "SPY" else None,
                    bars_per_day=self._bars_per_day,
                )
                feats = feats.reset_index(drop=True)
                feats_ml = feats_ml.reset_index(drop=True)
                n_min = min(len(feats), len(feats_ml))
                feats = feats.iloc[-n_min:].reset_index(drop=True)
                feats_ml = feats_ml.iloc[-n_min:].reset_index(drop=True)
                for col in feats.columns:
                    if col not in feats_ml.columns:
                        feats_ml[col] = feats[col].values
                feats = feats_ml
            else:
                feats = compute_ml_features(
                    raw_df,
                    spy_df=spy_ref if sym != "SPY" else None,
                    bars_per_day=self._bars_per_day,
                )
                feats = feats.reset_index(drop=True)

            # Preserve OHLCV columns
            n_feats = len(feats)
            for col in ["open", "high", "low", "close", "volume"]:
                if col in raw_df.columns and col not in feats.columns:
                    feats[col] = raw_df[col].values[-n_feats:]

            # Phase 4.2: Multi-timeframe features
            feats = add_multi_timeframe_features(feats)
            return feats

        async def _fetch_one(sym: str) -> tuple[str, pd.DataFrame | None]:
            async with _concurrency:
                try:
                    if sym == "SPY" and spy_df is not None:
                        raw_df = spy_df
                    else:
                        raw_df = await self._fetch_bars(sym)

                    if raw_df is None or len(raw_df) < MIN_BARS:
                        return sym, None

                    # When streaming is active, offload CPU-bound work
                    # to a thread so the event loop stays responsive
                    if _streaming_active:
                        feats = await asyncio.to_thread(
                            _compute_features_sync, raw_df, sym, spy_df,
                        )
                    else:
                        feats = _compute_features_sync(raw_df, sym, spy_df)

                    return sym, feats
                except Exception as e:
                    logger.warning("Failed to fetch/compute %s: %s", sym, e)
                    return sym, None

        # Fetch all universe symbols concurrently (semaphore-limited)
        tasks = [_fetch_one(sym) for sym in self._universe]
        results = await asyncio.gather(*tasks)
        for sym, feats in results:
            if feats is not None:
                features_by_symbol[sym] = feats

        # Also fetch features for open position symbols that aren't in
        # the universe.  Without this, exit checks are silently skipped
        # for positions whose symbols rotated out of the universe.
        try:
            current_positions = await self._positions_service.get_all_positions()
            position_syms_missing = [
                sym for sym in current_positions
                if sym not in features_by_symbol
            ]
            if position_syms_missing:
                pos_tasks = [_fetch_one(sym) for sym in position_syms_missing]
                pos_results = await asyncio.gather(*pos_tasks)
                for sym, feats in pos_results:
                    if feats is not None:
                        features_by_symbol[sym] = feats
                logger.info(
                    "Fetched features for %d position symbols outside universe: %s",
                    len(position_syms_missing),
                    position_syms_missing,
                )
        except Exception as e:
            logger.warning("Failed to fetch position symbol features: %s", e)

        return features_by_symbol

    async def _fetch_bars(self, symbol: str) -> pd.DataFrame | None:
        """Fetch historical bars for a single symbol.

        When a streaming provider is active, returns bars from the
        in-memory ring buffer (zero latency).  Falls back to REST
        if streaming has no data for this symbol.

        Handles both sync clients (AlpacaClient) and async clients
        (AlpacaDataClient) transparently.
        """
        from backend.organism.live_engine import LIVE_LOOKBACK, LIVE_TIMEFRAME, MIN_BARS

        # ── Streaming fast-path ──────────────────────────────────
        if self._streaming_provider is not None:
            try:
                df = self._streaming_provider.get_bars(symbol, LIVE_LOOKBACK)
                if df is not None and not df.empty and len(df) >= MIN_BARS:
                    return df
                # Fall through to REST if streaming buffer insufficient
            except Exception as e:
                logger.debug("Streaming fallback for %s: %s", symbol, e)

        try:
            if hasattr(self._data_client, "get_historical_bars_df"):
                method = self._data_client.get_historical_bars_df
                if asyncio.iscoroutinefunction(method):
                    df = await method(
                        symbol,
                        lookback=LIVE_LOOKBACK,
                        timeframe=LIVE_TIMEFRAME,
                    )
                else:
                    df = await asyncio.to_thread(
                        method,
                        symbol,
                        lookback=LIVE_LOOKBACK,
                        timeframe=LIVE_TIMEFRAME,
                    )
            elif hasattr(self._data_client, "get_historical_data"):
                method = self._data_client.get_historical_data
                if asyncio.iscoroutinefunction(method):
                    df = await method(
                        symbol,
                        timeframe=LIVE_TIMEFRAME,
                        limit=LIVE_LOOKBACK,
                    )
                else:
                    df = await asyncio.to_thread(
                        method,
                        symbol,
                        timeframe=LIVE_TIMEFRAME,
                        limit=LIVE_LOOKBACK,
                    )
            else:
                return None

            if df is None or df.empty:
                return None

            # Normalize columns
            col_map = {
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
            df = df.rename(columns=col_map)
            return df

        except Exception as e:
            logger.warning("Bar fetch failed for %s: %s", symbol, e)
            return None
