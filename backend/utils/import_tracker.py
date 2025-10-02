"""
Import Error Tracker - Comprehensive Import Validation and Logging

This module provides centralized import error tracking and validation,
replacing silent failures with intelligent error reporting and fallback management.
"""

import os
import sys
import logging
import traceback
import warnings
from typing import Any, Dict, List, Optional, Callable, Union
from functools import wraps
from datetime import datetime


class ImportErrorTracker:
    """
    Centralized tracking and management of import errors across the platform
    """
    
    def __init__(self):
        self.failed_imports: Dict[str, Dict[str, Any]] = {}
        self.fallback_usage: Dict[str, int] = {}
        self.critical_imports: List[str] = [
            'backend.config.unified',
            'backend.database.connection', 
            'backend.services.order_service',
            'backend.risk.risk_manager',
            'fastapi',
            'sqlalchemy'
        ]
        self.optional_imports: List[str] = [
            'redis',
            'prometheus_client',
            'scipy',
            'matplotlib',
            'transformers',
            'opentelemetry'
        ]
        
        # Setup logging
        self.logger = logging.getLogger('import_tracker')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.WARNING)
    
    def track_import_failure(self, module_name: str, error: Exception, 
                           context: str = "", is_critical: bool = None) -> None:
        """Track a failed import with full context"""
        
        if is_critical is None:
            is_critical = any(crit in module_name for crit in self.critical_imports)
        
        failure_info = {
            'module': module_name,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'is_critical': is_critical,
            'timestamp': datetime.now().isoformat(),
            'traceback': traceback.format_exc(),
            'python_path': sys.path.copy(),
            'environment': dict(os.environ)
        }
        
        self.failed_imports[module_name] = failure_info
        
        # Log based on criticality
        if is_critical:
            self.logger.error(
                f"🚨 CRITICAL IMPORT FAILURE: {module_name} - {error}"
                f"\n  Context: {context}"
                f"\n  This may cause platform instability!"
            )
        elif any(opt in module_name for opt in self.optional_imports):
            self.logger.info(
                f"📦 Optional dependency unavailable: {module_name} - {error}"
                f"\n  Context: {context} (fallback will be used)"
            )
        else:
            self.logger.warning(
                f"⚠️  Import failure: {module_name} - {error}"
                f"\n  Context: {context}"
            )
    
    def track_fallback_usage(self, fallback_name: str) -> None:
        """Track usage of fallback/mock objects"""
        self.fallback_usage[fallback_name] = self.fallback_usage.get(fallback_name, 0) + 1
        self.logger.info(f"🔄 Using fallback: {fallback_name} (usage count: {self.fallback_usage[fallback_name]})")
    
    def validate_critical_imports(self) -> bool:
        """Validate that all critical imports are available"""
        missing_critical = []
        
        for module_name in self.critical_imports:
            try:
                __import__(module_name)
            except ImportError as e:
                missing_critical.append((module_name, str(e)))
        
        if missing_critical:
            self.logger.error("🚨 CRITICAL IMPORTS MISSING:")
            for module, error in missing_critical:
                self.logger.error(f"   - {module}: {error}")
            return False
        
        self.logger.info("✅ All critical imports available")
        return True
    
    def get_import_status_report(self) -> Dict[str, Any]:
        """Generate comprehensive import status report"""
        return {
            'critical_imports_available': self.validate_critical_imports(),
            'failed_imports_count': len(self.failed_imports),
            'failed_imports': self.failed_imports,
            'fallback_usage': self.fallback_usage,
            'critical_failures': [
                name for name, info in self.failed_imports.items() 
                if info['is_critical']
            ],
            'optional_failures': [
                name for name, info in self.failed_imports.items() 
                if not info['is_critical']
            ]
        }
    
    def raise_on_critical_failure(self) -> None:
        """Raise exception if critical imports failed"""
        critical_failures = [
            name for name, info in self.failed_imports.items() 
            if info['is_critical']
        ]
        
        if critical_failures:
            raise ImportError(
                f"Critical imports failed: {', '.join(critical_failures)}. "
                f"Platform cannot operate safely. Check dependencies and configuration."
            )


# Global tracker instance
_import_tracker = ImportErrorTracker()


def safe_import(module_name: str, context: str = "", 
               is_critical: bool = None, fallback: Any = None) -> Any:
    """
    Safe import with comprehensive error tracking and fallback management
    
    Args:
        module_name: Module to import
        context: Context where import is being attempted
        is_critical: Whether this import is critical for platform operation
        fallback: Fallback object/class to use if import fails
    
    Returns:
        Imported module or fallback object
    """
    try:
        return __import__(module_name, fromlist=[''])
    except ImportError as e:
        _import_tracker.track_import_failure(module_name, e, context, is_critical)
        
        if fallback is not None:
            _import_tracker.track_fallback_usage(f"{module_name}->fallback")
            return fallback
        
        # Re-raise critical import failures
        if is_critical or any(crit in module_name for crit in _import_tracker.critical_imports):
            raise ImportError(f"Critical import failed: {module_name} - {e}") from e
        
        return None


def safe_import_from(module_name: str, class_name: str, context: str = "",
                    is_critical: bool = None, fallback: Any = None) -> Any:
    """
    Safe import of specific class/function from module
    
    Args:
        module_name: Module to import from
        class_name: Class/function name to import
        context: Context where import is being attempted
        is_critical: Whether this import is critical
        fallback: Fallback class/function to use
    
    Returns:
        Imported class/function or fallback
    """
    try:
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        _import_tracker.track_import_failure(f"{module_name}.{class_name}", e, context, is_critical)
        
        if fallback is not None:
            _import_tracker.track_fallback_usage(f"{module_name}.{class_name}->fallback")
            return fallback
        
        # Re-raise critical import failures
        if is_critical or any(crit in module_name for crit in _import_tracker.critical_imports):
            raise ImportError(f"Critical import failed: {module_name}.{class_name} - {e}") from e
        
        return None


def track_import_error(module_name: str, error: Exception, context: str = "") -> None:
    """Track an import error that occurred in a try/except block"""
    _import_tracker.track_import_failure(module_name, error, context)


def validate_platform_imports() -> bool:
    """Validate that all critical platform imports are available"""
    return _import_tracker.validate_critical_imports()


def get_import_status() -> Dict[str, Any]:
    """Get comprehensive import status report"""
    return _import_tracker.get_import_status_report()


def require_critical_imports() -> None:
    """Raise exception if critical imports are not available"""
    _import_tracker.raise_on_critical_failure()


def import_error_handler(func: Callable) -> Callable:
    """
    Decorator to wrap functions that may have import-related failures
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ImportError as e:
            context = f"function:{func.__name__}"
            track_import_error(str(e).split("'")[1] if "'" in str(e) else "unknown", e, context)
            raise
        except Exception as e:
            # Check if the exception was caused by an import error
            if "ImportError" in str(e) or "ModuleNotFoundError" in str(e):
                context = f"function:{func.__name__} (wrapped_exception)"
                track_import_error("unknown_module", e, context)
            raise
    return wrapper


# Backwards compatibility functions
def log_import_failure(module_name: str, error: Exception, context: str = "") -> None:
    """Backwards compatible function for logging import failures"""
    track_import_error(module_name, error, context)


def check_critical_imports() -> bool:
    """Backwards compatible function for checking critical imports"""
    return validate_platform_imports()


if __name__ == "__main__":
    # Demo/test the import tracker
    print("🔍 Testing Import Error Tracker...")
    
    # Test safe import with fallback
    redis = safe_import("redis", "test context", is_critical=False, fallback=type("MockRedis", (), {}))
    print(f"Redis import result: {type(redis)}")
    
    # Test critical import validation
    critical_ok = validate_platform_imports()
    print(f"Critical imports OK: {critical_ok}")
    
    # Test import status report
    status = get_import_status()
    print(f"Import status report: {len(status['failed_imports'])} failures tracked")
    
    print("✅ Import Error Tracker working!")