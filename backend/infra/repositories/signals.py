"""
Signals repository - tracks trading signals and model predictions.
Implements async CRUD operations with proper error handling.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import Signal

logger = logging.getLogger(__name__)


class SignalNotFoundError(Exception):
    """Raised when a signal is not found."""

    pass


class DuplicateSignalError(Exception):
    """Raised when attempting to create a duplicate signal."""

    pass


class SignalsRepo:
    """Repository for signal operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_signal(
        self,
        *,
        symbol: str,
        model_name: str,
        signal_type: str,
        direction: str,
        strength: Decimal,
        confidence: Decimal,
        target_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        expiry: datetime | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Signal:
        """
        Create a new trading signal.

        Args:
            symbol: Trading symbol
            model_name: Name of the model generating the signal
            signal_type: Type of signal ('buy', 'sell', 'hold', 'entry', 'exit')
            direction: Direction of the signal ('long', 'short', 'neutral')
            strength: Signal strength (0.0 to 1.0)
            confidence: Model confidence (0.0 to 1.0)
            target_price: Optional target price
            stop_loss: Optional stop loss price
            expiry: Optional expiry timestamp
            attributes: Optional additional attributes

        Returns:
            Signal: Newly created signal

        Raises:
            DuplicateSignalError: If there's a constraint violation
        """
        new_signal = Signal(
            symbol=symbol,
            model_name=model_name,
            signal_type=signal_type,
            direction=direction,
            strength=strength,
            confidence=confidence,
            target_price=target_price,
            stop_loss=stop_loss,
            expiry=expiry,
            attributes=attributes or {},
        )

        try:
            self.session.add(new_signal)
            await self.session.flush()  # Get the ID without committing

            logger.info(
                "New signal created",
                extra={
                    "signal_id": str(new_signal.id),
                    "symbol": symbol,
                    "model_name": model_name,
                    "signal_type": signal_type,
                    "direction": direction,
                    "strength": str(strength),
                    "confidence": str(confidence),
                },
            )

            return new_signal

        except IntegrityError as e:
            await self.session.rollback()
            logger.error(
                "Failed to create signal",
                extra={
                    "symbol": symbol,
                    "model_name": model_name,
                    "signal_type": signal_type,
                    "error": str(e),
                },
            )
            raise DuplicateSignalError(f"Failed to create signal for {symbol}") from e

    async def get_by_id(self, signal_id: uuid.UUID) -> Signal | None:
        """
        Get signal by ID.

        Args:
            signal_id: Signal ID

        Returns:
            Signal if found, None otherwise
        """
        stmt = select(Signal).where(Signal.id == signal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_signals(
        self,
        symbol: str | None = None,
        model_name: str | None = None,
        signal_type: str | None = None,
    ) -> list[Signal]:
        """
        Get active (non-expired) signals.

        Args:
            symbol: Optional symbol filter
            model_name: Optional model name filter
            signal_type: Optional signal type filter

        Returns:
            List of active signals
        """
        conditions = []

        # Only include active signals (not expired)
        current_time = datetime.now(UTC)
        conditions.append(or_(Signal.expiry.is_(None), Signal.expiry > current_time))

        if symbol:
            conditions.append(Signal.symbol == symbol)

        if model_name:
            conditions.append(Signal.model_name == model_name)

        if signal_type:
            conditions.append(Signal.signal_type == signal_type)

        stmt = (
            select(Signal).where(and_(*conditions)).order_by(Signal.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_signal_by_symbol_and_model(
        self, symbol: str, model_name: str
    ) -> Signal | None:
        """
        Get the latest signal for a symbol from a specific model.

        Args:
            symbol: Trading symbol
            model_name: Model name

        Returns:
            Latest signal if found, None otherwise
        """
        stmt = (
            select(Signal)
            .where(and_(Signal.symbol == symbol, Signal.model_name == model_name))
            .order_by(Signal.created_at.desc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_signals_by_timerange(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: str | None = None,
        model_name: str | None = None,
    ) -> list[Signal]:
        """
        Get signals within a time range.

        Args:
            start_time: Start time
            end_time: End time
            symbol: Optional symbol filter
            model_name: Optional model name filter

        Returns:
            List of signals in time range
        """
        conditions = [Signal.created_at >= start_time, Signal.created_at <= end_time]

        if symbol:
            conditions.append(Signal.symbol == symbol)

        if model_name:
            conditions.append(Signal.model_name == model_name)

        stmt = select(Signal).where(and_(*conditions)).order_by(Signal.created_at.asc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_high_confidence_signals(
        self,
        min_confidence: Decimal = Decimal("0.8"),
        min_strength: Decimal = Decimal("0.7"),
        limit: int = 50,
    ) -> list[Signal]:
        """
        Get high-confidence signals above specified thresholds.

        Args:
            min_confidence: Minimum confidence threshold
            min_strength: Minimum strength threshold
            limit: Maximum number of signals to return

        Returns:
            List of high-confidence signals
        """
        current_time = datetime.now(UTC)

        stmt = (
            select(Signal)
            .where(
                and_(
                    Signal.confidence >= min_confidence,
                    Signal.strength >= min_strength,
                    or_(Signal.expiry.is_(None), Signal.expiry > current_time),
                )
            )
            .order_by(
                (Signal.confidence * Signal.strength).desc(), Signal.created_at.desc()
            )
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def expire_signal(self, signal_id: uuid.UUID) -> None:
        """
        Mark a signal as expired.

        Args:
            signal_id: Signal ID

        Raises:
            SignalNotFoundError: If signal not found
        """
        stmt = (
            update(Signal)
            .where(Signal.id == signal_id)
            .values(expiry=datetime.now(UTC), updated_at=datetime.now(UTC))
            .returning(Signal.id)
        )

        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()

        if not updated_id:
            raise SignalNotFoundError(f"Signal {signal_id} not found")

        logger.info("Signal expired", extra={"signal_id": str(signal_id)})

    async def expire_signals_by_model(self, model_name: str) -> int:
        """
        Expire all active signals from a specific model.

        Args:
            model_name: Model name

        Returns:
            Number of signals expired
        """
        current_time = datetime.now(UTC)

        stmt = (
            update(Signal)
            .where(
                and_(
                    Signal.model_name == model_name,
                    or_(Signal.expiry.is_(None), Signal.expiry > current_time),
                )
            )
            .values(expiry=current_time, updated_at=current_time)
        )

        result = await self.session.execute(stmt)
        expired_count = result.rowcount or 0

        logger.info(
            "Signals expired by model",
            extra={"model_name": model_name, "expired_count": expired_count},
        )

        return expired_count

    async def get_signal_performance_metrics(
        self,
        model_name: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Calculate performance metrics for signals from a specific model.

        Args:
            model_name: Model name
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Dictionary with performance metrics
        """
        conditions = [Signal.model_name == model_name]

        if start_time:
            conditions.append(Signal.created_at >= start_time)

        if end_time:
            conditions.append(Signal.created_at <= end_time)

        # Get all signals for the model
        stmt = select(Signal).where(and_(*conditions)).order_by(Signal.created_at.asc())

        result = await self.session.execute(stmt)
        signals = list(result.scalars().all())

        if not signals:
            return {
                "model_name": model_name,
                "total_signals": 0,
                "avg_confidence": None,
                "avg_strength": None,
                "signal_types": {},
                "directions": {},
                "active_signals": 0,
            }

        # Calculate metrics
        total_signals = len(signals)
        avg_confidence = sum(s.confidence for s in signals) / total_signals
        avg_strength = sum(s.strength for s in signals) / total_signals

        # Count signal types
        signal_types = {}
        for signal in signals:
            signal_types[signal.signal_type] = (
                signal_types.get(signal.signal_type, 0) + 1
            )

        # Count directions
        directions = {}
        for signal in signals:
            directions[signal.direction] = directions.get(signal.direction, 0) + 1

        # Count active signals
        current_time = datetime.now(UTC)
        active_signals = sum(
            1 for s in signals if s.expiry is None or s.expiry > current_time
        )

        return {
            "model_name": model_name,
            "total_signals": total_signals,
            "avg_confidence": avg_confidence,
            "avg_strength": avg_strength,
            "signal_types": signal_types,
            "directions": directions,
            "active_signals": active_signals,
            "time_range": {
                "start": start_time,
                "end": end_time,
                "first_signal": signals[0].created_at if signals else None,
                "last_signal": signals[-1].created_at if signals else None,
            },
        }

    async def get_consensus_signals(
        self, symbol: str, min_models: int = 2, max_age_hours: int = 24
    ) -> dict[str, Any]:
        """
        Get consensus signals for a symbol from multiple models.

        Args:
            symbol: Trading symbol
            min_models: Minimum number of models required for consensus
            max_age_hours: Maximum age of signals in hours

        Returns:
            Dictionary with consensus analysis
        """
        from datetime import timedelta

        cutoff_time = datetime.now(UTC) - timedelta(hours=max_age_hours)

        # Get recent active signals for the symbol
        conditions = [
            Signal.symbol == symbol,
            Signal.created_at >= cutoff_time,
            or_(Signal.expiry.is_(None), Signal.expiry > datetime.now(UTC)),
        ]

        stmt = (
            select(Signal).where(and_(*conditions)).order_by(Signal.created_at.desc())
        )

        result = await self.session.execute(stmt)
        signals = list(result.scalars().all())

        if len(signals) < min_models:
            return {
                "symbol": symbol,
                "consensus": "insufficient_data",
                "model_count": len(signals),
                "min_models_required": min_models,
                "signals": [],
            }

        # Group by model name and get latest signal from each
        model_signals = {}
        for signal in signals:
            if (
                signal.model_name not in model_signals
                or signal.created_at > model_signals[signal.model_name].created_at
            ):
                model_signals[signal.model_name] = signal

        latest_signals = list(model_signals.values())

        if len(latest_signals) < min_models:
            return {
                "symbol": symbol,
                "consensus": "insufficient_models",
                "model_count": len(latest_signals),
                "min_models_required": min_models,
                "signals": [],
            }

        # Calculate consensus metrics
        directions = [s.direction for s in latest_signals]
        signal_types = [s.signal_type for s in latest_signals]

        # Find most common direction and signal type
        direction_counts = {d: directions.count(d) for d in set(directions)}
        type_counts = {t: signal_types.count(t) for t in set(signal_types)}

        consensus_direction = max(direction_counts, key=direction_counts.get)
        consensus_type = max(type_counts, key=type_counts.get)

        # Calculate agreement percentages
        direction_agreement = direction_counts[consensus_direction] / len(
            latest_signals
        )
        type_agreement = type_counts[consensus_type] / len(latest_signals)

        # Calculate average confidence and strength
        avg_confidence = sum(s.confidence for s in latest_signals) / len(latest_signals)
        avg_strength = sum(s.strength for s in latest_signals) / len(latest_signals)

        # Determine consensus strength
        if direction_agreement >= 0.8 and type_agreement >= 0.8:
            consensus_strength = "strong"
        elif direction_agreement >= 0.6 and type_agreement >= 0.6:
            consensus_strength = "moderate"
        else:
            consensus_strength = "weak"

        return {
            "symbol": symbol,
            "consensus": consensus_strength,
            "consensus_direction": consensus_direction,
            "consensus_type": consensus_type,
            "direction_agreement": direction_agreement,
            "type_agreement": type_agreement,
            "model_count": len(latest_signals),
            "avg_confidence": avg_confidence,
            "avg_strength": avg_strength,
            "signals": [
                {
                    "model_name": s.model_name,
                    "signal_type": s.signal_type,
                    "direction": s.direction,
                    "strength": s.strength,
                    "confidence": s.confidence,
                    "created_at": s.created_at,
                }
                for s in latest_signals
            ],
        }
