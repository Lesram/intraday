#!/usr/bin/env python3
"""
Module 120: MLOps Governance Test Suite
Comprehensive tests for backend/mlops/governance.py targeting 100% coverage.

Test Target: backend/mlops/governance.py (1085 lines)
Goal: Achieve 100% coverage with comprehensive testing of all classes and functions.
"""

import pytest
import json
import time
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List
import hashlib

# Import the module under test
try:
    from backend.mlops.governance import (
        # Enums
        GovernanceRole, ActionType, ResourceType, ComplianceStatus, ApprovalStatus, RiskLevel,
        # Data classes
        User, AuditLogEntry, CompliancePolicy, ComplianceCheck, ApprovalRequest, RiskAssessment,
        # Classes
        AccessControl, ComplianceEngine, WorkflowManager, AuditLogger, MLOpsGovernanceService,
        # Functions
        create_governance_service, create_user
    )
    MODULE_AVAILABLE = True
except ImportError as e:
    print(f"Import error: {e}")
    MODULE_AVAILABLE = False
    
    # Create minimal stubs for testing
    class GovernanceRole:
        ADMIN = "admin"
        DATA_SCIENTIST = "data_scientist"
        ML_ENGINEER = "ml_engineer"
        COMPLIANCE_OFFICER = "compliance_officer"
        AUDITOR = "auditor"
        BUSINESS_USER = "business_user"
        VIEWER = "viewer"
    
    class ActionType:
        CREATE = "create"
        READ = "read"
        UPDATE = "update"
        DELETE = "delete"
        DEPLOY = "deploy"
        APPROVE = "approve"
        REJECT = "reject"
        ARCHIVE = "archive"
    
    class ResourceType:
        MODEL = "model"
        DATASET = "dataset"
        EXPERIMENT = "experiment"
        PIPELINE = "pipeline"
        ENDPOINT = "endpoint"
        FEATURE = "feature"
        POLICY = "policy"
        USER = "user"


class TestEnumerations:
    """Test enumeration classes."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_governance_role_values(self):
        """Test GovernanceRole enumeration values."""
        assert GovernanceRole.ADMIN == "admin"
        assert GovernanceRole.DATA_SCIENTIST == "data_scientist"
        assert GovernanceRole.ML_ENGINEER == "ml_engineer"
        assert GovernanceRole.COMPLIANCE_OFFICER == "compliance_officer"
        assert GovernanceRole.AUDITOR == "auditor"
        assert GovernanceRole.BUSINESS_USER == "business_user"
        assert GovernanceRole.VIEWER == "viewer"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_action_type_values(self):
        """Test ActionType enumeration values."""
        assert ActionType.CREATE == "create"
        assert ActionType.READ == "read"
        assert ActionType.UPDATE == "update"
        assert ActionType.DELETE == "delete"
        assert ActionType.DEPLOY == "deploy"
        assert ActionType.APPROVE == "approve"
        assert ActionType.REJECT == "reject"
        assert ActionType.ARCHIVE == "archive"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_resource_type_values(self):
        """Test ResourceType enumeration values."""
        assert ResourceType.MODEL == "model"
        assert ResourceType.DATASET == "dataset"
        assert ResourceType.EXPERIMENT == "experiment"
        assert ResourceType.PIPELINE == "pipeline"
        assert ResourceType.ENDPOINT == "endpoint"
        assert ResourceType.FEATURE == "feature"
        assert ResourceType.POLICY == "policy"
        assert ResourceType.USER == "user"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_status_values(self):
        """Test ComplianceStatus enumeration values."""
        assert ComplianceStatus.COMPLIANT == "compliant"
        assert ComplianceStatus.NON_COMPLIANT == "non_compliant"
        assert ComplianceStatus.PENDING_REVIEW == "pending_review"
        assert ComplianceStatus.REQUIRES_ACTION == "requires_action"
        assert ComplianceStatus.EXEMPT == "exempt"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_approval_status_values(self):
        """Test ApprovalStatus enumeration values."""
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.APPROVED == "approved"
        assert ApprovalStatus.REJECTED == "rejected"
        assert ApprovalStatus.REQUIRES_CHANGES == "requires_changes"
        assert ApprovalStatus.CANCELLED == "cancelled"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_risk_level_values(self):
        """Test RiskLevel enumeration values."""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MEDIUM == "medium"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.CRITICAL == "critical"


class TestUser:
    """Test User dataclass."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_user_creation(self):
        """Test User creation with minimal parameters."""
        user = User(
            user_id="user123",
            username="testuser",
            email="test@example.com",
            role=GovernanceRole.DATA_SCIENTIST
        )
        
        assert user.user_id == "user123"
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == GovernanceRole.DATA_SCIENTIST
        assert user.permissions == []
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)
        assert user.last_login is None
        assert user.metadata == {}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_user_creation_with_all_parameters(self):
        """Test User creation with all parameters."""
        created_at = datetime.now()
        last_login = datetime.now() - timedelta(days=1)
        permissions = ["read", "write", "deploy"]
        metadata = {"department": "ML", "team": "research"}
        
        user = User(
            user_id="user456",
            username="poweruser",
            email="power@example.com",
            role=GovernanceRole.ML_ENGINEER,
            permissions=permissions,
            is_active=False,
            created_at=created_at,
            last_login=last_login,
            metadata=metadata
        )
        
        assert user.user_id == "user456"
        assert user.username == "poweruser"
        assert user.email == "power@example.com"
        assert user.role == GovernanceRole.ML_ENGINEER
        assert user.permissions == permissions
        assert user.is_active is False
        assert user.created_at == created_at
        assert user.last_login == last_login
        assert user.metadata == metadata
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_user_to_dict(self):
        """Test User to_dict method."""
        created_at = datetime(2023, 1, 15, 10, 30, 45)
        last_login = datetime(2023, 1, 14, 9, 15, 30)
        permissions = ["read", "write"]
        metadata = {"role": "senior"}
        
        user = User(
            user_id="dict_user",
            username="dictuser",
            email="dict@example.com",
            role=GovernanceRole.ADMIN,
            permissions=permissions,
            is_active=True,
            created_at=created_at,
            last_login=last_login,
            metadata=metadata
        )
        
        expected_dict = {
            'user_id': "dict_user",
            'username': "dictuser",
            'email': "dict@example.com",
            'role': "admin",
            'permissions': permissions,
            'is_active': True,
            'created_at': "2023-01-15T10:30:45",
            'last_login': "2023-01-14T09:15:30",
            'metadata': metadata
        }
        
        result_dict = user.to_dict()
        assert result_dict == expected_dict
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_user_to_dict_no_last_login(self):
        """Test User to_dict method with no last login."""
        user = User(
            user_id="no_login_user",
            username="nologin",
            email="nologin@example.com",
            role=GovernanceRole.VIEWER
        )
        
        result_dict = user.to_dict()
        assert result_dict['last_login'] is None


class TestAuditLogEntry:
    """Test AuditLogEntry dataclass."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_log_entry_creation(self):
        """Test AuditLogEntry creation with minimal parameters."""
        entry = AuditLogEntry(
            entry_id="entry123",
            user_id="user456",
            action_type=ActionType.CREATE,
            resource_type=ResourceType.MODEL,
            resource_id="model789",
            details={"name": "test_model"}
        )
        
        assert entry.entry_id == "entry123"
        assert entry.user_id == "user456"
        assert entry.action_type == ActionType.CREATE
        assert entry.resource_type == ResourceType.MODEL
        assert entry.resource_id == "model789"
        assert entry.details == {"name": "test_model"}
        assert isinstance(entry.timestamp, datetime)
        assert entry.ip_address == ""
        assert entry.user_agent == ""
        assert entry.success is True
        assert entry.error_message == ""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_log_entry_creation_with_all_parameters(self):
        """Test AuditLogEntry creation with all parameters."""
        timestamp = datetime.now()
        details = {"model_version": "1.0.0", "accuracy": 0.95}
        
        entry = AuditLogEntry(
            entry_id="full_entry",
            user_id="full_user",
            action_type=ActionType.DEPLOY,
            resource_type=ResourceType.MODEL,
            resource_id="full_model",
            details=details,
            timestamp=timestamp,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            success=False,
            error_message="Deployment failed"
        )
        
        assert entry.entry_id == "full_entry"
        assert entry.user_id == "full_user"
        assert entry.action_type == ActionType.DEPLOY
        assert entry.resource_type == ResourceType.MODEL
        assert entry.resource_id == "full_model"
        assert entry.details == details
        assert entry.timestamp == timestamp
        assert entry.ip_address == "192.168.1.100"
        assert entry.user_agent == "Mozilla/5.0"
        assert entry.success is False
        assert entry.error_message == "Deployment failed"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_log_entry_to_dict(self):
        """Test AuditLogEntry to_dict method."""
        timestamp = datetime(2023, 2, 10, 14, 20, 30)
        details = {"operation": "train", "epochs": 100}
        
        entry = AuditLogEntry(
            entry_id="dict_entry",
            user_id="dict_user",
            action_type=ActionType.UPDATE,
            resource_type=ResourceType.EXPERIMENT,
            resource_id="dict_experiment",
            details=details,
            timestamp=timestamp,
            ip_address="10.0.0.1",
            user_agent="Python/3.9",
            success=True,
            error_message=""
        )
        
        expected_dict = {
            'entry_id': "dict_entry",
            'user_id': "dict_user",
            'action_type': "update",
            'resource_type': "experiment",
            'resource_id': "dict_experiment",
            'details': details,
            'timestamp': "2023-02-10T14:20:30",
            'ip_address': "10.0.0.1",
            'user_agent': "Python/3.9",
            'success': True,
            'error_message': ""
        }
        
        result_dict = entry.to_dict()
        assert result_dict == expected_dict


class TestCompliancePolicy:
    """Test CompliancePolicy dataclass."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_policy_creation(self):
        """Test CompliancePolicy creation."""
        policy = CompliancePolicy(
            policy_id="policy123",
            name="Data Privacy Policy",
            description="Ensures data privacy compliance",
            requirements=["required_field:encryption", "required_field:anonymization"],
            resource_types=[ResourceType.DATASET, ResourceType.MODEL]
        )
        
        assert policy.policy_id == "policy123"
        assert policy.name == "Data Privacy Policy"
        assert policy.description == "Ensures data privacy compliance"
        assert policy.requirements == ["required_field:encryption", "required_field:anonymization"]
        assert policy.resource_types == [ResourceType.DATASET, ResourceType.MODEL]
        assert policy.is_active is True
        assert isinstance(policy.created_at, datetime)
        assert policy.metadata == {}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_policy_to_dict(self):
        """Test CompliancePolicy to_dict method."""
        created_at = datetime(2023, 3, 1, 12, 0, 0)
        requirements = ["required_field:max_size", "required_field:format"]
        metadata = {"owner": "compliance_team", "version": "1.2"}
        
        policy = CompliancePolicy(
            policy_id="dict_policy",
            name="Dict Policy",
            description="Policy for dict test",
            requirements=requirements,
            resource_types=[ResourceType.DATASET],
            is_active=False,
            created_at=created_at,
            metadata=metadata
        )
        
        result_dict = policy.to_dict()
        
        assert result_dict['policy_id'] == "dict_policy"
        assert result_dict['name'] == "Dict Policy"
        assert result_dict['description'] == "Policy for dict test"
        assert result_dict['requirements'] == requirements
        assert result_dict['resource_types'] == ["dataset"]
        assert result_dict['is_active'] is False
        assert result_dict['created_at'] == "2023-03-01T12:00:00"
        assert result_dict['metadata'] == metadata


class TestComplianceCheck:
    """Test ComplianceCheck dataclass."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_check_creation(self):
        """Test ComplianceCheck creation."""
        check = ComplianceCheck(
            check_id="check123",
            policy_id="policy456",
            resource_type=ResourceType.MODEL,
            resource_id="model789",
            status=ComplianceStatus.COMPLIANT,
            findings=["All checks passed"],
            recommendations=["Continue monitoring"]
        )
        
        assert check.check_id == "check123"
        assert check.policy_id == "policy456"
        assert check.resource_type == ResourceType.MODEL
        assert check.resource_id == "model789"
        assert check.status == ComplianceStatus.COMPLIANT
        assert check.findings == ["All checks passed"]
        assert check.recommendations == ["Continue monitoring"]
        assert isinstance(check.checked_at, datetime)
        assert check.checked_by == ""
        assert check.metadata == {}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_check_to_dict(self):
        """Test ComplianceCheck to_dict method."""
        checked_at = datetime(2023, 4, 1, 9, 30, 15)
        findings = ["Missing documentation", "Outdated dependencies"]
        recommendations = ["Add docs", "Update deps"]
        metadata = {"reviewer": "john_doe", "automated": True}
        
        check = ComplianceCheck(
            check_id="dict_check",
            policy_id="dict_policy",
            resource_type=ResourceType.PIPELINE,
            resource_id="dict_pipeline",
            status=ComplianceStatus.NON_COMPLIANT,
            findings=findings,
            recommendations=recommendations,
            checked_at=checked_at,
            checked_by="automated_system",
            metadata=metadata
        )
        
        result_dict = check.to_dict()
        
        assert result_dict['check_id'] == "dict_check"
        assert result_dict['policy_id'] == "dict_policy"
        assert result_dict['resource_type'] == "pipeline"
        assert result_dict['resource_id'] == "dict_pipeline"
        assert result_dict['status'] == "non_compliant"
        assert result_dict['findings'] == findings
        assert result_dict['recommendations'] == recommendations
        assert result_dict['checked_at'] == "2023-04-01T09:30:15"
        assert result_dict['checked_by'] == "automated_system"
        assert result_dict['metadata'] == metadata


class TestApprovalRequest:
    """Test ApprovalRequest dataclass."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_approval_request_creation(self):
        """Test ApprovalRequest creation."""
        request = ApprovalRequest(
            request_id="req123",
            resource_type=ResourceType.MODEL,
            resource_id="model456",
            action_type=ActionType.DEPLOY,
            requested_by="user789",
            approver="approver123"
        )
        
        assert request.request_id == "req123"
        assert request.resource_type == ResourceType.MODEL
        assert request.resource_id == "model456"
        assert request.action_type == ActionType.DEPLOY
        assert request.requested_by == "user789"
        assert request.approver == "approver123"
        assert request.status == ApprovalStatus.PENDING
        assert request.reason == ""
        assert request.reviewer_comments == ""
        assert isinstance(request.created_at, datetime)
        assert request.reviewed_at is None
        assert request.metadata == {}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_approval_request_to_dict(self):
        """Test ApprovalRequest to_dict method."""
        created_at = datetime(2023, 5, 1, 16, 45, 0)
        reviewed_at = datetime(2023, 5, 2, 10, 15, 0)
        metadata = {"priority": "high", "department": "ML"}
        
        request = ApprovalRequest(
            request_id="dict_req",
            resource_type=ResourceType.ENDPOINT,
            resource_id="dict_endpoint",
            action_type=ActionType.CREATE,
            requested_by="dict_user",
            approver="senior_approver",
            status=ApprovalStatus.APPROVED,
            reason="Create new endpoint",
            reviewer_comments="Looks good",
            created_at=created_at,
            reviewed_at=reviewed_at,
            metadata=metadata
        )
        
        result_dict = request.to_dict()
        
        assert result_dict['request_id'] == "dict_req"
        assert result_dict['resource_type'] == "endpoint"
        assert result_dict['resource_id'] == "dict_endpoint"
        assert result_dict['action_type'] == "create"
        assert result_dict['requested_by'] == "dict_user"
        assert result_dict['approver'] == "senior_approver"
        assert result_dict['status'] == "approved"
        assert result_dict['reason'] == "Create new endpoint"
        assert result_dict['reviewer_comments'] == "Looks good"
        assert result_dict['created_at'] == "2023-05-01T16:45:00"
        assert result_dict['reviewed_at'] == "2023-05-02T10:15:00"
        assert result_dict['metadata'] == metadata


class TestRiskAssessment:
    """Test RiskAssessment dataclass."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_risk_assessment_creation(self):
        """Test RiskAssessment creation."""
        assessment = RiskAssessment(
            assessment_id="risk123",
            resource_type=ResourceType.MODEL,
            resource_id="model456",
            risk_level=RiskLevel.MEDIUM,
            risk_factors=["bias detection needed", "explainability limited"],
            mitigation_strategies=["Add bias detection", "Improve documentation"],
            assessed_by="risk_assessor"
        )
        
        assert assessment.assessment_id == "risk123"
        assert assessment.resource_type == ResourceType.MODEL
        assert assessment.resource_id == "model456"
        assert assessment.risk_level == RiskLevel.MEDIUM
        assert assessment.risk_factors == ["bias detection needed", "explainability limited"]
        assert assessment.mitigation_strategies == ["Add bias detection", "Improve documentation"]
        assert assessment.assessed_by == "risk_assessor"
        assert isinstance(assessment.assessed_at, datetime)
        assert assessment.expires_at is None
        assert assessment.metadata == {}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_risk_assessment_to_dict(self):
        """Test RiskAssessment to_dict method."""
        assessed_at = datetime(2023, 6, 1, 11, 20, 30)
        expires_at = datetime(2024, 6, 1, 11, 20, 30)
        risk_factors = ["security vulnerability", "performance degradation", "compliance gap"]
        mitigation_strategies = ["Security audit", "Performance optimization", "Compliance review"]
        metadata = {"assessor_team": "risk_team", "method": "automated"}
        
        assessment = RiskAssessment(
            assessment_id="dict_risk",
            resource_type=ResourceType.DATASET,
            resource_id="dict_dataset",
            risk_level=RiskLevel.HIGH,
            risk_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            assessed_by="risk_assessor",
            assessed_at=assessed_at,
            expires_at=expires_at,
            metadata=metadata
        )
        
        result_dict = assessment.to_dict()
        
        assert result_dict['assessment_id'] == "dict_risk"
        assert result_dict['resource_type'] == "dataset"
        assert result_dict['resource_id'] == "dict_dataset"
        assert result_dict['risk_level'] == "high"
        assert result_dict['risk_factors'] == risk_factors
        assert result_dict['mitigation_strategies'] == mitigation_strategies
        assert result_dict['assessed_by'] == "risk_assessor"
        assert result_dict['assessed_at'] == "2023-06-01T11:20:30"
        assert result_dict['expires_at'] == "2024-06-01T11:20:30"
        assert result_dict['metadata'] == metadata


class TestAccessControl:
    """Test AccessControl class."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_access_control_initialization(self):
        """Test AccessControl initialization."""
        ac = AccessControl()
        
        assert hasattr(ac, 'role_permissions')
        assert isinstance(ac.role_permissions, dict)
        assert GovernanceRole.ADMIN in ac.role_permissions
        assert "create_user" in ac.role_permissions[GovernanceRole.ADMIN]
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_access_control_has_permission(self):
        """Test AccessControl has_permission method."""
        ac = AccessControl()
        
        # Create users with different roles
        admin_user = User("admin1", "admin", "admin@test.com", GovernanceRole.ADMIN)
        viewer_user = User("viewer1", "viewer", "viewer@test.com", GovernanceRole.VIEWER, permissions=["custom_read"])
        
        # Test admin permissions - admin should have create_user permission
        assert ac.has_permission(admin_user, "create_user") is True
        assert ac.has_permission(admin_user, "update_user") is True
        assert ac.has_permission(admin_user, "view_audit_logs") is True
        
        # Test viewer permissions - viewer should have view permissions
        assert ac.has_permission(viewer_user, "view_models") is True
        assert ac.has_permission(viewer_user, "custom_read") is True
        assert ac.has_permission(viewer_user, "create_user") is False
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_access_control_can_perform_action(self):
        """Test AccessControl can_perform_action method."""
        ac = AccessControl()
        
        # Create users
        ml_engineer = User("ml1", "mlengineer", "ml@test.com", GovernanceRole.ML_ENGINEER)
        business_user = User("biz1", "bizuser", "biz@test.com", GovernanceRole.BUSINESS_USER)
        
        # Test ML engineer can deploy models (has deploy_model permission)
        assert ac.can_perform_action(ml_engineer, ActionType.DEPLOY, ResourceType.MODEL) is True
        
        # Test business user cannot deploy models (no deploy_model permission)
        assert ac.can_perform_action(business_user, ActionType.DEPLOY, ResourceType.MODEL) is False
        
        # Test business user can view models (has view_models permission)
        assert ac.can_perform_action(business_user, ActionType.READ, ResourceType.MODEL) is False  # view_model != read_model
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_access_control_get_user_permissions(self):
        """Test AccessControl get_user_permissions method."""
        ac = AccessControl()
        
        # Create user with custom permissions
        data_scientist = User(
            "ds1", "datascientist", "ds@test.com", 
            GovernanceRole.DATA_SCIENTIST, 
            permissions=["custom_permission", "special_access"]
        )
        
        permissions = ac.get_user_permissions(data_scientist)
        
        # Should include both role-based and custom permissions
        assert isinstance(permissions, list)
        assert "create_experiment" in permissions  # DATA_SCIENTIST role permission
        assert "update_model" in permissions  # DATA_SCIENTIST role permission
        assert "custom_permission" in permissions
        assert "special_access" in permissions


class TestComplianceEngine:
    """Test ComplianceEngine class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_initialization(self):
        """Test ComplianceEngine initialization."""
        engine = ComplianceEngine()
        
        assert hasattr(engine, 'policies')
        assert hasattr(engine, 'checks')
        assert hasattr(engine, 'custom_checkers')
        assert isinstance(engine.policies, dict)
        assert isinstance(engine.checks, dict)
        assert isinstance(engine.custom_checkers, dict)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_add_policy(self):
        """Test ComplianceEngine add_policy method."""
        engine = ComplianceEngine()
        
        policy = CompliancePolicy(
            policy_id="test_policy",
            name="Test Policy",
            description="A test policy",
            requirements=["required_field:test_rule"],
            resource_types=[ResourceType.MODEL]
        )
        
        engine.add_policy(policy)
        
        assert "test_policy" in engine.policies
        assert engine.policies["test_policy"] == policy
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_update_policy(self):
        """Test ComplianceEngine update_policy method."""
        engine = ComplianceEngine()
        
        # Add initial policy
        policy = CompliancePolicy(
            policy_id="update_policy",
            name="Original Name",
            description="Original description",
            requirements=["required_field:original"],
            resource_types=[ResourceType.MODEL]
        )
        engine.add_policy(policy)
        
        # Update policy
        updates = {
            "name": "Updated Name",
            "description": "Updated description",
            "requirements": ["required_field:updated"]
        }
        
        result = engine.update_policy("update_policy", updates)
        
        assert result is True
        updated_policy = engine.policies["update_policy"]
        assert updated_policy.name == "Updated Name"
        assert updated_policy.description == "Updated description"
        assert updated_policy.requirements == ["required_field:updated"]
        
        # Test updating non-existent policy
        result = engine.update_policy("nonexistent", updates)
        assert result is False
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_register_custom_checker(self):
        """Test ComplianceEngine register_custom_checker method."""
        engine = ComplianceEngine()
        
        def custom_checker(resource_data, policy):
            return {
                'status': 'compliant' if resource_data.get("custom_check", False) else 'non_compliant',
                'findings': [] if resource_data.get("custom_check", False) else ['Custom check failed'],
                'recommendations': ['Keep monitoring'] if resource_data.get("custom_check", False) else ['Fix custom check']
            }
        
        engine.register_custom_checker("custom_policy", custom_checker)
        
        assert "custom_policy" in engine.custom_checkers
        assert engine.custom_checkers["custom_policy"] == custom_checker
        
        # Test custom checker usage
        policy = CompliancePolicy(
            policy_id="custom_policy",
            name="Custom Policy",
            description="Policy with custom checker",
            requirements=["custom_requirement"],
            resource_types=[ResourceType.MODEL]
        )
        engine.add_policy(policy)
        
        # Test passing custom check
        passing_data = {"custom_check": True}
        results = engine.check_compliance(ResourceType.MODEL, "custom_model", passing_data)
        assert len(results) == 1
        assert results[0].status == ComplianceStatus.COMPLIANT
        
        # Test failing custom check
        failing_data = {"custom_check": False}
        results = engine.check_compliance(ResourceType.MODEL, "custom_model_fail", failing_data)
        assert len(results) == 1
        assert results[0].status == ComplianceStatus.NON_COMPLIANT
        
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_custom_checker_error_handling(self):
        """Test ComplianceEngine custom checker error handling."""
        engine = ComplianceEngine()
        
        def failing_custom_checker(resource_data, policy):
            raise ValueError("Custom checker failed!")
        
        engine.register_custom_checker("failing_policy", failing_custom_checker)
        
        policy = CompliancePolicy(
            policy_id="failing_policy",
            name="Failing Policy",
            description="Policy with failing custom checker",
            requirements=["test"],
            resource_types=[ResourceType.MODEL]
        )
        engine.add_policy(policy)
        
        # Test error handling in custom checker
        results = engine.check_compliance(ResourceType.MODEL, "error_model", {})
        assert len(results) == 1
        assert results[0].status == ComplianceStatus.NON_COMPLIANT
        assert "Custom checker error" in results[0].findings[0]
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_check_compliance(self, temp_dir):
        """Test ComplianceEngine check_compliance method."""
        engine = ComplianceEngine()
        
        # Add a test policy
        policy = CompliancePolicy(
            policy_id="test_compliance",
            name="Test Compliance Policy",
            description="Test policy for compliance check",
            requirements=["required_field:test_field"],
            resource_types=[ResourceType.MODEL]
        )
        engine.add_policy(policy)
        
        # Test compliant resource
        compliant_data = {"test_field": "present", "name": "test_model"}
        results = engine.check_compliance(ResourceType.MODEL, "compliant_model", compliant_data)
        
        assert len(results) == 1
        assert results[0].status == ComplianceStatus.COMPLIANT
        assert results[0].resource_type == ResourceType.MODEL
        assert results[0].resource_id == "compliant_model"
        
        # Test non-compliant resource
        non_compliant_data = {"name": "test_model"}  # Missing test_field
        results = engine.check_compliance(ResourceType.MODEL, "non_compliant_model", non_compliant_data)
        
        assert len(results) == 1
        assert results[0].status in [ComplianceStatus.NON_COMPLIANT, ComplianceStatus.REQUIRES_ACTION]
        assert len(results[0].findings) > 0
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_engine_get_compliance_summary(self):
        """Test ComplianceEngine get_compliance_summary method."""
        engine = ComplianceEngine()
        
        # Add some test checks
        compliant_check = ComplianceCheck(
            check_id="compliant1",
            policy_id="policy1",
            resource_type=ResourceType.MODEL,
            resource_id="model1",
            status=ComplianceStatus.COMPLIANT,
            findings=[],
            recommendations=[]
        )
        
        non_compliant_check = ComplianceCheck(
            check_id="non_compliant1",
            policy_id="policy1",
            resource_type=ResourceType.DATASET,
            resource_id="dataset1",
            status=ComplianceStatus.NON_COMPLIANT,
            findings=["Missing field"],
            recommendations=["Add field"]
        )
        
        engine.checks["compliant1"] = compliant_check
        engine.checks["non_compliant1"] = non_compliant_check
        
        # Test summary for all resources
        summary = engine.get_compliance_summary()
        
        assert "total_checks" in summary
        assert "status_counts" in summary
        assert "compliance_rate" in summary
        assert summary["total_checks"] == 2
        assert summary["status_counts"]["compliant"] == 1
        assert summary["status_counts"]["non_compliant"] == 1
        
        # Test summary for specific resource type
        model_summary = engine.get_compliance_summary(ResourceType.MODEL)
        assert model_summary["total_checks"] == 1
        assert model_summary["status_counts"]["compliant"] == 1


class TestWorkflowManager:
    """Test WorkflowManager class."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_initialization(self):
        """Test WorkflowManager initialization."""
        wm = WorkflowManager()
        
        assert hasattr(wm, 'workflow_rules')
        assert hasattr(wm, 'approval_requests')
        assert isinstance(wm.workflow_rules, dict)
        assert isinstance(wm.approval_requests, dict)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_add_workflow_rule(self):
        """Test WorkflowManager add_workflow_rule method."""
        wm = WorkflowManager()
        
        wm.add_workflow_rule(
            ResourceType.MODEL, 
            ActionType.DEPLOY, 
            approval_required=True,
            approver_role=GovernanceRole.COMPLIANCE_OFFICER
        )
        
        key = f"{ResourceType.MODEL.value}_{ActionType.DEPLOY.value}"
        assert key in wm.workflow_rules
        rule = wm.workflow_rules[key]
        assert rule["approval_required"] is True
        assert rule["approver_role"] == GovernanceRole.COMPLIANCE_OFFICER
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_requires_approval(self):
        """Test WorkflowManager requires_approval method."""
        wm = WorkflowManager()
        
        # Add rule requiring approval
        wm.add_workflow_rule(ResourceType.MODEL, ActionType.DEPLOY, 
                           approval_required=True, approver_role=GovernanceRole.ADMIN)
        
        # Add rule not requiring approval
        wm.add_workflow_rule(ResourceType.DATASET, ActionType.READ, 
                           approval_required=False, approver_role=GovernanceRole.VIEWER)
        
        assert wm.requires_approval(ResourceType.MODEL, ActionType.DEPLOY) is True
        assert wm.requires_approval(ResourceType.DATASET, ActionType.READ) is False
        
        # Test default behavior for non-existent rule
        assert wm.requires_approval(ResourceType.EXPERIMENT, ActionType.CREATE) is False
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_create_approval_request(self):
        """Test WorkflowManager create_approval_request method."""
        wm = WorkflowManager()
        
        request = wm.create_approval_request(
            ResourceType.MODEL,
            "test_model",
            ActionType.DEPLOY,
            "ml_engineer_1",
            "senior_approver",
            "Deploy model to production"
        )
        
        assert request.resource_type == ResourceType.MODEL
        assert request.resource_id == "test_model"
        assert request.action_type == ActionType.DEPLOY
        assert request.requested_by == "ml_engineer_1"
        assert request.approver == "senior_approver"
        assert request.reason == "Deploy model to production"
        assert request.status == ApprovalStatus.PENDING
        
        # Verify request is stored
        assert request.request_id in wm.approval_requests
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_approve_request(self):
        """Test WorkflowManager approve_request method."""
        wm = WorkflowManager()
        
        # Create a pending request
        request = wm.create_approval_request(
            ResourceType.ENDPOINT,
            "test_endpoint",
            ActionType.CREATE,
            "requester",
            "approver_1",
            "Create endpoint"
        )
        
        # Approve the request
        result = wm.approve_request(request.request_id, "approver_1", "Looks good")
        
        assert result is True
        updated_request = wm.approval_requests[request.request_id]
        assert updated_request.status == ApprovalStatus.APPROVED
        assert updated_request.reviewer_comments == "Looks good"
        assert updated_request.reviewed_at is not None
        
        # Test approving non-existent request
        result = wm.approve_request("nonexistent", "approver")
        assert result is False
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_reject_request(self):
        """Test WorkflowManager reject_request method."""
        wm = WorkflowManager()
        
        # Create a pending request
        request = wm.create_approval_request(
            ResourceType.PIPELINE,
            "test_pipeline",
            ActionType.DELETE,
            "requester",
            "approver_2",
            "Delete pipeline"
        )
        
        # Reject the request
        result = wm.reject_request(request.request_id, "approver_2", "Security concerns")
        
        assert result is True
        updated_request = wm.approval_requests[request.request_id]
        assert updated_request.status == ApprovalStatus.REJECTED
        assert updated_request.reviewer_comments == "Security concerns"
        
        # Test rejecting non-existent request
        result = wm.reject_request("nonexistent", "approver", "reason")
        assert result is False


class TestAuditLogger:
    """Test AuditLogger class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_initialization(self):
        """Test AuditLogger initialization."""
        audit_logger = AuditLogger()
        
        assert hasattr(audit_logger, 'logs')
        assert isinstance(audit_logger.logs, list)
        assert hasattr(audit_logger, 'retention_days')
        assert audit_logger.retention_days == 365 * 7
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_log_action(self):
        """Test AuditLogger log_action method."""
        audit_logger = AuditLogger()
        
        audit_logger.log_action(
            user_id="test_user",
            action_type=ActionType.CREATE,
            resource_type=ResourceType.MODEL,
            resource_id="test_model",
            details={"version": "1.0"},
            ip_address="192.168.1.100",
            user_agent="Python/3.9"
        )
        
        assert len(audit_logger.logs) == 1
        entry = audit_logger.logs[0]
        
        assert entry.user_id == "test_user"
        assert entry.action_type == ActionType.CREATE
        assert entry.resource_type == ResourceType.MODEL
        assert entry.resource_id == "test_model"
        assert entry.details == {"version": "1.0"}
        assert entry.ip_address == "192.168.1.100"
        assert entry.user_agent == "Python/3.9"
        assert entry.success is True
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_log_error(self):
        """Test AuditLogger log_action method with error."""
        audit_logger = AuditLogger()
        
        audit_logger.log_action(
            user_id="error_user",
            action_type=ActionType.DEPLOY,
            resource_type=ResourceType.MODEL,
            resource_id="error_model",
            details={"error_code": 500},
            success=False,
            error_message="Deployment failed"
        )
        
        assert len(audit_logger.logs) == 1
        entry = audit_logger.logs[0]
        
        assert entry.user_id == "error_user"
        assert entry.action_type == ActionType.DEPLOY
        assert entry.resource_type == ResourceType.MODEL
        assert entry.resource_id == "error_model"
        assert entry.error_message == "Deployment failed"
        assert entry.details == {"error_code": 500}
        assert entry.success is False
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_search_logs(self):
        """Test AuditLogger search_logs method."""
        audit_logger = AuditLogger()
        
        # Add multiple entries
        audit_logger.log_action("user1", ActionType.CREATE, ResourceType.MODEL, "model1", {})
        audit_logger.log_action("user1", ActionType.UPDATE, ResourceType.MODEL, "model1", {})
        audit_logger.log_action("user2", ActionType.READ, ResourceType.DATASET, "dataset1", {})
        
        # Test searching for specific resource type
        model_logs = audit_logger.search_logs(resource_type=ResourceType.MODEL)
        assert len(model_logs) == 2
        
        # Test searching for specific user
        user_logs = audit_logger.search_logs(user_id="user1")
        assert len(user_logs) == 2
        
        # Test getting all logs (limited)
        all_logs = audit_logger.search_logs()
        assert len(all_logs) == 3
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_logs_storage(self, temp_dir):
        """Test AuditLogger logs storage and retrieval."""
        audit_logger = AuditLogger()
        
        # Add test entries
        audit_logger.log_action("export_user", ActionType.CREATE, ResourceType.MODEL, "export_model", {"test": True})
        
        # Verify logs are stored
        assert len(audit_logger.logs) == 1
        entry = audit_logger.logs[0]
        assert entry.user_id == "export_user"
        assert entry.resource_id == "export_model"
        assert entry.details == {"test": True}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_get_audit_summary(self):
        """Test AuditLogger get_audit_summary method."""
        audit_logger = AuditLogger()
        
        # Add various entries
        audit_logger.log_action("user1", ActionType.CREATE, ResourceType.MODEL, "model1", {})
        audit_logger.log_action("user2", ActionType.READ, ResourceType.DATASET, "dataset1", {})
        audit_logger.log_action("user1", ActionType.DEPLOY, ResourceType.MODEL, "model2", {}, success=False, error_message="Error occurred")
        
        summary = audit_logger.get_audit_summary()
        
        assert "total_actions" in summary
        assert "action_counts" in summary
        assert "resource_counts" in summary
        assert "top_users" in summary
        assert "success_rate" in summary
        
        assert summary["total_actions"] == 3
        assert summary["action_counts"]["create"] == 1
        assert summary["resource_counts"]["model"] == 2
        assert len(summary["top_users"]) >= 1


class TestMLOpsGovernanceService:
    """Test MLOpsGovernanceService class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_initialization(self, temp_dir):
        """Test MLOpsGovernanceService initialization."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        assert hasattr(service, 'storage_path')
        assert hasattr(service, 'users')
        assert hasattr(service, 'access_control')
        assert hasattr(service, 'compliance_engine')
        assert hasattr(service, 'workflow_manager')
        assert hasattr(service, 'audit_logger')
        
        assert service.storage_path == Path(temp_dir)
        assert isinstance(service.users, dict)
        assert isinstance(service.access_control, AccessControl)
        assert isinstance(service.compliance_engine, ComplianceEngine)
        assert isinstance(service.workflow_manager, WorkflowManager)
        assert isinstance(service.audit_logger, AuditLogger)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_create_user(self, temp_dir):
        """Test MLOpsGovernanceService create_user method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        user = service.create_user(
            user_id="register_user",
            username="testregister",
            email="register@test.com",
            role=GovernanceRole.DATA_SCIENTIST
        )
        
        assert "register_user" in service.users
        assert service.users["register_user"] == user
        assert user.username == "testregister"
        assert user.role == GovernanceRole.DATA_SCIENTIST
        
        # Verify audit log was created
        assert len(service.audit_logger.logs) > 0
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_authenticate_user(self, temp_dir):
        """Test MLOpsGovernanceService authenticate_user method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create a user
        user = service.create_user(
            user_id="auth_user",
            username="testauth",
            email="auth@test.com",
            role=GovernanceRole.ML_ENGINEER
        )
        
        # Test successful authentication
        auth_result = service.authenticate_user("auth_user")
        assert auth_result is not None
        assert auth_result.user_id == "auth_user"
        
        # Verify last_login was updated
        assert service.users["auth_user"].last_login is not None
        
        # Test authentication of non-existent user
        auth_result = service.authenticate_user("nonexistent")
        assert auth_result is None
        
        # Test authentication of inactive user
        inactive_user = service.create_user(
            user_id="inactive_user",
            username="inactive",
            email="inactive@test.com",
            role=GovernanceRole.VIEWER
        )
        inactive_user.is_active = False
        
        auth_result = service.authenticate_user("inactive_user")
        assert auth_result is None
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_check_permission(self, temp_dir):
        """Test MLOpsGovernanceService check_permission method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create users
        admin_user = service.create_user("admin", "admin", "admin@test.com", GovernanceRole.ADMIN)
        viewer_user = service.create_user("viewer", "viewer", "viewer@test.com", GovernanceRole.VIEWER)
        
        # Test admin permissions
        assert service.check_permission("admin", "create_user") is True
        assert service.check_permission("admin", "view_audit_logs") is True
        
        # Test viewer permissions
        assert service.check_permission("viewer", "view_models") is True
        assert service.check_permission("viewer", "create_user") is False
        
        # Test non-existent user
        assert service.check_permission("nonexistent", "view_models") is False
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_request_action_approval(self, temp_dir):
        """Test MLOpsGovernanceService request_action_approval method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create users (including an admin to act as approver)
        user = service.create_user("requester", "req", "req@test.com", GovernanceRole.DATA_SCIENTIST)
        admin = service.create_user("admin", "admin", "admin@test.com", GovernanceRole.ADMIN)
        
        # Request approval (model deployment has default approval requirement)
        request = service.request_action_approval(
            "requester",
            ResourceType.MODEL,
            "test_model",
            ActionType.DEPLOY,
            "Deploy model to production"
        )
        
        assert request is not None
        assert request.request_id in service.workflow_manager.approval_requests
        
        assert request.requested_by == "requester"
        assert request.resource_type == ResourceType.MODEL
        assert request.action_type == ActionType.DEPLOY
        assert request.reason == "Deploy model to production"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_approve_reject_action(self, temp_dir):
        """Test MLOpsGovernanceService approve_action and reject_action methods."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create approver
        approver = service.create_user("approver", "app", "app@test.com", GovernanceRole.ADMIN)
        
        # Create approval request
        request = service.workflow_manager.create_approval_request(
            ResourceType.ENDPOINT,
            "test_endpoint",
            ActionType.CREATE,
            "requester",
            "approver",
            "Create endpoint"
        )
        
        # Test approval
        result = service.approve_action("approver", request.request_id, "Looks good")
        assert result is True
        
        updated_request = service.workflow_manager.approval_requests[request.request_id]
        assert updated_request.status == ApprovalStatus.APPROVED
        
        # Create another request for rejection test
        reject_request = service.workflow_manager.create_approval_request(
            ResourceType.PIPELINE,
            "test_pipeline",
            ActionType.DELETE,
            "requester",
            "approver",
            "Delete pipeline"
        )
        
        # Test rejection
        result = service.reject_action("approver", reject_request.request_id, "Not necessary")
        assert result is True
        
        updated_reject_request = service.workflow_manager.approval_requests[reject_request.request_id]
        assert updated_reject_request.status == ApprovalStatus.REJECTED
        assert updated_reject_request.reviewer_comments == "Not necessary"
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_add_compliance_policy(self, temp_dir):
        """Test MLOpsGovernanceService compliance policy handling."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        policy = CompliancePolicy(
            policy_id="service_policy",
            name="Service Policy",
            description="Test policy for service",
            requirements=["required_field:test_rule"],
            resource_types=[ResourceType.MODEL]
        )
        
        service.compliance_engine.add_policy(policy)
        
        assert "service_policy" in service.compliance_engine.policies
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_check_compliance(self, temp_dir):
        """Test MLOpsGovernanceService check_resource_compliance method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create user
        user = service.create_user("checker", "check", "check@test.com", GovernanceRole.COMPLIANCE_OFFICER)
        
        # Check compliance (uses default policies)
        results = service.check_resource_compliance(
            "checker",
            ResourceType.MODEL,
            "compliance_model",
            {"accuracy": 0.95, "documentation": "Complete docs"}
        )
        
        assert len(results) >= 1  # At least one policy should apply
        # Check that we get compliance results
        assert all(isinstance(result, ComplianceCheck) for result in results)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_audit_logging(self, temp_dir):
        """Test MLOpsGovernanceService audit logging functionality."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        service.audit_logger.log_action(
            user_id="log_user",
            action_type=ActionType.CREATE,
            resource_type=ResourceType.DATASET,
            resource_id="log_dataset",
            details={"size": 1000}
        )
        
        assert len(service.audit_logger.logs) == 1
        entry = service.audit_logger.logs[0]
        assert entry.user_id == "log_user"
        assert entry.resource_id == "log_dataset"
        assert entry.details == {"size": 1000}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_get_governance_dashboard(self, temp_dir):
        """Test MLOpsGovernanceService get_governance_dashboard method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create user and add some activity
        user = service.create_user("dash_user", "dash", "dash@test.com", GovernanceRole.DATA_SCIENTIST)
        service.audit_logger.log_action("dash_user", ActionType.CREATE, ResourceType.MODEL, "dash_model", {})
        
        dashboard = service.get_governance_dashboard("dash_user")
        
        assert "user" in dashboard
        assert "compliance_summary" in dashboard
        assert "pending_approvals" in dashboard
        assert "audit_summary" in dashboard
        assert "risk_summary" in dashboard
        assert "user_activity" in dashboard
        assert "permissions" in dashboard
        
        assert dashboard["user"]["user_id"] == "dash_user"
        assert dashboard["pending_approvals"] >= 0


class TestWorkflowManagerExtended:
    """Additional WorkflowManager tests."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_workflow_manager_get_pending_requests(self):
        """Test WorkflowManager get_pending_requests method."""
        wm = WorkflowManager()
        
        # Create multiple requests
        req1 = wm.create_approval_request(
            ResourceType.MODEL, "model1", ActionType.DEPLOY, "user1", "approver1", "reason1"
        )
        req2 = wm.create_approval_request(
            ResourceType.DATASET, "dataset1", ActionType.DELETE, "user2", "approver2", "reason2"
        )
        
        # Get all pending requests
        pending = wm.get_pending_requests()
        assert len(pending) == 2
        
        # Get pending requests for specific approver
        pending_for_approver1 = wm.get_pending_requests("approver1")
        assert len(pending_for_approver1) == 1
        assert pending_for_approver1[0].approver == "approver1"
        
        # Approve one request and check pending count
        wm.approve_request(req1.request_id, "approver1")
        pending = wm.get_pending_requests()
        assert len(pending) == 1


class TestMLOpsGovernanceServiceExtended:
    """Additional MLOpsGovernanceService tests."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_create_risk_assessment(self, temp_dir):
        """Test MLOpsGovernanceService create_risk_assessment method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        user = service.create_user("risk_user", "riskuser", "risk@test.com", GovernanceRole.ADMIN)
        
        assessment = service.create_risk_assessment(
            user_id="risk_user",
            resource_type=ResourceType.MODEL,
            resource_id="risky_model",
            risk_level=RiskLevel.HIGH,
            risk_factors=["bias", "performance"],
            mitigation_strategies=["audit", "retrain"],
            expires_in_days=30
        )
        
        assert assessment.assessment_id in service.risk_assessments
        assert assessment.risk_level == RiskLevel.HIGH
        assert assessment.assessed_by == "risk_user"
        assert len(service.audit_logger.logs) > 0  # Should log the creation
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_export_compliance_report(self, temp_dir):
        """Test MLOpsGovernanceService export_compliance_report method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create auditor user (has export_reports permission)
        user = service.create_user("reporter", "reporter", "report@test.com", GovernanceRole.AUDITOR)
        
        # Generate some compliance data
        service.check_resource_compliance(
            "reporter",
            ResourceType.MODEL,
            "test_model",
            {"accuracy": 0.9, "documentation": "yes"}
        )
        
        # Export report
        report = service.export_compliance_report("reporter")
        
        assert "report_generated_at" in report
        assert "generated_by" in report
        assert report["generated_by"] == "reporter"
        assert "compliance_checks" in report
        assert isinstance(report["compliance_checks"], list)
        
        # Test permission denied for non-authorized user
        viewer = service.create_user("viewer", "viewer", "view@test.com", GovernanceRole.VIEWER)
        viewer_report = service.export_compliance_report("viewer")
        assert "error" in viewer_report
        assert "Permission denied" in viewer_report["error"]
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_mlops_governance_service_get_service_statistics(self, temp_dir):
        """Test MLOpsGovernanceService get_service_statistics method."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create some data
        user1 = service.create_user("stat_user1", "user1", "user1@test.com", GovernanceRole.DATA_SCIENTIST)
        user2 = service.create_user("stat_user2", "user2", "user2@test.com", GovernanceRole.ML_ENGINEER)
        user2.is_active = False  # Manually set inactive after creation
        
        stats = service.get_service_statistics()
        
        assert "total_users" in stats
        assert "active_users" in stats
        assert "total_policies" in stats
        assert "total_compliance_checks" in stats
        assert "total_approval_requests" in stats
        assert "pending_approvals" in stats
        assert "total_risk_assessments" in stats
        assert "total_audit_logs" in stats
        
        assert stats["total_users"] >= 2
        assert stats["active_users"] >= 1  # user1 is active, user2 is inactive


class TestDefaultPoliciesAndWorkflows:
    """Test default policies and workflows."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_default_policies_initialization(self, temp_dir):
        """Test that default policies are initialized."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Check default policies exist
        assert "model_deployment_policy" in service.compliance_engine.policies
        assert "data_governance_policy" in service.compliance_engine.policies
        
        model_policy = service.compliance_engine.policies["model_deployment_policy"]
        assert ResourceType.MODEL in model_policy.resource_types
        assert "min_accuracy:0.8" in model_policy.requirements
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")  
    def test_default_workflows_initialization(self, temp_dir):
        """Test that default workflows are initialized."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Check that model deployment requires approval
        assert service.workflow_manager.requires_approval(ResourceType.MODEL, ActionType.DEPLOY) is True
        
        # Check that dataset deletion requires approval
        assert service.workflow_manager.requires_approval(ResourceType.DATASET, ActionType.DELETE) is True
        
        # Check that pipeline deployment requires approval
        assert service.workflow_manager.requires_approval(ResourceType.PIPELINE, ActionType.DEPLOY) is True
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_default_compliance_check_logic(self, temp_dir):
        """Test the default compliance check logic comprehensively."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        user = service.create_user("test_user", "test", "test@test.com", GovernanceRole.ADMIN)
        
        # Test model compliance with various scenarios
        
        # Test passing all requirements
        good_model_data = {
            "accuracy": 0.95,  # Above min_accuracy:0.8
            "documentation": "Complete documentation available"  # documentation_required
        }
        results = service.check_resource_compliance("test_user", ResourceType.MODEL, "good_model", good_model_data)
        compliant_results = [r for r in results if r.status == ComplianceStatus.COMPLIANT]
        assert len(compliant_results) > 0
        
        # Test failing accuracy requirement
        low_accuracy_data = {
            "accuracy": 0.5,  # Below min_accuracy:0.8
            "documentation": "Complete documentation available"
        }
        results = service.check_resource_compliance("test_user", ResourceType.MODEL, "low_accuracy_model", low_accuracy_data)
        non_compliant = [r for r in results if r.status != ComplianceStatus.COMPLIANT]
        assert len(non_compliant) > 0
        accuracy_issue_found = any("Accuracy" in finding for result in non_compliant for finding in result.findings)
        assert accuracy_issue_found
        
        # Test missing documentation
        no_docs_data = {
            "accuracy": 0.9
            # Missing documentation
        }
        results = service.check_resource_compliance("test_user", ResourceType.MODEL, "no_docs_model", no_docs_data)
        non_compliant = [r for r in results if r.status != ComplianceStatus.COMPLIANT]
        assert len(non_compliant) > 0
        
        # Test dataset compliance
        good_dataset_data = {
            "data_source": "production_db",
            "privacy_classification": "public",
            "documentation": "Data schema and usage docs"
        }
        results = service.check_resource_compliance("test_user", ResourceType.DATASET, "good_dataset", good_dataset_data)
        compliant_results = [r for r in results if r.status == ComplianceStatus.COMPLIANT]
        assert len(compliant_results) > 0


class TestAuditLoggerExtended:
    """Additional AuditLogger tests."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_audit_logger_clean_old_logs(self):
        """Test AuditLogger _clean_old_logs method."""
        audit_logger = AuditLogger()
        
        # Set short retention period for testing
        audit_logger.retention_days = 1
        
        # Add an old log entry (simulate by modifying timestamp)
        audit_logger.log_action("user1", ActionType.CREATE, ResourceType.MODEL, "model1", {})
        old_entry = audit_logger.logs[0]
        old_entry.timestamp = datetime.now() - timedelta(days=2)  # Make it older than retention
        
        # Add a recent log entry
        audit_logger.log_action("user2", ActionType.UPDATE, ResourceType.MODEL, "model2", {})
        
        # Trigger cleanup by adding another log
        audit_logger.log_action("user3", ActionType.DELETE, ResourceType.MODEL, "model3", {})
        
        # Should have cleaned the old log
        assert len(audit_logger.logs) == 2  # Only recent logs should remain
        assert all(log.timestamp > datetime.now() - timedelta(days=1) for log in audit_logger.logs)


class TestComplianceEngineAdvanced:
    """Advanced ComplianceEngine tests to reach 100% coverage."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_check_multiple_violations(self):
        """Test compliance check with multiple violations (>2) to trigger NON_COMPLIANT status."""
        engine = ComplianceEngine()
        
        # Create a policy with multiple requirements
        policy = CompliancePolicy(
            policy_id="strict_policy",
            name="Strict Policy",
            description="Policy with many requirements",
            requirements=[
                "required_field:field1",
                "required_field:field2", 
                "required_field:field3",
                "required_field:field4",
                "documentation_required"
            ],
            resource_types=[ResourceType.MODEL]
        )
        engine.add_policy(policy)
        
        # Test with data missing many required fields (should trigger NON_COMPLIANT)
        bad_data = {"name": "test_model"}  # Missing field1, field2, field3, field4, and documentation
        results = engine.check_compliance(ResourceType.MODEL, "bad_model", bad_data)
        
        assert len(results) == 1
        assert results[0].status == ComplianceStatus.NON_COMPLIANT  # More than 2 findings
        assert len(results[0].findings) > 2
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_compliance_check_exactly_two_violations(self):
        """Test compliance check with exactly 2 violations to trigger REQUIRES_ACTION status."""
        engine = ComplianceEngine()
        
        # Create a policy with requirements
        policy = CompliancePolicy(
            policy_id="moderate_policy",
            name="Moderate Policy", 
            description="Policy with moderate requirements",
            requirements=[
                "required_field:field1",
                "required_field:field2",
                "min_accuracy:0.9"
            ],
            resource_types=[ResourceType.MODEL]
        )
        engine.add_policy(policy)
        
        # Test with data having exactly 2 violations (should trigger REQUIRES_ACTION)
        moderate_data = {"field1": "present", "accuracy": 0.7}  # Missing field2 and accuracy too low
        results = engine.check_compliance(ResourceType.MODEL, "moderate_model", moderate_data)
        
        assert len(results) == 1
        assert results[0].status == ComplianceStatus.REQUIRES_ACTION  # Exactly 2 or fewer findings
        assert len(results[0].findings) == 2


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_request_approval_no_admin_available(self, temp_dir):
        """Test request approval when no admin is available."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        # Create non-admin user
        user = service.create_user("user", "user", "user@test.com", GovernanceRole.DATA_SCIENTIST)
        
        # Try to request approval when no admin exists
        request = service.request_action_approval(
            "user",
            ResourceType.MODEL,
            "test_model",
            ActionType.DEPLOY,
            "Deploy model"
        )
        
        # Should return None when no approver is found
        assert request is None
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_request_approval_for_nonexistent_user(self, temp_dir):
        """Test request approval for non-existent user."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        request = service.request_action_approval(
            "nonexistent_user",
            ResourceType.MODEL,
            "test_model", 
            ActionType.DEPLOY,
            "Deploy model"
        )
        
        assert request is None
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_request_approval_no_approval_required(self, temp_dir):
        """Test request approval for action that doesn't require approval."""
        service = MLOpsGovernanceService(storage_path=temp_dir)
        
        user = service.create_user("user", "user", "user@test.com", GovernanceRole.DATA_SCIENTIST)
        
        # Try to request approval for action that doesn't require it
        request = service.request_action_approval(
            "user",
            ResourceType.MODEL,
            "test_model",
            ActionType.READ,  # READ typically doesn't require approval
            "Read model"
        )
        
        # Should return None when approval is not required
        assert request is None


class TestUtilityFunctions:
    """Test utility functions."""
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_create_governance_service(self):
        """Test create_governance_service function."""
        service = create_governance_service("./test_governance")
        
        assert isinstance(service, MLOpsGovernanceService)
        assert service.storage_path == Path("./test_governance")
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_create_governance_service_default_path(self):
        """Test create_governance_service function with default path."""
        service = create_governance_service()
        
        assert isinstance(service, MLOpsGovernanceService)
        assert service.storage_path == Path("./governance")
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_create_user_minimal(self):
        """Test create_user function with minimal parameters."""
        user = create_user(
            "create_user_test",
            "createuser",
            "create@test.com",
            GovernanceRole.AUDITOR
        )
        
        assert isinstance(user, User)
        assert user.user_id == "create_user_test"
        assert user.username == "createuser"
        assert user.email == "create@test.com"
        assert user.role == GovernanceRole.AUDITOR
        assert user.permissions == []
        assert user.metadata == {}
    
    @pytest.mark.skipif(not MODULE_AVAILABLE, reason="Module not available")
    def test_create_user_with_all_parameters(self):
        """Test create_user function with all parameters."""
        permissions = ["admin", "read", "write"]
        metadata = {"team": "governance", "level": "senior"}
        
        user = create_user(
            "full_create_user",
            "fulluser",
            "full@test.com",
            GovernanceRole.COMPLIANCE_OFFICER,
            permissions=permissions,
            metadata=metadata
        )
        
        assert isinstance(user, User)
        assert user.user_id == "full_create_user"
        assert user.username == "fulluser"
        assert user.email == "full@test.com"
        assert user.role == GovernanceRole.COMPLIANCE_OFFICER
        assert user.permissions == permissions
        assert user.metadata == metadata


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])