# Strategies package initialization.
#
# V8 NN-CRIT-2 / Wave-36 (2026-05-03): the prior re-export of
# `parity_checker` (M-42) pointed at an orphan module that was never
# reached in production. parity_checker.py is now deleted; versioning
# (M-41) IS used live via backend/services/strategy_service.py and is
# preserved.
from .versioning import (
    StrategyVersionManager,
    StrategyVersion,
    VersionChangeType,
    VersionComparison,
    get_version_manager,
)

__all__ = [
    "StrategyVersionManager",
    "StrategyVersion",
    "VersionChangeType",
    "VersionComparison",
    "get_version_manager",
]
