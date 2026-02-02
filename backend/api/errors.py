"""
Error handling for FastAPI application.
Provides standardized error response envelopes and business logic errors.
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.utils.logger import StandardEventLogger

event_logger = StandardEventLogger(__name__)


# Standardized Error Classes
class ErrorCodes:
    """Standard error codes used across the application."""

    # Authentication & Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"

    # Business Logic
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    MARKET_CLOSED = "MARKET_CLOSED"
    INVALID_SYMBOL = "INVALID_SYMBOL"

    # System
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


class APIError(Exception):
    """
    Base API error with standardized format.
    Use this for raising errors that should be returned to clients.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        field: str | None = None,
        context: dict[str, Any] | None = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.context = context or {}
        super().__init__(self.message)


class RiskError(APIError):
    """Risk management error with detailed context."""

    def __init__(
        self,
        message: str,
        issues: list[str] = None,
        warnings: list[str] = None,
        risk_score: float = None,
        context: dict[str, Any] | None = None
    ):
        risk_context = context or {}
        risk_context.update({
            "issues": issues or [],
            "warnings": warnings or [],
            "risk_score": risk_score
        })

        super().__init__(
            code=ErrorCodes.RISK_LIMIT_EXCEEDED,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            context=risk_context
        )


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
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": exc.errors()},
            )

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        """Handle APIError instances with standardized format."""
        # Log the API error
        event_logger.api_error_occurred(
            error_code=exc.code,
            error_message=exc.message,
            status_code=exc.status_code,
            path=str(request.url.path),
            user_id=getattr(request.state, 'user_id', None),
            field=exc.field,
            context=exc.context
        )

        return create_api_error_response(exc, request)

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
        M-23 FIX: Catch-all handler for unexpected exceptions.
        Returns 500 with generic error message to avoid exposing internals.
        
        SECURITY: Do NOT return str(exc) to clients as it may contain:
        - Database schema/table names
        - File paths
        - Internal service names
        - Stack traces
        """
        import uuid
        
        # Generate unique error ID for correlation
        error_id = str(uuid.uuid4())[:8]
        
        # Log the full exception for debugging (server-side only)
        logging.exception(
            f"Unhandled exception [{error_id}] in {request.method} {request.url}: {exc}"
        )

        # M-23 FIX: Return generic error message to clients
        # Do NOT expose internal exception details
        return create_error_response(
            error_type="internal_error",
            detail=f"An internal error occurred. Reference ID: {error_id}",
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


def create_api_error_response(error: APIError, request: Request) -> JSONResponse:
    """
    Create standardized error response for APIError instances.

    Args:
        error: APIError instance
        request: FastAPI request object

    Returns:
        JSONResponse with enhanced standardized error format
    """
    from datetime import datetime

    error_content = {
        "detail": error.message,  # Top-level detail for compatibility
        "error": {
            "code": error.code,
            "message": error.message,
            "type": type(error).__name__,
        }
    }

    # Add optional fields if present
    if error.field:
        error_content["error"]["field"] = error.field

    if error.context:
        error_content["error"]["context"] = error.context

    # Add request metadata
    error_content["error"]["timestamp"] = datetime.now().isoformat()
    error_content["error"]["path"] = str(request.url.path)

    return JSONResponse(
        status_code=error.status_code,
        content=error_content
    )


def format_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


# Helper functions for common error creation
def risk_error(
    message: str,
    issues: list[str] = None,
    warnings: list[str] = None,
    risk_score: float = None,
    context: dict[str, Any] = None
) -> RiskError:
    """Create risk management error."""
    return RiskError(
        message=message,
        issues=issues,
        warnings=warnings,
        risk_score=risk_score,
        context=context
    )


def validation_error(field: str, message: str, context: dict[str, Any] = None) -> APIError:
    """Create validation error."""
    return APIError(
        code=ErrorCodes.VALIDATION_ERROR,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        field=field,
        context=context
    )


def business_error(code: str, message: str, context: dict[str, Any] = None) -> APIError:
    """Create business logic error."""
    return APIError(
        code=code,
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        context=context
    )


def not_found_error(resource: str, identifier: str = None) -> APIError:
    """Create not found error."""
    message = f"{resource} not found"
    if identifier:
        message += f": {identifier}"

    return APIError(
        code="NOT_FOUND",
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
        context={"resource": resource, "identifier": identifier}
    )


def internal_error(message: str = "Internal server error", context: dict[str, Any] = None) -> APIError:
    """Create internal server error."""
    return APIError(
        code=ErrorCodes.INTERNAL_ERROR,
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        context=context
    )
