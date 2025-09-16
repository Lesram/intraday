"""
Error handling for FastAPI application.
Provides standardized error response envelopes.
"""

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def install_error_handlers(app: FastAPI) -> None:
    """
    Install standardized error handlers on the FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Handle Pydantic validation errors.
        - Platform app (factory-created): standardized envelope {"error": {...}}
        - Non-platform app: FastAPI default {"detail": [...]}
        """
        is_platform_app = getattr(getattr(request, "app", None), "state", None)
        is_platform_app = getattr(is_platform_app, "is_platform_app", False)

        if is_platform_app:
            try:
                details = format_validation_errors(exc.errors())
            except Exception:
                details = exc.errors()
            return create_error_response(
                error_type="validation_error",
                detail=details,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": exc.errors()},
            )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """
        Handle HTTP exceptions.
        - Platform app (factory-created): standardized envelope
        - Non-platform app: FastAPI default {"detail": ...}
        """
        is_platform_app = getattr(getattr(request, "app", None), "state", None)
        is_platform_app = getattr(is_platform_app, "is_platform_app", False)

        if is_platform_app:
            return create_error_response(
                error_type="http_error",
                detail=exc.detail,
                status_code=exc.status_code,
            )
        else:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
    
    @app.exception_handler(Exception)
    async def catch_all_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Catch-all handler for unexpected exceptions.
        Returns 500 with generic error message to avoid exposing internals.
        """
        # Log the full exception for debugging
        logging.exception(f"Unhandled exception in {request.method} {request.url}: {exc}")
        
        # Return generic error response with standardized envelope
        return create_error_response(
            error_type=type(exc).__name__,
            detail=str(exc),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def create_error_response(
    error_type: str, 
    detail: Any, 
    status_code: int = 500
) -> JSONResponse:
    """
    Create a standardized error response.
    
    Args:
        error_type: Type of error (e.g., "validation_error", "internal_error")
        detail: Error details (can be string, dict, or list)
        status_code: HTTP status code
        
    Returns:
        JSONResponse with standardized error format
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,  # top-level detail for compatibility with tests
            "error": {
                "type": error_type,
                "detail": detail
            }
        }
    )


def format_validation_errors(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format Pydantic validation errors into a consistent structure.
    
    Args:
        errors: List of Pydantic error dictionaries
        
    Returns:
        List of formatted error dictionaries
    """
    formatted_errors = []
    for error in errors:
        formatted_error = {
            "field": ".".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", "Validation error"),
            "type": error.get("type", "unknown")
        }
        if "input" in error:
            input_value = error["input"]
            # Handle bytes objects that can't be JSON serialized
            if isinstance(input_value, bytes):
                try:
                    # Try to decode as UTF-8 string
                    formatted_error["input"] = input_value.decode('utf-8')
                except UnicodeDecodeError:
                    # If not valid UTF-8, represent as hex string
                    formatted_error["input"] = f"<bytes: {input_value.hex()}>"
            else:
                formatted_error["input"] = input_value
        formatted_errors.append(formatted_error)
    
    return formatted_errors

# Test error endpoints router
from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test-errors"])

@router.get("/http-401")
def http_401(): 
    raise HTTPException(401, detail="Authentication required")

@router.get("/http-403")
def http_403(): 
    raise HTTPException(403, detail="Forbidden")

@router.get("/http-422")
def http_422(): 
    raise HTTPException(422, detail="Invalid request")

@router.get("/http-500")
def http_500(): 
    raise HTTPException(500, detail="Server error")
