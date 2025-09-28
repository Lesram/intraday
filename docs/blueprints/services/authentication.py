"""
Comprehensive authentication service for the trading platform.

Provides secure authentication functionality including:
- User login/logout
- JWT token generation and validation
- Password hashing with bcrypt
- Session management
- Multi-factor authentication (TOTP)
- Authentication middleware
- Role-based access control
"""

import asyncio
import jwt
import bcrypt
import hashlib
import hmac
import base64
import secrets
import time
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class UserRole(Enum):
    """User roles for access control."""
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"
    API_USER = "api_user"


class MFAMethod(Enum):
    """Multi-factor authentication methods."""
    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"


@dataclass
class AuthConfig:
    """Authentication configuration."""
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    session_timeout_minutes: int = 60
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    require_mfa: bool = False
    password_min_length: int = 8
    
    def __post_init__(self):
        if self.jwt_secret == "your-secret-key-change-in-production":
            # Generate a random secret for development
            self.jwt_secret = secrets.token_urlsafe(32)


@dataclass
class User:
    """User data structure."""
    user_id: str
    username: str
    email: str
    password_hash: str
    role: UserRole
    is_active: bool = True
    mfa_enabled: bool = False
    mfa_secret: Optional[str] = None
    created_at: datetime = None
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass
class Session:
    """User session data structure."""
    session_id: str
    user_id: str
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True


@dataclass
class AuthToken:
    """Authentication token data structure."""
    token: str
    token_type: str
    expires_at: datetime
    user_id: str
    role: UserRole


class AuthenticationError(Exception):
    """Base authentication error."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Invalid credentials error."""
    pass


class AccountLockedError(AuthenticationError):
    """Account locked error."""
    pass


class TokenExpiredError(AuthenticationError):
    """Token expired error."""
    pass


class MFARequiredError(AuthenticationError):
    """MFA required error."""
    pass


class AuthenticationService:
    """Comprehensive authentication service."""
    
    def __init__(self, config: Optional[AuthConfig] = None):
        """Initialize authentication service."""
        self.config = config or AuthConfig()
        self.users: Dict[str, User] = {}
        self.sessions: Dict[str, Session] = {}
        self._login_attempts: Dict[str, List[datetime]] = {}
        
    async def user_login(
        self, 
        username: str, 
        password: str,
        mfa_token: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuthToken:
        """
        Authenticate user and create session.
        
        Args:
            username: Username or email
            password: User password
            mfa_token: Multi-factor authentication token
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            AuthToken with JWT token
            
        Raises:
            InvalidCredentialsError: Invalid username/password
            AccountLockedError: Account is locked
            MFARequiredError: MFA token required
        """
        # Check if account is locked
        user = self._get_user_by_username(username)
        if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise AccountLockedError("Account is temporarily locked")
        
        # Check login attempts
        if self._is_rate_limited(username):
            raise AccountLockedError("Too many login attempts. Please try again later.")
        
        # Validate credentials
        if not user or not self._verify_password(password, user.password_hash):
            self._record_failed_login(username)
            raise InvalidCredentialsError("Invalid username or password")
        
        # Check if user is active
        if not user.is_active:
            raise InvalidCredentialsError("Account is disabled")
        
        # Check MFA if enabled
        if user.mfa_enabled:
            if not mfa_token:
                raise MFARequiredError("Multi-factor authentication required")
            if not self._verify_mfa_token(user, mfa_token):
                self._record_failed_login(username)
                raise InvalidCredentialsError("Invalid MFA token")
        
        # Clear failed login attempts
        self._clear_failed_login_attempts(username)
        
        # Update user login info
        user.last_login = datetime.now(timezone.utc)
        user.failed_login_attempts = 0
        user.locked_until = None
        
        # Create session
        session = await self._create_session(user, ip_address, user_agent)
        
        # Generate JWT token
        token = self._generate_jwt_token(user, session.session_id)
        
        return AuthToken(
            token=token,
            token_type="Bearer",
            expires_at=session.expires_at,
            user_id=user.user_id,
            role=user.role
        )
    
    async def user_logout(self, token: str) -> bool:
        """
        Logout user and invalidate session.
        
        Args:
            token: JWT token
            
        Returns:
            True if successful logout
        """
        try:
            payload = self._decode_jwt_token(token)
            session_id = payload.get("session_id")
            
            if session_id and session_id in self.sessions:
                self.sessions[session_id].is_active = False
                del self.sessions[session_id]
                return True
                
        except Exception as e:
            logger.warning(f"Logout error: {e}")
        
        return False
    
    def jwt_token_generation(self, user: User, session_id: str) -> str:
        """
        Generate JWT token for authenticated user.
        
        Args:
            user: User object
            session_id: Session identifier
            
        Returns:
            JWT token string
        """
        return self._generate_jwt_token(user, session_id)
    
    def token_validation(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT token and return payload.
        
        Args:
            token: JWT token string
            
        Returns:
            Token payload dictionary
            
        Raises:
            TokenExpiredError: Token has expired
            AuthenticationError: Invalid token
        """
        try:
            payload = self._decode_jwt_token(token)
            
            # Check if session is still active
            session_id = payload.get("session_id")
            if session_id not in self.sessions or not self.sessions[session_id].is_active:
                raise AuthenticationError("Session is no longer valid")
            
            # Update session last accessed time
            self.sessions[session_id].last_accessed = datetime.now(timezone.utc)
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")
    
    def password_hashing(self, password: str) -> str:
        """
        Hash password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
        """
        return self._hash_password(password)
    
    async def session_management(self, action: str, **kwargs) -> Any:
        """
        Manage user sessions.
        
        Args:
            action: Action to perform (create, get, delete, cleanup)
            **kwargs: Action-specific arguments
            
        Returns:
            Action-specific result
        """
        if action == "create":
            user = kwargs.get("user")
            ip_address = kwargs.get("ip_address")
            user_agent = kwargs.get("user_agent")
            return await self._create_session(user, ip_address, user_agent)
        
        elif action == "get":
            session_id = kwargs.get("session_id")
            return self.sessions.get(session_id)
        
        elif action == "delete":
            session_id = kwargs.get("session_id")
            if session_id in self.sessions:
                del self.sessions[session_id]
                return True
            return False
        
        elif action == "cleanup":
            return await self._cleanup_expired_sessions()
        
        return None
    
    async def multi_factor_authentication(
        self, 
        action: str, 
        user: User, 
        **kwargs
    ) -> Any:
        """
        Handle multi-factor authentication operations.
        
        Args:
            action: MFA action (enable, disable, verify, generate_secret)
            user: User object
            **kwargs: Action-specific arguments
            
        Returns:
            Action-specific result
        """
        if action == "enable":
            secret = self._generate_mfa_secret()
            user.mfa_secret = secret
            user.mfa_enabled = True
            return {
                "secret": secret,
                "qr_code_url": self._generate_mfa_qr_url(user, secret)
            }
        
        elif action == "disable":
            user.mfa_enabled = False
            user.mfa_secret = None
            return True
        
        elif action == "verify":
            token = kwargs.get("token")
            return self._verify_mfa_token(user, token)
        
        elif action == "generate_secret":
            return self._generate_mfa_secret()
        
        return False
    
    def authentication_middleware(self, required_role: Optional[UserRole] = None):
        """
        Create authentication middleware decorator.
        
        Args:
            required_role: Minimum required role for access
            
        Returns:
            Middleware decorator function
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Extract token from request (simplified for testing)
                token = kwargs.get("token") or getattr(args[0] if args else None, "token", None)
                
                if not token:
                    raise AuthenticationError("No authentication token provided")
                
                # Validate token
                payload = self.token_validation(token)
                user_id = payload.get("user_id")
                user_role = UserRole(payload.get("role"))
                
                # Check role permissions
                if required_role and not self._has_permission(user_role, required_role):
                    raise AuthenticationError("Insufficient permissions")
                
                # Add user info to kwargs
                kwargs["current_user_id"] = user_id
                kwargs["current_user_role"] = user_role
                
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator
    
    # User management methods
    async def create_user(
        self, 
        username: str, 
        email: str, 
        password: str, 
        role: UserRole = UserRole.TRADER
    ) -> User:
        """Create a new user."""
        if self._get_user_by_username(username):
            raise ValueError("Username already exists")
        
        if len(password) < self.config.password_min_length:
            raise ValueError(f"Password must be at least {self.config.password_min_length} characters")
        
        user_id = secrets.token_urlsafe(16)
        password_hash = self._hash_password(password)
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role
        )
        
        self.users[username] = user
        return user
    
    def get_user(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.users.get(username)
    
    # Private helper methods
    def _get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username or email."""
        # Check by username first
        if username in self.users:
            return self.users[username]
        
        # Check by email
        for user in self.users.values():
            if user.email == username:
                return user
        
        return None
    
    def _hash_password(self, password: str) -> str:
        """Hash password with bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False
    
    def _generate_jwt_token(self, user: User, session_id: str) -> str:
        """Generate JWT token."""
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role.value,
            "session_id": session_id,
            "iat": now,
            "exp": now + timedelta(hours=self.config.jwt_expiry_hours),
            "iss": "trading-platform"
        }
        
        return jwt.encode(payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm)
    
    def _decode_jwt_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token."""
        return jwt.decode(
            token,
            self.config.jwt_secret,
            algorithms=[self.config.jwt_algorithm],
            options={"verify_exp": True}
        )
    
    async def _create_session(
        self, 
        user: User, 
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Session:
        """Create new user session."""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        
        session = Session(
            session_id=session_id,
            user_id=user.user_id,
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(minutes=self.config.session_timeout_minutes),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.sessions[session_id] = session
        return session
    
    async def _cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        now = datetime.now(timezone.utc)
        expired_sessions = [
            session_id for session_id, session in self.sessions.items()
            if session.expires_at < now
        ]
        
        for session_id in expired_sessions:
            del self.sessions[session_id]
        
        return len(expired_sessions)
    
    def _is_rate_limited(self, username: str) -> bool:
        """Check if user is rate limited."""
        now = datetime.now(timezone.utc)
        attempts = self._login_attempts.get(username, [])
        
        # Remove old attempts (older than lockout duration)
        recent_attempts = [
            attempt for attempt in attempts
            if attempt > now - timedelta(minutes=self.config.lockout_duration_minutes)
        ]
        
        self._login_attempts[username] = recent_attempts
        return len(recent_attempts) >= self.config.max_login_attempts
    
    def _record_failed_login(self, username: str):
        """Record failed login attempt."""
        now = datetime.now(timezone.utc)
        if username not in self._login_attempts:
            self._login_attempts[username] = []
        
        self._login_attempts[username].append(now)
        
        # Lock account if too many failures
        user = self._get_user_by_username(username)
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.config.max_login_attempts:
                user.locked_until = now + timedelta(minutes=self.config.lockout_duration_minutes)
    
    def _clear_failed_login_attempts(self, username: str):
        """Clear failed login attempts."""
        if username in self._login_attempts:
            del self._login_attempts[username]
    
    def _generate_mfa_secret(self) -> str:
        """Generate MFA secret for TOTP."""
        return base64.b32encode(secrets.token_bytes(20)).decode('utf-8')
    
    def _generate_mfa_qr_url(self, user: User, secret: str) -> str:
        """Generate QR code URL for MFA setup."""
        return f"otpauth://totp/{user.email}?secret={secret}&issuer=TradingPlatform"
    
    def _verify_mfa_token(self, user: User, token: str) -> bool:
        """Verify MFA TOTP token."""
        if not user.mfa_secret:
            return False
        
        # Simple TOTP verification (in production, use proper TOTP library)
        current_time = int(time.time() // 30)
        
        for time_offset in [-1, 0, 1]:  # Allow for clock skew
            expected_token = self._generate_totp(user.mfa_secret, current_time + time_offset)
            if token == expected_token:
                return True
        
        return False
    
    def _generate_totp(self, secret: str, time_value: int) -> str:
        """Generate TOTP token for given time value."""
        key = base64.b32decode(secret)
        time_bytes = time_value.to_bytes(8, 'big')
        
        digest = hmac.new(key, time_bytes, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        truncated = digest[offset:offset + 4]
        code = int.from_bytes(truncated, 'big') & 0x7FFFFFFF
        
        return f"{code % 1000000:06d}"
    
    def _has_permission(self, user_role: UserRole, required_role: UserRole) -> bool:
        """Check if user role has required permissions."""
        role_hierarchy = {
            UserRole.VIEWER: 1,
            UserRole.API_USER: 2,
            UserRole.TRADER: 3,
            UserRole.ADMIN: 4
        }
        
        return role_hierarchy.get(user_role, 0) >= role_hierarchy.get(required_role, 0)


# Global instance
authentication_service = AuthenticationService()

# Convenience functions
async def user_login(username: str, password: str, mfa_token: Optional[str] = None, **kwargs) -> AuthToken:
    """Login user and return auth token."""
    return await authentication_service.user_login(username, password, mfa_token, **kwargs)

async def user_logout(token: str) -> bool:
    """Logout user and invalidate session."""
    return await authentication_service.user_logout(token)

def jwt_token_generation(user: User, session_id: str) -> str:
    """Generate JWT token."""
    return authentication_service.jwt_token_generation(user, session_id)

def token_validation(token: str) -> Dict[str, Any]:
    """Validate JWT token."""
    return authentication_service.token_validation(token)

def password_hashing(password: str) -> str:
    """Hash password."""
    return authentication_service.password_hashing(password)

async def session_management(action: str, **kwargs) -> Any:
    """Manage sessions."""
    return await authentication_service.session_management(action, **kwargs)

async def multi_factor_authentication(action: str, user: User, **kwargs) -> Any:
    """Handle MFA operations."""
    return await authentication_service.multi_factor_authentication(action, user, **kwargs)

def authentication_middleware(required_role: Optional[UserRole] = None):
    """Create authentication middleware."""
    return authentication_service.authentication_middleware(required_role)

def get_authentication_service() -> AuthenticationService:
    """Get authentication service instance."""
    return authentication_service