from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/risk", tags=["risk"]) 

@router.get("/limits")
async def limits():
    return {"limits": []}
