"""
Comprehensive authorization service for the trading platform.

Provides role-based access control (RBAC) functionality including:
- Permission management
- Role-based access control
- Resource-based permissions
- Access control middleware
- Permission inheritance
- Dynamic permission checking
- Audit logging for authorization events
"""

import asyncio
from typing import Dict, Any, Optional, List, Set, Union, Callable
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging
from functools import wraps

logger = logging.getLogger(__name__)


class Permission(Enum):
    """System permissions."""
    # User management
    CREATE_USER = "create_user"
    READ_USER = "read_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"
    
    # Trading permissions
    CREATE_ORDER = "create_order"
    CANCEL_ORDER = "cancel_order"
    VIEW_ORDERS = "view_orders"
    MANAGE_PORTFOLIO = "manage_portfolio"
    
    # Administrative permissions
    ADMIN_ACCESS = "admin_access"
    SYSTEM_CONFIG = "system_config"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    
    # API permissions
    API_READ = "api_read"
    API_WRITE = "api_write"
    API_ADMIN = "api_admin"
    
    # Risk management
    VIEW_RISK_METRICS = "view_risk_metrics"
    MANAGE_RISK_LIMITS = "manage_risk_limits"
    
    # Analytics and reporting
    VIEW_ANALYTICS = "view_analytics"
    EXPORT_DATA = "export_data"
    GENERATE_REPORTS = "generate_reports"


class ResourceType(Enum):
    """Resource types for fine-grained access control."""
    USER = "user"
    ORDER = "order"
    PORTFOLIO = "portfolio"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    REPORT = "report"
    SYSTEM = "system"


class AccessLevel(Enum):
    """Access levels for resources."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"


@dataclass
class ResourcePermission:
    """Resource-specific permission."""
    resource_type: ResourceType
    resource_id: Optional[str]
    access_level: AccessLevel
    conditions: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.conditions is None:
            self.conditions = {}


@dataclass
class Role:
    """User role with permissions."""
    name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    resource_permissions: List[ResourcePermission] = field(default_factory=list)
    inherits_from: Optional[Set[str]] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        if self.inherits_from is None:
            self.inherits_from = set()


@dataclass
class AccessRequest:
    """Access request for authorization checking."""
    user_id: str
    permission: Optional[Permission] = None
    resource_type: Optional[ResourceType] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}


@dataclass
class AuthorizationResult:
    """Result of authorization check."""
    granted: bool
    reason: str
    effective_permissions: List[Permission] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class AuthorizationError(Exception):
    """Base authorization error."""
    pass


class InsufficientPermissionsError(AuthorizationError):
    """Insufficient permissions error."""
    pass


class InvalidRoleError(AuthorizationError):
    """Invalid role error."""
    pass


class AuthorizationService:
    """Comprehensive authorization service."""
    
    def __init__(self):
        """Initialize authorization service."""
        self.roles: Dict[str, Role] = {}
        self.user_roles: Dict[str, Set[str]] = {}
        self.permission_cache: Dict[str, Set[Permission]] = {}
        self._initialize_default_roles()
    
    def _initialize_default_roles(self):
        """Initialize default system roles."""
        # Viewer role
        viewer_role = Role(
            name="viewer",
            description="Read-only access to basic features",
            permissions={
                Permission.READ_USER,
                Permission.VIEW_ORDERS,
                Permission.VIEW_RISK_METRICS,
                Permission.VIEW_ANALYTICS,
                Permission.API_READ
            }
        )
        
        # Trader role
        trader_role = Role(
            name="trader",
            description="Trading access with portfolio management",
            permissions={
                Permission.CREATE_ORDER,
                Permission.CANCEL_ORDER,
                Permission.MANAGE_PORTFOLIO,
                Permission.VIEW_ANALYTICS,
                Permission.EXPORT_DATA,
                Permission.API_READ,
                Permission.API_WRITE
            },
            inherits_from={"viewer"}
        )
        
        # Admin role
        admin_role = Role(
            name="admin",
            description="Administrative access to all features",
            permissions={
                Permission.CREATE_USER,
                Permission.UPDATE_USER,
                Permission.DELETE_USER,
                Permission.ADMIN_ACCESS,
                Permission.SYSTEM_CONFIG,
                Permission.VIEW_AUDIT_LOGS,
                Permission.MANAGE_RISK_LIMITS,
                Permission.GENERATE_REPORTS,
                Permission.API_ADMIN
            },
            inherits_from={"trader"}
        )
        
        # API User role
        api_user_role = Role(
            name="api_user",
            description="API access for external systems",
            permissions={
                Permission.API_READ,
                Permission.API_WRITE,
                Permission.VIEW_ORDERS,
                Permission.CREATE_ORDER
            }
        )
        
        self.roles.update({
            "viewer": viewer_role,
            "trader": trader_role,
            "admin": admin_role,
            "api_user": api_user_role
        })
    
    async def create_role(
        self,
        name: str,
        description: str,
        permissions: Optional[Set[Permission]] = None,
        inherits_from: Optional[Set[str]] = None
    ) -> Role:
        """
        Create a new role.
        
        Args:
            name: Role name
            description: Role description
            permissions: Set of permissions
            inherits_from: Roles to inherit from
            
        Returns:
            Created role
            
        Raises:
            InvalidRoleError: If role already exists or invalid inheritance
        """
        if name in self.roles:
            raise InvalidRoleError(f"Role '{name}' already exists")
        
        if inherits_from:
            for parent_role in inherits_from:
                if parent_role not in self.roles:
                    raise InvalidRoleError(f"Parent role '{parent_role}' does not exist")
        
        role = Role(
            name=name,
            description=description,
            permissions=permissions or set(),
            inherits_from=inherits_from or set()
        )
        
        self.roles[name] = role
        return role
    
    async def assign_role(self, user_id: str, role_name: str) -> bool:
        """
        Assign role to user.
        
        Args:
            user_id: User identifier
            role_name: Role name
            
        Returns:
            True if successful
            
        Raises:
            InvalidRoleError: If role doesn't exist
        """
        if role_name not in self.roles:
            raise InvalidRoleError(f"Role '{role_name}' does not exist")
        
        if user_id not in self.user_roles:
            self.user_roles[user_id] = set()
        
        self.user_roles[user_id].add(role_name)
        
        # Clear permission cache for user
        cache_key = f"user_permissions_{user_id}"
        if cache_key in self.permission_cache:
            del self.permission_cache[cache_key]
        
        return True
    
    async def revoke_role(self, user_id: str, role_name: str) -> bool:
        """
        Revoke role from user.
        
        Args:
            user_id: User identifier
            role_name: Role name
            
        Returns:
            True if successful
        """
        if user_id in self.user_roles:
            self.user_roles[user_id].discard(role_name)
            
            # Clear permission cache for user
            cache_key = f"user_permissions_{user_id}"
            if cache_key in self.permission_cache:
                del self.permission_cache[cache_key]
        
        return True
    
    async def get_user_roles(self, user_id: str) -> Set[str]:
        """Get roles assigned to user."""
        return self.user_roles.get(user_id, set())
    
    async def get_effective_permissions(self, user_id: str) -> Set[Permission]:
        """
        Get effective permissions for user including inherited permissions.
        
        Args:
            user_id: User identifier
            
        Returns:
            Set of effective permissions
        """
        cache_key = f"user_permissions_{user_id}"
        if cache_key in self.permission_cache:
            return self.permission_cache[cache_key]
        
        effective_permissions = set()
        user_roles = await self.get_user_roles(user_id)
        
        def collect_permissions(role_name: str, visited: Set[str] = None):
            """Recursively collect permissions from role hierarchy."""
            if visited is None:
                visited = set()
            
            if role_name in visited or role_name not in self.roles:
                return
            
            visited.add(role_name)
            role = self.roles[role_name]
            
            if role.is_active:
                effective_permissions.update(role.permissions)
                
                # Collect inherited permissions
                for parent_role in role.inherits_from:
                    collect_permissions(parent_role, visited)
        
        for role_name in user_roles:
            collect_permissions(role_name)
        
        # Cache the result
        self.permission_cache[cache_key] = effective_permissions
        return effective_permissions
    
    async def check_permission(
        self,
        user_id: str,
        permission: Permission,
        resource_type: Optional[ResourceType] = None,
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AuthorizationResult:
        """
        Check if user has specific permission.
        
        Args:
            user_id: User identifier
            permission: Permission to check
            resource_type: Optional resource type
            resource_id: Optional resource identifier
            context: Optional context data
            
        Returns:
            Authorization result
        """
        effective_permissions = await self.get_effective_permissions(user_id)
        
        if permission in effective_permissions:
            return AuthorizationResult(
                granted=True,
                reason="Permission granted",
                effective_permissions=list(effective_permissions)
            )
        
        # Check resource-specific permissions
        if resource_type and resource_id:
            resource_access = await self._check_resource_permission(
                user_id, resource_type, resource_id, permission, context
            )
            if resource_access.granted:
                return resource_access
        
        return AuthorizationResult(
            granted=False,
            reason=f"User does not have permission: {permission.value}",
            effective_permissions=list(effective_permissions)
        )
    
    async def _check_resource_permission(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str,
        permission: Permission,
        context: Optional[Dict[str, Any]] = None
    ) -> AuthorizationResult:
        """Check resource-specific permissions."""
        user_roles = await self.get_user_roles(user_id)
        
        for role_name in user_roles:
            if role_name not in self.roles:
                continue
            
            role = self.roles[role_name]
            for resource_perm in role.resource_permissions:
                if (resource_perm.resource_type == resource_type and
                    (resource_perm.resource_id is None or resource_perm.resource_id == resource_id)):
                    
                    # Check if access level allows the permission
                    if self._access_level_allows_permission(resource_perm.access_level, permission):
                        return AuthorizationResult(
                            granted=True,
                            reason=f"Resource permission granted via role: {role_name}"
                        )
        
        return AuthorizationResult(
            granted=False,
            reason="No resource-specific permission found"
        )
    
    def _access_level_allows_permission(self, access_level: AccessLevel, permission: Permission) -> bool:
        """Check if access level allows permission."""
        # Define permission mappings for access levels
        permission_mappings = {
            AccessLevel.READ: {
                Permission.READ_USER,
                Permission.VIEW_ORDERS,
                Permission.VIEW_RISK_METRICS,
                Permission.VIEW_ANALYTICS,
                Permission.API_READ
            },
            AccessLevel.WRITE: {
                Permission.CREATE_ORDER,
                Permission.CANCEL_ORDER,
                Permission.MANAGE_PORTFOLIO,
                Permission.API_WRITE,
                Permission.EXPORT_DATA
            },
            AccessLevel.ADMIN: {
                Permission.CREATE_USER,
                Permission.UPDATE_USER,
                Permission.DELETE_USER,
                Permission.ADMIN_ACCESS,
                Permission.SYSTEM_CONFIG,
                Permission.API_ADMIN
            },
            AccessLevel.OWNER: set(Permission)  # Owner has all permissions
        }
        
        # Check hierarchically
        if access_level == AccessLevel.OWNER:
            return True
        elif access_level == AccessLevel.ADMIN:
            return (permission in permission_mappings[AccessLevel.ADMIN] or
                   permission in permission_mappings[AccessLevel.WRITE] or
                   permission in permission_mappings[AccessLevel.READ])
        elif access_level == AccessLevel.WRITE:
            return (permission in permission_mappings[AccessLevel.WRITE] or
                   permission in permission_mappings[AccessLevel.READ])
        elif access_level == AccessLevel.READ:
            return permission in permission_mappings[AccessLevel.READ]
        
        return False
    
    async def authorize_request(self, request: AccessRequest) -> AuthorizationResult:
        """
        Authorize a complete access request.
        
        Args:
            request: Access request
            
        Returns:
            Authorization result
        """
        if request.permission:
            return await self.check_permission(
                request.user_id,
                request.permission,
                request.resource_type,
                request.resource_id,
                request.context
            )
        
        # If no specific permission, check based on action and resource
        if request.action and request.resource_type:
            inferred_permission = self._infer_permission_from_action(
                request.action, request.resource_type
            )
            if inferred_permission:
                return await self.check_permission(
                    request.user_id,
                    inferred_permission,
                    request.resource_type,
                    request.resource_id,
                    request.context
                )
        
        return AuthorizationResult(
            granted=False,
            reason="Cannot determine required permission from request"
        )
    
    def _infer_permission_from_action(
        self, 
        action: str, 
        resource_type: ResourceType
    ) -> Optional[Permission]:
        """Infer permission from action and resource type."""
        action_mappings = {
            "create": {
                ResourceType.USER: Permission.CREATE_USER,
                ResourceType.ORDER: Permission.CREATE_ORDER
            },
            "read": {
                ResourceType.USER: Permission.READ_USER,
                ResourceType.ORDER: Permission.VIEW_ORDERS
            },
            "update": {
                ResourceType.USER: Permission.UPDATE_USER,
                ResourceType.PORTFOLIO: Permission.MANAGE_PORTFOLIO
            },
            "delete": {
                ResourceType.USER: Permission.DELETE_USER,
                ResourceType.ORDER: Permission.CANCEL_ORDER
            }
        }
        
        return action_mappings.get(action, {}).get(resource_type)
    
    def require_permission(self, permission: Permission, resource_type: Optional[ResourceType] = None):
        """
        Decorator to require specific permission.
        
        Args:
            permission: Required permission
            resource_type: Optional resource type
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract user_id from kwargs or first argument
                user_id = kwargs.get('user_id') or kwargs.get('current_user_id')
                if not user_id and args:
                    user_id = getattr(args[0], 'user_id', None)
                
                if not user_id:
                    raise AuthorizationError("User ID not found in request")
                
                resource_id = kwargs.get('resource_id')
                context = kwargs.get('context', {})
                
                result = await self.check_permission(
                    user_id, permission, resource_type, resource_id, context
                )
                
                if not result.granted:
                    raise InsufficientPermissionsError(result.reason)
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def require_any_permission(self, permissions: List[Permission]):
        """
        Decorator to require any of the specified permissions.
        
        Args:
            permissions: List of acceptable permissions
            
        Returns:
            Decorator function
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                user_id = kwargs.get('user_id') or kwargs.get('current_user_id')
                if not user_id and args:
                    user_id = getattr(args[0], 'user_id', None)
                
                if not user_id:
                    raise AuthorizationError("User ID not found in request")
                
                effective_permissions = await self.get_effective_permissions(user_id)
                
                for permission in permissions:
                    if permission in effective_permissions:
                        return await func(*args, **kwargs)
                
                raise InsufficientPermissionsError(
                    f"User does not have any of the required permissions: {[p.value for p in permissions]}"
                )
            return wrapper
        return decorator
    
    async def list_roles(self) -> Dict[str, Role]:
        """List all available roles."""
        return self.roles.copy()
    
    async def get_role(self, role_name: str) -> Optional[Role]:
        """Get specific role by name."""
        return self.roles.get(role_name)
    
    async def update_role(
        self,
        role_name: str,
        permissions: Optional[Set[Permission]] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """
        Update existing role.
        
        Args:
            role_name: Role name
            permissions: New permissions set
            description: New description
            is_active: New active status
            
        Returns:
            True if successful
            
        Raises:
            InvalidRoleError: If role doesn't exist
        """
        if role_name not in self.roles:
            raise InvalidRoleError(f"Role '{role_name}' does not exist")
        
        role = self.roles[role_name]
        
        if permissions is not None:
            role.permissions = permissions
        if description is not None:
            role.description = description
        if is_active is not None:
            role.is_active = is_active
        
        # Clear all permission caches since role changed
        self.permission_cache.clear()
        
        return True
    
    async def delete_role(self, role_name: str) -> bool:
        """
        Delete role.
        
        Args:
            role_name: Role name
            
        Returns:
            True if successful
            
        Raises:
            InvalidRoleError: If role doesn't exist or is referenced
        """
        if role_name not in self.roles:
            raise InvalidRoleError(f"Role '{role_name}' does not exist")
        
        # Check if role is referenced by other roles
        for role in self.roles.values():
            if role_name in role.inherits_from:
                raise InvalidRoleError(f"Role '{role_name}' is inherited by other roles")
        
        # Remove role from all users
        for user_id in list(self.user_roles.keys()):
            await self.revoke_role(user_id, role_name)
        
        del self.roles[role_name]
        return True
    
    async def add_resource_permission(
        self,
        role_name: str,
        resource_type: ResourceType,
        access_level: AccessLevel,
        resource_id: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add resource-specific permission to role.
        
        Args:
            role_name: Role name
            resource_type: Resource type
            access_level: Access level
            resource_id: Optional specific resource ID
            conditions: Optional conditions
            
        Returns:
            True if successful
            
        Raises:
            InvalidRoleError: If role doesn't exist
        """
        if role_name not in self.roles:
            raise InvalidRoleError(f"Role '{role_name}' does not exist")
        
        resource_permission = ResourcePermission(
            resource_type=resource_type,
            resource_id=resource_id,
            access_level=access_level,
            conditions=conditions or {}
        )
        
        self.roles[role_name].resource_permissions.append(resource_permission)
        self.permission_cache.clear()  # Clear cache
        
        return True


# Global instance
authorization_service = AuthorizationService()

# Convenience functions
async def create_role(name: str, description: str, permissions: Optional[Set[Permission]] = None) -> Role:
    """Create a new role."""
    return await authorization_service.create_role(name, description, permissions)

async def assign_role(user_id: str, role_name: str) -> bool:
    """Assign role to user."""
    return await authorization_service.assign_role(user_id, role_name)

async def check_permission(user_id: str, permission: Permission, **kwargs) -> AuthorizationResult:
    """Check user permission."""
    return await authorization_service.check_permission(user_id, permission, **kwargs)

async def authorize_request(request: AccessRequest) -> AuthorizationResult:
    """Authorize access request."""
    return await authorization_service.authorize_request(request)

def require_permission(permission: Permission, resource_type: Optional[ResourceType] = None):
    """Permission requirement decorator."""
    return authorization_service.require_permission(permission, resource_type)

def require_any_permission(permissions: List[Permission]):
    """Any permission requirement decorator."""
    return authorization_service.require_any_permission(permissions)

def get_authorization_service() -> AuthorizationService:
    """Get authorization service instance."""
    return authorization_service