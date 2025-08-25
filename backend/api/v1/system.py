from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/system", tags=["system"]) 

@router.get("/status")
async def status():
    return {"status": "ok"}
