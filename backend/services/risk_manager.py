"""
Risk Management Service
Handles real-time risk metric calculations, violation detection, and emergency stops.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
import uuid
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.alerting import (
    AlertSeverity,
    get_alert_manager,
)
from backend.infra.schemas import (
    EmergencyStop as DBEmergencyStop,
)
from backend.infra.schemas import (
    Order,
    Position,
    Strategy,
)
from backend.infra.schemas import (
    RiskLimit as DBRiskLimit,
)
from backend.infra.schemas import (
    RiskMetric as DBRiskMetric,
)
from backend.infra.schemas import (
    RiskViolation as DBRiskViolation,
)
from backend.models.risk import (
    EmergencyStop,
    EmergencyStopStatus,
    RiskDashboardData,
    RiskLimit,
    RiskMetric,
    RiskStatus,
    RiskViolation,
    Severity,
    TriggerEmergencyStopRequest,
    UpdateRiskLimitRequest,
    ViolationType,
)

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk Management Service

    Handles:
    - Real-time risk metric calculations
    - Limit monitoring and violation detection
    - Emergency stop functionality
    - Risk configuration management
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # Metric Names
    DAILY_LOSS = "daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    POSITION_COUNT = "position_count"
    TOTAL_EXPOSURE = "total_exposure"
    ORDER_COUNT_DAILY = "order_count_daily"
    BUYING_POWER_USED = "buying_power_used"

    async def get_dashboard_data(self, user_id: int) -> RiskDashboardData:
        """
        Get complete risk dashboard data for user

        Args:
            user_id: User ID (integer)

        Returns:
            RiskDashboardData with all metrics, violations, limits, and summary
        """
        from backend.models.risk import RiskDashboardSummary

        # Get all current metrics
        metrics = await self.get_current_metrics(user_id)

        # Get recent violations (last 24 hours, unresolved)
        violations = await self.get_recent_violations(user_id, hours=24)

        # Get risk limits configuration
        limits = await self.get_risk_limits(user_id)

        # Get emergency stop status and object
        emergency_stop = await self.get_active_emergency_stop(user_id)

        # Calculate summary statistics
        breached_count = sum(1 for m in metrics if m.status == "BREACHED")
        critical_count = sum(1 for m in metrics if m.status == "CRITICAL")
        warning_count = sum(1 for m in metrics if m.status == "WARNING")

        summary = RiskDashboardSummary(
            total_metrics=len(metrics),
            breached_metrics=breached_count,
            critical_metrics=critical_count,
            warning_metrics=warning_count,
            recent_violations_count=len(violations),
            is_emergency_active=emergency_stop is not None
        )

        return RiskDashboardData(
            metrics=metrics,
            recent_violations=violations,
            active_limits=limits,
            emergency_status=emergency_stop,
            summary=summary,
            last_updated=datetime.now(UTC),
        )

    async def calculate_and_update_metrics(self, user_id: UUID) -> list[RiskMetric]:
        """
        Calculate all risk metrics for user and update database

        Args:
            user_id: User ID

        Returns:
            List of updated RiskMetric objects
        """
        logger.info(f"Calculating risk metrics for user {user_id}")

        metrics = []

        # 1. Daily Loss
        daily_loss_metric = await self._calculate_daily_loss(user_id)
        if daily_loss_metric:
            metrics.append(daily_loss_metric)

        # 2. Max Drawdown
        drawdown_metric = await self._calculate_max_drawdown(user_id)
        if drawdown_metric:
            metrics.append(drawdown_metric)

        # 3. Position Count
        position_count_metric = await self._calculate_position_count(user_id)
        if position_count_metric:
            metrics.append(position_count_metric)

        # 4. Total Exposure
        exposure_metric = await self._calculate_total_exposure(user_id)
        if exposure_metric:
            metrics.append(exposure_metric)

        # 5. Daily Order Count
        order_count_metric = await self._calculate_daily_order_count(user_id)
        if order_count_metric:
            metrics.append(order_count_metric)

        # 6. Buying Power Used
        buying_power_metric = await self._calculate_buying_power_used(user_id)
        if buying_power_metric:
            metrics.append(buying_power_metric)

        # Check for violations
        await self._check_violations(user_id, metrics)

        logger.info(f"Calculated {len(metrics)} risk metrics for user {user_id}")
        return metrics

    async def _calculate_daily_loss(self, user_id: UUID) -> RiskMetric | None:
        """Calculate daily P&L vs daily loss limit"""
        # Get daily loss limit
        limit = await self._get_limit_value(user_id, self.DAILY_LOSS)
        if not limit:
            return None

        # Calculate today's P&L
        # Audit-K finding K-3 (2026-05-02): use ET trading-day boundary,
        # not UTC midnight. UTC midnight = 7-8 PM ET, so an evening trade
        # was bucketed into the next "trading day" for daily P&L.
        from zoneinfo import ZoneInfo
        _et_now = datetime.now(UTC).astimezone(ZoneInfo("America/New_York"))
        today_start = _et_now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(UTC)

        # Query today's realized P&L from trades table
        try:
            from backend.infra.schemas import Order
            result = await self.db.execute(
                select(Order).where(
                    and_(
                        Order.user_id == user_id,
                        Order.status == "filled",
                        Order.updated_at >= today_start,
                    )
                )
            )
            filled_orders = result.scalars().all()
            current_loss = sum(
                Decimal(str(getattr(o, 'realized_pnl', 0) or 0))
                for o in filled_orders
            )
            # daily_loss is expressed as a positive value when losing
            current_loss = abs(min(current_loss, Decimal(0)))
        except Exception as e:
            logger.warning(f"Could not calculate daily loss for user {user_id}: {e}")
            current_loss = Decimal(0)

        # Calculate percentage and status
        percent_used = (current_loss / limit * 100) if limit > 0 else Decimal(0)
        status = await self._get_status_from_percent(user_id, self.DAILY_LOSS, percent_used)

        # Update or create metric in database
        metric = await self._upsert_metric(
            user_id=user_id,
            metric_name=self.DAILY_LOSS,
            current_value=current_loss,
            limit_value=limit,
            percent_used=percent_used,
            status=status,
        )

        return metric

    async def _calculate_max_drawdown(self, user_id: UUID) -> RiskMetric | None:
        """Calculate current drawdown vs max drawdown limit"""
        limit = await self._get_limit_value(user_id, self.MAX_DRAWDOWN)
        if not limit:
            return None

        # Calculate current drawdown from portfolio history
        try:
            from backend.infra.schemas import PortfolioHistory
            result = await self.db.execute(
                select(PortfolioHistory)
                .where(PortfolioHistory.user_id == user_id)
                .order_by(PortfolioHistory.timestamp.desc())
                .limit(252)  # ~1 year of trading days
            )
            history = result.scalars().all()
            if history:
                equity_values = [float(h.total_equity) for h in reversed(history)]
                peak = max(equity_values)
                current = equity_values[-1]
                current_drawdown = Decimal(str(max(0, (peak - current) / peak * 100))) if peak > 0 else Decimal(0)
            else:
                current_drawdown = Decimal(0)
        except Exception as e:
            logger.warning(f"Could not calculate max drawdown for user {user_id}: {e}")
            current_drawdown = Decimal(0)

        percent_used = (current_drawdown / limit * 100) if limit > 0 else Decimal(0)
        status = await self._get_status_from_percent(user_id, self.MAX_DRAWDOWN, percent_used)

        metric = await self._upsert_metric(
            user_id=user_id,
            metric_name=self.MAX_DRAWDOWN,
            current_value=current_drawdown,
            limit_value=limit,
            percent_used=percent_used,
            status=status,
        )

        return metric

    async def _calculate_position_count(self, user_id: UUID) -> RiskMetric | None:
        """Calculate open position count vs limit"""
        limit = await self._get_limit_value(user_id, self.POSITION_COUNT)
        if not limit:
            return None

        # Count open positions
        result = await self.db.execute(
            select(Position).where(
                and_(Position.user_id == str(user_id), Position.quantity > 0)
            )
        )
        positions = result.scalars().all()
        current_count = Decimal(len(positions))

        percent_used = (current_count / limit * 100) if limit > 0 else Decimal(0)
        status = await self._get_status_from_percent(user_id, self.POSITION_COUNT, percent_used)

        metric = await self._upsert_metric(
            user_id=user_id,
            metric_name=self.POSITION_COUNT,
            current_value=current_count,
            limit_value=limit,
            percent_used=percent_used,
            status=status,
        )

        return metric

    async def _calculate_total_exposure(self, user_id: UUID) -> RiskMetric | None:
        """Calculate total market exposure vs limit"""
        limit = await self._get_limit_value(user_id, self.TOTAL_EXPOSURE)
        if not limit:
            return None

        # Calculate total position value
        result = await self.db.execute(
            select(Position).where(Position.user_id == str(user_id))
        )
        positions = result.scalars().all()

        total_exposure = sum(
            abs(Decimal(str(p.quantity)) * Decimal(str(p.current_price or p.avg_entry_price)))
            for p in positions
        )

        percent_used = (total_exposure / limit * 100) if limit > 0 else Decimal(0)
        status = await self._get_status_from_percent(user_id, self.TOTAL_EXPOSURE, percent_used)

        metric = await self._upsert_metric(
            user_id=user_id,
            metric_name=self.TOTAL_EXPOSURE,
            current_value=total_exposure,
            limit_value=limit,
            percent_used=percent_used,
            status=status,
        )

        return metric

    async def _calculate_daily_order_count(self, user_id: UUID) -> RiskMetric | None:
        """Calculate today's order count vs daily limit"""
        limit = await self._get_limit_value(user_id, self.ORDER_COUNT_DAILY)
        if not limit:
            return None

        # Count today's orders
        # Audit-K finding K-3 (2026-05-02): use ET trading-day boundary,
        # not UTC midnight. UTC midnight = 7-8 PM ET, so an evening trade
        # was bucketed into the next "trading day" for daily P&L.
        from zoneinfo import ZoneInfo
        _et_now = datetime.now(UTC).astimezone(ZoneInfo("America/New_York"))
        today_start = _et_now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone(UTC)
        result = await self.db.execute(
            select(Order).where(
                and_(Order.user_id == str(user_id), Order.created_at >= today_start)
            )
        )
        orders = result.scalars().all()
        current_count = Decimal(len(orders))

        percent_used = (current_count / limit * 100) if limit > 0 else Decimal(0)
        status = await self._get_status_from_percent(
            user_id, self.ORDER_COUNT_DAILY, percent_used
        )

        metric = await self._upsert_metric(
            user_id=user_id,
            metric_name=self.ORDER_COUNT_DAILY,
            current_value=current_count,
            limit_value=limit,
            percent_used=percent_used,
            status=status,
        )

        return metric

    async def _calculate_buying_power_used(self, user_id: UUID) -> RiskMetric | None:
        """Calculate buying power utilization"""
        limit = await self._get_limit_value(user_id, self.BUYING_POWER_USED)
        if not limit:
            return None

        # Get buying power from portfolio service
        try:
            from backend.services.portfolio_service import PortfolioService
            portfolio_svc = PortfolioService()
            portfolio = await portfolio_svc.get_portfolio_data(str(user_id))
            total_equity = Decimal(str(portfolio.get('totalEquity', 0)))
            buying_power = Decimal(str(portfolio.get('buyingPower', 0)))
            current_buying_power_used = total_equity - buying_power if total_equity > buying_power else Decimal(0)
        except Exception as e:
            logger.warning(f"Could not calculate buying power for user {user_id}: {e}")
            current_buying_power_used = Decimal(0)

        percent_used = (
            (current_buying_power_used / limit * 100) if limit > 0 else Decimal(0)
        )
        status = await self._get_status_from_percent(
            user_id, self.BUYING_POWER_USED, percent_used
        )

        metric = await self._upsert_metric(
            user_id=user_id,
            metric_name=self.BUYING_POWER_USED,
            current_value=current_buying_power_used,
            limit_value=limit,
            percent_used=percent_used,
            status=status,
        )

        return metric

    async def _get_limit_value(
        self, user_id: UUID, limit_name: str
    ) -> Decimal | None:
        """Get limit value for metric"""
        result = await self.db.execute(
            select(DBRiskLimit).where(
                and_(
                    DBRiskLimit.user_id == user_id,
                    DBRiskLimit.limit_name == limit_name,
                    DBRiskLimit.enabled,
                )
            )
        )
        limit = result.scalar_one_or_none()
        return Decimal(str(limit.limit_value)) if limit else None

    async def _get_status_from_percent(
        self, user_id: UUID, metric_name: str, percent_used: Decimal
    ) -> RiskStatus:
        """Determine status based on percent used and thresholds"""
        # Get thresholds from risk_limits
        result = await self.db.execute(
            select(DBRiskLimit).where(
                and_(
                    DBRiskLimit.user_id == user_id,
                    DBRiskLimit.limit_name == metric_name,
                )
            )
        )
        limit = result.scalar_one_or_none()

        if limit:
            warning_threshold = Decimal(str(limit.warning_threshold))
            critical_threshold = Decimal(str(limit.critical_threshold))
        else:
            warning_threshold = Decimal(80)
            critical_threshold = Decimal(95)

        if percent_used >= 100:
            return RiskStatus.BREACHED
        elif percent_used >= critical_threshold:
            return RiskStatus.CRITICAL
        elif percent_used >= warning_threshold:
            return RiskStatus.WARNING
        else:
            return RiskStatus.NORMAL

    async def _upsert_metric(
        self,
        user_id: UUID,
        metric_name: str,
        current_value: Decimal,
        limit_value: Decimal,
        percent_used: Decimal,
        status: RiskStatus,
    ) -> RiskMetric:
        """Create or update risk metric in database"""
        # Check if metric exists
        result = await self.db.execute(
            select(DBRiskMetric).where(
                and_(
                    DBRiskMetric.user_id == user_id,
                    DBRiskMetric.metric_name == metric_name,
                )
            )
        )
        db_metric = result.scalar_one_or_none()

        if db_metric:
            # Update existing
            db_metric.current_value = current_value
            db_metric.limit_value = limit_value
            db_metric.percent_used = percent_used
            db_metric.status = status.value
            db_metric.last_updated = datetime.now(UTC)
        else:
            # Create new
            db_metric = DBRiskMetric(
                user_id=user_id,
                metric_name=metric_name,
                current_value=current_value,
                limit_value=limit_value,
                percent_used=percent_used,
                status=status.value,
                last_updated=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            self.db.add(db_metric)

        await self.db.commit()
        await self.db.refresh(db_metric)

        return RiskMetric.from_orm(db_metric)

    async def _check_violations(self, user_id: UUID, metrics: list[RiskMetric]):
        """Check metrics for violations and create violation records"""
        for metric in metrics:
            if metric.status in [RiskStatus.CRITICAL, RiskStatus.BREACHED]:
                # Create violation record
                await self._create_violation(
                    user_id=user_id,
                    metric=metric,
                    violation_type=(
                        ViolationType.BREACH
                        if metric.status == RiskStatus.BREACHED
                        else ViolationType.WARNING
                    ),
                )

    async def _create_violation(
        self, user_id: UUID, metric: RiskMetric, violation_type: ViolationType
    ):
        """Create new violation record and send alert"""
        severity = (
            Severity.CRITICAL if violation_type == ViolationType.BREACH else Severity.HIGH
        )

        message = f"{metric.metric_name} {violation_type.value}: {metric.current_value} / {metric.limit_value} ({metric.percent_used}%)"

        violation = DBRiskViolation(
            user_id=user_id,
            metric_name=metric.metric_name,
            violation_type=violation_type.value,
            current_value=metric.current_value,
            limit_value=metric.limit_value,
            severity=severity.value,
            message=message,
            resolved=False,
            created_at=datetime.now(UTC),
        )

        self.db.add(violation)
        await self.db.commit()

        logger.warning(f"Risk violation created: {message}")

        # Send alert to Slack/PagerDuty
        try:
            alert_severity = (
                AlertSeverity.CRITICAL if violation_type == ViolationType.BREACH
                else AlertSeverity.WARNING
            )
            alert_manager = get_alert_manager()
            await alert_manager.risk_violation(
                user_id=user_id if isinstance(user_id, int) else 0,
                metric_name=metric.metric_name,
                current_value=metric.current_value,
                limit_value=metric.limit_value,
                severity=alert_severity,
            )
        except Exception as e:
            # Don't let alerting failure break the flow
            logger.error(f"Failed to send risk violation alert: {e}")

    async def get_current_metrics(self, user_id: UUID) -> list[RiskMetric]:
        """Get all current risk metrics for user"""
        result = await self.db.execute(
            select(DBRiskMetric).where(DBRiskMetric.user_id == user_id)
        )
        db_metrics = result.scalars().all()
        return [RiskMetric.from_orm(m) for m in db_metrics]

    async def get_recent_violations(
        self, user_id: UUID, hours: int = 24
    ) -> list[RiskViolation]:
        """Get recent violations"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        result = await self.db.execute(
            select(DBRiskViolation)
            .where(
                and_(
                    DBRiskViolation.user_id == user_id,
                    or_(
                        ~DBRiskViolation.resolved,
                        DBRiskViolation.created_at >= cutoff,
                    ),
                )
            )
            .order_by(DBRiskViolation.created_at.desc())
        )
        db_violations = result.scalars().all()
        return [RiskViolation.from_orm(v) for v in db_violations]

    async def get_risk_limits(self, user_id: UUID) -> list[RiskLimit]:
        """Get all risk limits for user"""
        result = await self.db.execute(
            select(DBRiskLimit).where(DBRiskLimit.user_id == user_id)
        )
        db_limits = result.scalars().all()
        return [RiskLimit.from_orm(l) for l in db_limits]

    async def update_risk_limit(
        self,
        user_id: UUID,
        limit_name: str,
        request: UpdateRiskLimitRequest,
        updated_by: UUID,
    ) -> RiskLimit:
        """Update risk limit configuration"""
        result = await self.db.execute(
            select(DBRiskLimit).where(
                and_(
                    DBRiskLimit.user_id == user_id, DBRiskLimit.limit_name == limit_name
                )
            )
        )
        db_limit = result.scalar_one_or_none()

        if not db_limit:
            # Create new limit
            db_limit = DBRiskLimit(
                user_id=user_id,
                limit_name=limit_name,
                limit_value=request.limit_value,
                warning_threshold=request.warning_threshold,
                critical_threshold=request.critical_threshold,
                enabled=request.enabled,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                updated_by=updated_by,
            )
            self.db.add(db_limit)
        else:
            # Update existing
            db_limit.limit_value = request.limit_value
            db_limit.warning_threshold = request.warning_threshold
            db_limit.critical_threshold = request.critical_threshold
            db_limit.enabled = request.enabled
            db_limit.updated_at = datetime.now(UTC)
            db_limit.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(db_limit)

        logger.info(f"Updated risk limit {limit_name} for user {user_id}")
        return RiskLimit.from_orm(db_limit)

    async def delete_risk_limit(self, user_id: int, limit_id: str) -> None:
        """Delete a risk limit by ID"""
        try:
            # Convert string UUID to UUID object
            limit_uuid = uuid.UUID(limit_id)
        except ValueError:
            raise ValueError(f"Invalid limit_id format: {limit_id}")

        result = await self.db.execute(
            select(DBRiskLimit).where(
                and_(
                    DBRiskLimit.user_id == user_id,
                    DBRiskLimit.id == limit_uuid
                )
            )
        )
        db_limit = result.scalar_one_or_none()

        if not db_limit:
            raise ValueError(f"Risk limit not found: {limit_id}")

        await self.db.delete(db_limit)
        await self.db.commit()
        logger.info(f"Deleted risk limit {limit_id} for user {user_id}")

    async def trigger_emergency_stop(
        self,
        user_id: UUID,
        request: TriggerEmergencyStopRequest,
        triggered_by: UUID,
    ) -> EmergencyStop:
        """
        CRITICAL: Trigger emergency stop

        Stops all strategies and cancels all open orders
        """
        logger.critical(
            f"EMERGENCY STOP triggered by {triggered_by} for user {user_id}: {request.reason}"
        )
        # V10 YY-1 / Wave-52 (2026-05-03): wire operator alert.  This
        # logger.critical at the entry of emergency_stop() previously
        # had no Slack/PagerDuty dispatch.
        try:
            from backend.infra.alerting import (
                AlertCategory, AlertSeverity, send_alert,
                dispatch_alert_from_thread,
            )
            _reason = request.reason
            _by = triggered_by
            _uid = user_id
            dispatch_alert_from_thread(
                lambda: send_alert(
                    AlertCategory.SYSTEM_ERROR,
                    AlertSeverity.CRITICAL,
                    "Emergency Stop Triggered",
                    f"User {_uid} triggered emergency stop "
                    f"by {_by}.  Reason: {_reason}",
                )
            )
        except Exception as _alert_err:
            logger.warning(
                "YY-1: emergency-stop-triggered alert dispatch failed: %s",
                _alert_err,
            )

        strategies_stopped = 0
        orders_cancelled = 0

        try:
            # 1. Stop all active strategies (no user filtering - system-wide)
            result = await self.db.execute(
                select(Strategy).where(Strategy.status == "active")
            )
            strategies = result.scalars().all()

            for strategy in strategies:
                strategy.status = "inactive"  # Fixed: Use valid status "inactive" instead of "stopped"
                strategy.stopped_at = datetime.now(UTC)
                strategies_stopped += 1

            # 2. Cancel all open orders (no user filtering - system-wide)
            result = await self.db.execute(
                select(Order).where(
                    Order.status.in_(["pending", "new", "partially_filled"])
                )
            )
            orders = result.scalars().all()

            for order in orders:
                order.status = "cancelled"
                orders_cancelled += 1

            # 3. Create emergency stop record
            db_stop = DBEmergencyStop(
                user_id=user_id,
                triggered_by=triggered_by,
                reason=request.reason,
                strategies_stopped=strategies_stopped,
                orders_cancelled=orders_cancelled,
                status=EmergencyStopStatus.ACTIVE.value,
                triggered_at=datetime.now(UTC),
            )
            self.db.add(db_stop)

            await self.db.commit()
            await self.db.refresh(db_stop)

            logger.critical(
                f"EMERGENCY STOP executed: "
                f"{strategies_stopped} strategies stopped, "
                f"{orders_cancelled} orders cancelled"
            )

            return EmergencyStop.from_orm(db_stop)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Emergency stop failed: {e}")
            raise

    async def resolve_emergency_stop(
        self, stop_id: UUID, user_id: UUID, resolved_by: UUID
    ) -> EmergencyStop:
        """Resolve an active emergency stop"""
        result = await self.db.execute(
            select(DBEmergencyStop).where(
                and_(
                    DBEmergencyStop.id == stop_id,
                    DBEmergencyStop.user_id == user_id,
                    DBEmergencyStop.status == EmergencyStopStatus.ACTIVE.value,
                )
            )
        )
        db_stop = result.scalar_one_or_none()

        if not db_stop:
            raise ValueError(f"Emergency stop {stop_id} not found or already resolved")

        db_stop.status = EmergencyStopStatus.RESOLVED.value
        db_stop.resolved_at = datetime.now(UTC)
        db_stop.resolved_by = resolved_by

        await self.db.commit()
        await self.db.refresh(db_stop)

        logger.info(f"Emergency stop {stop_id} resolved by {resolved_by}")
        return EmergencyStop.from_orm(db_stop)

    async def get_active_emergency_stop(self, user_id: int) -> EmergencyStop | None:
        """Get active emergency stop for user, if any"""
        result = await self.db.execute(
            select(DBEmergencyStop).where(
                and_(
                    DBEmergencyStop.user_id == user_id,
                    DBEmergencyStop.status == EmergencyStopStatus.ACTIVE.value,
                )
            )
        )
        db_stop = result.scalar_one_or_none()
        if not db_stop:
            return None
        return EmergencyStop.from_orm(db_stop)

    async def is_emergency_stop_active(self, user_id: UUID) -> bool:
        """Check if emergency stop is currently active for user"""
        result = await self.db.execute(
            select(DBEmergencyStop).where(
                and_(
                    DBEmergencyStop.user_id == user_id,
                    DBEmergencyStop.status == EmergencyStopStatus.ACTIVE.value,
                )
            )
        )
        return result.scalar_one_or_none() is not None
