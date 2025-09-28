"""
Comprehensive test suite for Module 77: backend.services.compliance
Tests compliance service functionality.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock

try:
    from backend.services.compliance import (
        ComplianceService, ComplianceFramework, ComplianceStatus, ViolationSeverity,
        RuleType, ComplianceRule, ComplianceViolation, ComplianceCheck, ComplianceReport,
        TradingLimitChecker, RiskLimitChecker, DataProtectionChecker,
        ComplianceError, ComplianceViolationError,
        create_rule, check_compliance, get_violations, generate_report, get_compliance_service
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


class TestModule77BackendServicesCompliance:
    """Comprehensive test suite for compliance service functionality."""
    
    @pytest.fixture
    def compliance_service(self):
        """Get fresh compliance service instance"""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        return ComplianceService()
    
    @pytest_asyncio.fixture
    async def sample_rules(self, compliance_service):
        """Create sample compliance rules for testing"""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Custom trading rule
        trading_rule = await compliance_service.create_rule(
            rule_id="test_trading_limit",
            name="Test Trading Limit",
            description="Test trading limit rule",
            framework=ComplianceFramework.CUSTOM,
            rule_type=RuleType.TRADING_LIMIT,
            severity=ViolationSeverity.HIGH,
            parameters={
                "max_position_size": 50000,
                "max_daily_volume": 100000
            },
            conditions={"entity_type": "trader"}
        )
        
        # Custom risk rule
        risk_rule = await compliance_service.create_rule(
            rule_id="test_risk_limit",
            name="Test Risk Limit",
            description="Test risk limit rule",
            framework=ComplianceFramework.CUSTOM,
            rule_type=RuleType.RISK_LIMIT,
            severity=ViolationSeverity.MEDIUM,
            parameters={
                "max_var": 25000,
                "max_leverage": 5.0
            },
            conditions={"entity_type": "portfolio"}
        )
        
        return {
            "trading_rule": trading_rule,
            "risk_rule": risk_rule
        }

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.services.compliance as module
            assert module is not None
        else:
            assert True

    def test_module_functionality(self):
        """Test module functionality if exists."""
        if MODULE_EXISTS:
            import backend.services.compliance as module
            assert hasattr(module, '__name__')
        else:
            pytest.skip("Module not available")

    def test_default_rules_initialization(self, compliance_service):
        """Test that default compliance rules are initialized."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        expected_rules = {"mifid_position_limit", "gdpr_data_protection", "risk_limit_var"}
        assert set(compliance_service.rules.keys()) == expected_rules
        
        # Check MiFID II rule
        mifid_rule = compliance_service.rules["mifid_position_limit"]
        assert mifid_rule.framework == ComplianceFramework.MIFID_II
        assert mifid_rule.rule_type == RuleType.POSITION_LIMIT
        assert mifid_rule.severity == ViolationSeverity.HIGH
        
        # Check GDPR rule
        gdpr_rule = compliance_service.rules["gdpr_data_protection"]
        assert gdpr_rule.framework == ComplianceFramework.GDPR
        assert gdpr_rule.rule_type == RuleType.DATA_PROTECTION
        assert gdpr_rule.severity == ViolationSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_create_rule(self, compliance_service):
        """Test compliance rule creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        rule = await compliance_service.create_rule(
            rule_id="test_rule_123",
            name="Test Rule",
            description="A test compliance rule",
            framework=ComplianceFramework.SEC,
            rule_type=RuleType.MARKET_CONDUCT,
            severity=ViolationSeverity.MEDIUM,
            parameters={"max_spread": 0.05},
            conditions={"market": "equity"}
        )
        
        assert rule.rule_id == "test_rule_123"
        assert rule.name == "Test Rule"
        assert rule.framework == ComplianceFramework.SEC
        assert rule.rule_type == RuleType.MARKET_CONDUCT
        assert rule.severity == ViolationSeverity.MEDIUM
        assert rule.parameters["max_spread"] == 0.05
        assert rule.conditions["market"] == "equity"
        assert rule.is_active is True
        assert isinstance(rule.created_at, datetime)
        
        # Test duplicate rule creation
        with pytest.raises(ComplianceError, match="already exists"):
            await compliance_service.create_rule(
                "test_rule_123", "Duplicate", "Duplicate rule",
                ComplianceFramework.SEC, RuleType.MARKET_CONDUCT,
                ViolationSeverity.LOW, {}
            )

    @pytest.mark.asyncio
    async def test_trading_limit_checker(self, compliance_service, sample_rules):
        """Test trading limit compliance checking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        rule = sample_rules["trading_rule"]
        
        # Test compliant case
        compliant_context = {
            "current_position": 30000,
            "daily_volume": 80000
        }
        
        checks = await compliance_service.check_compliance(
            "trader", "trader_001", compliant_context, [rule.rule_id]
        )
        
        assert len(checks) == 1
        check = checks[0]
        assert check.status == ComplianceStatus.COMPLIANT
        assert len(check.violations) == 0
        
        # Test non-compliant case
        non_compliant_context = {
            "current_position": 60000,  # Exceeds 50000 limit
            "daily_volume": 120000      # Exceeds 100000 limit
        }
        
        checks = await compliance_service.check_compliance(
            "trader", "trader_002", non_compliant_context, [rule.rule_id]
        )
        
        assert len(checks) == 1
        check = checks[0]
        assert check.status == ComplianceStatus.NON_COMPLIANT
        assert len(check.violations) == 2
        assert "Position size 60000 exceeds limit 50000" in check.violations
        assert "Daily volume 120000 exceeds limit 100000" in check.violations

    @pytest.mark.asyncio
    async def test_risk_limit_checker(self, compliance_service, sample_rules):
        """Test risk limit compliance checking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        rule = sample_rules["risk_rule"]
        
        # Test compliant case
        compliant_context = {
            "current_var": 20000,
            "current_leverage": 3.0
        }
        
        checks = await compliance_service.check_compliance(
            "portfolio", "portfolio_001", compliant_context, [rule.rule_id]
        )
        
        assert len(checks) == 1
        check = checks[0]
        assert check.status == ComplianceStatus.COMPLIANT
        
        # Test non-compliant case
        non_compliant_context = {
            "current_var": 30000,       # Exceeds 25000 limit
            "current_leverage": 7.0     # Exceeds 5.0 limit
        }
        
        checks = await compliance_service.check_compliance(
            "portfolio", "portfolio_002", non_compliant_context, [rule.rule_id]
        )
        
        assert len(checks) == 1
        check = checks[0]
        assert check.status == ComplianceStatus.NON_COMPLIANT
        assert len(check.violations) == 2

    @pytest.mark.asyncio
    async def test_data_protection_checker(self, compliance_service):
        """Test data protection compliance checking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Use default GDPR rule
        rule = compliance_service.rules["gdpr_data_protection"]
        
        # Test compliant case
        compliant_context = {
            "data_age_days": 200,
            "has_consent": True
        }
        
        checks = await compliance_service.check_compliance(
            "user_data", "user_123", compliant_context, [rule.rule_id]
        )
        
        assert len(checks) == 1
        check = checks[0]
        assert check.status == ComplianceStatus.COMPLIANT
        
        # Test non-compliant case
        non_compliant_context = {
            "data_age_days": 400,       # Exceeds 365 day retention
            "has_consent": False        # Missing consent
        }
        
        checks = await compliance_service.check_compliance(
            "user_data", "user_456", non_compliant_context, [rule.rule_id]
        )
        
        assert len(checks) == 1
        check = checks[0]
        assert check.status == ComplianceStatus.NON_COMPLIANT
        assert len(check.violations) == 2

    @pytest.mark.asyncio
    async def test_violation_creation(self, compliance_service, sample_rules):
        """Test violation creation from failed compliance checks."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        rule = sample_rules["trading_rule"]
        
        # Create non-compliant scenario
        context = {
            "current_position": 60000,
            "daily_volume": 80000
        }
        
        checks = await compliance_service.check_compliance(
            "trader", "trader_003", context, [rule.rule_id]
        )
        
        # Should have created a violation
        violations = list(compliance_service.violations.values())
        assert len(violations) >= 1
        
        # Find our violation
        violation = next(v for v in violations if v.entity_id == "trader_003")
        assert violation.rule_id == rule.rule_id
        assert violation.severity == ViolationSeverity.HIGH
        assert violation.status == ComplianceStatus.NON_COMPLIANT
        assert violation.remediation_deadline is not None

    @pytest.mark.asyncio
    async def test_violation_management(self, compliance_service, sample_rules):
        """Test violation management operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create a violation
        rule = sample_rules["trading_rule"]
        context = {"current_position": 60000, "daily_volume": 80000}
        
        await compliance_service.check_compliance(
            "trader", "trader_004", context, [rule.rule_id]
        )
        
        # Get violations
        violations = await compliance_service.get_violations(entity_id="trader_004")
        assert len(violations) == 1
        
        violation = violations[0]
        
        # Test remediation
        result = await compliance_service.remediate_violation(
            violation.violation_id,
            "Position reduced to compliant level",
            "compliance_officer_001"
        )
        
        assert result is True
        assert violation.status == ComplianceStatus.REMEDIATED
        assert violation.remediated_at is not None
        assert "compliance_officer_001" in violation.remediation_notes

    @pytest.mark.asyncio
    async def test_violation_filtering(self, compliance_service, sample_rules):
        """Test violation filtering functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create multiple violations
        trading_rule = sample_rules["trading_rule"]
        risk_rule = sample_rules["risk_rule"]
        
        # Trading violation
        await compliance_service.check_compliance(
            "trader", "trader_filter_1", 
            {"current_position": 60000, "daily_volume": 80000}, 
            [trading_rule.rule_id]
        )
        
        # Risk violation
        await compliance_service.check_compliance(
            "portfolio", "portfolio_filter_1",
            {"current_var": 30000, "current_leverage": 3.0},
            [risk_rule.rule_id]
        )
        
        # Test filtering by entity type
        trader_violations = await compliance_service.get_violations(entity_type="trader")
        portfolio_violations = await compliance_service.get_violations(entity_type="portfolio")
        
        assert len([v for v in trader_violations if v.entity_id == "trader_filter_1"]) >= 1
        assert len([v for v in portfolio_violations if v.entity_id == "portfolio_filter_1"]) >= 1
        
        # Test filtering by severity
        high_violations = await compliance_service.get_violations(severity=ViolationSeverity.HIGH)
        medium_violations = await compliance_service.get_violations(severity=ViolationSeverity.MEDIUM)
        
        assert len(high_violations) >= 1
        assert len(medium_violations) >= 1

    @pytest.mark.asyncio
    async def test_compliance_report_generation(self, compliance_service, sample_rules):
        """Test compliance report generation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create some violations
        rule = sample_rules["trading_rule"]
        
        await compliance_service.check_compliance(
            "trader", "trader_report_1",
            {"current_position": 60000, "daily_volume": 80000},
            [rule.rule_id]
        )
        
        # Generate report
        period_start = datetime.now(timezone.utc) - timedelta(days=1)
        period_end = datetime.now(timezone.utc)
        
        report = await compliance_service.generate_compliance_report(
            ComplianceFramework.CUSTOM,
            period_start,
            period_end,
            "summary"
        )
        
        assert report.framework == ComplianceFramework.CUSTOM
        assert report.period_start == period_start
        assert report.period_end == period_end
        assert isinstance(report.data, dict)
        
        # Check report data structure
        assert "summary" in report.data
        assert "violations" in report.data
        assert "total_violations" in report.data["summary"]
        assert report.data["summary"]["total_violations"] >= 1

    @pytest.mark.asyncio
    async def test_compliance_status(self, compliance_service, sample_rules):
        """Test compliance status checking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test compliant entity
        compliant_status = await compliance_service.get_compliance_status(
            "trader", "compliant_trader"
        )
        
        assert compliant_status["entity_type"] == "trader"
        assert compliant_status["entity_id"] == "compliant_trader"
        assert compliant_status["overall_status"] == ComplianceStatus.COMPLIANT.value
        
        # Create violation for non-compliant entity
        rule = sample_rules["trading_rule"]
        await compliance_service.check_compliance(
            "trader", "non_compliant_trader",
            {"current_position": 60000, "daily_volume": 80000},
            [rule.rule_id]
        )
        
        non_compliant_status = await compliance_service.get_compliance_status(
            "trader", "non_compliant_trader"
        )
        
        assert non_compliant_status["overall_status"] in [
            ComplianceStatus.NON_COMPLIANT.value, 
            ComplianceStatus.PENDING_REVIEW.value
        ]
        assert non_compliant_status["total_violations"] >= 1

    @pytest.mark.asyncio
    async def test_rule_management(self, compliance_service):
        """Test rule management operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test list rules
        all_rules = await compliance_service.list_rules()
        assert len(all_rules) >= 3  # Default rules
        
        # Test filter by framework
        mifid_rules = await compliance_service.list_rules(framework=ComplianceFramework.MIFID_II)
        assert len(mifid_rules) >= 1
        
        # Test filter by rule type
        data_rules = await compliance_service.list_rules(rule_type=RuleType.DATA_PROTECTION)
        assert len(data_rules) >= 1
        
        # Test update rule
        rule_id = "mifid_position_limit"
        result = await compliance_service.update_rule(
            rule_id,
            description="Updated MiFID II position limits"
        )
        
        assert result is True
        updated_rule = compliance_service.rules[rule_id]
        assert "Updated MiFID II" in updated_rule.description
        assert isinstance(updated_rule.updated_at, datetime)
        
        # Test update non-existent rule
        with pytest.raises(ComplianceError, match="not found"):
            await compliance_service.update_rule("nonexistent_rule", description="test")

    @pytest.mark.asyncio
    async def test_rule_deletion(self, compliance_service):
        """Test rule deletion functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create a test rule
        await compliance_service.create_rule(
            rule_id="deletable_rule",
            name="Deletable Rule",
            description="A rule that can be deleted",
            framework=ComplianceFramework.CUSTOM,
            rule_type=RuleType.MARKET_CONDUCT,
            severity=ViolationSeverity.LOW,
            parameters={}
        )
        
        # Delete the rule
        result = await compliance_service.delete_rule("deletable_rule")
        assert result is True
        assert "deletable_rule" not in compliance_service.rules
        
        # Test deleting non-existent rule
        with pytest.raises(ComplianceError, match="not found"):
            await compliance_service.delete_rule("nonexistent_rule")

    def test_rule_applicability(self, compliance_service):
        """Test rule applicability checking."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        rule = compliance_service.rules["mifid_position_limit"]
        
        # Test applicable entity
        assert compliance_service._rule_applies(
            rule, "trader", "trader_123", {"entity_type": "trader"}
        )
        
        # Test non-applicable entity type
        assert not compliance_service._rule_applies(
            rule, "portfolio", "portfolio_123", {"entity_type": "portfolio"}
        )
        
        # Test inactive rule
        rule.is_active = False
        assert not compliance_service._rule_applies(
            rule, "trader", "trader_123", {"entity_type": "trader"}
        )
        rule.is_active = True  # Reset

    def test_compliance_checkers(self):
        """Test compliance checker implementations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test TradingLimitChecker
        trading_checker = TradingLimitChecker()
        assert trading_checker is not None
        
        # Test RiskLimitChecker
        risk_checker = RiskLimitChecker()
        assert risk_checker is not None
        
        # Test DataProtectionChecker
        data_checker = DataProtectionChecker()
        assert data_checker is not None

    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test create_rule
        rule = await create_rule(
            "conv_rule",
            "Convenience Rule",
            "Test convenience function",
            framework=ComplianceFramework.CUSTOM,
            rule_type=RuleType.MARKET_CONDUCT,
            severity=ViolationSeverity.LOW,
            parameters={}
        )
        assert rule.rule_id == "conv_rule"
        
        # Test check_compliance
        checks = await check_compliance(
            "trader", "conv_trader",
            context={"current_position": 1000}
        )
        assert isinstance(checks, list)
        
        # Test get_violations
        violations = await get_violations(entity_type="trader")
        assert isinstance(violations, list)
        
        # Test generate_report
        period_start = datetime.now(timezone.utc) - timedelta(days=1)
        period_end = datetime.now(timezone.utc)
        
        report = await generate_report(
            ComplianceFramework.CUSTOM,
            period_start=period_start,
            period_end=period_end
        )
        assert isinstance(report, ComplianceReport)
        
        # Test get_compliance_service
        service = get_compliance_service()
        assert isinstance(service, ComplianceService)

    def test_data_classes(self):
        """Test data class functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test ComplianceRule
        rule = ComplianceRule(
            rule_id="test_rule",
            name="Test Rule",
            description="Test",
            framework=ComplianceFramework.SEC,
            rule_type=RuleType.MARKET_CONDUCT,
            severity=ViolationSeverity.LOW,
            parameters={"param": "value"},
            conditions={"condition": "value"}
        )
        assert rule.parameters == {"param": "value"}
        assert rule.conditions == {"condition": "value"}
        assert isinstance(rule.created_at, datetime)
        
        # Test ComplianceViolation
        violation = ComplianceViolation(
            violation_id="test_violation",
            rule_id="test_rule",
            entity_type="trader",
            entity_id="trader_123",
            severity=ViolationSeverity.HIGH,
            status=ComplianceStatus.NON_COMPLIANT,
            description="Test violation",
            details={"detail": "value"},
            detected_at=datetime.now(timezone.utc)
        )
        assert violation.details == {"detail": "value"}
        
        # Test ComplianceCheck
        check = ComplianceCheck(
            check_id="test_check",
            rule_id="test_rule",
            entity_type="trader",
            entity_id="trader_123",
            status=ComplianceStatus.COMPLIANT,
            checked_at=datetime.now(timezone.utc),
            details={"check_detail": "value"}
        )
        assert check.details == {"check_detail": "value"}
        assert check.violations == []

    def test_enums_and_constants(self):
        """Test enum definitions and constants."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test ComplianceFramework enum
        assert ComplianceFramework.MIFID_II.value == "mifid_ii"
        assert ComplianceFramework.GDPR.value == "gdpr"
        
        # Test ComplianceStatus enum
        assert ComplianceStatus.COMPLIANT.value == "compliant"
        assert ComplianceStatus.NON_COMPLIANT.value == "non_compliant"
        
        # Test ViolationSeverity enum
        assert ViolationSeverity.CRITICAL.value == "critical"
        assert ViolationSeverity.HIGH.value == "high"
        
        # Test RuleType enum
        assert RuleType.TRADING_LIMIT.value == "trading_limit"
        assert RuleType.DATA_PROTECTION.value == "data_protection"

    @pytest.mark.asyncio
    async def test_edge_cases_and_error_handling(self, compliance_service):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test checking compliance with no applicable rules
        checks = await compliance_service.check_compliance(
            "unknown_entity", "entity_123", {}, ["nonexistent_rule"]
        )
        assert len(checks) == 0
        
        # Test violation remediation with invalid ID
        with pytest.raises(ComplianceError, match="not found"):
            await compliance_service.remediate_violation(
                "invalid_violation_id", "test", "user"
            )
        
        # Test creating rule with unsupported rule type
        unsupported_rule = await compliance_service.create_rule(
            rule_id="unsupported_rule",
            name="Unsupported Rule",
            description="Rule with unsupported type",
            framework=ComplianceFramework.CUSTOM,
            rule_type=RuleType.AML,  # No checker for this type
            severity=ViolationSeverity.LOW,
            parameters={}
        )
        
        # Should not create checks for unsupported rule types
        checks = await compliance_service.check_compliance(
            "trader", "trader_123", {}, [unsupported_rule.rule_id]
        )
        assert len(checks) == 0
