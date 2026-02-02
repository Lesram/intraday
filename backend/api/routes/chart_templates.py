"""
Chart Template API Endpoints

Provides REST API for managing chart templates (layouts, indicators, styles).

Features:
- Save/load chart configurations
- Template presets
- Share templates between users (future)

Phase 7 - Market Data & Charting
Created: October 18, 2025
"""

from datetime import datetime
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_db_user
from backend.infra.db import get_db_session
from backend.infra.schemas import ChartTemplate, User

logger = logging.getLogger(__name__)

# Main router for protected endpoints (requires auth)
router = APIRouter(prefix="/chart-templates", tags=["chart-templates"])

# Public router for presets (no auth required)
public_router = APIRouter(prefix="/chart-templates", tags=["chart-templates-public"])

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ChartTemplateCreate(BaseModel):
    """Create chart template request"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    layout: dict[str, Any] = Field(..., description="Chart layout configuration")
    indicators: list[dict[str, Any]] = Field(default_factory=list, description="Active indicators")
    drawings: list[dict[str, Any]] = Field(default_factory=list, description="Chart drawings")
    settings: dict[str, Any] = Field(default_factory=dict, description="Chart settings (colors, styles, etc.)")
    is_default: bool = Field(False, description="Set as default template")

class ChartTemplateUpdate(BaseModel):
    """Update chart template request"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    layout: dict[str, Any] | None = None
    indicators: list[dict[str, Any]] | None = None
    drawings: list[dict[str, Any]] | None = None
    settings: dict[str, Any] | None = None
    is_default: bool | None = None

class ChartTemplateResponse(BaseModel):
    """Chart template response"""
    id: int
    user_id: int
    name: str
    description: str | None
    layout: dict[str, Any]
    indicators: list[dict[str, Any]]
    drawings: list[dict[str, Any]]
    settings: dict[str, Any]
    is_default: bool
    is_preset: bool
    created_at: datetime
    updated_at: datetime

# ============================================================================
# PRESET TEMPLATES
# ============================================================================

PRESET_TEMPLATES = [
    {
        "name": "Classic Trading",
        "description": "Traditional trading view with SMA 20/50/200 and volume",
        "layout": {
            "type": "single",
            "height": 600,
            "timeframe": "1D"
        },
        "indicators": [
            {"type": "SMA", "params": {"period": 20}, "color": "#2196F3"},
            {"type": "SMA", "params": {"period": 50}, "color": "#FF9800"},
            {"type": "SMA", "params": {"period": 200}, "color": "#F44336"},
            {"type": "VOLUME_MA", "params": {"period": 20}, "color": "#9C27B0"}
        ],
        "drawings": [],
        "settings": {
            "theme": "dark",
            "gridLines": True,
            "crosshair": True
        }
    },
    {
        "name": "Day Trading",
        "description": "Intraday setup with EMA 9/21, RSI, and MACD",
        "layout": {
            "type": "split",
            "height": 600,
            "timeframe": "5m",
            "panes": [
                {"height": "70%"},
                {"height": "15%", "indicator": "RSI"},
                {"height": "15%", "indicator": "MACD"}
            ]
        },
        "indicators": [
            {"type": "EMA", "params": {"period": 9}, "color": "#00BCD4"},
            {"type": "EMA", "params": {"period": 21}, "color": "#FF5722"},
            {"type": "RSI", "params": {"period": 14}, "color": "#9C27B0", "pane": 1},
            {"type": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}, "pane": 2}
        ],
        "drawings": [],
        "settings": {
            "theme": "dark",
            "gridLines": True,
            "crosshair": True,
            "priceScale": {
                "scaleMargins": {
                    "top": 0.1,
                    "bottom": 0.2
                }
            }
        }
    }
]

# ============================================================================
# ENDPOINTS
# ============================================================================

@public_router.get("/presets", response_model=list[ChartTemplateResponse])
async def get_preset_templates():
    """
    Get preset chart templates (public endpoint - no authentication required)
    """
    presets = []
    for i, preset in enumerate(PRESET_TEMPLATES):
        presets.append({
            "id": -(i + 1),  # Negative IDs for presets
            "user_id": 0,  # System user
            "name": preset["name"],
            "description": preset["description"],
            "layout": preset["layout"],
            "indicators": preset["indicators"],
            "drawings": preset["drawings"],
            "settings": preset["settings"],
            "is_default": False,
            "is_preset": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })

    return presets


@router.get("/", response_model=list[ChartTemplateResponse])
async def get_chart_templates(
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get all chart templates for current user
    """
    result = await db.execute(
        select(ChartTemplate)
        .filter(ChartTemplate.user_id == current_user.id)
        .order_by(ChartTemplate.is_default.desc(), ChartTemplate.created_at.desc())
    )
    templates = result.scalars().all()

    return [template.to_dict() for template in templates]


@router.post("/", response_model=ChartTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_chart_template(
    request: ChartTemplateCreate,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Create a new chart template
    """
    # If setting as default, unset other defaults
    if request.is_default:
        await db.execute(
            update(ChartTemplate)
            .where(
                ChartTemplate.user_id == current_user.id,
                ChartTemplate.is_default
            )
            .values(is_default=False)
        )

    # Create template
    template = ChartTemplate(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        layout=request.layout,
        indicators=request.indicators,
        drawings=request.drawings,
        settings=request.settings,
        is_default=request.is_default,
        is_preset=False
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info(f"User {current_user.id} created chart template '{request.name}'")

    return template.to_dict()


@router.get("/{template_id}", response_model=ChartTemplateResponse)
async def get_chart_template(
    template_id: int,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Get a specific chart template
    """
    result = await db.execute(
        select(ChartTemplate)
        .filter(
            ChartTemplate.id == template_id,
            ChartTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chart template {template_id} not found"
        )

    return template.to_dict()


@router.put("/{template_id}", response_model=ChartTemplateResponse)
async def update_chart_template(
    template_id: int,
    request: ChartTemplateUpdate,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Update a chart template
    """
    result = await db.execute(
        select(ChartTemplate)
        .filter(
            ChartTemplate.id == template_id,
            ChartTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chart template {template_id} not found"
        )

    # If setting as default, unset other defaults
    if request.is_default:
        await db.execute(
            update(ChartTemplate)
            .where(
                ChartTemplate.user_id == current_user.id,
                ChartTemplate.is_default,
                ChartTemplate.id != template_id
            )
            .values(is_default=False)
        )

    # Update fields
    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.layout is not None:
        template.layout = request.layout
    if request.indicators is not None:
        template.indicators = request.indicators
    if request.drawings is not None:
        template.drawings = request.drawings
    if request.settings is not None:
        template.settings = request.settings
    if request.is_default is not None:
        template.is_default = request.is_default

    template.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(template)

    logger.info(f"User {current_user.id} updated chart template {template_id}")

    return template.to_dict()


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chart_template(
    template_id: int,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Delete a chart template
    """
    result = await db.execute(
        select(ChartTemplate)
        .filter(
            ChartTemplate.id == template_id,
            ChartTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chart template {template_id} not found"
        )

    await db.delete(template)
    await db.commit()

    logger.info(f"User {current_user.id} deleted chart template {template_id}")


@router.post("/{template_id}/apply", status_code=status.HTTP_200_OK, response_model=ChartTemplateResponse)
async def apply_chart_template(
    template_id: int,
    current_user: User = Depends(get_current_db_user),
    db: AsyncSession = Depends(get_db_session)
) -> ChartTemplateResponse:
    """
    Apply a chart template (marks it as last used)
    """
    # Support both user templates and presets
    if template_id < 0:
        # It's a preset
        preset_index = -(template_id + 1)
        if preset_index >= len(PRESET_TEMPLATES):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preset template {template_id} not found"
            )
        return PRESET_TEMPLATES[preset_index]

    result = await db.execute(
        select(ChartTemplate)
        .filter(
            ChartTemplate.id == template_id,
            ChartTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chart template {template_id} not found"
        )

    template.last_used_at = datetime.utcnow()
    await db.commit()

    logger.info(f"User {current_user.id} applied chart template {template_id}")

    return template.to_dict()
