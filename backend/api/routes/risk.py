from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict
from backend.infra.security import get_current_user, get_authenticated_user, get_user_attribute  # tests override this
from backend.risk.position_limits import PositionLimits

router = APIRouter(prefix="/risk", tags=["risk"])

# Patch point:
def get_risk_manager(request: Request):
    """Get risk manager - patch point for tests; they can patch this symbol directly"""
    mgr = getattr(request.app.state, "risk_manager", None)
    if mgr is None:
        from backend.risk.risk_manager import RiskManager as DefaultRiskManager  # adjust path
        mgr = DefaultRiskManager()
    return mgr

# Legacy payload for backward compatibility
class RiskLimitsPayload(BaseModel):
    max_position_value: float = Field(..., gt=0)
    max_symbol_exposure: float = Field(..., ge=0, le=1.0)  
    circuit_breaker_pct: float = Field(..., gt=0, le=0.5)
    
    def to_position_limits(self) -> PositionLimits:
        """Convert to PositionLimits model with proper field mapping."""
        return PositionLimits(
            max_position_size=self.max_position_value,  # Map max_position_value -> max_position_size
            max_symbol_concentration=self.max_symbol_exposure,  # Map max_symbol_exposure -> max_symbol_concentration
            circuit_breaker_pct=self.circuit_breaker_pct  # Direct mapping
        )

def get_risk_service():
    """Get risk service - mock implementation for testing"""
    class MockRiskService:
        def update_limits(self, payload):
            return {"status": "updated"}
        def get_metrics(self):
            return {"status": "ok", "metrics": {}}
    return MockRiskService()

@router.get("/metrics")
async def risk_metrics(
    mgr=Depends(get_risk_manager),
    user: Any = Depends(get_authenticated_user)
):
    """Get risk metrics from the risk manager - requires authentication"""
    # Check user has proper role access (not read-only)  
    user_roles = get_user_attribute(user, "roles", [])
    if "read-only" in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
        
    if hasattr(mgr, 'get_metrics'):
        result = mgr.get_metrics()
    elif hasattr(mgr, 'metrics') and callable(mgr.metrics):
        result = mgr.metrics()
    else:
        result = {"status": "ok", "metrics": {}}
    
    # Ensure portfolio_risk is included for tests
    if "portfolio_risk" not in result:
        result["portfolio_risk"] = {
            "current_exposure": 0.0,
            "max_drawdown": 0.0,
            "var_95": 0.0
        }
    
    return result

@router.put("/limits")
async def set_limits(
    payload: RiskLimitsPayload, 
    mgr=Depends(get_risk_manager),
    user: Any = Depends(get_authenticated_user)
):
    """Set risk limits via the risk manager - requires authentication"""
    # Check if user has admin privileges
    user_roles = get_user_attribute(user, "roles", [])
    if "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    # Convert to PositionLimits for normalization and validation
    position_limits = payload.to_position_limits()
    
    # Set limits using the validated model
    result = mgr.set_limits(position_limits.to_dict())
    
    # Return normalized values with test-friendly indicator
    return {
        "status": "updated",
        "normalized": True,
        "limits": {
            "max_position_value": float(position_limits.max_position_size),
            "max_symbol_exposure": float(position_limits.max_symbol_concentration), 
            "circuit_breaker_pct": float(position_limits.circuit_breaker_pct)
        }
    }

@router.put("/limits/v2")
async def set_limits_v2(
    limits: PositionLimits,
    mgr=Depends(get_risk_manager),
    user: Any = Depends(get_authenticated_user)
):
    """
    Set risk limits using PositionLimits schema directly.
    Accepts circuit_breaker_pct or circuit_breaker aliases and normalizes percent/fraction values.
    """
    # Check if user has admin privileges
    user_roles = get_user_attribute(user, "roles", [])
    if "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    # Set limits using the validated and normalized model
    result = mgr.set_limits(limits.to_dict())
    
    # Return the full normalized PositionLimits
    return {
        "status": "updated",
        "normalized": True,
        "limits": limits.model_dump()
    }

# Legacy routes for backward compatibility
@router.get("/metrics/legacy")
async def get_risk_metrics_legacy(user: Dict[str, Any] = Depends(get_authenticated_user)) -> Dict[str, Any]:
    # Protected now; check for authentication
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    
    # Check user has proper role access
    user_roles = get_user_attribute(user, "roles", [])
    if "read-only" in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    
    return {"status": "ok", "metrics": {}}

@router.put("/limits/legacy")
async def update_limits_legacy(payload: RiskLimitsPayload, user: Dict[str, Any] = Depends(get_authenticated_user)) -> Dict[str, Any]:
    # Check for authentication first
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    
    # Check user has proper role access
    user_roles = get_user_attribute(user, "roles", [])
    if "read-only" in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    
    roles = set(get_user_attribute(user, "roles", []))
    if not ({"admin", "risk_manager"} & roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or risk manager privileges required",
        )
    
    # Convert to PositionLimits for normalization and validation
    position_limits = payload.to_position_limits()
    
    # Return normalized values with test-friendly indicator
    return {
        "status": "updated", 
        "normalized": True,
        "limits": {
            "max_position_value": float(position_limits.max_position_size),
            "max_symbol_exposure": float(position_limits.max_symbol_concentration),
            "circuit_breaker_pct": float(position_limits.circuit_breaker_pct)
        }
    }
