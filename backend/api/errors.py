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
        Handle Pydantic validation errors with FastAPI standard format.
        Returns 422 with detailed validation error information.
        """
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()}
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """
        Handle HTTP exceptions with standardized response format.
        Preserves the original status code but standardizes the response structure.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": "http_error",
                    "detail": exc.detail
                }
            }
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
        
        # Return generic error response
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "type": type(exc).__name__,
                    "detail": str(exc)
                }
            }
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
            formatted_error["input"] = error["input"]
        formatted_errors.append(formatted_error)
    
    return formatted_errors
