"""
Monitoring API routes.
Provides SLI metrics, SLO compliance, and observability endpoints.

Metrics are computed from real request data tracked by the MetricsCollector
middleware (stored on app.state.metrics_collector). When no collector is
available, the endpoints return an explicit "no_data" source — never
synthetic/hardcoded numbers.
"""

import time
from collections import defaultdict
from datetime import datetime

import numpy as np
from fastapi import APIRouter, HTTPException, Request

from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


# ── In-process request metrics collector ─────────────────────────────
class MetricsCollector:
    """Collect per-route latency and error counts in-process."""

    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self._requests: dict[str, list[dict]] = defaultdict(list)

    def record(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        key = f"{method} {path}"
        now = time.time()
        self._requests[key].append({
            "ts": now,
            "status": status_code,
            "duration_ms": duration_ms,
        })
        # Prune old entries
        cutoff = now - self.window
        self._requests[key] = [r for r in self._requests[key] if r["ts"] > cutoff]

    def get_route_metrics(self) -> dict[str, dict]:
        now = time.time()
        cutoff = now - self.window
        result = {}
        for route_key, records in self._requests.items():
            recent = [r for r in records if r["ts"] > cutoff]
            if not recent:
                continue
            total = len(recent)
            errors = sum(1 for r in recent if r["status"] >= 500)
            durations = sorted(r["duration_ms"] for r in recent)
            arr = np.array(durations)
            result[route_key] = {
                "availability": round(1.0 - (errors / total), 6),
                "latency_p50_ms": round(float(np.percentile(arr, 50)), 2),
                "latency_p95_ms": round(float(np.percentile(arr, 95)), 2),
                "latency_p99_ms": round(float(np.percentile(arr, 99)), 2),
                "error_rate": round(errors / total, 6),
                "total_requests": total,
            }
        return result


def get_metrics_collector(request: Request) -> MetricsCollector | None:
    return getattr(request.app.state, "metrics_collector", None)


@router.get("/sli-metrics", openapi_extra={"security": []})
async def get_sli_metrics(request: Request):
    """Get per-route SLI metrics computed from real request data."""
    try:
        # Check for cached SLI data first
        sli_cache = getattr(request.app.state, "sli_metrics_cache", None)
        if sli_cache and isinstance(sli_cache, dict):
            return sli_cache

        collector = get_metrics_collector(request)
        if collector:
            routes_data = collector.get_route_metrics()
            return {
                "routes": routes_data,
                "timestamp": datetime.now().isoformat(),
                "collection_period_seconds": collector.window,
                "data_source": "live",
            }

        return {
            "routes": {},
            "timestamp": datetime.now().isoformat(),
            "collection_period_seconds": 300,
            "data_source": "no_data",
            "message": "MetricsCollector middleware not installed. No request data available.",
        }

    except Exception as e:
        logger.error(f"SLI metrics generation failed: {e}")
        raise HTTPException(status_code=503, detail=f"SLI metrics unavailable: {str(e)}")


@router.get("/slo-status", openapi_extra={"security": []})
async def get_slo_status(request: Request):
    """Get SLO compliance status computed from real SLI data."""
    try:
        slo_cache = getattr(request.app.state, "slo_status_cache", None)
        if slo_cache and isinstance(slo_cache, dict):
            return slo_cache

        # Compute SLO from real SLI data
        collector = get_metrics_collector(request)
        if not collector:
            return {
                "compliance": {},
                "error_budget": {"total": 100, "consumed": 0, "remaining": 100, "remaining_percentage": 100.0},
                "timestamp": datetime.now().isoformat(),
                "collection_period_seconds": 3600,
                "data_source": "no_data",
                "message": "MetricsCollector middleware not installed.",
            }

        routes = collector.get_route_metrics()
        if not routes:
            return {
                "compliance": {},
                "error_budget": {"total": 100, "consumed": 0, "remaining": 100, "remaining_percentage": 100.0},
                "timestamp": datetime.now().isoformat(),
                "collection_period_seconds": collector.window,
                "data_source": "live",
                "message": "No requests recorded yet.",
            }

        # Aggregate across all routes
        total_reqs = sum(r["total_requests"] for r in routes.values())
        weighted_error_rate = sum(r["error_rate"] * r["total_requests"] for r in routes.values()) / max(total_reqs, 1)
        weighted_avail = sum(r["availability"] * r["total_requests"] for r in routes.values()) / max(total_reqs, 1)
        all_p95 = [r["latency_p95_ms"] for r in routes.values()]
        all_p99 = [r["latency_p99_ms"] for r in routes.values()]
        max_p95 = max(all_p95) if all_p95 else 0.0
        max_p99 = max(all_p99) if all_p99 else 0.0

        # SLO thresholds
        slo_error_threshold = 1.0  # 1%
        slo_avail_threshold = 99.0  # 99%
        slo_p95_threshold = 500.0  # 500ms
        slo_p99_threshold = 2000.0  # 2s

        error_pct = weighted_error_rate * 100
        avail_pct = weighted_avail * 100

        compliance = {
            "error_rate": {
                "current": round(error_pct, 3),
                "threshold": slo_error_threshold,
                "status": "compliant" if error_pct <= slo_error_threshold else "breached",
            },
            "availability": {
                "current": round(avail_pct, 3),
                "threshold": slo_avail_threshold,
                "status": "compliant" if avail_pct >= slo_avail_threshold else "breached",
            },
            "latency_p95": {
                "current": round(max_p95, 2),
                "threshold": slo_p95_threshold,
                "status": "compliant" if max_p95 <= slo_p95_threshold else "breached",
            },
            "latency_p99": {
                "current": round(max_p99, 2),
                "threshold": slo_p99_threshold,
                "status": "compliant" if max_p99 <= slo_p99_threshold else "breached",
            },
        }

        # Error budget: how much of 1% error rate has been consumed
        budget_consumed = min(error_pct / slo_error_threshold * 100, 100.0)

        return {
            "compliance": compliance,
            "error_budget": {
                "total": 100,
                "consumed": round(budget_consumed, 1),
                "remaining": round(100.0 - budget_consumed, 1),
                "remaining_percentage": round(100.0 - budget_consumed, 1),
            },
            "timestamp": datetime.now().isoformat(),
            "collection_period_seconds": collector.window,
            "data_source": "live",
        }

    except Exception as e:
        logger.error(f"SLO status generation failed: {e}")
        raise HTTPException(status_code=503, detail=f"SLO status unavailable: {str(e)}")
