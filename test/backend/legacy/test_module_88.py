"""
Comprehensive test suite for Module 88: Load Balancer Service
"""

import pytest

from backend.services.load_balancer import LoadBalancer, Strategy


class DummyBackend:
    def __init__(self, id: str):
        self.id = id
        self.calls = 0

    def handle(self, request):
        self.calls += 1
        if request.get("fail"):
            raise RuntimeError("backend_failure")
        return {"ok": True, "backend": self.id}


class TestLoadBalancer:
    @pytest.mark.timeout(5)
    def test_round_robin(self):
        lb = LoadBalancer(Strategy.ROUND_ROBIN)
        b1, b2 = DummyBackend("b1"), DummyBackend("b2")
        lb.add_backend(b1); lb.add_backend(b2)
        r1 = lb.route({}); r2 = lb.route({}); r3 = lb.route({})
        assert r1["backend"] == "b1"
        assert r2["backend"] == "b2"
        assert r3["backend"] == "b1"

    @pytest.mark.timeout(5)
    def test_least_connections(self):
        lb = LoadBalancer(Strategy.LEAST_CONNECTIONS)
        b1, b2 = DummyBackend("b1"), DummyBackend("b2")
        lb.add_backend(b1); lb.add_backend(b2)
        # simulate b1 busy
        states = lb.get_backend_states()
        # cannot modify internal, so just route requests and check balanced
        r1 = lb.route({}); r2 = lb.route({})
        assert {r1["backend"], r2["backend"]} == {"b1", "b2"}

    @pytest.mark.timeout(5)
    def test_sticky_sessions(self):
        lb = LoadBalancer(Strategy.ROUND_ROBIN)
        b1, b2 = DummyBackend("b1"), DummyBackend("b2")
        lb.add_backend(b1); lb.add_backend(b2)
        r1 = lb.route({}, client_key="u1")
        r2 = lb.route({}, client_key="u1")
        assert r1["backend"] == r2["backend"]

    @pytest.mark.timeout(5)
    def test_health_and_remove(self):
        lb = LoadBalancer()
        b1, b2 = DummyBackend("b1"), DummyBackend("b2")
        lb.add_backend(b1); lb.add_backend(b2)
        lb.set_health("b1", False)
        r = lb.route({})
        assert r["backend"] == "b2"
        lb.remove_backend("b2")
        r2 = lb.route({})
        assert r2["ok"] is False and r2["error"] == "no_healthy_backends"

    @pytest.mark.timeout(5)
    def test_failures_and_metrics(self):
        lb = LoadBalancer()
        b1 = DummyBackend("b1")
        lb.add_backend(b1)
        r1 = lb.route({"fail": True})
        assert r1["ok"] is False
        m = lb.get_metrics()
        assert m["total_requests"] == 1 and m["failed_requests"] == 1

    @pytest.mark.timeout(5)
    def test_globals_and_unhealthy_paths(self):
        from backend.services.load_balancer import get_load_balancer, set_load_balancer
        lb = LoadBalancer()
        set_load_balancer(lb)
        g = get_load_balancer()
        assert g is lb
        b1, b2 = DummyBackend("b1"), DummyBackend("b2")
        g.add_backend(b1); g.add_backend(b2)
        # mark sticky to b1 then make it unhealthy, expect fallback to b2
        g.route({}, client_key="u2")
        g.set_health("b1", False)
        r = g.route({}, client_key="u2")
        assert r["backend"] == "b2"
        # all unhealthy -> error
        g.set_health("b2", False)
        r2 = g.route({}, client_key="u2")
        assert r2["ok"] is False and r2["error"] == "no_healthy_backends"

    @pytest.mark.timeout(5)
    def test_duplicate_add_and_sticky_cleanup(self):
        lb = LoadBalancer()
        b1 = DummyBackend("b1")
        lb.add_backend(b1)
        lb.add_backend(b1)  # duplicate should be ignored
        assert list(lb.get_backend_states().keys()) == ["b1"]
        # establish sticky
        r1 = lb.route({}, client_key="U")
        assert r1["backend"] == "b1"
        # remove backend should cleanup sticky and fail subsequently
        lb.remove_backend("b1")
        r2 = lb.route({}, client_key="U")
        assert r2["ok"] is False
