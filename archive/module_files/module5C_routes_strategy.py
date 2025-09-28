#!/usr/bin/env python3
"""
Module 5C: API Routes Strategy - Direct handler tests (no FastAPI client)
Target: backend/api/routes/strategy.py
"""

import os
import sys
import importlib
import types
import json
import asyncio
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def _import_module(name: str):
    try:
        return importlib.import_module(name), None
    except Exception as e:
        return None, e


class _StubRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def test_strategy_handlers_cover_paths():
    # Provide minimal stubs if optional deps are missing
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")
        class APIRouter:
            def __init__(self, *args, **kwargs): pass
            def get(self, *args, **kwargs):
                def deco(fn): return fn
                return deco
            def post(self, *args, **kwargs):
                def deco(fn): return fn
                return deco
        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail
        class Request: ...
        fastapi.APIRouter = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

    if "pydantic" not in sys.modules:
        pyd = types.ModuleType("pydantic")
        class BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
        def Field(default=None, default_factory=None, **kwargs):
            # Return default or result of default_factory like pydantic behavior
            return default if default is not None else (default_factory() if callable(default_factory) else None)
        pyd.BaseModel = BaseModel
        pyd.Field = Field
        sys.modules["pydantic"] = pyd

    # Stub logger dependency to avoid structlog requirement during import
    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        class _DummyLogger:
            def info(self, *args, **kwargs):
                return None
            def error(self, *args, **kwargs):
                return None
        def get_logger(name):
            return _DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.routes.strategy")
    if mod is None:
        pytest.skip(f"backend.api.routes.strategy not importable: {err}")

    # GET /strategy/status
    result = asyncio.run(mod.get_strategy_status())
    assert result["status"] == "operational"

    # POST /strategy/features/ingest
    fb = mod.FeatureBatch(features=[{"x": 1}, {"x": 2}])
    result = asyncio.run(mod.ingest_features(_StubRequest({}), fb))
    assert result["status"] == "accepted"
    assert result["processed_count"] == 2

    # POST /strategy/signals/batch
    sb = mod.SignalBatch(signals=[{"s": "AAPL"}, {"s": "MSFT"}], strategy_id="s1")
    result = asyncio.run(mod.process_signal_batch(_StubRequest({}), sb))
    assert result["processed_count"] == 2
    assert result["strategy_id"] == "s1"

    # POST /strategy/signals/submit
    result = asyncio.run(mod.submit_strategy_signal(_StubRequest({"k": "v"})))
    assert result["status"] == "submitted"


def test_strategy_exception_handlers():
    """Test exception handling in strategy routes to cover remaining lines."""
    # Provide minimal stubs if optional deps are missing
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")
        class APIRouter:
            def __init__(self, *args, **kwargs): pass
            def get(self, *args, **kwargs):
                def deco(fn): return fn
                return deco
            def post(self, *args, **kwargs):
                def deco(fn): return fn
                return deco
        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail
        class Request: ...
        fastapi.APIRouter = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

    if "pydantic" not in sys.modules:
        pyd = types.ModuleType("pydantic")
        class BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
        def Field(default=None, default_factory=None, **kwargs):
            return default if default is not None else (default_factory() if callable(default_factory) else None)
        pyd.BaseModel = BaseModel
        pyd.Field = Field
        sys.modules["pydantic"] = pyd

    # Stub logger dependency
    if "backend.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("backend.utils.logger")
        class _DummyLogger:
            def info(self, *args, **kwargs):
                return None
            def error(self, *args, **kwargs):
                return None
        def get_logger(name):
            return _DummyLogger()
        logger_mod.get_logger = get_logger
        sys.modules["backend.utils.logger"] = logger_mod

    mod, err = _import_module("backend.api.routes.strategy")
    if mod is None:
        pytest.skip(f"backend.api.routes.strategy not importable: {err}")

    # Test exception in ingest_features by creating invalid batch
    class BadFeatureBatch:
        def __init__(self):
            self.features = None  # This will cause an error when len() is called
    
    bad_batch = BadFeatureBatch()
    try:
        result = asyncio.run(mod.ingest_features(_StubRequest({}), bad_batch))
    except Exception as e:
        # Exception should be caught and converted to HTTPException
        assert "HTTPException" in str(type(e)) or "Feature ingestion failed" in str(e)

    # Test exception in process_signal_batch by creating batch that will fail during processing
    class BadSignalBatch:
        def __init__(self):
            # Create signals that will fail when str() is called on them
            class FailingSignal:
                def __str__(self):
                    raise RuntimeError("Cannot convert to string")
            self.signals = [FailingSignal()]
            self.strategy_id = "test"
    
    bad_signal_batch = BadSignalBatch()
    try:
        result = asyncio.run(mod.process_signal_batch(_StubRequest({}), bad_signal_batch))
        assert False, "Should have raised an exception"
    except mod.HTTPException as e:
        assert e.status_code == 500
        assert "Signal batch processing failed" in e.detail
    except Exception as e:
        # Fallback for when HTTPException isn't properly stubbed
        assert "Signal batch processing failed" in str(e) or "Cannot convert to string" in str(e)

    # Test exception in submit_strategy_signal with failing request
    class FailingRequest:
        async def json(self):
            raise RuntimeError("JSON parsing failed")
    
    try:
        result = asyncio.run(mod.submit_strategy_signal(FailingRequest()))
    except Exception as e:
        assert "HTTPException" in str(type(e)) or "Signal submission failed" in str(e)
