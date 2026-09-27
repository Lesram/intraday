"""Offline regressions for disposable Docker probe address allocation."""

import json
import sys

import pytest

from scripts.ci import check_frontend_container as probe


def network(identity, *subnets):
    return {
        "Id": identity,
        "Driver": "bridge",
        "IPAM": {"Config": [{"Subnet": subnet} for subnet in subnets]},
    }


def inventory(monkeypatch, networks, *, ids=None):
    listed = ids if ids is not None else [row["Id"] for row in networks]
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        if args == ("network", "ls", "--no-trunc", "--quiet"):
            return "\n".join(listed)
        assert args == ("network", "inspect", *listed)
        return json.dumps(networks)

    monkeypatch.setattr(probe, "docker", docker)
    return calls


def test_selects_after_all_overlapping_subnets_and_handles_ipv6(monkeypatch):
    inventory(monkeypatch, [
        network("a" * 64, "10.240.0.0/16", "fd00:1234::/64"),
        network("b" * 64, "10.241.0.128/25"),
        network("c" * 64, "192.168.0.0/16"),
        {"Id": "d" * 64, "Driver": "host", "IPAM": {"Config": None}},
        {"Id": "e" * 64, "Driver": "null", "IPAM": {"Config": []}},
    ])
    assert probe.available_probe_subnet() == "10.241.1.0/24"


def test_empty_inventory_never_calls_inspect_without_ids(monkeypatch):
    calls = inventory(monkeypatch, [])
    assert probe.available_probe_subnet() == "10.240.0.0/24"
    assert len(calls) == 1


def test_exhausted_private_pool_refuses_without_mutation(monkeypatch):
    calls = inventory(monkeypatch, [network("a" * 64, "10.0.0.0/8")])
    with pytest.raises(ValueError, match="No nonoverlapping"):
        probe.available_probe_subnet()
    assert all(call[1] in ("ls", "inspect") for call in calls)


@pytest.mark.parametrize("networks,ids", [
    ([], ["not-a-network-id"]),
    ([], ["a" * 64, "a" * 64]),
    ([], [f"{value:064x}" for value in range(257)]),
    ([], ["a" * 64]),
    ({}, ["a" * 64]),
    ([None], ["a" * 64]),
    ([network("b" * 64, "10.0.0.0/8")], ["a" * 64]),
    ([network("a" * 64), network("a" * 64)], ["a" * 64, "b" * 64]),
    ([{"Id": "a" * 64}], ["a" * 64]),
    ([{"Id": "a" * 64, "Driver": "bridge", "IPAM": {}}], ["a" * 64]),
    ([{"Id": "a" * 64, "Driver": "bridge", "IPAM": {"Config": None}}], ["a" * 64]),
    ([network("a" * 64)], ["a" * 64]),
    ([{"Id": "a" * 64, "IPAM": {"Config": "invalid"}}], ["a" * 64]),
    ([{"Id": "a" * 64, "IPAM": {"Config": [{}]}}], ["a" * 64]),
    ([network("a" * 64, "not-a-subnet")], ["a" * 64]),
    ([network("a" * 64, *(["10.0.0.0/8"] * 65))], ["a" * 64]),
])
def test_invalid_inventory_refuses_without_mutation(monkeypatch, networks, ids):
    calls = inventory(monkeypatch, networks, ids=ids)
    with pytest.raises(ValueError):
        probe.available_probe_subnet()
    assert all(call[1] in ("ls", "inspect") for call in calls)


@pytest.mark.parametrize("mode", ["success", "overlap_race", "same_ip"])
def test_main_preserves_replacement_proof_isolation_and_owned_cleanup(monkeypatch, tmp_path, mode):
    """Exercise actual orchestration, including Linux's static-IP requirement."""
    calls, created_networks, containers, removed = [], [], set(), []
    state = {"api_up": False, "starts": 0, "explicit": False}
    old_ip, new_ip = "10.241.0.2", "10.241.0.4"

    def docker(*args, **kwargs):
        calls.append(args)
        if args[:2] == ("network", "ls"):
            return "a" * 64
        if args[:2] == ("network", "inspect"):
            return json.dumps([network("a" * 64, "10.240.0.0/16")])
        if args[:2] == ("network", "create"):
            if "--internal" in args:
                assert "--subnet" in args
                assert args[args.index("--subnet") + 1] == "10.241.0.0/24"
                if mode == "overlap_race":
                    raise RuntimeError("Pool overlaps concurrent network")
                state["explicit"] = True
            created_networks.append(args[-1])
        elif args[0] == "run":
            name = args[args.index("--name") + 1]
            assert name.startswith("intra-ui-probe-")
            assert "--read-only" in args and "--cap-drop" in args
            containers.add(name)
            if name.endswith("-api"):
                assert args[args.index("--network") + 1].endswith("-net")
                assert "-p" not in args
                state["api_up"] = True
                state["starts"] += 1
            elif name.endswith("-holder"):
                assert state["explicit"], "Linux refuses --ip without explicit subnet"
                assert args[args.index("--ip") + 1] == old_ip
            else:
                assert args[args.index("-p") + 1] == "127.0.0.1::8080"
        elif args[0] == "port":
            return "127.0.0.1:65432"
        elif args[0] == "inspect":
            internal = next(name for name in created_networks if name.endswith("-net"))
            address = old_ip if state["starts"] == 1 or mode == "same_ip" else new_ip
            return json.dumps([{"NetworkSettings": {"Networks": {internal: {"IPAddress": address}}}}])
        elif args[0] == "rm":
            assert args[-1] in containers
            containers.remove(args[-1])
            removed.append(args[-1])
            if args[-1].endswith("-api"):
                state["api_up"] = False
        elif args[:2] == ("network", "rm"):
            assert args[-1] in created_networks
            assert not containers
            created_networks.remove(args[-1])
            removed.append(args[-1])
        elif args[:2] == ("image", "inspect"):
            return "sha256:synthetic-owned-image"
        return ""

    def fetch(base, path):
        if path == "/ui-health":
            return 200, b'{"scope":"frontend"}', {}
        if path in ("/", "/portfolio"):
            return 200, b'<div id="root">', {}
        if path.startswith("/assets"):
            return 404, b"not found", {}
        if not state["api_up"]:
            return 502, b"upstream unavailable", {}
        body = json.dumps({"path": path, "authorization": "Bearer synthetic-ui-probe", "host": "127.0.0.1:65432"}).encode()
        return 503 if path.endswith("/reject") else 200, body, {}

    echoes = []
    monkeypatch.setattr(probe, "docker", docker)
    monkeypatch.setattr(probe, "fetch", fetch)
    monkeypatch.setattr(probe, "websocket_echo", lambda port, path: echoes.append(path))
    monkeypatch.setattr(sys, "argv", ["probe", "--image", "synthetic-owned-ui", "--output-dir", str(tmp_path)])
    code = probe.main()
    receipt = json.loads((tmp_path / "result.json").read_text())
    assert not containers and not created_networks
    assert receipt["cleanup_errors"] == []
    if mode == "success":
        assert code == 0 and receipt["passed"] is True
        assert len(receipt["checks"]) == 5
        assert receipt["api_replacement"] == {"old_ip": old_ip, "new_ip": new_ip}
        assert len(echoes) == 3
        assert len(removed) == 6  # old API, replacement, holder, UI, two networks.
    else:
        assert code == 1 and receipt["passed"] is False
        if mode == "overlap_race":
            assert not removed and not any(call[0] == "run" for call in calls)
        else:
            assert len(receipt["checks"]) == 3
