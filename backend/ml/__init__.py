"""
Machine Learning module package.

V9 Z7-1 / Wave-48 (2026-05-03): the prior re-export of
`staleness_detector` (M-47) pointed at an orphan module that wave-38
deleted; the leftover import here broke `from backend.ml import ...`
in any callers (lifecycle_scheduler, active_model_pointer, etc.).

This module is intentionally minimal — submodules are imported
directly (`from backend.ml.model_manager import ...`).
"""

__all__: list[str] = []
