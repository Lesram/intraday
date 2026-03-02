"""
Alerting Integration Module for Trading Platform.

Provides unified alerting to multiple channels:
- Slack (for team notifications)
- PagerDuty (for critical alerts requiring immediate action)
- Email (future expansion)

Environment Variables Required:
- SLACK_WEBHOOK_URL: Slack incoming webhook URL
- PAGERDUTY_ROUTING_KEY: PagerDuty Events API v2 routing key
- ALERT_ENVIRONMENT: prod/staging/dev (affects severity routing)
"""

import asyncio
from datetime import UTC, datetime, time as dt_time, timedelta
from decimal import Decimal
from enum import Enum
import hashlib
import logging
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

# L-25: Market hours — import from canonical source
from backend.utils.market_hours import is_market_open as _is_market_open


def is_market_hours(include_extended: bool = True) -> bool:
    """Check if current time is within market hours (L-25)."""
    return _is_market_open(include_extended=include_extended)


class AlertSeverity(Enum):
    """Alert severity levels mapped to PagerDuty and Slack formatting."""

    INFO = "info"           # Informational, Slack only
    WARNING = "warning"     # Warning, Slack + PagerDuty (low urgency)
    ERROR = "error"         # Error, Slack + PagerDuty (high urgency)
    CRITICAL = "critical"   # Critical, Slack + PagerDuty (immediate)


class AlertCategory(Enum):
    """Categories for routing and grouping alerts."""

    RISK_VIOLATION = "risk_violation"
    ORDER_FAILURE = "order_failure"
    SYSTEM_ERROR = "system_error"
    CONNECTIVITY = "connectivity"
    PERFORMANCE = "performance"
    SECURITY = "security"


class AlertConfig:
    """Configuration for alerting services."""

    def __init__(
        self,
        slack_webhook_url: str | None = None,
        pagerduty_routing_key: str | None = None,
        environment: str = "development",
        dedup_window_seconds: int = 300,  # 5 minutes
        rate_limit_per_minute: int = 30,
    ):
        self.slack_webhook_url = slack_webhook_url
        self.pagerduty_routing_key = pagerduty_routing_key
        self.environment = environment
        self.dedup_window_seconds = dedup_window_seconds
        self.rate_limit_per_minute = rate_limit_per_minute


class AlertDeduplicator:
    """
    Prevents alert fatigue by deduplicating similar alerts.
    Uses content-based hashing with time windows.
    """

    def __init__(self, window_seconds: int = 300):
        self._window = timedelta(seconds=window_seconds)
        self._seen: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    def _hash_alert(
        self,
        category: AlertCategory,
        severity: AlertSeverity,
        title: str
    ) -> str:
        """Generate dedup key from alert content."""
        content = f"{category.value}:{severity.value}:{title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def should_send(
        self,
        category: AlertCategory,
        severity: AlertSeverity,
        title: str
    ) -> bool:
        """Check if alert should be sent (not a duplicate)."""
        key = self._hash_alert(category, severity, title)
        now = datetime.now(UTC)

        async with self._lock:
            # Clean up old entries
            expired = [
                k for k, v in self._seen.items()
                if now - v > self._window
            ]
            for k in expired:
                del self._seen[k]

            # Check if seen recently
            if key in self._seen:
                logger.debug(f"Deduplicating alert: {title}")
                return False

            # Mark as seen
            self._seen[key] = now
            return True


class AlertRateLimiter:
    """Sliding window rate limiter for alerts."""

    def __init__(self, max_per_minute: int = 30):
        self._max = max_per_minute
        self._window = timedelta(minutes=1)
        self._timestamps: list[datetime] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to acquire a rate limit slot."""
        now = datetime.now(UTC)

        async with self._lock:
            # Remove old timestamps
            cutoff = now - self._window
            self._timestamps = [ts for ts in self._timestamps if ts > cutoff]

            # Check limit
            if len(self._timestamps) >= self._max:
                logger.warning(f"Alert rate limit exceeded ({self._max}/min)")
                return False

            self._timestamps.append(now)
            return True


class AlertManager:
    """
    Unified alerting manager for the trading platform.

    Features:
    - Multi-channel delivery (Slack, PagerDuty)
    - Alert deduplication to prevent fatigue
    - Rate limiting to prevent flooding
    - Severity-based routing
    - Environment-aware (prod alerts get priority)

    Usage:
        alert_manager = AlertManager.from_env()
        await alert_manager.send_alert(
            category=AlertCategory.RISK_VIOLATION,
            severity=AlertSeverity.CRITICAL,
            title="Daily Loss Limit Breached",
            description="User xyz exceeded 5% daily loss limit",
            details={"user_id": 123, "loss_pct": 5.2}
        )
    """

    def __init__(self, config: AlertConfig):
        self._config = config
        self._dedup = AlertDeduplicator(config.dedup_window_seconds)
        self._limiter = AlertRateLimiter(config.rate_limit_per_minute)
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_env(cls) -> "AlertManager":
        """Create AlertManager from environment variables."""
        import os

        config = AlertConfig(
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            pagerduty_routing_key=os.getenv("PAGERDUTY_ROUTING_KEY"),
            environment=os.getenv("ALERT_ENVIRONMENT", "development"),
        )
        return cls(config)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _severity_emoji(self, severity: AlertSeverity) -> str:
        """Get Slack emoji for severity level."""
        return {
            AlertSeverity.INFO: ":information_source:",
            AlertSeverity.WARNING: ":warning:",
            AlertSeverity.ERROR: ":x:",
            AlertSeverity.CRITICAL: ":rotating_light:",
        }[severity]

    def _severity_color(self, severity: AlertSeverity) -> str:
        """Get Slack color for severity level."""
        return {
            AlertSeverity.INFO: "#36a64f",      # Green
            AlertSeverity.WARNING: "#ffc107",    # Yellow
            AlertSeverity.ERROR: "#dc3545",      # Red
            AlertSeverity.CRITICAL: "#721c24",   # Dark Red
        }[severity]

    async def send_alert(
        self,
        category: AlertCategory,
        severity: AlertSeverity,
        title: str,
        description: str,
        details: dict[str, Any] | None = None,
        dedup: bool = True,
        respect_market_hours: bool = True,
    ) -> bool:
        """
        Send alert to configured channels.

        Args:
            category: Alert category for routing/grouping
            severity: Alert severity level
            title: Short alert title
            description: Detailed description
            details: Additional structured data
            dedup: Whether to deduplicate (default True)
            respect_market_hours: If True, suppress non-critical alerts outside market hours (L-25)

        Returns:
            True if alert was sent, False if deduplicated/rate-limited/suppressed
        """
        # L-25: Suppress non-critical alerts outside market hours
        if respect_market_hours and severity in (AlertSeverity.INFO, AlertSeverity.WARNING):
            if not is_market_hours(include_extended=True):
                logger.debug(f"Alert suppressed outside market hours: {title}")
                return False

        # Check deduplication
        if dedup and not await self._dedup.should_send(category, severity, title):
            return False

        # Check rate limit
        if not await self._limiter.acquire():
            logger.warning(f"Alert rate-limited: {title}")
            return False

        # Build alert context
        context = {
            "category": category.value,
            "severity": severity.value,
            "title": title,
            "description": description,
            "details": details or {},
            "environment": self._config.environment,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Send to channels based on severity
        tasks = []

        # Always send to Slack if configured
        if self._config.slack_webhook_url:
            tasks.append(self._send_slack(context))

        # Send to PagerDuty for warning+ in production, error+ everywhere
        if self._config.pagerduty_routing_key:
            should_page = (
                severity in (AlertSeverity.ERROR, AlertSeverity.CRITICAL) or
                (severity == AlertSeverity.WARNING and
                 self._config.environment == "production")
            )
            if should_page:
                tasks.append(self._send_pagerduty(context))

        if not tasks:
            logger.warning(f"No alert channels configured for: {title}")
            return False

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any failures
        for _i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Alert delivery failed: {result}")

        success = any(r is True for r in results if not isinstance(r, Exception))
        return success

    async def _send_slack(self, context: dict[str, Any]) -> bool:
        """Send alert to Slack via webhook."""
        if not self._config.slack_webhook_url:
            return False

        severity = AlertSeverity(context["severity"])

        # Build Slack message with blocks
        payload = {
            "attachments": [
                {
                    "color": self._severity_color(severity),
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{self._severity_emoji(severity)} {context['title']}",
                                "emoji": True
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": context["description"]
                            }
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"*Category:* {context['category']} | *Environment:* {context['environment']} | *Time:* {context['timestamp']}"
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Add details as fields if present
        if context.get("details"):
            fields = []
            for key, value in context["details"].items():
                # Format Decimal values
                if isinstance(value, Decimal):
                    value = float(value)
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:* `{value}`"
                })

            if fields:
                payload["attachments"][0]["blocks"].append({
                    "type": "section",
                    "fields": fields[:10]  # Slack limit
                })

        try:
            client = await self._get_client()
            response = await client.post(
                self._config.slack_webhook_url,
                json=payload
            )

            if response.status_code == 200:
                logger.info(f"Slack alert sent: {context['title']}")
                return True
            else:
                logger.error(f"Slack alert failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Slack alert error: {e}")
            return False

    async def _send_pagerduty(self, context: dict[str, Any]) -> bool:
        """Send alert to PagerDuty via Events API v2."""
        if not self._config.pagerduty_routing_key:
            return False

        severity = AlertSeverity(context["severity"])

        # Map to PagerDuty severity
        pd_severity = {
            AlertSeverity.INFO: "info",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.ERROR: "error",
            AlertSeverity.CRITICAL: "critical",
        }[severity]

        # Build PagerDuty event
        payload = {
            "routing_key": self._config.pagerduty_routing_key,
            "event_action": "trigger",
            "dedup_key": f"{context['category']}:{context['title'][:50]}",
            "payload": {
                "summary": f"[{context['environment'].upper()}] {context['title']}: {context['description'][:200]}",
                "source": f"trading-platform-{context['environment']}",
                "severity": pd_severity,
                "timestamp": context["timestamp"],
                "component": context["category"],
                "group": "trading-platform",
                "class": context["category"],
                "custom_details": context.get("details", {})
            }
        }

        try:
            client = await self._get_client()
            response = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload
            )

            if response.status_code in (200, 201, 202):
                logger.info(f"PagerDuty alert sent: {context['title']}")
                return True
            else:
                logger.error(f"PagerDuty alert failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"PagerDuty alert error: {e}")
            return False

    # Convenience methods for common alerts

    async def risk_violation(
        self,
        user_id: int,
        metric_name: str,
        current_value: Decimal,
        limit_value: Decimal,
        severity: AlertSeverity = AlertSeverity.WARNING,
    ):
        """Send risk violation alert."""
        percent = (current_value / limit_value * 100) if limit_value else Decimal(0)

        await self.send_alert(
            category=AlertCategory.RISK_VIOLATION,
            severity=severity,
            title=f"Risk Limit {severity.value.title()}: {metric_name}",
            description=f"User {user_id} at {percent:.1f}% of {metric_name} limit",
            details={
                "user_id": user_id,
                "metric": metric_name,
                "current_value": current_value,
                "limit_value": limit_value,
                "percent_used": percent,
            }
        )

    async def order_failure(
        self,
        order_id: str,
        symbol: str,
        error: str,
        user_id: int | None = None,
    ):
        """Send order failure alert."""
        await self.send_alert(
            category=AlertCategory.ORDER_FAILURE,
            severity=AlertSeverity.ERROR,
            title=f"Order Failed: {symbol}",
            description=f"Order {order_id} for {symbol} failed: {error}",
            details={
                "order_id": order_id,
                "symbol": symbol,
                "error": error,
                "user_id": user_id,
            }
        )

    async def system_error(
        self,
        component: str,
        error: str,
        severity: AlertSeverity = AlertSeverity.ERROR,
    ):
        """Send system error alert."""
        await self.send_alert(
            category=AlertCategory.SYSTEM_ERROR,
            severity=severity,
            title=f"System Error: {component}",
            description=error,
            details={"component": component}
        )

    async def connectivity_issue(
        self,
        service: str,
        status: str,
        details: dict[str, Any] | None = None,
    ):
        """Send connectivity issue alert."""
        await self.send_alert(
            category=AlertCategory.CONNECTIVITY,
            severity=AlertSeverity.WARNING,
            title=f"Connectivity Issue: {service}",
            description=f"{service} connection status: {status}",
            details={"service": service, "status": status, **(details or {})}
        )


# Global singleton (lazy initialization)
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Get or create global AlertManager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager.from_env()
    return _alert_manager


async def send_alert(
    category: AlertCategory,
    severity: AlertSeverity,
    title: str,
    description: str,
    details: dict[str, Any] | None = None,
) -> bool:
    """Convenience function to send alert via global manager."""
    manager = get_alert_manager()
    return await manager.send_alert(category, severity, title, description, details)
