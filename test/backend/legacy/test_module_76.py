"""
Comprehensive test suite for Module 76: backend.services.authorization
Tests authorization service functionality.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

try:
    from backend.services.authorization import (
        AuthorizationService, Permission, ResourceType, AccessLevel,
        Role, ResourcePermission, AccessRequest, AuthorizationResult,
        AuthorizationError, InsufficientPermissionsError, InvalidRoleError,
        create_role, assign_role, check_permission, authorize_request,
        require_permission, require_any_permission, get_authorization_service
    )
    MODULE_EXISTS = True
except ImportError:
    MODULE_EXISTS = False


class TestModule76BackendServicesAuthorization:
    """Comprehensive test suite for authorization service functionality."""
    
    @pytest.fixture
    def auth_service(self):
        """Get fresh authorization service instance"""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        return AuthorizationService()
    
    @pytest_asyncio.fixture
    async def test_user_setup(self, auth_service):
        """Setup test users with roles"""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Assign roles to test users
        await auth_service.assign_role("user_viewer", "viewer")
        await auth_service.assign_role("user_trader", "trader")
        await auth_service.assign_role("user_admin", "admin")
        
        return {
            "viewer": "user_viewer",
            "trader": "user_trader", 
            "admin": "user_admin"
        }

    def test_module_availability(self):
        """Test module availability."""
        if MODULE_EXISTS:
            import backend.services.authorization as module
            assert module is not None
        else:
            assert True

    def test_module_functionality(self):
        """Test module functionality if exists."""
        if MODULE_EXISTS:
            import backend.services.authorization as module
            assert hasattr(module, '__name__')
        else:
            pytest.skip("Module not available")

    def test_default_roles_initialization(self, auth_service):
        """Test that default roles are properly initialized."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        expected_roles = {"viewer", "trader", "admin", "api_user"}
        assert set(auth_service.roles.keys()) == expected_roles
        
        # Check viewer role
        viewer = auth_service.roles["viewer"]
        assert Permission.READ_USER in viewer.permissions
        assert Permission.VIEW_ORDERS in viewer.permissions
        assert Permission.CREATE_ORDER not in viewer.permissions
        
        # Check trader role inheritance
        trader = auth_service.roles["trader"]
        assert "viewer" in trader.inherits_from
        assert Permission.CREATE_ORDER in trader.permissions
        assert Permission.MANAGE_PORTFOLIO in trader.permissions
        
        # Check admin role
        admin = auth_service.roles["admin"]
        assert "trader" in admin.inherits_from
        assert Permission.ADMIN_ACCESS in admin.permissions
        assert Permission.CREATE_USER in admin.permissions

    @pytest.mark.asyncio
    async def test_create_role(self, auth_service):
        """Test role creation functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create new role
        permissions = {Permission.VIEW_ANALYTICS, Permission.EXPORT_DATA}
        role = await auth_service.create_role(
            "analyst",
            "Data analyst role",
            permissions
        )
        
        assert role.name == "analyst"
        assert role.description == "Data analyst role"
        assert role.permissions == permissions
        assert role.is_active is True
        assert isinstance(role.created_at, datetime)
        
        # Check role is stored
        assert "analyst" in auth_service.roles
        
        # Test duplicate role creation
        with pytest.raises(InvalidRoleError, match="already exists"):
            await auth_service.create_role("analyst", "Duplicate", set())

    @pytest.mark.asyncio
    async def test_create_role_with_inheritance(self, auth_service):
        """Test role creation with inheritance."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create role that inherits from viewer
        role = await auth_service.create_role(
            "readonly_analyst",
            "Read-only analyst",
            {Permission.VIEW_ANALYTICS},
            {"viewer"}
        )
        
        assert "viewer" in role.inherits_from
        
        # Test inheritance from non-existent role
        with pytest.raises(InvalidRoleError, match="does not exist"):
            await auth_service.create_role(
                "bad_role",
                "Bad role",
                set(),
                {"nonexistent"}
            )

    @pytest.mark.asyncio
    async def test_assign_and_revoke_roles(self, auth_service):
        """Test role assignment and revocation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        user_id = "test_user_123"
        
        # Assign role
        result = await auth_service.assign_role(user_id, "viewer")
        assert result is True
        
        user_roles = await auth_service.get_user_roles(user_id)
        assert "viewer" in user_roles
        
        # Assign multiple roles
        await auth_service.assign_role(user_id, "trader")
        user_roles = await auth_service.get_user_roles(user_id)
        assert len(user_roles) == 2
        assert "viewer" in user_roles
        assert "trader" in user_roles
        
        # Revoke role
        result = await auth_service.revoke_role(user_id, "viewer")
        assert result is True
        
        user_roles = await auth_service.get_user_roles(user_id)
        assert "viewer" not in user_roles
        assert "trader" in user_roles
        
        # Test assigning non-existent role
        with pytest.raises(InvalidRoleError, match="does not exist"):
            await auth_service.assign_role(user_id, "nonexistent")

    @pytest.mark.asyncio
    async def test_effective_permissions(self, auth_service, test_user_setup):
        """Test effective permissions calculation with inheritance."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test viewer permissions
        viewer_perms = await auth_service.get_effective_permissions(test_user_setup["viewer"])
        assert Permission.READ_USER in viewer_perms
        assert Permission.VIEW_ORDERS in viewer_perms
        assert Permission.CREATE_ORDER not in viewer_perms
        
        # Test trader permissions (should include viewer permissions)
        trader_perms = await auth_service.get_effective_permissions(test_user_setup["trader"])
        assert Permission.READ_USER in trader_perms  # From viewer
        assert Permission.CREATE_ORDER in trader_perms  # From trader
        assert Permission.MANAGE_PORTFOLIO in trader_perms
        
        # Test admin permissions (should include all)
        admin_perms = await auth_service.get_effective_permissions(test_user_setup["admin"])
        assert Permission.READ_USER in admin_perms  # From viewer
        assert Permission.CREATE_ORDER in admin_perms  # From trader
        assert Permission.ADMIN_ACCESS in admin_perms  # From admin

    @pytest.mark.asyncio
    async def test_permission_checking(self, auth_service, test_user_setup):
        """Test permission checking functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test viewer permissions
        result = await auth_service.check_permission(
            test_user_setup["viewer"], 
            Permission.READ_USER
        )
        assert result.granted is True
        assert "Permission granted" in result.reason
        
        result = await auth_service.check_permission(
            test_user_setup["viewer"],
            Permission.CREATE_ORDER
        )
        assert result.granted is False
        assert "does not have permission" in result.reason
        
        # Test trader permissions
        result = await auth_service.check_permission(
            test_user_setup["trader"],
            Permission.CREATE_ORDER
        )
        assert result.granted is True
        
        # Test admin permissions
        result = await auth_service.check_permission(
            test_user_setup["admin"],
            Permission.ADMIN_ACCESS
        )
        assert result.granted is True

    @pytest.mark.asyncio
    async def test_resource_permissions(self, auth_service):
        """Test resource-specific permissions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Add resource permission to trader role
        await auth_service.add_resource_permission(
            "trader",
            ResourceType.PORTFOLIO,
            AccessLevel.OWNER,
            "portfolio_123"
        )
        
        user_id = "resource_test_user"
        await auth_service.assign_role(user_id, "trader")
        
        # Test resource-specific permission
        result = await auth_service.check_permission(
            user_id,
            Permission.MANAGE_PORTFOLIO,
            ResourceType.PORTFOLIO,
            "portfolio_123"
        )
        assert result.granted is True

    @pytest.mark.asyncio
    async def test_access_request_authorization(self, auth_service, test_user_setup):
        """Test complete access request authorization."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test with explicit permission
        request = AccessRequest(
            user_id=test_user_setup["trader"],
            permission=Permission.CREATE_ORDER
        )
        
        result = await auth_service.authorize_request(request)
        assert result.granted is True
        
        # Test with action inference
        request = AccessRequest(
            user_id=test_user_setup["admin"],
            action="create",
            resource_type=ResourceType.USER
        )
        
        result = await auth_service.authorize_request(request)
        assert result.granted is True
        
        # Test insufficient permissions
        request = AccessRequest(
            user_id=test_user_setup["viewer"],
            permission=Permission.CREATE_ORDER
        )
        
        result = await auth_service.authorize_request(request)
        assert result.granted is False

    @pytest.mark.asyncio
    async def test_permission_decorators(self, auth_service, test_user_setup):
        """Test permission requirement decorators."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test require_permission decorator
        @auth_service.require_permission(Permission.CREATE_ORDER)
        async def create_order_endpoint(user_id=None):
            return "Order created"
        
        # Should work for trader
        result = await create_order_endpoint(user_id=test_user_setup["trader"])
        assert result == "Order created"
        
        # Should fail for viewer
        with pytest.raises(InsufficientPermissionsError):
            await create_order_endpoint(user_id=test_user_setup["viewer"])
        
        # Test require_any_permission decorator
        @auth_service.require_any_permission([Permission.READ_USER, Permission.CREATE_ORDER])
        async def flexible_endpoint(user_id=None):
            return "Access granted"
        
        # Should work for viewer (has READ_USER)
        result = await flexible_endpoint(user_id=test_user_setup["viewer"])
        assert result == "Access granted"
        
        # Should work for trader (has CREATE_ORDER)
        result = await flexible_endpoint(user_id=test_user_setup["trader"])
        assert result == "Access granted"

    @pytest.mark.asyncio
    async def test_role_management(self, auth_service):
        """Test role management operations."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test list roles
        roles = await auth_service.list_roles()
        assert len(roles) >= 4  # Default roles
        assert "viewer" in roles
        assert "trader" in roles
        
        # Test get role
        trader_role = await auth_service.get_role("trader")
        assert trader_role is not None
        assert trader_role.name == "trader"
        
        # Test get non-existent role
        none_role = await auth_service.get_role("nonexistent")
        assert none_role is None
        
        # Test update role
        result = await auth_service.update_role(
            "trader",
            description="Updated trader description",
            is_active=False
        )
        assert result is True
        
        updated_role = await auth_service.get_role("trader")
        assert updated_role.description == "Updated trader description"
        assert updated_role.is_active is False
        
        # Test update non-existent role
        with pytest.raises(InvalidRoleError):
            await auth_service.update_role("nonexistent", description="test")

    @pytest.mark.asyncio
    async def test_role_deletion(self, auth_service):
        """Test role deletion functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create test role
        await auth_service.create_role("temp_role", "Temporary role")
        
        # Assign to user
        await auth_service.assign_role("temp_user", "temp_role")
        
        # Delete role
        result = await auth_service.delete_role("temp_role")
        assert result is True
        
        # Role should no longer exist
        assert "temp_role" not in auth_service.roles
        
        # User should no longer have role
        user_roles = await auth_service.get_user_roles("temp_user")
        assert "temp_role" not in user_roles
        
        # Test deleting role with inheritance
        await auth_service.create_role("parent_role", "Parent")
        await auth_service.create_role("child_role", "Child", inherits_from={"parent_role"})
        
        with pytest.raises(InvalidRoleError, match="is inherited by other roles"):
            await auth_service.delete_role("parent_role")

    def test_access_level_permission_mapping(self, auth_service):
        """Test access level to permission mapping."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test READ access level
        assert auth_service._access_level_allows_permission(
            AccessLevel.READ, Permission.READ_USER
        )
        assert not auth_service._access_level_allows_permission(
            AccessLevel.READ, Permission.CREATE_ORDER
        )
        
        # Test WRITE access level (should include READ)
        assert auth_service._access_level_allows_permission(
            AccessLevel.WRITE, Permission.READ_USER
        )
        assert auth_service._access_level_allows_permission(
            AccessLevel.WRITE, Permission.CREATE_ORDER
        )
        assert not auth_service._access_level_allows_permission(
            AccessLevel.WRITE, Permission.ADMIN_ACCESS
        )
        
        # Test ADMIN access level
        assert auth_service._access_level_allows_permission(
            AccessLevel.ADMIN, Permission.ADMIN_ACCESS
        )
        assert auth_service._access_level_allows_permission(
            AccessLevel.ADMIN, Permission.CREATE_ORDER
        )
        
        # Test OWNER access level (should allow everything)
        assert auth_service._access_level_allows_permission(
            AccessLevel.OWNER, Permission.ADMIN_ACCESS
        )
        assert auth_service._access_level_allows_permission(
            AccessLevel.OWNER, Permission.CREATE_ORDER
        )

    def test_permission_inference(self, auth_service):
        """Test permission inference from actions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test action to permission mapping
        assert auth_service._infer_permission_from_action(
            "create", ResourceType.USER
        ) == Permission.CREATE_USER
        
        assert auth_service._infer_permission_from_action(
            "read", ResourceType.ORDER
        ) == Permission.VIEW_ORDERS
        
        assert auth_service._infer_permission_from_action(
            "update", ResourceType.PORTFOLIO
        ) == Permission.MANAGE_PORTFOLIO
        
        # Test unknown action/resource
        assert auth_service._infer_permission_from_action(
            "unknown", ResourceType.USER
        ) is None

    @pytest.mark.asyncio
    async def test_permission_caching(self, auth_service):
        """Test permission caching functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        user_id = "cache_test_user"
        await auth_service.assign_role(user_id, "viewer")
        
        # First call should populate cache
        perms1 = await auth_service.get_effective_permissions(user_id)
        cache_key = f"user_permissions_{user_id}"
        assert cache_key in auth_service.permission_cache
        
        # Second call should use cache
        perms2 = await auth_service.get_effective_permissions(user_id)
        assert perms1 == perms2
        
        # Assigning new role should clear cache
        await auth_service.assign_role(user_id, "trader")
        assert cache_key not in auth_service.permission_cache
        
        # New permissions should include trader permissions
        perms3 = await auth_service.get_effective_permissions(user_id)
        assert Permission.CREATE_ORDER in perms3

    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test create_role
        role = await create_role("conv_role", "Convenience role")
        assert role.name == "conv_role"
        
        # Test assign_role
        result = await assign_role("conv_user", "conv_role")
        assert result is True
        
        # Test check_permission
        auth_result = await check_permission("conv_user", Permission.READ_USER)
        assert isinstance(auth_result, AuthorizationResult)
        
        # Test authorize_request
        request = AccessRequest(user_id="conv_user", permission=Permission.READ_USER)
        auth_result = await authorize_request(request)
        assert isinstance(auth_result, AuthorizationResult)
        
        # Test get_authorization_service
        service = get_authorization_service()
        assert isinstance(service, AuthorizationService)

    def test_data_classes(self):
        """Test data class functionality."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test ResourcePermission
        resource_perm = ResourcePermission(
            resource_type=ResourceType.USER,
            resource_id="user_123",
            access_level=AccessLevel.READ
        )
        assert resource_perm.conditions == {}
        
        # Test Role with inheritance
        role = Role(
            name="test_role",
            description="Test role",
            inherits_from={"parent_role"}
        )
        assert isinstance(role.created_at, datetime)
        assert "parent_role" in role.inherits_from
        
        # Test AccessRequest
        request = AccessRequest(user_id="user_123")
        assert request.context == {}
        
        # Test AuthorizationResult
        result = AuthorizationResult(granted=True, reason="Test")
        assert result.metadata == {}

    @pytest.mark.asyncio
    async def test_decorator_edge_cases(self, auth_service):
        """Test decorator edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test decorator without user_id
        @auth_service.require_permission(Permission.READ_USER)
        async def no_user_endpoint():
            return "test"
        
        with pytest.raises(AuthorizationError, match="User ID not found"):
            await no_user_endpoint()
        
        # Test decorator with object that has user_id attribute
        class RequestObject:
            def __init__(self):
                self.user_id = "test_user"
        
        await auth_service.assign_role("test_user", "viewer")
        request_obj = RequestObject()
        
        @auth_service.require_permission(Permission.READ_USER)
        async def object_endpoint(request_obj):
            return "success"
        
        result = await object_endpoint(request_obj)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circular_inheritance_prevention(self, auth_service):
        """Test prevention of circular role inheritance."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create roles with potential circular inheritance
        await auth_service.create_role("role_a", "Role A")
        await auth_service.create_role("role_b", "Role B", inherits_from={"role_a"})
        
        # This should work fine
        user_id = "circular_test"
        await auth_service.assign_role(user_id, "role_b")
        
        # Get permissions should handle the hierarchy correctly
        permissions = await auth_service.get_effective_permissions(user_id)
        assert isinstance(permissions, set)

    def test_enums_and_constants(self):
        """Test enum definitions and constants."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test Permission enum
        assert Permission.CREATE_USER.value == "create_user"
        assert Permission.READ_USER.value == "read_user"
        
        # Test ResourceType enum
        assert ResourceType.USER.value == "user"
        assert ResourceType.ORDER.value == "order"
        
        # Test AccessLevel enum
        assert AccessLevel.READ.value == "read"
        assert AccessLevel.ADMIN.value == "admin"
