"""
Load Balancer Service

Provides simple in-process load balancing strategies:
- Round-robin and least-connections
- Health checking and dynamic backend pool
- Sticky sessions via client key
- Metrics and basic circuit-breaker style fail marking

Backends implement a synchronous 'handle(request)' API for simplicity in tests.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple


class Strategy(Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"


class Backend(Protocol):
    id: str
    def handle(self, request: Dict[str, Any]) -> Dict[str, Any]:
        ...


@dataclass
class BackendState:
    id: str
    healthy: bool = True
    active_connections: int = 0
    last_check: Optional[datetime] = None
    failures: int = 0
    success: int = 0


@dataclass
class LbMetrics:
    total_requests: int = 0
    routed_requests: int = 0
    failed_requests: int = 0
    last_route_time: Optional[datetime] = None


class LoadBalancer:
    def __init__(self, strategy: Strategy = Strategy.ROUND_ROBIN):
        self.strategy = strategy
        self._backends: Dict[str, Tuple[Backend, BackendState]] = {}
        self._order: List[str] = []
        self._rr_index = 0
        self._lock = threading.RLock()
        self._metrics = LbMetrics()
        self._sticky: Dict[str, str] = {}

    # Backend management
    def add_backend(self, backend: Backend):
        with self._lock:
            if backend.id in self._backends:
                return
            self._backends[backend.id] = (backend, BackendState(id=backend.id))
            self._order.append(backend.id)

    def remove_backend(self, backend_id: str):
        with self._lock:
            if backend_id in self._backends:
                del self._backends[backend_id]
            if backend_id in self._order:
                self._order.remove(backend_id)
            # clean sticky
            for k, v in list(self._sticky.items()):
                if v == backend_id:
                    del self._sticky[k]

    def set_health(self, backend_id: str, healthy: bool):
        with self._lock:
            if backend_id in self._backends:
                self._backends[backend_id][1].healthy = healthy
                self._backends[backend_id][1].last_check = datetime.now(timezone.utc)

    def _pick_backend(self, client_key: Optional[str]) -> Optional[Tuple[Backend, BackendState]]:
        ids = [bid for bid in self._order if self._backends[bid][1].healthy]
        if not ids:
            return None
        # sticky first
        if client_key and client_key in self._sticky and self._sticky[client_key] in ids:
            bid = self._sticky[client_key]
            return self._backends[bid]

        if self.strategy == Strategy.ROUND_ROBIN:
            bid = ids[self._rr_index % len(ids)]
            self._rr_index += 1
            if client_key:
                self._sticky[client_key] = bid
            return self._backends[bid]
        else:  # LEAST_CONNECTIONS
            # Find all with minimal active connections
            min_conn = min(self._backends[x][1].active_connections for x in ids)
            candidates = [x for x in ids if self._backends[x][1].active_connections == min_conn]
            # Cycle among candidates to avoid bias
            bid = candidates[self._rr_index % len(candidates)]
            self._rr_index += 1
            if client_key:
                self._sticky[client_key] = bid
            return self._backends[bid]

    def route(self, request: Dict[str, Any], client_key: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            self._metrics.total_requests += 1
            picked = self._pick_backend(client_key)
            if not picked:
                self._metrics.failed_requests += 1
                return {"ok": False, "error": "no_healthy_backends"}
            backend, state = picked
            state.active_connections += 1
        try:
            resp = backend.handle(request)
            with self._lock:
                self._metrics.routed_requests += 1
                self._metrics.last_route_time = datetime.now(timezone.utc)
                state.success += 1
            return resp
        except Exception as e:
            with self._lock:
                self._metrics.failed_requests += 1
                state.failures += 1
            return {"ok": False, "error": str(e)}
        finally:
            with self._lock:
                state.active_connections = max(0, state.active_connections - 1)

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self._metrics)

    def get_backend_states(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {bid: asdict(st) for bid, (_, st) in self._backends.items()}


# Convenience globals
_lb_instance: Optional[LoadBalancer] = None


def get_load_balancer() -> LoadBalancer:
    global _lb_instance
    if _lb_instance is None:
        _lb_instance = LoadBalancer()
    return _lb_instance


def set_load_balancer(lb: LoadBalancer):
    global _lb_instance
    _lb_instance = lb
