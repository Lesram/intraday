"""
MLOps Governance Service

Comprehensive governance system providing:
- Compliance tracking and enforcement
- Audit trails and logging
- Access control and permissions
- Regulatory reporting
- Policy management
- Data lineage tracking
- Model approval workflows
- Risk assessment and management
- Documentation and metadata management
- Compliance dashboard and alerts

Author: MLOps Team
Created: 2025-01-01
Version: 1.0.0
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import logging
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GovernanceRole(str, Enum):
    """Governance role enumeration."""
    ADMIN = "admin"
    DATA_SCIENTIST = "data_scientist"
    ML_ENGINEER = "ml_engineer"
    COMPLIANCE_OFFICER = "compliance_officer"
    AUDITOR = "auditor"
    BUSINESS_USER = "business_user"
    VIEWER = "viewer"


class ActionType(str, Enum):
    """Action type enumeration."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    DEPLOY = "deploy"
    APPROVE = "approve"
    REJECT = "reject"
    ARCHIVE = "archive"


class ResourceType(str, Enum):
    """Resource type enumeration."""
    MODEL = "model"
    DATASET = "dataset"
    EXPERIMENT = "experiment"
    PIPELINE = "pipeline"
    ENDPOINT = "endpoint"
    FEATURE = "feature"
    POLICY = "policy"
    USER = "user"


class ComplianceStatus(str, Enum):
    """Compliance status enumeration."""
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PENDING_REVIEW = "pending_review"
    REQUIRES_ACTION = "requires_action"
    EXEMPT = "exempt"


class ApprovalStatus(str, Enum):
    """Approval status enumeration."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REQUIRES_CHANGES = "requires_changes"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class User:
    """User representation."""
    user_id: str
    username: str
    email: str
    role: GovernanceRole
    permissions: list[str] = field(default_factory=list)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_login: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value,
            'permissions': self.permissions,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'metadata': self.metadata
        }


@dataclass
class AuditLogEntry:
    """Audit log entry representation."""
    entry_id: str
    user_id: str
    action_type: ActionType
    resource_type: ResourceType
    resource_id: str
    details: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    ip_address: str = ""
    user_agent: str = ""
    success: bool = True
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'entry_id': self.entry_id,
            'user_id': self.user_id,
            'action_type': self.action_type.value,
            'resource_type': self.resource_type.value,
            'resource_id': self.resource_id,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'success': self.success,
            'error_message': self.error_message
        }


@dataclass
class CompliancePolicy:
    """Compliance policy representation."""
    policy_id: str
    name: str
    description: str
    requirements: list[str]
    resource_types: list[ResourceType]
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'policy_id': self.policy_id,
            'name': self.name,
            'description': self.description,
            'requirements': self.requirements,
            'resource_types': [rt.value for rt in self.resource_types],
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'created_by': self.created_by,
            'metadata': self.metadata
        }


@dataclass
class ComplianceCheck:
    """Compliance check representation."""
    check_id: str
    policy_id: str
    resource_type: ResourceType
    resource_id: str
    status: ComplianceStatus
    findings: list[str]
    recommendations: list[str]
    checked_at: datetime = field(default_factory=datetime.now)
    checked_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'check_id': self.check_id,
            'policy_id': self.policy_id,
            'resource_type': self.resource_type.value,
            'resource_id': self.resource_id,
            'status': self.status.value,
            'findings': self.findings,
            'recommendations': self.recommendations,
            'checked_at': self.checked_at.isoformat(),
            'checked_by': self.checked_by,
            'metadata': self.metadata
        }


@dataclass
class ApprovalRequest:
    """Approval request representation."""
    request_id: str
    resource_type: ResourceType
    resource_id: str
    action_type: ActionType
    requested_by: str
    approver: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str = ""
    reviewer_comments: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    reviewed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'request_id': self.request_id,
            'resource_type': self.resource_type.value,
            'resource_id': self.resource_id,
            'action_type': self.action_type.value,
            'requested_by': self.requested_by,
            'approver': self.approver,
            'status': self.status.value,
            'reason': self.reason,
            'reviewer_comments': self.reviewer_comments,
            'created_at': self.created_at.isoformat(),
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'metadata': self.metadata
        }


@dataclass
class RiskAssessment:
    """Risk assessment representation."""
    assessment_id: str
    resource_type: ResourceType
    resource_id: str
    risk_level: RiskLevel
    risk_factors: list[str]
    mitigation_strategies: list[str]
    assessed_by: str
    assessed_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'assessment_id': self.assessment_id,
            'resource_type': self.resource_type.value,
            'resource_id': self.resource_id,
            'risk_level': self.risk_level.value,
            'risk_factors': self.risk_factors,
            'mitigation_strategies': self.mitigation_strategies,
            'assessed_by': self.assessed_by,
            'assessed_at': self.assessed_at.isoformat(),
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'metadata': self.metadata
        }


class AccessControl:
    """Access control manager."""

    def __init__(self):
        self.role_permissions = {
            GovernanceRole.ADMIN: [
                "create_user", "update_user", "delete_user",
                "create_policy", "update_policy", "delete_policy",
                "approve_request", "reject_request",
                "view_audit_logs", "export_data"
            ],
            GovernanceRole.COMPLIANCE_OFFICER: [
                "create_policy", "update_policy",
                "approve_request", "reject_request",
                "view_audit_logs", "create_compliance_check"
            ],
            GovernanceRole.AUDITOR: [
                "view_audit_logs", "create_compliance_check",
                "view_compliance_status", "export_reports"
            ],
            GovernanceRole.DATA_SCIENTIST: [
                "create_experiment", "update_experiment",
                "create_model", "update_model",
                "request_approval"
            ],
            GovernanceRole.ML_ENGINEER: [
                "create_pipeline", "update_pipeline",
                "deploy_model", "create_endpoint",
                "request_approval"
            ],
            GovernanceRole.BUSINESS_USER: [
                "view_models", "view_experiments",
                "request_approval"
            ],
            GovernanceRole.VIEWER: [
                "view_models", "view_experiments", "view_pipelines"
            ]
        }

    def has_permission(self, user: User, permission: str) -> bool:
        """Check if user has specific permission."""
        # Check role-based permissions
        role_perms = self.role_permissions.get(user.role, [])
        if permission in role_perms:
            return True

        # Check custom permissions
        if permission in user.permissions:
            return True

        return False

    def can_perform_action(self, user: User, action_type: ActionType,
                          resource_type: ResourceType) -> bool:
        """Check if user can perform action on resource type."""
        permission = f"{action_type.value}_{resource_type.value}"
        return self.has_permission(user, permission)

    def get_user_permissions(self, user: User) -> list[str]:
        """Get all permissions for a user."""
        role_perms = self.role_permissions.get(user.role, [])
        all_perms = set(role_perms + user.permissions)
        return list(all_perms)


class ComplianceEngine:
    """Compliance checking engine."""

    def __init__(self):
        self.policies: dict[str, CompliancePolicy] = {}
        self.checks: dict[str, ComplianceCheck] = {}
        self.custom_checkers: dict[str, Callable] = {}

    def add_policy(self, policy: CompliancePolicy):
        """Add a compliance policy."""
        self.policies[policy.policy_id] = policy
        logger.info(f"Added compliance policy: {policy.name}")

    def update_policy(self, policy_id: str, updates: dict[str, Any]) -> bool:
        """Update a compliance policy."""
        if policy_id not in self.policies:
            return False

        policy = self.policies[policy_id]
        for key, value in updates.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        policy.updated_at = datetime.now()
        return True

    def register_custom_checker(self, policy_id: str, checker_func: Callable):
        """Register a custom compliance checker function."""
        self.custom_checkers[policy_id] = checker_func

    def check_compliance(self, resource_type: ResourceType, resource_id: str,
                        resource_data: dict[str, Any], checked_by: str = "") -> list[ComplianceCheck]:
        """Check compliance for a resource."""
        results = []

        # Find applicable policies
        applicable_policies = [
            policy for policy in self.policies.values()
            if resource_type in policy.resource_types and policy.is_active
        ]

        for policy in applicable_policies:
            check_id = hashlib.md5(f"{policy.policy_id}_{resource_id}_{datetime.now()}".encode()).hexdigest()[:16]

            # Use custom checker if available
            if policy.policy_id in self.custom_checkers:
                checker = self.custom_checkers[policy.policy_id]
                try:
                    check_result = checker(resource_data, policy)
                    findings = check_result.get('findings', [])
                    recommendations = check_result.get('recommendations', [])
                    status = ComplianceStatus(check_result.get('status', 'compliant'))
                except Exception as e:
                    findings = [f"Custom checker error: {str(e)}"]
                    recommendations = ["Review custom checker implementation"]
                    status = ComplianceStatus.NON_COMPLIANT
            else:
                # Default compliance check
                findings, recommendations, status = self._default_compliance_check(
                    resource_data, policy
                )

            check = ComplianceCheck(
                check_id=check_id,
                policy_id=policy.policy_id,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status,
                findings=findings,
                recommendations=recommendations,
                checked_by=checked_by
            )

            results.append(check)
            self.checks[check_id] = check

        return results

    def _default_compliance_check(self, resource_data: dict[str, Any],
                                 policy: CompliancePolicy) -> tuple[list[str], list[str], ComplianceStatus]:
        """Default compliance checking logic."""
        findings = []
        recommendations = []

        # Simple checks based on policy requirements
        for requirement in policy.requirements:
            if requirement.startswith("required_field:"):
                field_name = requirement.replace("required_field:", "")
                if field_name not in resource_data:
                    findings.append(f"Missing required field: {field_name}")
                    recommendations.append(f"Add {field_name} to resource")

            elif requirement.startswith("min_accuracy:"):
                min_acc = float(requirement.replace("min_accuracy:", ""))
                accuracy = resource_data.get("accuracy", 0.0)
                if accuracy < min_acc:
                    findings.append(f"Accuracy {accuracy} below minimum {min_acc}")
                    recommendations.append(f"Improve model accuracy to at least {min_acc}")

            elif requirement.startswith("documentation_required"):
                if not resource_data.get("documentation"):
                    findings.append("Documentation is required")
                    recommendations.append("Add comprehensive documentation")

        # Determine status
        if not findings:
            status = ComplianceStatus.COMPLIANT
        elif len(findings) <= 2:
            status = ComplianceStatus.REQUIRES_ACTION
        else:
            status = ComplianceStatus.NON_COMPLIANT

        return findings, recommendations, status

    def get_compliance_summary(self, resource_type: ResourceType = None) -> dict[str, Any]:
        """Get compliance summary."""
        checks = list(self.checks.values())

        if resource_type:
            checks = [c for c in checks if c.resource_type == resource_type]

        total_checks = len(checks)
        if total_checks == 0:
            return {'total_checks': 0}

        status_counts = {}
        for status in ComplianceStatus:
            status_counts[status.value] = len([c for c in checks if c.status == status])

        compliance_rate = status_counts.get('compliant', 0) / total_checks

        return {
            'total_checks': total_checks,
            'status_counts': status_counts,
            'compliance_rate': compliance_rate,
            'last_check': max(c.checked_at for c in checks).isoformat() if checks else None
        }


class WorkflowManager:
    """Approval workflow manager."""

    def __init__(self):
        self.approval_requests: dict[str, ApprovalRequest] = {}
        self.workflow_rules: dict[str, dict[str, Any]] = {}

    def add_workflow_rule(self, resource_type: ResourceType, action_type: ActionType,
                         approval_required: bool, approver_role: GovernanceRole):
        """Add workflow rule."""
        rule_key = f"{resource_type.value}_{action_type.value}"
        self.workflow_rules[rule_key] = {
            'approval_required': approval_required,
            'approver_role': approver_role
        }

    def requires_approval(self, resource_type: ResourceType, action_type: ActionType) -> bool:
        """Check if action requires approval."""
        rule_key = f"{resource_type.value}_{action_type.value}"
        rule = self.workflow_rules.get(rule_key, {})
        return rule.get('approval_required', False)

    def create_approval_request(self, resource_type: ResourceType, resource_id: str,
                              action_type: ActionType, requested_by: str,
                              approver: str, reason: str = "") -> ApprovalRequest:
        """Create approval request."""
        request_id = hashlib.md5(f"{resource_type.value}_{resource_id}_{action_type.value}_{datetime.now()}".encode()).hexdigest()[:16]

        request = ApprovalRequest(
            request_id=request_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action_type=action_type,
            requested_by=requested_by,
            approver=approver,
            reason=reason
        )

        self.approval_requests[request_id] = request
        logger.info(f"Created approval request: {request_id}")
        return request

    def approve_request(self, request_id: str, approver: str, comments: str = "") -> bool:
        """Approve a request."""
        if request_id not in self.approval_requests:
            return False

        request = self.approval_requests[request_id]
        request.status = ApprovalStatus.APPROVED
        request.reviewer_comments = comments
        request.reviewed_at = datetime.now()

        logger.info(f"Approved request: {request_id} by {approver}")
        return True

    def reject_request(self, request_id: str, approver: str, comments: str = "") -> bool:
        """Reject a request."""
        if request_id not in self.approval_requests:
            return False

        request = self.approval_requests[request_id]
        request.status = ApprovalStatus.REJECTED
        request.reviewer_comments = comments
        request.reviewed_at = datetime.now()

        logger.info(f"Rejected request: {request_id} by {approver}")
        return True

    def get_pending_requests(self, approver: str = None) -> list[ApprovalRequest]:
        """Get pending approval requests."""
        requests = [r for r in self.approval_requests.values() if r.status == ApprovalStatus.PENDING]

        if approver:
            requests = [r for r in requests if r.approver == approver]

        return requests


class AuditLogger:
    """Audit logging system."""

    def __init__(self):
        self.logs: list[AuditLogEntry] = []
        self.retention_days = 365 * 7  # 7 years default

    def log_action(self, user_id: str, action_type: ActionType, resource_type: ResourceType,
                  resource_id: str, details: dict[str, Any], success: bool = True,
                  error_message: str = "", ip_address: str = "", user_agent: str = ""):
        """Log an action."""
        entry_id = hashlib.md5(f"{user_id}_{action_type.value}_{resource_id}_{datetime.now()}".encode()).hexdigest()[:16]

        entry = AuditLogEntry(
            entry_id=entry_id,
            user_id=user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )

        self.logs.append(entry)

        # Clean old logs
        self._clean_old_logs()

    def _clean_old_logs(self):
        """Clean logs older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        self.logs = [log for log in self.logs if log.timestamp > cutoff_date]

    def search_logs(self, user_id: str = None, action_type: ActionType = None,
                   resource_type: ResourceType = None, start_date: datetime = None,
                   end_date: datetime = None, limit: int = 100) -> list[AuditLogEntry]:
        """Search audit logs."""
        results = self.logs.copy()

        if user_id:
            results = [log for log in results if log.user_id == user_id]

        if action_type:
            results = [log for log in results if log.action_type == action_type]

        if resource_type:
            results = [log for log in results if log.resource_type == resource_type]

        if start_date:
            results = [log for log in results if log.timestamp >= start_date]

        if end_date:
            results = [log for log in results if log.timestamp <= end_date]

        # Sort by timestamp (newest first) and limit
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def get_audit_summary(self, days: int = 30) -> dict[str, Any]:
        """Get audit summary for the last N days."""
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_logs = [log for log in self.logs if log.timestamp >= cutoff_date]

        if not recent_logs:
            return {'total_actions': 0, 'period_days': days}

        # Count by action type
        action_counts = {}
        for action_type in ActionType:
            action_counts[action_type.value] = len([log for log in recent_logs if log.action_type == action_type])

        # Count by resource type
        resource_counts = {}
        for resource_type in ResourceType:
            resource_counts[resource_type.value] = len([log for log in recent_logs if log.resource_type == resource_type])

        # Count by user
        user_counts = {}
        for log in recent_logs:
            user_counts[log.user_id] = user_counts.get(log.user_id, 0) + 1

        success_count = len([log for log in recent_logs if log.success])
        failure_count = len(recent_logs) - success_count

        return {
            'total_actions': len(recent_logs),
            'period_days': days,
            'action_counts': action_counts,
            'resource_counts': resource_counts,
            'top_users': sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            'success_count': success_count,
            'failure_count': failure_count,
            'success_rate': success_count / len(recent_logs) if recent_logs else 0
        }


class MLOpsGovernanceService:
    """Main MLOps governance service."""

    def __init__(self, storage_path: str = "./governance"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.users: dict[str, User] = {}
        self.access_control = AccessControl()
        self.compliance_engine = ComplianceEngine()
        self.workflow_manager = WorkflowManager()
        self.audit_logger = AuditLogger()
        self.risk_assessments: dict[str, RiskAssessment] = {}

        # Initialize default policies and workflows
        self._initialize_default_policies()
        self._initialize_default_workflows()

    def _initialize_default_policies(self):
        """Initialize default compliance policies."""
        # Model deployment policy
        model_policy = CompliancePolicy(
            policy_id="model_deployment_policy",
            name="Model Deployment Policy",
            description="Requirements for model deployment",
            requirements=[
                "required_field:accuracy",
                "required_field:documentation",
                "min_accuracy:0.8",
                "documentation_required"
            ],
            resource_types=[ResourceType.MODEL]
        )
        self.compliance_engine.add_policy(model_policy)

        # Data governance policy
        data_policy = CompliancePolicy(
            policy_id="data_governance_policy",
            name="Data Governance Policy",
            description="Requirements for data handling",
            requirements=[
                "required_field:data_source",
                "required_field:privacy_classification",
                "documentation_required"
            ],
            resource_types=[ResourceType.DATASET]
        )
        self.compliance_engine.add_policy(data_policy)

    def _initialize_default_workflows(self):
        """Initialize default approval workflows."""
        # Model deployment requires approval
        self.workflow_manager.add_workflow_rule(
            ResourceType.MODEL, ActionType.DEPLOY, True, GovernanceRole.COMPLIANCE_OFFICER
        )

        # Dataset deletion requires approval
        self.workflow_manager.add_workflow_rule(
            ResourceType.DATASET, ActionType.DELETE, True, GovernanceRole.ADMIN
        )

        # Pipeline deployment requires approval
        self.workflow_manager.add_workflow_rule(
            ResourceType.PIPELINE, ActionType.DEPLOY, True, GovernanceRole.ML_ENGINEER
        )

    def create_user(self, user_id: str, username: str, email: str, role: GovernanceRole,
                   permissions: list[str] = None, metadata: dict[str, Any] = None) -> User:
        """Create a new user."""
        if permissions is None:
            permissions = []
        if metadata is None:
            metadata = {}

        user = User(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            permissions=permissions,
            metadata=metadata
        )

        self.users[user_id] = user

        # Log user creation
        self.audit_logger.log_action(
            user_id="system",
            action_type=ActionType.CREATE,
            resource_type=ResourceType.USER,
            resource_id=user_id,
            details={'username': username, 'role': role.value}
        )

        logger.info(f"Created user: {username} ({role.value})")
        return user

    def authenticate_user(self, user_id: str) -> User | None:
        """Authenticate and get user."""
        user = self.users.get(user_id)
        if user and user.is_active:
            user.last_login = datetime.now()
            return user
        return None

    def check_permission(self, user_id: str, permission: str) -> bool:
        """Check if user has permission."""
        user = self.users.get(user_id)
        if not user or not user.is_active:
            return False

        return self.access_control.has_permission(user, permission)

    def request_action_approval(self, user_id: str, resource_type: ResourceType,
                              resource_id: str, action_type: ActionType,
                              reason: str = "") -> ApprovalRequest | None:
        """Request approval for an action."""
        user = self.users.get(user_id)
        if not user:
            return None

        # Check if approval is required
        if not self.workflow_manager.requires_approval(resource_type, action_type):
            return None

        # Find appropriate approver (simplified - use first admin)
        approver = None
        for u in self.users.values():
            if u.role == GovernanceRole.ADMIN:
                approver = u.user_id
                break

        if not approver:
            return None

        request = self.workflow_manager.create_approval_request(
            resource_type=resource_type,
            resource_id=resource_id,
            action_type=action_type,
            requested_by=user_id,
            approver=approver,
            reason=reason
        )

        # Log approval request
        self.audit_logger.log_action(
            user_id=user_id,
            action_type=ActionType.CREATE,
            resource_type=ResourceType.POLICY,  # Using POLICY as proxy for approval
            resource_id=request.request_id,
            details={'approval_request': request.to_dict()}
        )

        return request

    def approve_action(self, approver_id: str, request_id: str, comments: str = "") -> bool:
        """Approve an action request."""
        user = self.users.get(approver_id)
        if not user:
            return False

        success = self.workflow_manager.approve_request(request_id, approver_id, comments)

        # Log approval decision
        self.audit_logger.log_action(
            user_id=approver_id,
            action_type=ActionType.APPROVE,
            resource_type=ResourceType.POLICY,
            resource_id=request_id,
            details={'comments': comments},
            success=success
        )

        return success

    def reject_action(self, approver_id: str, request_id: str, comments: str = "") -> bool:
        """Reject an action request."""
        user = self.users.get(approver_id)
        if not user:
            return False

        success = self.workflow_manager.reject_request(request_id, approver_id, comments)

        # Log rejection decision
        self.audit_logger.log_action(
            user_id=approver_id,
            action_type=ActionType.REJECT,
            resource_type=ResourceType.POLICY,
            resource_id=request_id,
            details={'comments': comments},
            success=success
        )

        return success

    def check_resource_compliance(self, user_id: str, resource_type: ResourceType,
                                resource_id: str, resource_data: dict[str, Any]) -> list[ComplianceCheck]:
        """Check compliance for a resource."""
        user = self.users.get(user_id)
        if not user:
            return []

        results = self.compliance_engine.check_compliance(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_data=resource_data,
            checked_by=user_id
        )

        # Log compliance check
        self.audit_logger.log_action(
            user_id=user_id,
            action_type=ActionType.READ,
            resource_type=resource_type,
            resource_id=resource_id,
            details={'compliance_checks': len(results)}
        )

        return results

    def create_risk_assessment(self, user_id: str, resource_type: ResourceType,
                             resource_id: str, risk_level: RiskLevel,
                             risk_factors: list[str], mitigation_strategies: list[str],
                             expires_in_days: int = 365) -> RiskAssessment:
        """Create risk assessment."""
        assessment_id = hashlib.md5(f"risk_{resource_type.value}_{resource_id}_{datetime.now()}".encode()).hexdigest()[:16]

        expires_at = datetime.now() + timedelta(days=expires_in_days)

        assessment = RiskAssessment(
            assessment_id=assessment_id,
            resource_type=resource_type,
            resource_id=resource_id,
            risk_level=risk_level,
            risk_factors=risk_factors,
            mitigation_strategies=mitigation_strategies,
            assessed_by=user_id,
            expires_at=expires_at
        )

        self.risk_assessments[assessment_id] = assessment

        # Log risk assessment
        self.audit_logger.log_action(
            user_id=user_id,
            action_type=ActionType.CREATE,
            resource_type=resource_type,
            resource_id=resource_id,
            details={
                'risk_assessment_id': assessment_id,
                'risk_level': risk_level.value
            }
        )

        logger.info(f"Created risk assessment: {assessment_id} for {resource_id}")
        return assessment

    def get_governance_dashboard(self, user_id: str) -> dict[str, Any]:
        """Get governance dashboard data."""
        user = self.users.get(user_id)
        if not user:
            return {}

        # Compliance summary
        compliance_summary = self.compliance_engine.get_compliance_summary()

        # Pending approvals
        pending_approvals = self.workflow_manager.get_pending_requests()

        # Audit summary
        audit_summary = self.audit_logger.get_audit_summary()

        # Risk summary
        risk_summary = self._get_risk_summary()

        # User activity
        user_activity = self._get_user_activity(user_id)

        return {
            'user': user.to_dict(),
            'compliance_summary': compliance_summary,
            'pending_approvals': len(pending_approvals),
            'audit_summary': audit_summary,
            'risk_summary': risk_summary,
            'user_activity': user_activity,
            'permissions': self.access_control.get_user_permissions(user)
        }

    def _get_risk_summary(self) -> dict[str, Any]:
        """Get risk assessment summary."""
        assessments = list(self.risk_assessments.values())

        if not assessments:
            return {'total_assessments': 0}

        # Count by risk level
        risk_counts = {}
        for risk_level in RiskLevel:
            risk_counts[risk_level.value] = len([a for a in assessments if a.risk_level == risk_level])

        # Count expired assessments
        now = datetime.now()
        expired_count = len([a for a in assessments if a.expires_at and a.expires_at < now])

        return {
            'total_assessments': len(assessments),
            'risk_level_counts': risk_counts,
            'expired_assessments': expired_count
        }

    def _get_user_activity(self, user_id: str, days: int = 7) -> dict[str, Any]:
        """Get user activity summary."""
        user_logs = self.audit_logger.search_logs(
            user_id=user_id,
            start_date=datetime.now() - timedelta(days=days),
            limit=1000
        )

        if not user_logs:
            return {'total_actions': 0, 'period_days': days}

        # Count by action type
        action_counts = {}
        for action_type in ActionType:
            action_counts[action_type.value] = len([log for log in user_logs if log.action_type == action_type])

        return {
            'total_actions': len(user_logs),
            'period_days': days,
            'action_counts': action_counts,
            'last_activity': user_logs[0].timestamp.isoformat() if user_logs else None
        }

    def export_compliance_report(self, user_id: str, resource_type: ResourceType = None,
                               start_date: datetime = None, end_date: datetime = None) -> dict[str, Any]:
        """Export compliance report."""
        user = self.users.get(user_id)
        if not user or not self.access_control.has_permission(user, "export_reports"):
            return {'error': 'Permission denied'}

        # Get compliance checks
        checks = list(self.compliance_engine.checks.values())

        if resource_type:
            checks = [c for c in checks if c.resource_type == resource_type]

        if start_date:
            checks = [c for c in checks if c.checked_at >= start_date]

        if end_date:
            checks = [c for c in checks if c.checked_at <= end_date]

        # Log report export
        self.audit_logger.log_action(
            user_id=user_id,
            action_type=ActionType.READ,
            resource_type=ResourceType.POLICY,
            resource_id="compliance_report",
            details={
                'resource_type': resource_type.value if resource_type else 'all',
                'checks_count': len(checks)
            }
        )

        return {
            'report_generated_at': datetime.now().isoformat(),
            'generated_by': user_id,
            'filters': {
                'resource_type': resource_type.value if resource_type else None,
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None
            },
            'total_checks': len(checks),
            'compliance_checks': [check.to_dict() for check in checks],
            'summary': self.compliance_engine.get_compliance_summary(resource_type)
        }

    def get_service_statistics(self) -> dict[str, Any]:
        """Get governance service statistics."""
        return {
            'total_users': len(self.users),
            'active_users': len([u for u in self.users.values() if u.is_active]),
            'total_policies': len(self.compliance_engine.policies),
            'total_compliance_checks': len(self.compliance_engine.checks),
            'total_approval_requests': len(self.workflow_manager.approval_requests),
            'pending_approvals': len(self.workflow_manager.get_pending_requests()),
            'total_risk_assessments': len(self.risk_assessments),
            'total_audit_logs': len(self.audit_logger.logs),
            'compliance_summary': self.compliance_engine.get_compliance_summary(),
            'audit_summary': self.audit_logger.get_audit_summary()
        }


# Convenience functions
def create_governance_service(storage_path: str = "./governance") -> MLOpsGovernanceService:
    """Create a governance service instance."""
    return MLOpsGovernanceService(storage_path)


def create_user(user_id: str, username: str, email: str, role: GovernanceRole,
               permissions: list[str] = None, metadata: dict[str, Any] = None) -> User:
    """Create a user instance."""
    if permissions is None:
        permissions = []
    if metadata is None:
        metadata = {}

    return User(
        user_id=user_id,
        username=username,
        email=email,
        role=role,
        permissions=permissions,
        metadata=metadata
    )


# Export all classes and functions
__all__ = [
    'GovernanceRole', 'ActionType', 'ResourceType', 'ComplianceStatus', 'ApprovalStatus', 'RiskLevel',
    'User', 'AuditLogEntry', 'CompliancePolicy', 'ComplianceCheck', 'ApprovalRequest', 'RiskAssessment',
    'AccessControl', 'ComplianceEngine', 'WorkflowManager', 'AuditLogger', 'MLOpsGovernanceService',
    'create_governance_service', 'create_user'
]
