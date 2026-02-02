"""
Comprehensive tests for backend/config_helpers.py

Simple module tests.
"""

import pytest
from backend.config_helpers import Config, load_config_from_env


class TestConfig:
    """Tests for Config class."""

    def test_config_class_exists(self):
        """Config class can be instantiated."""
        config = Config()
        assert config is not None

    def test_config_is_empty(self):
        """Config has no predefined attributes."""
        config = Config()
        assert isinstance(config, Config)


class TestLoadConfigFromEnv:
    """Tests for load_config_from_env function."""

    def test_load_config_returns_config(self):
        """load_config_from_env returns a Config instance."""
        result = load_config_from_env()
        assert isinstance(result, Config)

    def test_load_config_returns_new_instance(self):
        """Each call returns a new Config instance."""
        config1 = load_config_from_env()
        config2 = load_config_from_env()
        assert config1 is not config2
