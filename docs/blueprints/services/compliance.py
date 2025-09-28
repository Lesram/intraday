"""
Comprehensive compliance service for the trading platform.

Provides regulatory compliance functionality including:
- Compliance rule management
- Automated compliance checking
- Regulatory reporting
- Violation tracking and remediation
- Policy enforcement
- Compliance monitoring and alerts
- Regulatory framework support (MiFID II, GDPR, SOX, etc.)
"""

import asyncio
from typing import Dict, Any, Optional, List, Set, Union, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging
import json
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ComplianceFramework(Enum):
    """Regulatory frameworks."""
    MIFID_II = "mifid_ii"
    GDPR = "gdpr"
    SOX = "sox"
    DODD_FRANK = "dodd_frank"
    BASEL_III = "basel_iii"
    CFTC = "cftc"
    SEC = "sec"
    FCA = "fca"
    ESMA = "esma"
    CUSTOM = "custom"


class ComplianceStatus(Enum):
    """Compliance status."""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PENDING_REVIEW = "pending_review"
    UNDER_INVESTIGATION = "under_investigation"
    REMEDIATED = "remediated"
    WAIVED = "waived"


class ViolationSeverity(Enum):
    """Violation severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuleType(Enum):
    """Types of compliance rules."""
    TRADING_LIMIT = "trading_limit"
    POSITION_LIMIT = "position_limit"
    RISK_LIMIT = "risk_limit"
    DATA_PROTECTION = "data_protection"
    MARKET_CONDUCT = "market_conduct"
    REPORTING = "reporting"
    KYC = "kyc"
    AML = "aml"
    BEST_EXECUTION = "best_execution"
    TRANSACTION_REPORTING = "transaction_reporting"


@dataclass
class ComplianceRule:
    """Compliance rule definition."""
    rule_id: str
    name: str
    description: str
    framework: ComplianceFramework
    rule_type: RuleType
    severity: ViolationSeverity
    parameters: Dict[str, Any]
    conditions: Dict[str, Any]
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        if not self.parameters:
            self.parameters = {}
        if not self.conditions:
            self.conditions = {}


@dataclass
class ComplianceViolation:
    """Compliance violation record."""
    violation_id: str
    rule_id: str
    entity_type: str
    entity_id: str
    severity: ViolationSeverity
    status: ComplianceStatus
    description: str
    details: Dict[str, Any]
    detected_at: datetime
    remediation_deadline: Optional[datetime] = None
    remediated_at: Optional[datetime] = None
    remediation_notes: Optional[str] = None
    
    def __post_init__(self):
        if not self.details:
            self.details = {}


@dataclass
class ComplianceCheck:
    """Compliance check result."""
    check_id: str
    rule_id: str
    entity_type: str
    entity_id: str
    status: ComplianceStatus
    checked_at: datetime
    details: Dict[str, Any]
    violations: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.details:
            self.details = {}


@dataclass
class ComplianceReport:
    """Compliance report."""
    report_id: str
    framework: ComplianceFramework
    report_type: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    data: Dict[str, Any]
    status: str = "draft"
    
    def __post_init__(self):
        if not self.data:
            self.data = {}


class ComplianceChecker(ABC):
    """Abstract base class for compliance checkers."""
    
    @abstractmethod
    async def check_compliance(
        self, 
        rule: ComplianceRule, 
        entity_type: str, 
        entity_id: str, 
        context: Dict[str, Any]
    ) -> ComplianceCheck:
        """Check compliance for a specific rule."""
        pass


class TradingLimitChecker(ComplianceChecker):
    """Trading limit compliance checker."""
    
    async def check_compliance(
        self, 
        rule: ComplianceRule, 
        entity_type: str, 
        entity_id: str, 
        context: Dict[str, Any]
    ) -> ComplianceCheck:
        """Check trading limits compliance."""
        check_id = f"check_{rule.rule_id}_{entity_id}_{datetime.now(timezone.utc).isoformat()}"
        
        # Extract parameters
        max_position_size = rule.parameters.get("max_position_size", float("inf"))
        max_daily_volume = rule.parameters.get("max_daily_volume", float("inf"))
        
        # Get current positions and volumes from context
        current_position = context.get("current_position", 0)
        daily_volume = context.get("daily_volume", 0)
        
        violations = []
        
        if current_position > max_position_size:
            violations.append(f"Position size {current_position} exceeds limit {max_position_size}")
        
        if daily_volume > max_daily_volume:
            violations.append(f"Daily volume {daily_volume} exceeds limit {max_daily_volume}")
        
        status = ComplianceStatus.COMPLIANT if not violations else ComplianceStatus.NON_COMPLIANT
        
        return ComplianceCheck(
            check_id=check_id,
            rule_id=rule.rule_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            checked_at=datetime.now(timezone.utc),
            details={
                "current_position": current_position,
                "max_position_size": max_position_size,
                "daily_volume": daily_volume,
                "max_daily_volume": max_daily_volume
            },
            violations=violations
        )


class RiskLimitChecker(ComplianceChecker):
    """Risk limit compliance checker."""
    
    async def check_compliance(
        self, 
        rule: ComplianceRule, 
        entity_type: str, 
        entity_id: str, 
        context: Dict[str, Any]
    ) -> ComplianceCheck:
        """Check risk limits compliance."""
        check_id = f"check_{rule.rule_id}_{entity_id}_{datetime.now(timezone.utc).isoformat()}"
        
        # Extract parameters
        max_var = rule.parameters.get("max_var", float("inf"))
        max_leverage = rule.parameters.get("max_leverage", float("inf"))
        
        # Get current risk metrics from context
        current_var = context.get("current_var", 0)
        current_leverage = context.get("current_leverage", 1)
        
        violations = []
        
        if current_var > max_var:
            violations.append(f"VaR {current_var} exceeds limit {max_var}")
        
        if current_leverage > max_leverage:
            violations.append(f"Leverage {current_leverage} exceeds limit {max_leverage}")
        
        status = ComplianceStatus.COMPLIANT if not violations else ComplianceStatus.NON_COMPLIANT
        
        return ComplianceCheck(
            check_id=check_id,
            rule_id=rule.rule_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            checked_at=datetime.now(timezone.utc),
            details={
                "current_var": current_var,
                "max_var": max_var,
                "current_leverage": current_leverage,
                "max_leverage": max_leverage
            },
            violations=violations
        )


class DataProtectionChecker(ComplianceChecker):
    """Data protection compliance checker (GDPR)."""
    
    async def check_compliance(
        self, 
        rule: ComplianceRule, 
        entity_type: str, 
        entity_id: str, 
        context: Dict[str, Any]
    ) -> ComplianceCheck:
        """Check data protection compliance."""
        check_id = f"check_{rule.rule_id}_{entity_id}_{datetime.now(timezone.utc).isoformat()}"
        
        # Extract parameters
        data_retention_days = rule.parameters.get("data_retention_days", 365)
        require_consent = rule.parameters.get("require_consent", True)
        
        # Get data from context
        data_age_days = context.get("data_age_days", 0)
        has_consent = context.get("has_consent", False)
        
        violations = []
        
        if data_age_days > data_retention_days:
            violations.append(f"Data age {data_age_days} days exceeds retention limit {data_retention_days} days")
        
        if require_consent and not has_consent:
            violations.append("Data processing without required consent")
        
        status = ComplianceStatus.COMPLIANT if not violations else ComplianceStatus.NON_COMPLIANT
        
        return ComplianceCheck(
            check_id=check_id,
            rule_id=rule.rule_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            checked_at=datetime.now(timezone.utc),
            details={
                "data_age_days": data_age_days,
                "data_retention_days": data_retention_days,
                "has_consent": has_consent,
                "require_consent": require_consent
            },
            violations=violations
        )


class ComplianceError(Exception):
    """Base compliance error."""
    pass


class ComplianceViolationError(ComplianceError):
    """Compliance violation error."""
    pass


class ComplianceService:
    """Comprehensive compliance service."""
    
    def __init__(self):
        """Initialize compliance service."""
        self.rules: Dict[str, ComplianceRule] = {}
        self.violations: Dict[str, ComplianceViolation] = {}
        self.checks: Dict[str, ComplianceCheck] = {}
        self.reports: Dict[str, ComplianceReport] = {}
        self.checkers: Dict[RuleType, ComplianceChecker] = {
            RuleType.TRADING_LIMIT: TradingLimitChecker(),
            RuleType.RISK_LIMIT: RiskLimitChecker(),
            RuleType.DATA_PROTECTION: DataProtectionChecker()
        }
        
        # Initialize default rules
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """Initialize default compliance rules."""
        # MiFID II trading limits
        mifid_position_rule = ComplianceRule(
            rule_id="mifid_position_limit",
            name="MiFID II Position Limit",
            description="Maximum position size limits per MiFID II",
            framework=ComplianceFramework.MIFID_II,
            rule_type=RuleType.POSITION_LIMIT,
            severity=ViolationSeverity.HIGH,
            parameters={
                "max_position_size": 1000000,  # €1M
                "max_daily_volume": 5000000    # €5M
            },
            conditions={"entity_type": "trader"}
        )
        
        # GDPR data protection
        gdpr_data_rule = ComplianceRule(
            rule_id="gdpr_data_protection",
            name="GDPR Data Protection",
            description="Data protection and retention per GDPR",
            framework=ComplianceFramework.GDPR,
            rule_type=RuleType.DATA_PROTECTION,
            severity=ViolationSeverity.CRITICAL,
            parameters={
                "data_retention_days": 365,
                "require_consent": True
            },
            conditions={"entity_type": "user_data"}
        )
        
        # Risk limit rule
        risk_limit_rule = ComplianceRule(
            rule_id="risk_limit_var",
            name="Value at Risk Limit",
            description="Maximum VaR exposure limits",
            framework=ComplianceFramework.CUSTOM,
            rule_type=RuleType.RISK_LIMIT,
            severity=ViolationSeverity.HIGH,
            parameters={
                "max_var": 100000,      # $100K
                "max_leverage": 10.0    # 10x
            },
            conditions={"entity_type": "portfolio"}
        )
        
        self.rules.update({
            "mifid_position_limit": mifid_position_rule,
            "gdpr_data_protection": gdpr_data_rule,
            "risk_limit_var": risk_limit_rule
        })
    
    async def create_rule(
        self,
        rule_id: str,
        name: str,
        description: str,
        framework: ComplianceFramework,
        rule_type: RuleType,
        severity: ViolationSeverity,
        parameters: Dict[str, Any],
        conditions: Optional[Dict[str, Any]] = None
    ) -> ComplianceRule:
        """
        Create new compliance rule.
        
        Args:
            rule_id: Unique rule identifier
            name: Rule name
            description: Rule description
            framework: Regulatory framework
            rule_type: Type of rule
            severity: Violation severity
            parameters: Rule parameters
            conditions: Rule conditions
            
        Returns:
            Created compliance rule
            
        Raises:
            ComplianceError: If rule already exists
        """
        if rule_id in self.rules:
            raise ComplianceError(f"Rule '{rule_id}' already exists")
        
        rule = ComplianceRule(
            rule_id=rule_id,
            name=name,
            description=description,
            framework=framework,
            rule_type=rule_type,
            severity=severity,
            parameters=parameters,
            conditions=conditions or {}
        )
        
        self.rules[rule_id] = rule
        return rule
    
    async def check_compliance(
        self,
        entity_type: str,
        entity_id: str,
        context: Optional[Dict[str, Any]] = None,
        rule_ids: Optional[List[str]] = None
    ) -> List[ComplianceCheck]:
        """
        Check compliance for an entity.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            context: Additional context data
            rule_ids: Specific rules to check (if None, check all applicable)
            
        Returns:
            List of compliance check results
        """
        if context is None:
            context = {}
        
        checks = []
        applicable_rules = rule_ids or list(self.rules.keys())
        
        for rule_id in applicable_rules:
            if rule_id not in self.rules:
                continue
            
            rule = self.rules[rule_id]
            
            # Check if rule applies to this entity
            if not self._rule_applies(rule, entity_type, entity_id, context):
                continue
            
            # Get appropriate checker
            checker = self.checkers.get(rule.rule_type)
            if not checker:
                logger.warning(f"No checker available for rule type: {rule.rule_type}")
                continue
            
            # Perform compliance check
            check = await checker.check_compliance(rule, entity_type, entity_id, context)
            checks.append(check)
            
            # Store check result
            self.checks[check.check_id] = check
            
            # Create violation if non-compliant
            if check.status == ComplianceStatus.NON_COMPLIANT:
                await self._create_violation(check, rule)
        
        return checks
    
    def _rule_applies(
        self, 
        rule: ComplianceRule, 
        entity_type: str, 
        entity_id: str, 
        context: Dict[str, Any]
    ) -> bool:
        """Check if rule applies to entity."""
        if not rule.is_active:
            return False
        
        # Check entity type condition
        if "entity_type" in rule.conditions:
            if rule.conditions["entity_type"] != entity_type:
                return False
        
        # Check other conditions
        for condition_key, condition_value in rule.conditions.items():
            if condition_key == "entity_type":
                continue
            
            context_value = context.get(condition_key)
            if context_value != condition_value:
                return False
        
        return True
    
    async def _create_violation(self, check: ComplianceCheck, rule: ComplianceRule):
        """Create violation record from failed compliance check."""
        violation_id = f"violation_{check.check_id}"
        
        # Calculate remediation deadline based on severity
        deadline_days = {
            ViolationSeverity.CRITICAL: 1,
            ViolationSeverity.HIGH: 7,
            ViolationSeverity.MEDIUM: 30,
            ViolationSeverity.LOW: 90
        }
        
        remediation_deadline = (
            datetime.now(timezone.utc) + 
            timedelta(days=deadline_days.get(rule.severity, 30))
        )
        
        violation = ComplianceViolation(
            violation_id=violation_id,
            rule_id=rule.rule_id,
            entity_type=check.entity_type,
            entity_id=check.entity_id,
            severity=rule.severity,
            status=ComplianceStatus.NON_COMPLIANT,
            description=f"Violation of rule: {rule.name}",
            details={
                "check_id": check.check_id,
                "violations": check.violations,
                "check_details": check.details
            },
            detected_at=check.checked_at,
            remediation_deadline=remediation_deadline
        )
        
        self.violations[violation_id] = violation
        return violation
    
    async def get_violations(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        severity: Optional[ViolationSeverity] = None,
        status: Optional[ComplianceStatus] = None
    ) -> List[ComplianceViolation]:
        """
        Get violations with optional filtering.
        
        Args:
            entity_type: Filter by entity type
            entity_id: Filter by entity ID
            severity: Filter by severity
            status: Filter by status
            
        Returns:
            List of violations
        """
        violations = list(self.violations.values())
        
        if entity_type:
            violations = [v for v in violations if v.entity_type == entity_type]
        
        if entity_id:
            violations = [v for v in violations if v.entity_id == entity_id]
        
        if severity:
            violations = [v for v in violations if v.severity == severity]
        
        if status:
            violations = [v for v in violations if v.status == status]
        
        return violations
    
    async def remediate_violation(
        self,
        violation_id: str,
        remediation_notes: str,
        remediated_by: str
    ) -> bool:
        """
        Mark violation as remediated.
        
        Args:
            violation_id: Violation identifier
            remediation_notes: Notes about remediation
            remediated_by: Who performed remediation
            
        Returns:
            True if successful
            
        Raises:
            ComplianceError: If violation not found
        """
        if violation_id not in self.violations:
            raise ComplianceError(f"Violation '{violation_id}' not found")
        
        violation = self.violations[violation_id]
        violation.status = ComplianceStatus.REMEDIATED
        violation.remediated_at = datetime.now(timezone.utc)
        violation.remediation_notes = f"{remediation_notes} (by: {remediated_by})"
        
        return True
    
    async def generate_compliance_report(
        self,
        framework: ComplianceFramework,
        period_start: datetime,
        period_end: datetime,
        report_type: str = "summary"
    ) -> ComplianceReport:
        """
        Generate compliance report.
        
        Args:
            framework: Regulatory framework
            period_start: Report period start
            period_end: Report period end
            report_type: Type of report
            
        Returns:
            Compliance report
        """
        report_id = f"report_{framework.value}_{period_start.date()}_{period_end.date()}"
        
        # Filter violations by framework and period
        framework_violations = [
            v for v in self.violations.values()
            if (self.rules.get(v.rule_id, {}).framework if v.rule_id in self.rules else None) == framework
            and period_start <= v.detected_at <= period_end
        ]
        
        # Calculate statistics
        total_violations = len(framework_violations)
        by_severity = {}
        by_status = {}
        
        for violation in framework_violations:
            severity_key = violation.severity.value
            status_key = violation.status.value
            
            by_severity[severity_key] = by_severity.get(severity_key, 0) + 1
            by_status[status_key] = by_status.get(status_key, 0) + 1
        
        # Remediation rate
        remediated_count = by_status.get("remediated", 0)
        remediation_rate = (remediated_count / total_violations * 100) if total_violations > 0 else 100
        
        report_data = {
            "framework": framework.value,
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat()
            },
            "summary": {
                "total_violations": total_violations,
                "by_severity": by_severity,
                "by_status": by_status,
                "remediation_rate": round(remediation_rate, 2)
            },
            "violations": [
                {
                    "violation_id": v.violation_id,
                    "rule_id": v.rule_id,
                    "entity_type": v.entity_type,
                    "entity_id": v.entity_id,
                    "severity": v.severity.value,
                    "status": v.status.value,
                    "detected_at": v.detected_at.isoformat(),
                    "remediated_at": v.remediated_at.isoformat() if v.remediated_at else None
                }
                for v in framework_violations
            ]
        }
        
        report = ComplianceReport(
            report_id=report_id,
            framework=framework,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            generated_at=datetime.now(timezone.utc),
            data=report_data
        )
        
        self.reports[report_id] = report
        return report
    
    async def get_compliance_status(
        self,
        entity_type: str,
        entity_id: str
    ) -> Dict[str, Any]:
        """
        Get overall compliance status for entity.
        
        Args:
            entity_type: Entity type
            entity_id: Entity identifier
            
        Returns:
            Compliance status summary
        """
        # Get all violations for entity
        entity_violations = await self.get_violations(
            entity_type=entity_type,
            entity_id=entity_id
        )
        
        # Get recent checks
        recent_checks = [
            check for check in self.checks.values()
            if (check.entity_type == entity_type and 
                check.entity_id == entity_id and
                check.checked_at > datetime.now(timezone.utc) - timedelta(days=7))
        ]
        
        # Calculate status
        open_violations = [v for v in entity_violations if v.status not in [
            ComplianceStatus.REMEDIATED, ComplianceStatus.WAIVED
        ]]
        
        critical_violations = [
            v for v in open_violations 
            if v.severity == ViolationSeverity.CRITICAL
        ]
        
        overall_status = ComplianceStatus.COMPLIANT
        if critical_violations:
            overall_status = ComplianceStatus.NON_COMPLIANT
        elif open_violations:
            overall_status = ComplianceStatus.PENDING_REVIEW
        
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "overall_status": overall_status.value,
            "total_violations": len(entity_violations),
            "open_violations": len(open_violations),
            "critical_violations": len(critical_violations),
            "recent_checks": len(recent_checks),
            "last_checked": max([c.checked_at for c in recent_checks]) if recent_checks else None
        }
    
    async def list_rules(
        self,
        framework: Optional[ComplianceFramework] = None,
        rule_type: Optional[RuleType] = None,
        is_active: Optional[bool] = None
    ) -> List[ComplianceRule]:
        """
        List compliance rules with optional filtering.
        
        Args:
            framework: Filter by framework
            rule_type: Filter by rule type
            is_active: Filter by active status
            
        Returns:
            List of rules
        """
        rules = list(self.rules.values())
        
        if framework:
            rules = [r for r in rules if r.framework == framework]
        
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        
        if is_active is not None:
            rules = [r for r in rules if r.is_active == is_active]
        
        return rules
    
    async def update_rule(
        self,
        rule_id: str,
        **updates
    ) -> bool:
        """
        Update compliance rule.
        
        Args:
            rule_id: Rule identifier
            **updates: Fields to update
            
        Returns:
            True if successful
            
        Raises:
            ComplianceError: If rule not found
        """
        if rule_id not in self.rules:
            raise ComplianceError(f"Rule '{rule_id}' not found")
        
        rule = self.rules[rule_id]
        
        for field, value in updates.items():
            if hasattr(rule, field):
                setattr(rule, field, value)
        
        rule.updated_at = datetime.now(timezone.utc)
        return True
    
    async def delete_rule(self, rule_id: str) -> bool:
        """
        Delete compliance rule.
        
        Args:
            rule_id: Rule identifier
            
        Returns:
            True if successful
            
        Raises:
            ComplianceError: If rule not found or has violations
        """
        if rule_id not in self.rules:
            raise ComplianceError(f"Rule '{rule_id}' not found")
        
        # Check for existing violations
        rule_violations = [v for v in self.violations.values() if v.rule_id == rule_id]
        if rule_violations:
            raise ComplianceError(f"Cannot delete rule '{rule_id}' with existing violations")
        
        del self.rules[rule_id]
        return True


# Global instance
compliance_service = ComplianceService()

# Convenience functions
async def create_rule(rule_id: str, name: str, description: str, **kwargs) -> ComplianceRule:
    """Create compliance rule."""
    return await compliance_service.create_rule(rule_id, name, description, **kwargs)

async def check_compliance(entity_type: str, entity_id: str, **kwargs) -> List[ComplianceCheck]:
    """Check entity compliance."""
    return await compliance_service.check_compliance(entity_type, entity_id, **kwargs)

async def get_violations(**filters) -> List[ComplianceViolation]:
    """Get violations with filters."""
    return await compliance_service.get_violations(**filters)

async def generate_report(framework: ComplianceFramework, **kwargs) -> ComplianceReport:
    """Generate compliance report."""
    return await compliance_service.generate_compliance_report(framework, **kwargs)

def get_compliance_service() -> ComplianceService:
    """Get compliance service instance."""
    return compliance_service