"""No-op Model Manager for Light Mode.

Provides stub implementations when heavy ML modules are disabled.
All returns are clearly flagged as no-op to prevent downstream
code from treating them as real predictions.
"""

import logging
import warnings

logger = logging.getLogger(__name__)


class NoopModelManager:
    """No-op model manager that satisfies interfaces without real inference.

    Every method returns data clearly marked ``"noop": True`` so
    downstream consumers can detect that no real model ran.
    """

    def __init__(self):
        warnings.warn(
            "NoopModelManager active — predictions are NOT from a trained model. "
            "Set DISABLE_ML=0 and provide trained models for production.",
            RuntimeWarning,
            stacklevel=2,
        )

    def predict(self, *args, **kwargs):
        """Return neutral (no-signal) prediction flagged as no-op."""
        logger.warning("NoopModelManager.predict() called — returning neutral no-op prediction")
        return {"prediction": 0.0, "confidence": 0.0, "noop": True}

    def train(self, *args, **kwargs):
        """No-op training — returns status indicating no real training occurred."""
        logger.warning("NoopModelManager.train() called — no real training performed")
        return {"status": "skipped", "noop": True, "reason": "ML disabled"}

    def save(self, *args, **kwargs):
        """No-op save."""
        return True

    def load(self, *args, **kwargs):
        """No-op load."""
        return True

    def get_metrics(self):
        """Return empty metrics flagged as no-op."""
        return {"noop": True, "reason": "ML disabled — no real metrics available"}


def get_model_manager():
    """Factory function for getting model manager."""
    return NoopModelManager()
