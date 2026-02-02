#!/usr/bin/env python3
"""
SLO Burn-Rate Alert Configuration
Hedge Fund Grade Alert System for Production SLOs
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

from .slo_metrics import get_slo_collector


@dataclass
class AlertRule:
    """SLO Alert Rule Configuration"""
    name: str
    slo_name: str
    burn_rate_threshold: float  # Alert if burn rate exceeds this
    window_minutes: int         # Evaluation window
    severity: str              # critical, warning, info
    cooldown_minutes: int      # Minimum time between alerts
    notification_channels: list[str]  # email, slack, pagerduty
    escalation_delay_minutes: int = 0  # Auto-escalation delay

@dataclass
class AlertNotification:
    """Alert Notification Message"""
    timestamp: datetime
    rule_name: str
    slo_name: str
    severity: str
    message: str
    burn_rate: float
    error_budget_remaining: float
    context: dict[str, Any]

class SLOBurnRateAlertManager:
    """
    Production SLO Burn-Rate Alert Manager
    Implements hedge fund grade alerting with multi-channel notifications
    """

    def __init__(self, config_file: str = "config/slo_alerts.json"):
        """Initialize alert manager with configuration"""
        self.config_file = Path(config_file)
        self.logger = logging.getLogger(__name__)

        # Load alert rules
        self.alert_rules: dict[str, AlertRule] = {}
        self.load_alert_configuration()

        # Alert state tracking
        self.last_alert_times: dict[str, datetime] = {}
        self.active_alerts: dict[str, AlertNotification] = {}
        self.alert_history: list[AlertNotification] = []

        # Notification channels
        self.notification_channels = {
            'email': self._send_email_notification,
            'slack': self._send_slack_notification,
            'pagerduty': self._send_pagerduty_notification,
            'webhook': self._send_webhook_notification
        }

        # SLO collector
        self.slo_collector = get_slo_collector()

    def load_alert_configuration(self):
        """Load alert rules from configuration file"""

        # Default hedge fund alert rules
        default_rules = {
            "order_latency_p99_critical": AlertRule(
                name="order_latency_p99_critical",
                slo_name="order_submission_latency_p99",
                burn_rate_threshold=2.0,  # 2x normal burn rate
                window_minutes=5,
                severity="critical",
                cooldown_minutes=15,
                notification_channels=["email", "slack", "pagerduty"],
                escalation_delay_minutes=5
            ),
            "order_latency_p99_warning": AlertRule(
                name="order_latency_p99_warning",
                slo_name="order_submission_latency_p99",
                burn_rate_threshold=1.0,  # 1x normal burn rate
                window_minutes=15,
                severity="warning",
                cooldown_minutes=30,
                notification_channels=["email", "slack"]
            ),
            "order_accuracy_critical": AlertRule(
                name="order_accuracy_critical",
                slo_name="order_accuracy_daily",
                burn_rate_threshold=1.5,  # 1.5x normal burn rate
                window_minutes=30,
                severity="critical",
                cooldown_minutes=60,
                notification_channels=["email", "slack", "pagerduty"],
                escalation_delay_minutes=10
            ),
            "fill_rate_warning": AlertRule(
                name="fill_rate_warning",
                slo_name="fill_rate_5min",
                burn_rate_threshold=0.8,  # 0.8x normal burn rate (early warning)
                window_minutes=10,
                severity="warning",
                cooldown_minutes=20,
                notification_channels=["slack"]
            ),
            "system_availability_critical": AlertRule(
                name="system_availability_critical",
                slo_name="system_availability_hourly",
                burn_rate_threshold=1.0,
                window_minutes=5,
                severity="critical",
                cooldown_minutes=10,
                notification_channels=["email", "slack", "pagerduty"],
                escalation_delay_minutes=2
            )
        }

        try:
            if self.config_file.exists():
                with open(self.config_file) as f:
                    config_data = json.load(f)

                # Load rules from config
                for rule_name, rule_data in config_data.get('alert_rules', {}).items():
                    self.alert_rules[rule_name] = AlertRule(**rule_data)

                self.logger.info(f"Loaded {len(self.alert_rules)} alert rules from {self.config_file}")
            else:
                # Use defaults and save to file
                self.alert_rules = default_rules
                self.save_alert_configuration()
                self.logger.info(f"Created default alert configuration at {self.config_file}")

        except Exception as e:
            self.logger.error(f"Failed to load alert configuration: {e}")
            self.alert_rules = default_rules

    def save_alert_configuration(self):
        """Save current alert rules to configuration file"""

        try:
            # Ensure config directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            config_data = {
                'alert_rules': {
                    rule_name: asdict(rule)
                    for rule_name, rule in self.alert_rules.items()
                },
                'notification_config': {
                    'email': {
                        'smtp_server': 'smtp.gmail.com',
                        'smtp_port': 587,
                        'from_address': 'alerts@tradingplatform.com',
                        'to_addresses': ['ops@hedgefund.com', 'risk@hedgefund.com']
                    },
                    'slack': {
                        'webhook_url': 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK',
                        'channel': '#trading-alerts'
                    },
                    'pagerduty': {
                        'integration_key': 'YOUR_PAGERDUTY_INTEGRATION_KEY'
                    }
                }
            }

            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)

            self.logger.info(f"Saved alert configuration to {self.config_file}")

        except Exception as e:
            self.logger.error(f"Failed to save alert configuration: {e}")

    def evaluate_alert_rules(self) -> list[AlertNotification]:
        """Evaluate all alert rules and return triggered notifications"""

        triggered_notifications = []
        now = datetime.now()

        for rule_name, rule in self.alert_rules.items():
            try:
                # Check if rule is in cooldown
                last_alert = self.last_alert_times.get(rule_name)
                if last_alert:
                    cooldown_elapsed = (now - last_alert).total_seconds() / 60
                    if cooldown_elapsed < rule.cooldown_minutes:
                        continue  # Still in cooldown

                # Get current SLO compliance data
                compliance_data = self.slo_collector.calculate_slo_compliance(rule.slo_name)

                if not compliance_data:
                    continue  # No data available

                current_burn_rate = compliance_data.get('burn_rate', 0.0)
                error_budget_remaining = compliance_data.get('error_budget_remaining', 1.0)

                # Check if burn rate exceeds threshold
                if current_burn_rate >= rule.burn_rate_threshold:

                    notification = AlertNotification(
                        timestamp=now,
                        rule_name=rule_name,
                        slo_name=rule.slo_name,
                        severity=rule.severity,
                        message=self._format_alert_message(rule, current_burn_rate, error_budget_remaining),
                        burn_rate=current_burn_rate,
                        error_budget_remaining=error_budget_remaining,
                        context={
                            'compliance_ratio': compliance_data.get('compliance_ratio', 1.0),
                            'window_minutes': rule.window_minutes,
                            'threshold': rule.burn_rate_threshold
                        }
                    )

                    triggered_notifications.append(notification)

                    # Update alert state
                    self.last_alert_times[rule_name] = now
                    self.active_alerts[rule_name] = notification
                    self.alert_history.append(notification)

                    self.logger.warning(f"SLO Alert Triggered: {rule_name} - {notification.message}")

                # Clear active alert if burn rate is back to normal
                elif rule_name in self.active_alerts:
                    del self.active_alerts[rule_name]
                    self.logger.info(f"SLO Alert Resolved: {rule_name}")

            except Exception as e:
                self.logger.error(f"Error evaluating alert rule {rule_name}: {e}")

        return triggered_notifications

    def _format_alert_message(self, rule: AlertRule, burn_rate: float, error_budget: float) -> str:
        """Format alert notification message"""

        severity_emoji = {
            'critical': '🚨',
            'warning': '⚠️',
            'info': 'ℹ️'
        }

        message = f"{severity_emoji.get(rule.severity, '🔔')} SLO {rule.severity.upper()}: {rule.slo_name}\n"
        message += f"Burn Rate: {burn_rate:.2f}x (threshold: {rule.burn_rate_threshold}x)\n"
        message += f"Error Budget Remaining: {error_budget:.1%}\n"
        message += f"Window: {rule.window_minutes} minutes\n"

        if rule.severity == 'critical':
            message += "\n🏃 IMMEDIATE ACTION REQUIRED"
        elif rule.severity == 'warning':
            message += "\n👀 Please investigate"

        return message

    async def send_notifications(self, notifications: list[AlertNotification]):
        """Send notifications through configured channels"""

        for notification in notifications:
            rule = self.alert_rules.get(notification.rule_name)
            if not rule:
                continue

            # Send to each configured channel
            for channel in rule.notification_channels:
                if channel in self.notification_channels:
                    try:
                        await self.notification_channels[channel](notification)
                        self.logger.info(f"Sent {notification.severity} alert via {channel}: {notification.rule_name}")
                    except Exception as e:
                        self.logger.error(f"Failed to send alert via {channel}: {e}")

    async def _send_email_notification(self, notification: AlertNotification):
        """Send email notification"""
        # Implementation would use actual SMTP configuration
        self.logger.info(f"EMAIL ALERT: {notification.message}")

    async def _send_slack_notification(self, notification: AlertNotification):
        """Send Slack notification"""
        # Implementation would use Slack webhook
        self.logger.info(f"SLACK ALERT: {notification.message}")

    async def _send_pagerduty_notification(self, notification: AlertNotification):
        """Send PagerDuty notification"""
        # Implementation would use PagerDuty API
        self.logger.info(f"PAGERDUTY ALERT: {notification.message}")

    async def _send_webhook_notification(self, notification: AlertNotification):
        """Send webhook notification"""
        # Implementation would POST to webhook URL
        self.logger.info(f"WEBHOOK ALERT: {notification.message}")

    async def run_alert_loop(self, check_interval: int = 30):
        """Run continuous alert evaluation loop"""

        self.logger.info(f"Starting SLO alert monitoring with {check_interval}s interval")

        while True:
            try:
                # Evaluate all alert rules
                notifications = self.evaluate_alert_rules()

                # Send notifications
                if notifications:
                    await self.send_notifications(notifications)

                # Wait for next check
                await asyncio.sleep(check_interval)

            except Exception as e:
                self.logger.error(f"Error in alert loop: {e}")
                await asyncio.sleep(check_interval)

    def get_alert_status(self) -> dict[str, Any]:
        """Get current alert system status"""

        return {
            'timestamp': datetime.now().isoformat(),
            'active_alerts': {
                rule_name: {
                    'severity': alert.severity,
                    'burn_rate': alert.burn_rate,
                    'error_budget_remaining': alert.error_budget_remaining,
                    'triggered_at': alert.timestamp.isoformat()
                }
                for rule_name, alert in self.active_alerts.items()
            },
            'alert_rules_count': len(self.alert_rules),
            'recent_alerts_24h': len([
                alert for alert in self.alert_history
                if alert.timestamp > datetime.now() - timedelta(days=1)
            ])
        }

# Global alert manager instance
_alert_manager = None

def get_alert_manager() -> SLOBurnRateAlertManager:
    """Get global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = SLOBurnRateAlertManager()
    return _alert_manager

async def start_alert_monitoring(check_interval: int = 30):
    """Start SLO alert monitoring system"""
    alert_manager = get_alert_manager()
    await alert_manager.run_alert_loop(check_interval)
