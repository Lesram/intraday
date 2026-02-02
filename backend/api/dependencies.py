"""
API dependencies for Phase 7 watchlists and chart templates
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.schemas import User
from backend.infra.security import AuthenticatedUser, get_current_user


async def get_current_db_user(
    auth_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
) -> User:
    """
    Dependency to get the full User model from database based on authenticated user.

    Args:
        auth_user: Authenticated user from JWT token
        db: Database session

    Returns:
        Full User model from database

    Raises:
        HTTPException: If user not found in database
    """
    if not auth_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    result = await db.execute(
        select(User).filter(User.username == auth_user.username)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user
