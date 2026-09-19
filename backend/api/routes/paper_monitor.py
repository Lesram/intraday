"""Narrow read-only operational access for the local paper monitor.

The observer role has no trading or administration permission. Existing
admin/trader endpoints retain their original authorization dependencies.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.infra.security import require_roles


def require_paper_configuration() -> None:
    """Never expose this operational surface for a real-money broker."""
    if (
        os.getenv("ALPACA_PAPER", "").lower() != "true"
        or os.getenv("ALPACA_BASE_URL", "").rstrip("/")
        != "https://paper-api.alpaca.markets"
    ):
        raise HTTPException(status_code=403, detail="Paper monitoring requires paper broker configuration")


router = APIRouter(
    prefix="/paper-monitor",
    tags=["Paper monitoring"],
    dependencies=[
        Depends(require_roles("paper_monitor", "admin")),
        Depends(require_paper_configuration),
    ],
)


@router.get("/organism/status")
async def organism_status(request: Request):
    from backend.organism.routes import get_organism_status

    return await get_organism_status(request)


@router.get("/deploy")
async def deployment():
    from backend.api.routes.deploy_health import deploy_health

    return await deploy_health()


@router.get("/data-integrity")
async def accounting(request: Request):
    from backend.api.routes.data_integrity_health import data_integrity

    return await data_integrity(request)


@router.get("/edge")
async def edge():
    from backend.api.routes.strategy_health import edge_health

    return await edge_health()
