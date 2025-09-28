"""
Comprehensive test suite for Module 3: backend/api/errors.py
Targeting 100% code coverage with complete line-by-line testing.

This test suite covers:
- Error handler installation (install_error_handlers)
- Validation error handler (validation_error_handler)
- HTTP exception handler (http_exception_handler) 
- Catch-all exception handler (catch_all_handler)
- Error response creation (create_error_response)
- Validation error formatting (format_validation_errors)
- Test error endpoints (http_401, http_403, http_422, http_500, router)
"""

import unittest
import asyncio
import logging
from unittest.mock import MagicMock, patch, Mock, AsyncMock, call
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

# Import module under test
from backend.api.errors import (
    install_error_handlers,
    create_error_response, 
    format_validation_errors,
    router,
    http_401,
    http_403, 
    http_422,
    http_500
)


class TestModule3ErrorHandlerInstallation(unittest.TestCase):
    """Test error handler installation functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = MagicMock(spec=FastAPI)

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_install_error_handlers_basic_functionality(self):
        """Test basic error handler installation on FastAPI app"""
        # Call the function under test
        install_error_handlers(self.mock_app)
        
        # Verify that exception_handler was called 3 times (for 3 different exception types)
        self.assertEqual(self.mock_app.exception_handler.call_count, 3)
        
        # Verify the function returns None (no explicit return)
        result = install_error_handlers(self.mock_app)
        self.assertIsNone(result)

    def test_install_error_handlers_decorator_registration(self):
        """Test that exception handlers are registered as decorators"""
        # Mock the decorator calls
        validation_decorator = MagicMock()
        http_decorator = MagicMock()
        catch_all_decorator = MagicMock()
        
        self.mock_app.exception_handler.side_effect = [
            validation_decorator,
            http_decorator, 
            catch_all_decorator
        ]
        
        # Call the function
        install_error_handlers(self.mock_app)
        
        # Verify exception types were registered
        calls = self.mock_app.exception_handler.call_args_list
        self.assertEqual(len(calls), 3)
        
        # Check first call is for RequestValidationError
        self.assertEqual(calls[0][0][0], RequestValidationError)
        # Check second call is for HTTPException
        self.assertEqual(calls[1][0][0], HTTPException)
        # Check third call is for Exception
        self.assertEqual(calls[2][0][0], Exception)


class TestModule3ValidationErrorHandler(unittest.TestCase):
    """Test validation error handler functionality"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = MagicMock(spec=FastAPI)
        
        # Create a real FastAPI app to get actual handler
        self.real_app = FastAPI()
        install_error_handlers(self.real_app)
        
        # Extract the validation error handler from the real app
        self.validation_handler = None
        for exc_type, handler in self.real_app.exception_handlers.items():
            if exc_type == RequestValidationError:
                self.validation_handler = handler
                break

    def tearDown(self):
        """Clean up after each test"""
        pass

    @patch('backend.api.errors.format_validation_errors')
    @patch('backend.api.errors.create_error_response')
    def test_validation_error_handler_platform_app(self, mock_create_response, mock_format_errors):
        """Test validation error handler for platform app (lines 32-42)"""
        # Set up mock request with platform app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.is_platform_app = True
        
        # Set up mock validation error
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [{"field": "test", "message": "error"}]
        
        # Set up mock responses
        mock_format_errors.return_value = [{"formatted": "error"}]
        mock_response = MagicMock(spec=JSONResponse)
        mock_create_response.return_value = mock_response
        
        # Call the handler
        result = asyncio.run(self.validation_handler(mock_request, mock_exc))
        
        # Verify format_validation_errors was called
        mock_format_errors.assert_called_once_with([{"field": "test", "message": "error"}])
        
        # Verify create_error_response was called with correct parameters
        mock_create_response.assert_called_once_with(
            error_type="validation_error",
            detail=[{"formatted": "error"}],
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
        
        # Verify the response is returned
        self.assertEqual(result, mock_response)

    def test_validation_error_handler_non_platform_app(self):
        """Test validation error handler for non-platform app (lines 43-46)"""
        # Set up mock request with non-platform app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.is_platform_app = False
        
        # Set up mock validation error
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [{"field": "test", "message": "error"}]
        
        # Call the handler
        result = asyncio.run(self.validation_handler(mock_request, mock_exc))
        
        # Verify response is JSONResponse with FastAPI default format
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        # Extract body content
        import json
        content = json.loads(result.body.decode())
        self.assertEqual(content["detail"], [{"field": "test", "message": "error"}])

    def test_validation_error_handler_no_app_state(self):
        """Test validation error handler when app has no state (line 32)"""
        # Set up mock request with app that has no state
        mock_request = MagicMock(spec=Request)
        mock_request.app.state = None
        
        # Set up mock validation error
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [{"field": "test", "message": "error"}]
        
        # Call the handler
        result = asyncio.run(self.validation_handler(mock_request, mock_exc))
        
        # Should default to non-platform behavior since state is None
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_validation_error_handler_no_app(self):
        """Test validation error handler when request has no app"""
        # Set up mock request with no app
        mock_request = MagicMock(spec=Request)
        mock_request.app = None
        
        # Set up mock validation error
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = [{"field": "test", "message": "error"}]
        
        # Call the handler
        result = asyncio.run(self.validation_handler(mock_request, mock_exc))
        
        # Should default to non-platform behavior since app is None
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @patch('backend.api.errors.format_validation_errors')
    @patch('backend.api.errors.create_error_response')
    def test_validation_error_handler_format_exception(self, mock_create_response, mock_format_errors):
        """Test validation error handler when format_validation_errors raises exception (lines 35-36)"""
        # Set up mock request with platform app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.is_platform_app = True
        
        # Set up mock validation error
        mock_exc = MagicMock(spec=RequestValidationError)
        error_list = [{"field": "test", "message": "error"}]
        mock_exc.errors.return_value = error_list
        
        # Make format_validation_errors raise an exception
        mock_format_errors.side_effect = Exception("Format error")
        
        # Set up mock response
        mock_response = MagicMock(spec=JSONResponse)
        mock_create_response.return_value = mock_response
        
        # Call the handler
        result = asyncio.run(self.validation_handler(mock_request, mock_exc))
        
        # Verify format_validation_errors was called and failed
        mock_format_errors.assert_called_once_with(error_list)
        
        # Verify create_error_response was called with raw errors (fallback)
        mock_create_response.assert_called_once_with(
            error_type="validation_error",
            detail=error_list,  # Raw errors used as fallback
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
        
        self.assertEqual(result, mock_response)


class TestModule3HTTPExceptionHandler(unittest.TestCase):
    """Test HTTP exception handler functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a real FastAPI app to get actual handler
        self.real_app = FastAPI()
        install_error_handlers(self.real_app)
        
        # Extract the HTTP exception handler from the real app
        self.http_handler = None
        for exc_type, handler in self.real_app.exception_handlers.items():
            if exc_type == HTTPException:
                self.http_handler = handler
                break

    def tearDown(self):
        """Clean up after each test"""
        pass

    @patch('backend.api.errors.create_error_response')
    def test_http_exception_handler_platform_app(self, mock_create_response):
        """Test HTTP exception handler for platform app (lines 60-65)"""
        # Set up mock request with platform app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.is_platform_app = True
        
        # Set up mock HTTP exception
        mock_exc = HTTPException(status_code=404, detail="Not found")
        
        # Set up mock response
        mock_response = MagicMock(spec=JSONResponse)
        mock_create_response.return_value = mock_response
        
        # Call the handler
        result = asyncio.run(self.http_handler(mock_request, mock_exc))
        
        # Verify create_error_response was called with correct parameters
        mock_create_response.assert_called_once_with(
            error_type="http_error",
            detail="Not found",
            status_code=404,
        )
        
        self.assertEqual(result, mock_response)

    def test_http_exception_handler_non_platform_app(self):
        """Test HTTP exception handler for non-platform app (lines 66-70)"""
        # Set up mock request with non-platform app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.is_platform_app = False
        
        # Set up mock HTTP exception
        mock_exc = HTTPException(status_code=403, detail="Forbidden")
        
        # Call the handler
        result = asyncio.run(self.http_handler(mock_request, mock_exc))
        
        # Verify response is JSONResponse with FastAPI default format
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 403)
        # Extract body content
        import json
        content = json.loads(result.body.decode())
        self.assertEqual(content["detail"], "Forbidden")

    def test_http_exception_handler_no_state_attribute(self):
        """Test HTTP exception handler when state has no is_platform_app attribute"""
        # Set up mock request with state that lacks is_platform_app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state = MagicMock()
        del mock_request.app.state.is_platform_app  # Remove the attribute
        
        # Set up mock HTTP exception
        mock_exc = HTTPException(status_code=500, detail="Server error")
        
        # Call the handler
        result = asyncio.run(self.http_handler(mock_request, mock_exc))
        
        # Should default to non-platform behavior
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 500)


class TestModule3CatchAllHandler(unittest.TestCase):
    """Test catch-all exception handler functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a real FastAPI app to get actual handler
        self.real_app = FastAPI()
        install_error_handlers(self.real_app)
        
        # Extract the catch-all handler from the real app
        self.catch_all_handler = None
        for exc_type, handler in self.real_app.exception_handlers.items():
            if exc_type == Exception:
                self.catch_all_handler = handler
                break

    def tearDown(self):
        """Clean up after each test"""
        pass

    @patch('backend.api.errors.create_error_response')
    @patch('backend.api.errors.logging.exception')
    def test_catch_all_handler_basic_exception(self, mock_logging, mock_create_response):
        """Test catch-all handler with basic exception (lines 79-87)"""
        # Set up mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "GET"
        mock_request.url = "http://test.com/api/test"
        
        # Set up mock exception
        test_exception = ValueError("Test error")
        
        # Set up mock response
        mock_response = MagicMock(spec=JSONResponse)
        mock_create_response.return_value = mock_response
        
        # Call the handler
        result = asyncio.run(self.catch_all_handler(mock_request, test_exception))
        
        # Verify logging.exception was called with correct message
        mock_logging.assert_called_once_with(
            f"Unhandled exception in GET http://test.com/api/test: Test error"
        )
        
        # Verify create_error_response was called with correct parameters
        mock_create_response.assert_called_once_with(
            error_type="ValueError",
            detail="Test error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        
        self.assertEqual(result, mock_response)

    @patch('backend.api.errors.create_error_response')
    @patch('backend.api.errors.logging.exception')
    def test_catch_all_handler_different_exception_types(self, mock_logging, mock_create_response):
        """Test catch-all handler with different exception types"""
        # Set up mock request
        mock_request = MagicMock(spec=Request)
        mock_request.method = "POST"
        mock_request.url = "http://test.com/api/data"
        
        # Test with RuntimeError
        runtime_error = RuntimeError("Runtime issue")
        mock_response = MagicMock(spec=JSONResponse)
        mock_create_response.return_value = mock_response
        
        result = asyncio.run(self.catch_all_handler(mock_request, runtime_error))
        
        # Verify correct exception type name is used
        mock_create_response.assert_called_with(
            error_type="RuntimeError",
            detail="Runtime issue",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class TestModule3ErrorResponseCreation(unittest.TestCase):
    """Test error response creation functionality"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_create_error_response_basic_parameters(self):
        """Test create_error_response with basic parameters (lines 92-108)"""
        # Test with string detail
        response = create_error_response(
            error_type="test_error",
            detail="Test message",
            status_code=400
        )
        
        # Verify response type and status code
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 400)
        
        # Verify response content structure
        import json
        content = json.loads(response.body.decode())
        expected_content = {
            "detail": "Test message",
            "error": {
                "type": "test_error",
                "detail": "Test message"
            }
        }
        self.assertEqual(content, expected_content)

    def test_create_error_response_default_status_code(self):
        """Test create_error_response with default status code"""
        response = create_error_response(
            error_type="internal_error",
            detail="Internal issue"
        )
        
        # Verify default status code is 500
        self.assertEqual(response.status_code, 500)

    def test_create_error_response_dict_detail(self):
        """Test create_error_response with dict detail"""
        detail_dict = {"field": "username", "issue": "required"}
        response = create_error_response(
            error_type="validation_error",
            detail=detail_dict,
            status_code=422
        )
        
        # Verify response content with dict detail
        import json
        content = json.loads(response.body.decode())
        expected_content = {
            "detail": detail_dict,
            "error": {
                "type": "validation_error",
                "detail": detail_dict
            }
        }
        self.assertEqual(content, expected_content)

    def test_create_error_response_list_detail(self):
        """Test create_error_response with list detail"""
        detail_list = [{"error": "first"}, {"error": "second"}]
        response = create_error_response(
            error_type="multiple_errors",
            detail=detail_list,
            status_code=422
        )
        
        # Verify response content with list detail
        import json
        content = json.loads(response.body.decode())
        expected_content = {
            "detail": detail_list,
            "error": {
                "type": "multiple_errors",
                "detail": detail_list
            }
        }
        self.assertEqual(content, expected_content)


class TestModule3ValidationErrorFormatting(unittest.TestCase):
    """Test validation error formatting functionality"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_format_validation_errors_basic_error(self):
        """Test format_validation_errors with basic error (lines 122-138)"""
        errors = [
            {
                "loc": ["field1"],
                "msg": "Field is required",
                "type": "value_error.missing",
                "input": "test_input"
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "field1",
                "message": "Field is required",
                "type": "value_error.missing",
                "input": "test_input"
            }
        ]
        
        self.assertEqual(result, expected)

    def test_format_validation_errors_nested_field(self):
        """Test format_validation_errors with nested field location"""
        errors = [
            {
                "loc": ["user", "profile", "name"],
                "msg": "String too short",
                "type": "value_error.any_str.min_length",
                "input": "ab"
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "user.profile.name",
                "message": "String too short", 
                "type": "value_error.any_str.min_length",
                "input": "ab"
            }
        ]
        
        self.assertEqual(result, expected)

    def test_format_validation_errors_missing_fields(self):
        """Test format_validation_errors with missing optional fields"""
        errors = [
            {
                # Missing loc, msg, type, input
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "",  # Empty string from empty loc
                "message": "Validation error",  # Default message
                "type": "unknown",  # Default type
                # No input field since not present
            }
        ]
        
        self.assertEqual(result, expected)

    def test_format_validation_errors_bytes_input_utf8(self):
        """Test format_validation_errors with bytes input that decodes as UTF-8 (lines 139-143)"""
        errors = [
            {
                "loc": ["data"],
                "msg": "Invalid format",
                "type": "value_error",
                "input": b"hello world"  # Valid UTF-8 bytes
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "data",
                "message": "Invalid format",
                "type": "value_error",
                "input": "hello world"  # Decoded as string
            }
        ]
        
        self.assertEqual(result, expected)

    def test_format_validation_errors_bytes_input_invalid_utf8(self):
        """Test format_validation_errors with bytes input that fails UTF-8 decode (lines 144-146)"""
        errors = [
            {
                "loc": ["binary_data"],
                "msg": "Invalid binary",
                "type": "value_error",
                "input": b"\xff\xfe\x00\x01"  # Invalid UTF-8 bytes
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "binary_data",
                "message": "Invalid binary",
                "type": "value_error",
                "input": "<bytes: fffe0001>"  # Correct hex representation
            }
        ]
        
        self.assertEqual(result, expected)

    def test_format_validation_errors_no_input_field(self):
        """Test format_validation_errors when input field is not present"""
        errors = [
            {
                "loc": ["field1"],
                "msg": "Required field",
                "type": "value_error.missing"
                # No input field
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "field1",
                "message": "Required field",
                "type": "value_error.missing"
                # No input field in result
            }
        ]
        
        self.assertEqual(result, expected)

    def test_format_validation_errors_multiple_errors(self):
        """Test format_validation_errors with multiple errors"""
        errors = [
            {
                "loc": ["field1"],
                "msg": "Required",
                "type": "value_error.missing"
            },
            {
                "loc": ["field2"],
                "msg": "Too long",
                "type": "value_error.any_str.max_length",
                "input": "very long string"
            },
            {
                "loc": ["field3"],
                "msg": "Invalid bytes",
                "type": "value_error",
                "input": b"\x80\x81"  # Invalid UTF-8
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "field1",
                "message": "Required",
                "type": "value_error.missing"
            },
            {
                "field": "field2",
                "message": "Too long",
                "type": "value_error.any_str.max_length",
                "input": "very long string"
            },
            {
                "field": "field3",
                "message": "Invalid bytes",
                "type": "value_error",
                "input": "<bytes: 8081>"
            }
        ]
        
        self.assertEqual(result, expected)


class TestModule3ErrorRouterEndpoints(unittest.TestCase):
    """Test error router and endpoints functionality"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_router_configuration(self):
        """Test router prefix and tags configuration (lines 150-152)"""
        self.assertEqual(router.prefix, "/test")
        self.assertEqual(router.tags, ["test-errors"])

    def test_router_routes_registered(self):
        """Test that all error endpoints are registered on router"""
        # Get all route paths from router
        route_paths = [route.path for route in router.routes]
        
        # Expected paths with router prefix
        expected_paths = ["/test/http-401", "/test/http-403", "/test/http-422", "/test/http-500"]
        
        for expected_path in expected_paths:
            self.assertIn(expected_path, route_paths)

    def test_http_401_endpoint(self):
        """Test http_401 endpoint function (lines 154-155)"""
        with self.assertRaises(HTTPException) as context:
            http_401()
        
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, "Authentication required")

    def test_http_403_endpoint(self):
        """Test http_403 endpoint function (lines 157-158)"""
        with self.assertRaises(HTTPException) as context:
            http_403()
        
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.detail, "Forbidden")

    def test_http_422_endpoint(self):
        """Test http_422 endpoint function (lines 160-161)"""
        with self.assertRaises(HTTPException) as context:
            http_422()
        
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(context.exception.detail, "Invalid request")

    def test_http_500_endpoint(self):
        """Test http_500 endpoint function (lines 163-164)"""
        with self.assertRaises(HTTPException) as context:
            http_500()
        
        self.assertEqual(context.exception.status_code, 500)
        self.assertEqual(context.exception.detail, "Server error")


class TestModule3EdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_validation_error_handler_empty_errors_list(self):
        """Test validation error handler with empty errors list"""
        # Create a real FastAPI app to get actual handler
        real_app = FastAPI()
        install_error_handlers(real_app)
        
        # Extract the validation error handler
        validation_handler = None
        for exc_type, handler in real_app.exception_handlers.items():
            if exc_type == RequestValidationError:
                validation_handler = handler
                break
        
        # Set up mock request with platform app
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.is_platform_app = True
        
        # Set up mock validation error with empty errors
        mock_exc = MagicMock(spec=RequestValidationError)
        mock_exc.errors.return_value = []
        
        # Call the handler
        result = asyncio.run(validation_handler(mock_request, mock_exc))
        
        # Should handle empty errors gracefully
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_format_validation_errors_empty_list(self):
        """Test format_validation_errors with empty error list"""
        result = format_validation_errors([])
        self.assertEqual(result, [])

    def test_format_validation_errors_numeric_loc_elements(self):
        """Test format_validation_errors with numeric location elements"""
        errors = [
            {
                "loc": ["items", 0, "name"],
                "msg": "Required field",
                "type": "value_error.missing"
            }
        ]
        
        result = format_validation_errors(errors)
        
        expected = [
            {
                "field": "items.0.name",
                "message": "Required field",
                "type": "value_error.missing"
            }
        ]
        
        self.assertEqual(result, expected)

    def test_create_error_response_none_detail(self):
        """Test create_error_response with None detail"""
        response = create_error_response(
            error_type="null_error",
            detail=None,
            status_code=400
        )
        
        # Should handle None detail
        import json
        content = json.loads(response.body.decode())
        expected_content = {
            "detail": None,
            "error": {
                "type": "null_error",
                "detail": None
            }
        }
        self.assertEqual(content, expected_content)


class TestModule3IntegrationScenarios(unittest.TestCase):
    """Test integration scenarios and complete workflows"""

    def setUp(self):
        """Set up test fixtures"""
        pass

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_complete_error_handling_workflow(self):
        """Test complete error handling workflow from installation to response"""
        # Create FastAPI app and install handlers
        app = FastAPI()
        app.state.is_platform_app = True
        install_error_handlers(app)
        
        # Verify handlers are installed
        self.assertTrue(len(app.exception_handlers) >= 3)
        
        # Verify specific exception types are handled
        exception_types = list(app.exception_handlers.keys())
        self.assertIn(RequestValidationError, exception_types)
        self.assertIn(HTTPException, exception_types)
        self.assertIn(Exception, exception_types)

    def test_error_response_json_serialization(self):
        """Test that error responses are properly JSON serializable"""
        # Test with complex nested data
        complex_detail = {
            "errors": [
                {"field": "user.email", "issue": "invalid"},
                {"field": "user.age", "issue": "too_young"}
            ],
            "metadata": {"timestamp": "2023-01-01", "request_id": "123"}
        }
        
        response = create_error_response(
            error_type="complex_validation_error",
            detail=complex_detail,
            status_code=422
        )
        
        # Should be able to parse the JSON response
        import json
        content = json.loads(response.body.decode())
        
        # Verify structure is preserved
        self.assertEqual(content["detail"], complex_detail)
        self.assertEqual(content["error"]["detail"], complex_detail)
        self.assertEqual(content["error"]["type"], "complex_validation_error")


if __name__ == '__main__':
    unittest.main()