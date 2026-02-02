"""
Machine Learning module package.
Contains sentiment analysis, drift detection, and model management components.
"""

from .staleness_detector import (
    ModelStalenessDetector,
    StalenessMetrics,
    StalenessLevel,
    StalenessReason,
    get_staleness_detector,
)

__all__ = [
    "SocialSentimentAnalyzer",
    # Model Staleness Detection (M-47)
    "ModelStalenessDetector",
    "StalenessMetrics",
    "StalenessLevel",
    "StalenessReason",
    "get_staleness_detector",
]
