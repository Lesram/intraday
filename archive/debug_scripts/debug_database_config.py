#!/usr/bin/env python3
"""Debug script to check DatabaseConfig issue."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

# Import the same way as the test
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any

class IsolationLevel(Enum):
    READ_UNCOMMITTED = "READ_UNCOMMITTED"
    READ_COMMITTED = "READ_COMMITTED"
    REPEATABLE_READ = "REPEATABLE_READ"
    SERIALIZABLE = "SERIALIZABLE"

@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    url: str = "sqlite:///trading_platform.db"
    pool_size: int = 20
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    echo_pool: bool = False
    isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    connect_args: Dict[str, Any] = field(default_factory=dict)
    autocommit: bool = False
    autoflush: bool = True
    expire_on_commit: bool = True

# Test
config = DatabaseConfig()
print(f"Config created: {config}")
print(f"Has url attribute: {hasattr(config, 'url')}")
print(f"URL value: {getattr(config, 'url', 'MISSING')}")
print(f"Config type: {type(config)}")
print(f"Config fields: {config.__dataclass_fields__.keys() if hasattr(config, '__dataclass_fields__') else 'No fields'}")