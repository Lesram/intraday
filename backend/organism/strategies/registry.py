"""name -> Strategy class registry.

Adding a future strategy is a "write one module + one config block" operation:
decorate the class with @register("name") and add its config section. The engine
and backtester look strategies up here by name, never by importing concrete
classes directly.
"""
from __future__ import annotations

from typing import Any, Callable

from backend.organism.strategies.base import Strategy

_REGISTRY: dict[str, type[Strategy]] = {}


def register(name: str) -> Callable[[type[Strategy]], type[Strategy]]:
    """Class decorator: register a Strategy subclass under ``name``."""
    def _deco(cls: type[Strategy]) -> type[Strategy]:
        if not isinstance(cls, type) or not issubclass(cls, Strategy):
            raise TypeError(f"@register({name!r}) requires a Strategy subclass")
        if name in _REGISTRY and _REGISTRY[name] is not cls:
            raise ValueError(f"strategy {name!r} already registered to {_REGISTRY[name]!r}")
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return _deco


def get_strategy_class(name: str) -> type[Strategy]:
    if name not in _REGISTRY:
        raise KeyError(f"no strategy registered as {name!r} (have: {registered_names()})")
    return _REGISTRY[name]


def registered_names() -> list[str]:
    return sorted(_REGISTRY)


def build_strategy(name: str, config: dict[str, Any]) -> Strategy:
    """Instantiate a registered strategy with its config block (validates on load)."""
    return get_strategy_class(name)(config)
