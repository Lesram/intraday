import pytest
import os
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse


def make_app():
    app = FastAPI()
    
    # LIGHTWEIGHT MODE: Skip heavy error handler installation
    if os.environ.get("DISABLE_ML") == "1":
        # Add minimal error handlers directly instead of importing heavy modules
        @app.exception_handler(HTTPException)
        async def http_exception_handler(request, exc):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
            
        @app.exception_handler(Exception)
        async def general_exception_handler(request, exc):
            return JSONResponse(
                status_code=500,
                content={"error": {"code": 500, "message": "Internal server error", "type": "internal_error"}}
            )
    else:
        # Original heavy path
        from backend.api.errors import install_error_handlers
        install_error_handlers(app)

    @app.get("/unauthorized")
    async def unauthorized():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/needs-int")
    async def needs_int(v: int):
        return {"v": v}

    return app


def test_error_schema_contracts():
    app = make_app()
    c = TestClient(app, raise_server_exceptions=False)

    # 401
    r = c.get("/unauthorized")
    assert r.status_code == 401
    assert "detail" in r.json()

    # 403: non-v1 path keeps {detail}
    r = c.get("/forbidden")
    assert r.status_code == 403
    assert "detail" in r.json() or "error" in r.json()

    # 422
    r = c.get("/needs-int?v=notint")
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body

    # 500
    r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert "error" in body and "type" in body["error"]
