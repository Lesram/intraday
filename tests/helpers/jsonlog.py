"""
JSON logging test helper for capturing and parsing structured logs.
"""

import json
import logging
import threading
from typing import List, Dict, Any, Optional
from unittest.mock import Mock


class JSONLogCapture:
    """Captures and parses JSON-formatted log records."""
    
    def __init__(self, logger_name: str = None):
        self.logger_name = logger_name or "root"
        self.records: List[Dict[str, Any]] = []
        self.handler: Optional[logging.Handler] = None
        self.original_level: Optional[int] = None
        self._lock = threading.Lock()
    
    def __enter__(self):
        """Start capturing logs."""
        logger = logging.getLogger(self.logger_name)
        self.original_level = logger.level
        logger.setLevel(logging.DEBUG)
        
        self.handler = LogRecordHandler(self.records, self._lock)
        logger.addHandler(self.handler)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing logs."""
        if self.handler:
            logger = logging.getLogger(self.logger_name)
            logger.removeHandler(self.handler)
            
            if self.original_level is not None:
                logger.setLevel(self.original_level)
    
    def get_records(self) -> List[Dict[str, Any]]:
        """Get captured log records."""
        with self._lock:
            return self.records.copy()
    
    def get_json_records(self) -> List[Dict[str, Any]]:
        """Get log records that are valid JSON."""
        json_records = []
        for record in self.get_records():
            if 'message' in record:
                try:
                    # Try to parse the message as JSON
                    parsed = json.loads(record['message'])
                    json_records.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    # Not JSON, skip
                    continue
        return json_records
    
    def assert_request_id_present(self):
        """Assert that all records contain a request_id."""
        json_records = self.get_json_records()
        for record in json_records:
            assert 'request_id' in record, f"Record missing request_id: {record}"
    
    def assert_structured_format(self):
        """Assert that logs are in structured JSON format."""
        json_records = self.get_json_records()
        assert json_records, "No JSON-formatted log records found"
        
        required_fields = {'timestamp', 'level', 'message'}
        for record in json_records:
            missing_fields = required_fields - set(record.keys())
            assert not missing_fields, f"Record missing required fields {missing_fields}: {record}"
    
    def find_records_with_request_id(self, request_id: str) -> List[Dict[str, Any]]:
        """Find all records with a specific request_id."""
        json_records = self.get_json_records()
        return [r for r in json_records if r.get('request_id') == request_id]
    
    def assert_trace_context(self, require_trace_id: bool = False, require_span_id: bool = False):
        """Assert trace context is present when OTEL is enabled."""
        json_records = self.get_json_records()
        
        for record in json_records:
            if require_trace_id:
                assert 'trace_id' in record, f"Record missing trace_id: {record}"
            if require_span_id:
                assert 'span_id' in record, f"Record missing span_id: {record}"


class LogRecordHandler(logging.Handler):
    """Custom log handler that captures records for testing."""
    
    def __init__(self, records_list: List[Dict[str, Any]], lock: threading.Lock):
        super().__init__()
        self.records_list = records_list
        self.lock = lock
    
    def emit(self, record: logging.LogRecord):
        """Capture the log record."""
        try:
            # Convert LogRecord to dict
            record_dict = {
                'name': record.name,
                'level': record.levelname,
                'message': record.getMessage(),
                'created': record.created,
                'filename': record.filename,
                'funcName': record.funcName,
                'lineno': record.lineno,
                'module': record.module,
                'pathname': record.pathname,
                'process': record.process,
                'thread': record.thread,
            }
            
            # Add extra fields if present
            for key, value in record.__dict__.items():
                if key not in record_dict and not key.startswith('_'):
                    record_dict[key] = value
            
            with self.lock:
                self.records_list.append(record_dict)
                
        except Exception:
            self.handleError(record)


# Convenience fixtures for common logging scenarios
def capture_json_logs(logger_name: str = None) -> JSONLogCapture:
    """Create a JSON log capture context manager."""
    return JSONLogCapture(logger_name)


def mock_request_id_middleware():
    """Mock middleware that adds request_id to log context."""
    mock_middleware = Mock()
    
    def add_request_id(record):
        if not hasattr(record, 'request_id'):
            record.request_id = "test-request-123"
    
    mock_middleware.process = add_request_id
    return mock_middleware
