from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"]) 

@router.get("/ping")
async def ping():
    return {"auth": "ready"}
