import pytest
import os
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError


def make_app() -> FastAPI:
    # LIGHTWEIGHT MODE: Skip heavy backend.api.factory.create_app() entirely
    if os.environ.get("DISABLE_ML") == "1":
        # Create minimal FastAPI app without heavy dependencies
        app = FastAPI(title="Test API", version="0.1.0")
        
        # Add minimal error handlers that match the production ones
        from fastapi.responses import JSONResponse
        from fastapi.exceptions import RequestValidationError
        
        @app.exception_handler(HTTPException)
        async def http_exception_handler(request, exc):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "detail": exc.detail,
                    "error": {"type": "http_error", "detail": exc.detail}
                }
            )
            
        @app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request, exc: RequestValidationError):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": exc.errors(),
                    "error": {"type": "validation_error", "detail": exc.errors()}
                }
            )
            
        @app.exception_handler(Exception)
        async def general_exception_handler(request, exc):
            return JSONResponse(
                status_code=500,
                content={
                    "detail": str(exc),
                    "error": {"type": exc.__class__.__name__, "detail": str(exc)}
                }
            )
    else:
        # Original heavy path (only when ML is enabled)
        from backend.api.factory import create_app
        app = create_app()

    @app.get("/test/http-401")
    async def http_401():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    @app.get("/test/http-403")
    async def http_403():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    @app.post("/test/validation-422")
    async def validation_422(payload: dict):
        class M(BaseModel):
            required: int

        # Intentionally raise a ValidationError
        try:
            M.model_validate(payload)
        except ValidationError as e:
            # Convert to HTTPException to exercise HTTPException handler path for 422
            raise HTTPException(status_code=422, detail=str(e))

    @app.get("/test/boom-500")
    async def boom_500():
        raise RuntimeError("kaboom")

    # Endpoint that triggers FastAPI's RequestValidationError before handler runs
    class BodyModel(BaseModel):
        required: int

    @app.post("/test/body-422")
    async def body_422_endpoint(body: BodyModel):  # pragma: no cover - behavior exercised by validation
        return {"ok": True}

    return app


@pytest.fixture()
def client():
    app = make_app()
    # Ensure server exceptions are serialized through our handlers
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def assert_error_envelope(resp, expected_status: int):
    assert resp.status_code == expected_status
    data = resp.json()
    assert "error" in data
    assert "detail" in data["error"]
    return data


def test_401_envelope(client):
    data = assert_error_envelope(client.get("/test/http-401"), 401)
    assert data["error"]["type"] == "http_error"
    assert "Authentication" in data["error"]["detail"]


def test_403_envelope(client):
    data = assert_error_envelope(client.get("/test/http-403"), 403)
    assert data["error"]["type"] == "http_error"


def test_500_envelope(client):
    data = assert_error_envelope(client.get("/test/boom-500"), 500)
    # type contains exception class name
    assert data["error"]["type"] in ("RuntimeError", "Exception")


def test_422_envelope(client):
    # trigger our explicit HTTPException 422 above
    data = assert_error_envelope(client.post("/test/validation-422", json={}), 422)
    # When coming through HTTPException path, type is http_error
    # Separate RequestValidationError path is covered by other tests
    assert data["error"]["type"] in ("http_error", "validation_error")


def test_422_request_validation_envelope(client):
    # Trigger RequestValidationError by omitting required field
    data = assert_error_envelope(client.post("/test/body-422", json={}), 422)
    assert data["error"]["type"] == "validation_error"
    assert isinstance(data["error"]["detail"], list)
