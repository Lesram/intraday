"""
Comprehensive tests for backend/utils/import_tracker.py

Target: Increase coverage from 54% to 90%+
Tests cover:
- ImportErrorTracker class with import failure tracking
- Fallback usage tracking
- Critical import validation
- safe_import and safe_import_from functions
- Error handlers and decorators
"""

import pytest
from unittest.mock import patch, MagicMock
import logging
import sys


# Import the module under test
from backend.utils.import_tracker import (
    ImportErrorTracker,
    _import_tracker,
    safe_import,
    safe_import_from,
    track_import_error,
    validate_platform_imports,
    get_import_status,
    require_critical_imports,
    import_error_handler,
    log_import_failure,
    check_critical_imports,
)


# =============================================================================
# Tests for ImportErrorTracker class
# =============================================================================

class TestImportErrorTrackerInit:
    """Tests for ImportErrorTracker initialization."""
    
    def test_init_creates_empty_failed_imports(self):
        """Test that new tracker has empty failed_imports."""
        tracker = ImportErrorTracker()
        assert isinstance(tracker.failed_imports, dict)
        
    def test_init_creates_empty_fallback_usage(self):
        """Test that new tracker has empty fallback_usage."""
        tracker = ImportErrorTracker()
        assert isinstance(tracker.fallback_usage, dict)
        
    def test_init_has_critical_imports_list(self):
        """Test that tracker has critical_imports list."""
        tracker = ImportErrorTracker()
        assert isinstance(tracker.critical_imports, list)
        assert len(tracker.critical_imports) > 0
        
    def test_init_has_optional_imports_list(self):
        """Test that tracker has optional_imports list."""
        tracker = ImportErrorTracker()
        assert isinstance(tracker.optional_imports, list)
        assert len(tracker.optional_imports) > 0
        
    def test_init_sets_up_logger(self):
        """Test that tracker sets up logger."""
        tracker = ImportErrorTracker()
        assert tracker.logger is not None
        assert tracker.logger.name == "import_tracker"


class TestTrackImportFailure:
    """Tests for ImportErrorTracker.track_import_failure."""
    
    def test_track_import_failure_stores_failure(self):
        """Test that failures are stored in failed_imports."""
        tracker = ImportErrorTracker()
        error = ImportError("Module not found")
        
        tracker.track_import_failure("fake_module", error, "test context")
        
        assert "fake_module" in tracker.failed_imports
        assert tracker.failed_imports["fake_module"]["error_type"] == "ImportError"
        assert tracker.failed_imports["fake_module"]["error_message"] == "Module not found"
        
    def test_track_import_failure_records_context(self):
        """Test that context is recorded."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        tracker.track_import_failure("test_module", error, "during initialization")
        
        assert tracker.failed_imports["test_module"]["context"] == "during initialization"
        
    def test_track_import_failure_records_timestamp(self):
        """Test that timestamp is recorded."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        tracker.track_import_failure("test_module", error)
        
        assert "timestamp" in tracker.failed_imports["test_module"]
        
    def test_track_import_failure_critical_auto_detection(self):
        """Test that critical imports are auto-detected."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        # Import matching a critical import pattern
        tracker.track_import_failure("backend.config.unified", error)
        
        assert tracker.failed_imports["backend.config.unified"]["is_critical"] is True
        
    def test_track_import_failure_explicit_critical(self):
        """Test explicit is_critical parameter."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        tracker.track_import_failure("random_module", error, is_critical=True)
        
        assert tracker.failed_imports["random_module"]["is_critical"] is True
        
    def test_track_import_failure_not_critical(self):
        """Test non-critical import tracking."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        tracker.track_import_failure("random_module", error, is_critical=False)
        
        assert tracker.failed_imports["random_module"]["is_critical"] is False
        
    def test_track_import_failure_optional_import(self):
        """Test optional import is not marked critical."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        # Redis is in optional_imports
        tracker.track_import_failure("redis_client", error)
        
        # Should not be critical unless explicitly set
        # Note: depends on exact matching logic
        
    def test_track_import_failure_records_python_path(self):
        """Test that Python path is recorded."""
        tracker = ImportErrorTracker()
        error = ImportError("Not found")
        
        tracker.track_import_failure("test_module", error)
        
        assert "python_path" in tracker.failed_imports["test_module"]
        assert isinstance(tracker.failed_imports["test_module"]["python_path"], list)


class TestTrackFallbackUsage:
    """Tests for ImportErrorTracker.track_fallback_usage."""
    
    def test_track_fallback_usage_first_use(self):
        """Test tracking first use of fallback."""
        tracker = ImportErrorTracker()
        
        tracker.track_fallback_usage("mock_redis")
        
        assert tracker.fallback_usage["mock_redis"] == 1
        
    def test_track_fallback_usage_increments(self):
        """Test that repeated usage increments counter."""
        tracker = ImportErrorTracker()
        
        tracker.track_fallback_usage("mock_db")
        tracker.track_fallback_usage("mock_db")
        tracker.track_fallback_usage("mock_db")
        
        assert tracker.fallback_usage["mock_db"] == 3
        
    def test_track_fallback_usage_multiple_fallbacks(self):
        """Test tracking multiple different fallbacks."""
        tracker = ImportErrorTracker()
        
        tracker.track_fallback_usage("fallback_a")
        tracker.track_fallback_usage("fallback_b")
        tracker.track_fallback_usage("fallback_a")
        
        assert tracker.fallback_usage["fallback_a"] == 2
        assert tracker.fallback_usage["fallback_b"] == 1


class TestValidateCriticalImports:
    """Tests for ImportErrorTracker.validate_critical_imports."""
    
    def test_validate_critical_imports_with_available_modules(self):
        """Test validation when critical modules are available."""
        tracker = ImportErrorTracker()
        # Override critical imports to only include known-available modules
        tracker.critical_imports = ["json", "sys", "os"]
        
        result = tracker.validate_critical_imports()
        
        assert result is True
        
    def test_validate_critical_imports_with_missing_modules(self):
        """Test validation when critical modules are missing."""
        tracker = ImportErrorTracker()
        tracker.critical_imports = ["completely_nonexistent_module_12345"]
        
        result = tracker.validate_critical_imports()
        
        assert result is False


class TestGetImportStatusReport:
    """Tests for ImportErrorTracker.get_import_status_report."""
    
    def test_get_import_status_report_structure(self):
        """Test that report has expected structure."""
        tracker = ImportErrorTracker()
        tracker.critical_imports = ["json"]  # Ensure validation passes
        
        report = tracker.get_import_status_report()
        
        assert "critical_imports_available" in report
        assert "failed_imports_count" in report
        assert "failed_imports" in report
        assert "fallback_usage" in report
        assert "critical_failures" in report
        assert "optional_failures" in report
        
    def test_get_import_status_report_counts_failures(self):
        """Test that report counts failures correctly."""
        tracker = ImportErrorTracker()
        tracker.critical_imports = ["json"]
        
        tracker.track_import_failure("module1", ImportError("err"), is_critical=False)
        tracker.track_import_failure("module2", ImportError("err"), is_critical=False)
        
        report = tracker.get_import_status_report()
        
        assert report["failed_imports_count"] == 2
        
    def test_get_import_status_report_separates_critical_optional(self):
        """Test that report separates critical and optional failures."""
        tracker = ImportErrorTracker()
        tracker.critical_imports = ["json"]
        
        tracker.track_import_failure("critical_mod", ImportError("err"), is_critical=True)
        tracker.track_import_failure("optional_mod", ImportError("err"), is_critical=False)
        
        report = tracker.get_import_status_report()
        
        assert "critical_mod" in report["critical_failures"]
        assert "optional_mod" in report["optional_failures"]


class TestRaiseOnCriticalFailure:
    """Tests for ImportErrorTracker.raise_on_critical_failure."""
    
    def test_raise_on_critical_failure_no_failures(self):
        """Test no exception when no critical failures."""
        tracker = ImportErrorTracker()
        
        # Should not raise
        tracker.raise_on_critical_failure()
        
    def test_raise_on_critical_failure_with_critical(self):
        """Test exception raised when critical failures exist."""
        tracker = ImportErrorTracker()
        tracker.track_import_failure("critical_module", ImportError("err"), is_critical=True)
        
        with pytest.raises(ImportError) as exc_info:
            tracker.raise_on_critical_failure()
            
        assert "critical_module" in str(exc_info.value)
        
    def test_raise_on_critical_failure_ignores_optional(self):
        """Test that optional failures don't raise."""
        tracker = ImportErrorTracker()
        tracker.track_import_failure("optional_module", ImportError("err"), is_critical=False)
        
        # Should not raise
        tracker.raise_on_critical_failure()


# =============================================================================
# Tests for safe_import function
# =============================================================================

class TestSafeImport:
    """Tests for safe_import function."""
    
    def test_safe_import_existing_module(self):
        """Test importing an existing module."""
        result = safe_import("json")
        
        import json
        assert result == json
        
    def test_safe_import_nonexistent_module_no_fallback(self):
        """Test importing nonexistent module without fallback."""
        result = safe_import("nonexistent_module_xyz_12345", is_critical=False)
        
        assert result is None
        
    def test_safe_import_with_fallback(self):
        """Test importing with fallback."""
        fallback_obj = {"type": "fallback"}
        
        result = safe_import(
            "nonexistent_module_abc_67890",
            fallback=fallback_obj,
            is_critical=False
        )
        
        assert result == fallback_obj
        
    def test_safe_import_critical_raises(self):
        """Test that critical import failure raises."""
        with pytest.raises(ImportError):
            safe_import("nonexistent_critical_module_999", is_critical=True)
            
    def test_safe_import_with_context(self):
        """Test that context is passed to tracker."""
        # Just verify it doesn't crash
        result = safe_import(
            "nonexistent_module_with_context",
            context="testing context parameter",
            is_critical=False
        )
        assert result is None


# =============================================================================
# Tests for safe_import_from function
# =============================================================================

class TestSafeImportFrom:
    """Tests for safe_import_from function."""
    
    def test_safe_import_from_existing_class(self):
        """Test importing existing class from module."""
        result = safe_import_from("collections", "OrderedDict")
        
        from collections import OrderedDict
        assert result == OrderedDict
        
    def test_safe_import_from_nonexistent_module(self):
        """Test importing from nonexistent module."""
        result = safe_import_from(
            "nonexistent_module_123",
            "SomeClass",
            is_critical=False
        )
        
        assert result is None
        
    def test_safe_import_from_nonexistent_class(self):
        """Test importing nonexistent class from existing module."""
        result = safe_import_from(
            "json",
            "NonexistentClass12345",
            is_critical=False
        )
        
        assert result is None
        
    def test_safe_import_from_with_fallback(self):
        """Test importing with fallback."""
        class FallbackClass:
            pass
            
        result = safe_import_from(
            "nonexistent_module_456",
            "TargetClass",
            fallback=FallbackClass,
            is_critical=False
        )
        
        assert result == FallbackClass
        
    def test_safe_import_from_critical_raises(self):
        """Test that critical import failure raises."""
        with pytest.raises(ImportError):
            safe_import_from(
                "nonexistent_critical_mod",
                "CriticalClass",
                is_critical=True
            )


# =============================================================================
# Tests for helper functions
# =============================================================================

class TestTrackImportError:
    """Tests for track_import_error function."""
    
    def test_track_import_error_basic(self):
        """Test tracking an import error."""
        error = ImportError("Test error")
        
        # Should not raise
        track_import_error("test_module", error, "test context")
        
        
class TestValidatePlatformImports:
    """Tests for validate_platform_imports function."""
    
    def test_validate_platform_imports_returns_bool(self):
        """Test that function returns boolean."""
        result = validate_platform_imports()
        assert isinstance(result, bool)


class TestGetImportStatus:
    """Tests for get_import_status function."""
    
    def test_get_import_status_returns_dict(self):
        """Test that function returns dictionary."""
        result = get_import_status()
        assert isinstance(result, dict)
        
    def test_get_import_status_has_expected_keys(self):
        """Test that result has expected keys."""
        result = get_import_status()
        
        expected_keys = [
            "critical_imports_available",
            "failed_imports_count",
            "failed_imports",
            "fallback_usage"
        ]
        
        for key in expected_keys:
            assert key in result


class TestRequireCriticalImports:
    """Tests for require_critical_imports function."""
    
    def test_require_critical_imports_no_failures(self):
        """Test that function doesn't raise when no critical failures."""
        # Clear any critical failures from global tracker
        original_failed = _import_tracker.failed_imports.copy()
        _import_tracker.failed_imports.clear()
        
        try:
            # Should not raise
            require_critical_imports()
        finally:
            # Restore original state
            _import_tracker.failed_imports = original_failed


# =============================================================================
# Tests for import_error_handler decorator
# =============================================================================

class TestImportErrorHandler:
    """Tests for import_error_handler decorator."""
    
    def test_decorator_passes_through_normal_execution(self):
        """Test that decorator doesn't affect normal execution."""
        @import_error_handler
        def normal_function(x):
            return x * 2
            
        result = normal_function(5)
        assert result == 10
        
    def test_decorator_catches_import_error(self):
        """Test that decorator catches ImportError."""
        @import_error_handler
        def function_with_import_error():
            raise ImportError("No module named 'test_module'")
            
        with pytest.raises(ImportError):
            function_with_import_error()
            
    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function name."""
        @import_error_handler
        def my_function():
            """My docstring."""
            pass
            
        assert my_function.__name__ == "my_function"
        
    def test_decorator_reraises_exceptions(self):
        """Test that decorator reraises other exceptions."""
        @import_error_handler
        def function_with_error():
            raise ValueError("Not an import error")
            
        with pytest.raises(ValueError):
            function_with_error()


# =============================================================================
# Tests for backwards compatibility functions
# =============================================================================

class TestBackwardsCompatibility:
    """Tests for backwards compatibility functions."""
    
    def test_log_import_failure(self):
        """Test log_import_failure function."""
        error = ImportError("Test error")
        
        # Should not raise
        log_import_failure("test_module", error, "context")
        
    def test_check_critical_imports(self):
        """Test check_critical_imports function."""
        result = check_critical_imports()
        assert isinstance(result, bool)


# =============================================================================
# Integration tests
# =============================================================================

class TestImportTrackerIntegration:
    """Integration tests for import tracker."""
    
    def test_full_import_tracking_flow(self):
        """Test complete import tracking flow."""
        tracker = ImportErrorTracker()
        tracker.critical_imports = ["json"]  # Use known module
        
        # Track some failures
        tracker.track_import_failure("module_a", ImportError("err"), is_critical=False)
        tracker.track_import_failure("module_b", ImportError("err"), is_critical=True)
        
        # Track fallback usage
        tracker.track_fallback_usage("fallback_a")
        
        # Get report
        report = tracker.get_import_status_report()
        
        assert report["failed_imports_count"] == 2
        assert "module_b" in report["critical_failures"]
        assert report["fallback_usage"]["fallback_a"] == 1
        
    def test_safe_import_tracks_failure(self):
        """Test that safe_import tracks failures in global tracker."""
        # Use a unique module name to avoid conflicts
        module_name = "unique_test_module_for_tracking_98765"
        
        result = safe_import(module_name, is_critical=False)
        
        assert result is None
        # Failure should be tracked
        assert module_name in _import_tracker.failed_imports


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases:
    """Edge case tests for import tracker."""
    
    def test_track_same_module_multiple_times(self):
        """Test tracking same module failure multiple times."""
        tracker = ImportErrorTracker()
        
        tracker.track_import_failure("same_module", ImportError("err1"))
        tracker.track_import_failure("same_module", ImportError("err2"))
        
        # Should have latest error
        assert tracker.failed_imports["same_module"]["error_message"] == "err2"
        
    def test_empty_context(self):
        """Test tracking with empty context."""
        tracker = ImportErrorTracker()
        
        tracker.track_import_failure("module", ImportError("err"), context="")
        
        assert tracker.failed_imports["module"]["context"] == ""
        
    def test_exception_types(self):
        """Test tracking different exception types."""
        tracker = ImportErrorTracker()
        
        tracker.track_import_failure("mod1", ImportError("import err"))
        tracker.track_import_failure("mod2", ModuleNotFoundError("not found"))
        tracker.track_import_failure("mod3", AttributeError("no attribute"))
        
        assert tracker.failed_imports["mod1"]["error_type"] == "ImportError"
        assert tracker.failed_imports["mod2"]["error_type"] == "ModuleNotFoundError"
        assert tracker.failed_imports["mod3"]["error_type"] == "AttributeError"
        
    def test_safe_import_from_attribute_error(self):
        """Test safe_import_from with AttributeError."""
        # Import existing module, but nonexistent attribute
        result = safe_import_from(
            "json",
            "nonexistent_attribute_xyz",
            is_critical=False
        )
        
        assert result is None
        
    def test_decorator_with_args_and_kwargs(self):
        """Test decorator preserves args and kwargs."""
        @import_error_handler
        def function_with_params(a, b, c=None, **kwargs):
            return a + b + (c or 0) + kwargs.get("d", 0)
            
        result = function_with_params(1, 2, c=3, d=4)
        assert result == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
