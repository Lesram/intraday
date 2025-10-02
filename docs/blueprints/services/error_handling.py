"""
Error Handling Service Module

This module provides comprehensive error management including:
- Centralized error tracking and monitoring
- Error classification and categorization
- Recovery strategies and retry mechanisms
- Alert generation and notification
- Error reporting and analytics
- Debug information collection
"""

import asyncio
import logging
import traceback
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Set
import json
import hashlib
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories."""
    SYSTEM = "system"
    NETWORK = "network"
    DATABASE = "database"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_LOGIC = "business_logic"
    EXTERNAL_SERVICE = "external_service"
    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class ErrorStatus(Enum):
    """Error status."""
    NEW = "new"
    INVESTIGATING = "investigating"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class RecoveryStrategy(Enum):
    """Recovery strategies."""
    NONE = "none"
    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_BREAKER = "circuit_breaker"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    RESTART = "restart"
    ESCALATE = "escalate"


@dataclass
class ErrorContext:
    """Context information for an error."""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    operation: Optional[str] = None
    module: Optional[str] = None
    function: Optional[str] = None
    line_number: Optional[int] = None
    file_path: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, str] = field(default_factory=dict)
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorOccurrence:
    """Single occurrence of an error."""
    id: str
    error_id: str
    occurred_at: datetime
    context: ErrorContext
    stack_trace: Optional[str] = None
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Comprehensive error record."""
    id: str
    error_type: str
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    status: ErrorStatus = ErrorStatus.NEW
    first_occurred: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_occurred: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    occurrence_count: int = 1
    occurrences: List[ErrorOccurrence] = field(default_factory=list)
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    is_resolved: bool = False
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    
    def add_occurrence(self, context: ErrorContext, stack_trace: Optional[str] = None) -> str:
        """Add new occurrence of this error."""
        occurrence_id = str(uuid.uuid4())
        occurrence = ErrorOccurrence(
            id=occurrence_id,
            error_id=self.id,
            occurred_at=datetime.now(timezone.utc),
            context=context,
            stack_trace=stack_trace
        )
        
        self.occurrences.append(occurrence)
        self.occurrence_count += 1
        self.last_occurred = occurrence.occurred_at
        
        return occurrence_id
    
    def can_retry(self) -> bool:
        """Check if error can be retried."""
        return (self.recovery_strategy == RecoveryStrategy.RETRY and 
                self.recovery_attempts < self.max_recovery_attempts)
    
    def should_escalate(self) -> bool:
        """Check if error should be escalated."""
        return (self.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] or
                self.occurrence_count > 10 or
                self.recovery_attempts >= self.max_recovery_attempts)


@dataclass
class RecoveryAction:
    """Recovery action definition."""
    strategy: RecoveryStrategy
    handler: Callable
    delay_seconds: float = 0.0
    max_attempts: int = 3
    backoff_multiplier: float = 2.0
    conditions: Dict[str, Any] = field(default_factory=dict)


class ErrorHandler(ABC):
    """Abstract base class for error handlers."""
    
    @abstractmethod
    async def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle error occurrence."""
        pass
    
    @abstractmethod
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if this handler can handle the error."""
        pass


class RetryHandler(ErrorHandler):
    """Handler for retry recovery strategy."""
    
    def __init__(self, max_attempts: int = 3, backoff_multiplier: float = 2.0):
        self.max_attempts = max_attempts
        self.backoff_multiplier = backoff_multiplier
    
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if error can be retried."""
        return (error_record.recovery_strategy == RecoveryStrategy.RETRY and
                error_record.can_retry())
    
    async def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle error with retry strategy."""
        if not self.can_handle(error_record):
            return False
        
        delay = min(2 ** error_record.recovery_attempts * self.backoff_multiplier, 60)
        await asyncio.sleep(delay)
        
        error_record.recovery_attempts += 1
        
        logger.info(f"Retrying error {error_record.id}, attempt {error_record.recovery_attempts}")
        return True


class FallbackHandler(ErrorHandler):
    """Handler for fallback recovery strategy."""
    
    def __init__(self, fallback_function: Optional[Callable] = None):
        self.fallback_function = fallback_function
    
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if error can use fallback."""
        return error_record.recovery_strategy == RecoveryStrategy.FALLBACK
    
    async def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle error with fallback strategy."""
        if not self.can_handle(error_record):
            return False
        
        try:
            if self.fallback_function:
                if asyncio.iscoroutinefunction(self.fallback_function):
                    await self.fallback_function(error_record)
                else:
                    self.fallback_function(error_record)
            
            logger.info(f"Applied fallback for error {error_record.id}")
            return True
            
        except Exception as e:
            logger.error(f"Fallback failed for error {error_record.id}: {e}")
            return False


class CircuitBreakerHandler(ErrorHandler):
    """Handler for circuit breaker pattern."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_counts: Dict[str, int] = defaultdict(int)
        self.last_failure_time: Dict[str, datetime] = {}
        self.circuit_open: Dict[str, bool] = defaultdict(bool)
    
    def can_handle(self, error_record: ErrorRecord) -> bool:
        """Check if error should trigger circuit breaker."""
        return error_record.recovery_strategy == RecoveryStrategy.CIRCUIT_BREAKER
    
    async def handle_error(self, error_record: ErrorRecord) -> bool:
        """Handle error with circuit breaker pattern."""
        if not self.can_handle(error_record):
            return False
        
        service_key = f"{error_record.category.value}_{error_record.error_type}"
        
        # Increment failure count
        self.failure_counts[service_key] += 1
        self.last_failure_time[service_key] = datetime.now(timezone.utc)
        
        # Check if circuit should be opened
        if self.failure_counts[service_key] >= self.failure_threshold:
            self.circuit_open[service_key] = True
            logger.warning(f"Circuit breaker opened for {service_key}")
        
        return True
    
    def is_circuit_open(self, service_key: str) -> bool:
        """Check if circuit is open for a service."""
        if not self.circuit_open.get(service_key, False):
            return False
        
        # Check if recovery timeout has passed
        last_failure = self.last_failure_time.get(service_key)
        if last_failure:
            time_since_failure = datetime.now(timezone.utc) - last_failure
            if time_since_failure.total_seconds() > self.recovery_timeout:
                # Reset circuit breaker
                self.circuit_open[service_key] = False
                self.failure_counts[service_key] = 0
                logger.info(f"Circuit breaker reset for {service_key}")
                return False
        
        return True


class ErrorCollector:
    """Collects and aggregates error information."""
    
    def __init__(self, max_errors: int = 10000):
        self.max_errors = max_errors
        self.errors: Dict[str, ErrorRecord] = {}
        self.error_queue: deque = deque(maxlen=max_errors)
        self._lock = threading.RLock()
    
    def collect_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext] = None,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE
    ) -> str:
        """Collect and store error information."""
        with self._lock:
            # Generate error signature for deduplication
            error_signature = self._generate_error_signature(exception, context)
            
            if error_signature in self.errors:
                # Update existing error
                error_record = self.errors[error_signature]
                occurrence_id = error_record.add_occurrence(
                    context or ErrorContext(),
                    traceback.format_exc()
                )
            else:
                # Create new error record
                error_id = str(uuid.uuid4())
                error_record = ErrorRecord(
                    id=error_id,
                    error_type=type(exception).__name__,
                    message=str(exception),
                    category=category,
                    severity=severity,
                    recovery_strategy=recovery_strategy
                )
                
                occurrence_id = error_record.add_occurrence(
                    context or ErrorContext(),
                    traceback.format_exc()
                )
                
                self.errors[error_signature] = error_record
                self.error_queue.append(error_record)
                
                # Remove oldest errors if we exceed max_errors
                if len(self.errors) > self.max_errors:
                    oldest_error = self.error_queue.popleft()
                    if oldest_error.id in [e.id for e in self.errors.values()]:
                        error_to_remove = next(
                            sig for sig, err in self.errors.items() 
                            if err.id == oldest_error.id
                        )
                        del self.errors[error_to_remove]
            
            return error_record.id
    
    def _generate_error_signature(self, exception: Exception, context: Optional[ErrorContext]) -> str:
        """Generate unique signature for error deduplication."""
        signature_parts = [
            type(exception).__name__,
            str(exception),
        ]
        
        if context:
            signature_parts.extend([
                context.module or "",
                context.function or "",
                str(context.line_number or ""),
            ])
        
        signature_string = "|".join(signature_parts)
        return hashlib.md5(signature_string.encode()).hexdigest()
    
    def get_error(self, error_id: str) -> Optional[ErrorRecord]:
        """Get error record by ID."""
        with self._lock:
            for error_record in self.errors.values():
                if error_record.id == error_id:
                    return error_record
            return None
    
    def get_errors_by_category(self, category: ErrorCategory) -> List[ErrorRecord]:
        """Get errors by category."""
        with self._lock:
            return [err for err in self.errors.values() if err.category == category]
    
    def get_errors_by_severity(self, severity: ErrorSeverity) -> List[ErrorRecord]:
        """Get errors by severity."""
        with self._lock:
            return [err for err in self.errors.values() if err.severity == severity]
    
    def get_unresolved_errors(self) -> List[ErrorRecord]:
        """Get all unresolved errors."""
        with self._lock:
            return [err for err in self.errors.values() if not err.is_resolved]
    
    def resolve_error(self, error_id: str, notes: str = "", resolved_by: str = "") -> bool:
        """Mark error as resolved."""
        with self._lock:
            error_record = self.get_error(error_id)
            if error_record:
                error_record.is_resolved = True
                error_record.status = ErrorStatus.RESOLVED
                error_record.resolution_notes = notes
                error_record.resolved_at = datetime.now(timezone.utc)
                error_record.resolved_by = resolved_by
                return True
            return False


class ErrorNotifier:
    """Handles error notifications and alerts."""
    
    def __init__(self):
        self.notification_handlers: List[Callable] = []
        self.notification_rules: List[Dict[str, Any]] = []
    
    def add_notification_handler(self, handler: Callable) -> None:
        """Add notification handler."""
        self.notification_handlers.append(handler)
    
    def add_notification_rule(
        self,
        condition: Dict[str, Any],
        handler: Callable,
        throttle_minutes: int = 0
    ) -> None:
        """Add notification rule."""
        rule = {
            "condition": condition,
            "handler": handler,
            "throttle_minutes": throttle_minutes,
            "last_notification": None
        }
        self.notification_rules.append(rule)
    
    async def notify_error(self, error_record: ErrorRecord) -> None:
        """Send error notifications based on rules."""
        for rule in self.notification_rules:
            if self._matches_condition(error_record, rule["condition"]):
                # Check throttling
                if self._should_throttle(rule):
                    continue
                
                try:
                    handler = rule["handler"]
                    if asyncio.iscoroutinefunction(handler):
                        await handler(error_record)
                    else:
                        handler(error_record)
                    
                    rule["last_notification"] = datetime.now(timezone.utc)
                    
                except Exception as e:
                    logger.error(f"Failed to send error notification: {e}")
    
    def _matches_condition(self, error_record: ErrorRecord, condition: Dict[str, Any]) -> bool:
        """Check if error matches notification condition."""
        if "severity" in condition:
            if error_record.severity != condition["severity"]:
                return False
        
        if "category" in condition:
            if error_record.category != condition["category"]:
                return False
        
        if "min_occurrences" in condition:
            if error_record.occurrence_count < condition["min_occurrences"]:
                return False
        
        return True
    
    def _should_throttle(self, rule: Dict[str, Any]) -> bool:
        """Check if notification should be throttled."""
        throttle_minutes = rule.get("throttle_minutes", 0)
        if throttle_minutes == 0:
            return False
        
        last_notification = rule.get("last_notification")
        if not last_notification:
            return False
        
        time_since_last = datetime.now(timezone.utc) - last_notification
        return time_since_last.total_seconds() < (throttle_minutes * 60)


class ErrorHandlingService:
    """Comprehensive error handling service."""
    
    def __init__(self):
        self.collector = ErrorCollector()
        self.notifier = ErrorNotifier()
        self.handlers: List[ErrorHandler] = []
        self.recovery_actions: Dict[RecoveryStrategy, RecoveryAction] = {}
        self.circuit_breaker = CircuitBreakerHandler()
        self.monitoring_enabled = True
        self.auto_recovery_enabled = True
        self._monitoring_task: Optional[asyncio.Task] = None
        
        # Add default handlers
        self.add_handler(RetryHandler())
        self.add_handler(FallbackHandler())
        self.add_handler(self.circuit_breaker)
    
    def add_handler(self, handler: ErrorHandler) -> None:
        """Add error handler."""
        self.handlers.append(handler)
    
    def add_recovery_action(self, strategy: RecoveryStrategy, action: RecoveryAction) -> None:
        """Add recovery action for strategy."""
        self.recovery_actions[strategy] = action
    
    async def handle_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext] = None,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE,
        auto_recover: bool = True
    ) -> str:
        """Handle error occurrence."""
        try:
            # Collect error information
            error_id = self.collector.collect_error(
                exception, context, category, severity, recovery_strategy
            )
            
            error_record = self.collector.get_error(error_id)
            if not error_record:
                return error_id
            
            # Send notifications
            await self.notifier.notify_error(error_record)
            
            # Attempt recovery if enabled
            if auto_recover and self.auto_recovery_enabled:
                await self._attempt_recovery(error_record)
            
            logger.error(f"Error handled: {error_record.error_type} - {error_record.message}")
            return error_id
            
        except Exception as e:
            logger.critical(f"Failed to handle error: {e}")
            return ""
    
    async def _attempt_recovery(self, error_record: ErrorRecord) -> bool:
        """Attempt to recover from error."""
        for handler in self.handlers:
            if handler.can_handle(error_record):
                try:
                    success = await handler.handle_error(error_record)
                    if success:
                        logger.info(f"Recovery successful for error {error_record.id}")
                        return True
                except Exception as e:
                    logger.error(f"Recovery failed for error {error_record.id}: {e}")
        
        return False
    
    async def start_monitoring(self) -> None:
        """Start error monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._monitoring_task = asyncio.create_task(self._monitor_errors())
        self.monitoring_enabled = True
        logger.info("Error monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop error monitoring."""
        self.monitoring_enabled = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Error monitoring stopped")
    
    async def _monitor_errors(self) -> None:
        """Monitor errors for patterns and escalation."""
        while self.monitoring_enabled:
            try:
                unresolved_errors = self.collector.get_unresolved_errors()
                
                for error_record in unresolved_errors:
                    # Check for escalation
                    if error_record.should_escalate():
                        await self._escalate_error(error_record)
                    
                    # Check for auto-resolution opportunities
                    if self._can_auto_resolve(error_record):
                        self.collector.resolve_error(
                            error_record.id, 
                            "Auto-resolved: No recent occurrences", 
                            "system"
                        )
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)
    
    async def _escalate_error(self, error_record: ErrorRecord) -> None:
        """Escalate error to higher severity."""
        if error_record.severity != ErrorSeverity.CRITICAL:
            old_severity = error_record.severity
            error_record.severity = ErrorSeverity.CRITICAL
            error_record.status = ErrorStatus.ACKNOWLEDGED
            
            logger.warning(f"Escalated error {error_record.id} from {old_severity} to CRITICAL")
            await self.notifier.notify_error(error_record)
    
    def _can_auto_resolve(self, error_record: ErrorRecord) -> bool:
        """Check if error can be auto-resolved."""
        # Auto-resolve if no occurrences in the last hour
        time_since_last = datetime.now(timezone.utc) - error_record.last_occurred
        return time_since_last.total_seconds() > 3600
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics."""
        all_errors = list(self.collector.errors.values())
        
        stats = {
            "total_errors": len(all_errors),
            "unresolved_errors": len([e for e in all_errors if not e.is_resolved]),
            "errors_by_severity": {},
            "errors_by_category": {},
            "recent_errors": len([
                e for e in all_errors 
                if (datetime.now(timezone.utc) - e.last_occurred).total_seconds() < 3600
            ])
        }
        
        # Count by severity
        for severity in ErrorSeverity:
            count = len([e for e in all_errors if e.severity == severity])
            stats["errors_by_severity"][severity.value] = count
        
        # Count by category
        for category in ErrorCategory:
            count = len([e for e in all_errors if e.category == category])
            stats["errors_by_category"][category.value] = count
        
        return stats
    
    def clear_resolved_errors(self, older_than_days: int = 7) -> int:
        """Clear resolved errors older than specified days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        
        errors_to_remove = []
        for signature, error_record in self.collector.errors.items():
            if (error_record.is_resolved and 
                error_record.resolved_at and 
                error_record.resolved_at < cutoff_date):
                errors_to_remove.append(signature)
        
        for signature in errors_to_remove:
            del self.collector.errors[signature]
        
        return len(errors_to_remove)


# Utility functions and decorators
def get_error_service() -> ErrorHandlingService:
    """Get singleton error handling service."""
    if not hasattr(get_error_service, '_instance'):
        get_error_service._instance = ErrorHandlingService()
    return get_error_service._instance


def handle_errors(
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.NONE,
    auto_recover: bool = True
):
    """Decorator for automatic error handling."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    function=func.__name__,
                    module=func.__module__,
                    parameters={"args": str(args), "kwargs": str(kwargs)}
                )
                
                service = get_error_service()
                await service.handle_error(
                    e, context, category, severity, recovery_strategy, auto_recover
                )
                raise
        
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    function=func.__name__,
                    module=func.__module__,
                    parameters={"args": str(args), "kwargs": str(kwargs)}
                )
                
                service = get_error_service()
                # For sync functions, we need to handle async call differently
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(service.handle_error(
                        e, context, category, severity, recovery_strategy, auto_recover
                    ))
                except RuntimeError:
                    # No event loop running
                    pass
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


async def report_error(
    message: str,
    category: ErrorCategory = ErrorCategory.UNKNOWN,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    context: Optional[ErrorContext] = None
) -> str:
    """Report custom error."""
    exception = RuntimeError(message)
    service = get_error_service()
    return await service.handle_error(exception, context, category, severity)


def get_current_context(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    operation: Optional[str] = None,
    **additional_data
) -> ErrorContext:
    """Create current error context."""
    import inspect
    
    frame = inspect.currentframe().f_back
    context = ErrorContext(
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
        operation=operation,
        module=frame.f_globals.get('__name__'),
        function=frame.f_code.co_name,
        line_number=frame.f_lineno,
        file_path=frame.f_code.co_filename,
        additional_data=additional_data
    )
    
    return context