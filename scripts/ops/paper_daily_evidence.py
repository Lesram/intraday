#!/usr/bin/env python3
"""Manual GET-only paper evidence collection and immutable offline replay.

No broker mutations, scheduling, platform imports at startup, or brain writes.
A READY_FOR_REVIEW pack is evidence for review, never promotion authority.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ops.standdown_session_row import ET, calendar_session, session_diagnostics, timestamp
from scripts.research.paper_fill_reconciliation import reconcile

PAPER_BASE = "https://paper-api.alpaca.markets"
LOCAL_BASE = "http://127.0.0.1:8000"
PAPER_PATHS = {"/v2/calendar", "/v2/clock", "/v2/account", "/v2/positions", "/v2/orders"}
LOCAL_PATHS = {"/api/v1/paper-monitor/deploy", "/api/v1/paper-monitor/organism/status"}
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_LOCAL_BYTES = 512 * 1024 * 1024
SCHEMA = "paper_daily_evidence_v1"
TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class EvidenceError(ValueError):
    """Messages are controlled reason codes; never include broker bodies/secrets."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EvidenceError("redirect_refused")


class GetTransport:
    def __init__(self, key: str, secret: str, token: str):
        self.paper_headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.local_headers = {"Authorization": "Bearer " + token}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def get(self, origin: str, path: str, params: dict) -> bytes:
        if origin == "paper" and path in PAPER_PATHS:
            base, headers = PAPER_BASE, self.paper_headers
        elif origin == "local" and path in LOCAL_PATHS:
            base, headers = LOCAL_BASE, self.local_headers
        else:
            raise EvidenceError("non_allowlisted_endpoint")
        request = urllib.request.Request(base + path + "?" + urllib.parse.urlencode(params),
                                         headers=headers, method="GET")
        try:
            with self.opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise EvidenceError("http_status_failure")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise EvidenceError("response_size_limit")
            return raw
        except (OSError, urllib.error.URLError):
            raise EvidenceError("transport_failure") from None

    def container_identity(self) -> bytes:
        # Format selects safe identity fields only; never dump Config.Env/Cmd.
        template = ('{"name":{{json .Name}},"image_digest":{{json .Image}},'
                    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                    '"service":{{json (index .Config.Labels "com.docker.compose.service")}}}')
        try:
            result = subprocess.run(["docker", "inspect", "--format", template, "intra-api-1"],
                                    capture_output=True, timeout=10, check=False)
            if result.returncode:
                raise EvidenceError("container_identity_unavailable")
            return result.stdout
        except (OSError, subprocess.TimeoutExpired):
            raise EvidenceError("container_identity_unavailable") from None


class Recorder:
    def __init__(self, transport, inputs: dict[str, bytes]):
        self.transport, self.inputs, self.requests = transport, inputs, []

    def get(self, name: str, origin: str, path: str, params: dict):
        raw = self.transport.get(origin, path, params)
        self.inputs[name] = raw
        self.requests.append({"input": name, "origin": origin, "method": "GET",
                              "path": path, "params": params, "sha256": digest(raw)})
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise EvidenceError("invalid_json_response") from None


def collect_orders(recorder: Recorder, cutoff: str, captured_at: str, *,
                   page_size: int = 500, max_pages: int = 100) -> tuple[list, dict]:
    """ID cursor avoids timestamp ties; endpoint rejects time filters with ID cursors.

    First request fixes an exclusive upper bound. Subsequent ID cursors must
    strictly advance; duplicates are failures. Stop on cutoff crossing or a
    short page. The active-cutoff activation must attest flat/no open orders.
    """
    if not 1 <= page_size <= 500 or not 1 <= max_pages <= 100:
        raise EvidenceError("invalid_pagination_budget")
    lower, upper = timestamp(cutoff), timestamp(captured_at)
    seen, result, cursor, previous_time = set(), [], None, upper
    for index in range(max_pages):
        params = {"status": "all", "limit": page_size, "direction": "desc", "nested": "false"}
        params.update({"before_order_id": cursor} if cursor else {"until": captured_at})
        page = recorder.get(f"broker/orders-{index:03d}.json", "paper", "/v2/orders", params)
        if not isinstance(page, list) or len(page) > page_size:
            raise EvidenceError("invalid_order_page")
        crossed = False
        for order in page:
            if not isinstance(order, dict) or not isinstance(order.get("id"), str) or not order["id"]:
                raise EvidenceError("invalid_order_identity")
            if order["id"] in seen:
                raise EvidenceError("duplicate_order_or_cursor")
            seen.add(order["id"])
            submitted = timestamp(order["submitted_at"])
            if submitted > previous_time or submitted >= upper:
                raise EvidenceError("nonchronological_order_page")
            previous_time = submitted
            if submitted <= lower:
                crossed = True
            else:
                result.append(order)
        if crossed or len(page) < page_size:
            return result, {"pages": index + 1, "termination": "cutoff_crossed" if crossed else "exhausted",
                            "order_count": len(result), "cutoff": cutoff, "until": captured_at,
                            "pagination": "before_order_id", "status_filter": "all"}
        next_cursor = page[-1]["id"]
        if next_cursor == cursor:
            raise EvidenceError("nonadvancing_cursor")
        cursor = next_cursor
    raise EvidenceError("order_page_limit")


def stable_read(path: Path) -> bytes:
    if path.is_symlink():
        raise EvidenceError("symlink_input")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_LOCAL_BYTES:
        raise EvidenceError("invalid_or_oversized_input")
    with path.open("rb") as source:
        content = source.read(MAX_LOCAL_BYTES + 1)
        after_fd = os.fstat(source.fileno())
    after = path.stat()
    signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if signature(before) != signature(after) or signature(before) != signature(after_fd) or len(content) != before.st_size:
        raise EvidenceError("input_changed_during_capture")
    return content


def capture_local(root: Path, freeze: Path, activation: Path, release: Path, baseline: Path | None,
                  inputs: dict[str, bytes]) -> list[Path]:
    mapping = {"local/freeze.json": freeze, "local/activation.json": activation,
               "local/release.json": release,
               "local/trades.csv": root / "organism_brain/trade_history.csv",
               "local/events.jsonl": root / "organism_brain/strategy_evidence_events.jsonl"}
    checkpoint = root / "organism_brain/close_accounting.json"
    if checkpoint.exists():
        mapping["local/close_accounting.json"] = checkpoint
    entry_evidence = root / "organism_brain/entry_evidence.jsonl"
    if entry_evidence.exists():
        mapping["local/entry_evidence.jsonl"] = entry_evidence
    logs = sorted((root / "logs").glob("application.log*"))
    mapping.update({"logs/" + path.name: path for path in logs if path.is_file()})
    if baseline:
        mapping["baseline/backup_manifest.json"] = baseline / "backup_manifest.json"
        mapping["baseline/trades.csv"] = baseline / "trade_history.csv"
    states = {name: path.stat() for name, path in mapping.items()}
    for name, path in mapping.items():
        inputs[name] = stable_read(path)
    for name, path in mapping.items():
        before, after = states[name], path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise EvidenceError("input_set_changed_during_capture")
    if logs != sorted((root / "logs").glob("application.log*")):
        raise EvidenceError("log_rotation_during_capture")
    return list(mapping.values())


def rows_from(raw: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def approved_baseline(inputs: dict[str, bytes], activation: dict, ledger: list[dict]) -> int:
    """Only a checksum-pinned activation backup can exempt old undated records."""
    if "baseline/trades.csv" not in inputs:
        return 0
    receipt_raw = inputs["baseline/backup_manifest.json"]
    if digest(receipt_raw) != activation["backups"]["brain"]["manifest_sha256"]:
        raise EvidenceError("baseline_manifest_unapproved")
    receipt = json.loads(receipt_raw)
    raw = inputs["baseline/trades.csv"]
    expected = receipt["files"]["trade_history.csv"]
    if digest(raw) != expected["sha256"] or len(raw) != expected["bytes"]:
        raise EvidenceError("baseline_ledger_checksum")
    prior = rows_from(raw)
    if len(prior) > len(ledger):
        raise EvidenceError("baseline_rows_missing")
    for old, current in zip(prior, ledger):
        if any(current.get(key) != value for key, value in old.items()):
            raise EvidenceError("baseline_ledger_rewritten")
    return len(prior)


def native_gates(ledger_bytes: bytes, cutoff: str) -> dict:
    from backend.organism.phase2_gate import MOMENTUM_TREND_REGIMES, gate_for_strategy, load_forward_corpus
    with tempfile.TemporaryDirectory(prefix="intra-evidence-corpus-") as temporary:
        path = Path(temporary) / "trades.csv"
        path.write_bytes(ledger_bytes)
        corpus = load_forward_corpus(str(path), cutoff, cost_bps=6.0)
    return {name: gate_for_strategy(corpus, name, regimes) for name, regimes in
            (("momentum", MOMENTUM_TREND_REGIMES), ("breakout", None), ("mean_reversion", None), ("orb", None))}


def analyze(inputs: dict[str, bytes], collection: dict, *, gate_fn: Callable = native_gates) -> dict:
    issues = list(collection.get("issues", []))
    report = {"schema": SCHEMA, "status": "BLOCKED", "session_date": collection["session_date"],
              "captured_at": collection["captured_at"], "issues": issues,
              "promotion_authorized": False, "primary_cost_bps_round_trip": 6,
              "strategy_gate": {"state": "WITHHELD", "reason": "evidence_quality"},
              "limits": ["Manual evidence pack; no scheduler installed or operational acceptance awarded.",
                         "Paper fills do not establish live-market execution or profitability.",
                         "Runtime snapshot is capture-time evidence, not per-decision freshness proof."]}
    try:
        for request in collection["requests"]:
            allowed = PAPER_PATHS if request.get("origin") == "paper" else LOCAL_PATHS if request.get("origin") == "local" else set()
            if request.get("method") != "GET" or request.get("path") not in allowed or digest(inputs[request["input"]]) != request["sha256"]:
                raise EvidenceError("acquisition_trace_mismatch")
        calendar_requests = [r for r in collection["requests"] if r.get("input") == "broker/calendar.json"]
        if (len(calendar_requests) != 1 or calendar_requests[0]["path"] != "/v2/calendar"
                or calendar_requests[0]["params"] != {"start": collection["session_date"], "end": collection["session_date"]}):
            raise EvidenceError("calendar_acquisition_missing")
        now = timestamp(collection["captured_at"])
        calendar = json.loads(inputs["broker/calendar.json"])
        session = calendar_session(collection["session_date"], calendar, now)
        report["session"] = session
        if session["state"] == "NO_SESSION":
            if not issues:
                report["status"] = "NO_SESSION"
            return report
        expected_reads = {
            "broker/account.json": ("paper", "/v2/account", {}),
            "broker/clock.json": ("paper", "/v2/clock", {}),
            "broker/positions.json": ("paper", "/v2/positions", {}),
            "broker/final-positions.json": ("paper", "/v2/positions", {}),
            "runtime/deploy.json": ("local", "/api/v1/paper-monitor/deploy", {}),
            "runtime/status.json": ("local", "/api/v1/paper-monitor/organism/status", {}),
            "broker/final-order-probe.json": ("paper", "/v2/orders", {
                "status": "all", "limit": 1, "direction": "asc", "nested": "false", "after": (timestamp(collection["captured_at"]) - timedelta(microseconds=1)).isoformat()}),
        }
        for name, expected in expected_reads.items():
            matches = [request for request in collection["requests"] if request["input"] == name]
            if len(matches) != 1 or (matches[0]["origin"], matches[0]["path"], matches[0]["params"]) != expected:
                raise EvidenceError("required_acquisition_trace_missing")
        if session["state"] != "CLOSED":
            issues.append("before_authoritative_close")
        if now.astimezone(ET).date().isoformat() != collection["session_date"]:
            issues.append("current_broker_state_cannot_attest_past_session")
        freeze = json.loads(inputs["local/freeze.json"])
        activation = json.loads(inputs["local/activation.json"])
        cutoff = freeze["FROZEN_AT"]
        if digest(inputs["local/freeze.json"]) != activation["active_freeze_sha256"] or cutoff != activation["activation_timestamp_utc"]:
            issues.append("freeze_activation_mismatch")
        before = activation["broker_before_transition"]
        if before.get("paper_endpoint_verified") is not True or before.get("positions") != 0 or before.get("open_orders") != 0:
            issues.append("cutoff_flat_state_unverified")
        identity = json.loads(inputs["runtime/deploy.json"])
        release = json.loads(inputs["local/release.json"])
        container = json.loads(inputs["runtime/container.json"])
        if any(release.get(key) in (None, "", "unknown") for key in ("source_sha", "image_sha", "image_digest", "runtime_config_hash")):
            issues.append("approved_release_identity_missing")
        if (identity.get("source_sha") != release["source_sha"] or identity.get("image_sha") != release["image_sha"]
                or container.get("image_digest") != release["image_digest"]
                or (container.get("name"), container.get("project"), container.get("service")) != ("/intra-api-1", "intra", "api")):
            issues.append("runtime_release_identity_mismatch")
        if (not release.get("runtime_config_hash") or release["runtime_config_hash"] == "unknown"
                or identity.get("runtime_config_hash") != release["runtime_config_hash"]):
            issues.append("runtime_config_identity_mismatch")
        report["runtime_identity"] = identity
        report["runtime_state"] = json.loads(inputs["runtime/status.json"])
        scheduler = report["runtime_state"].get("live_engine") or {}
        if scheduler.get("running") is not True or not isinstance(scheduler.get("engine"), dict):
            issues.append("runtime_engine_not_running")
        live_accounting = (scheduler.get("engine") or {}).get("close_accounting") or {}
        if (live_accounting.get("policy") != "exact_position_fills_or_pending_v1"
                or live_accounting.get("error") or live_accounting.get("pending")):
            issues.append("runtime_close_accounting_not_clear")
        ledger = rows_from(inputs["local/trades.csv"])
        baseline_count = approved_baseline(inputs, activation, ledger)
        report["approved_historical_rows"] = baseline_count
        forward, duplicate_keys = [], set()
        mapped = {"alpha", "alpha+breakout", "breakout", "orb", "orb_sip", "mr", "mean_reversion"}
        for index, row in enumerate(ledger):
            try:
                closed = timestamp(row["closed_at"])
            except (ValueError, KeyError, TypeError, AttributeError):
                if index >= baseline_count:
                    issues.append(f"unscoped_ledger_row:{index}")
                continue
            if closed <= timestamp(cutoff):
                continue
            forward.append(row)
            if closed > now:
                issues.append(f"future_ledger_row:{index}")
            key = json.dumps(row, sort_keys=True)
            if key in duplicate_keys:
                issues.append(f"duplicate_ledger_row:{index}")
            duplicate_keys.add(key)
            if row.get("entry_source") not in mapped:
                issues.append(f"unmapped_strategy:{index}")
            if row.get("price_source") != "db_position_fills":
                issues.append(f"unqualified_price_source:{index}")
        orders = json.loads(inputs["derived/orders.json"])
        replay_order_collection(inputs, collection, cutoff, orders)
        inventory = collection.get("order_inventory") or {}
        if inventory.get("termination") not in {"cutoff_crossed", "exhausted"} or inventory.get("order_count") != len(orders) or inventory.get("cutoff") != cutoff:
            issues.append("broker_inventory_unverified")
        if json.loads(inputs["broker/final-order-probe.json"]):
            issues.append("orders_changed_during_collection")
        if json.loads(inputs["broker/final-positions.json"]) != json.loads(inputs["broker/positions.json"]):
            issues.append("positions_changed_during_collection")
        positions = json.loads(inputs["broker/positions.json"])
        if not isinstance(positions, list) or positions:
            issues.append("broker_not_flat")
        account = json.loads(inputs["broker/account.json"])
        if account.get("status") != "ACTIVE" or account.get("trading_blocked") is not False or account.get("account_blocked") is not False:
            issues.append("broker_account_not_ready")
        clock = json.loads(inputs["broker/clock.json"])
        if (clock.get("is_open") is not False or timestamp(clock["timestamp"]) < timestamp(session["eligible_at"])
                or abs((timestamp(clock["timestamp"]) - now).total_seconds()) > 120):
            issues.append("broker_clock_not_closed_or_fresh")
        if any(order.get("status") not in TERMINAL for order in orders):
            issues.append("nonterminal_order_at_close")
        reconciliation = reconcile(orders, ledger, cutoff)
        report["reconciliation"] = reconciliation
        no_trade = (not forward and reconciliation["counts"]["organism_filled_orders"] == 0
                    and reconciliation["issues"] == [{"kind": "no_forward_evidence"}])
        if reconciliation["status"] != "RECONCILED" and not no_trade:
            issues.append("financial_reconciliation_unresolved")
        logs = {name: raw for name, raw in inputs.items() if name.startswith("logs/")}
        diagnostic = session_diagnostics(collection["session_date"], session, inputs["local/events.jsonl"],
                                         inputs["local/trades.csv"], logs,
                                         naive_timezone=collection.get("log_timezone"))
        report["standdown"] = diagnostic
        if diagnostic["coverage"] != "OBSERVED_TICK_COVERAGE":
            issues.append("session_tick_coverage_unverified")
        # A source hash at capture cannot prove historical decision attribution.
        # The close checkpoint adapter below must bind each forward row to evidence.
        checkpoint_quality(inputs, forward, identity, issues, report)
        report["trade_observation"] = "NO_FORWARD_TRADES" if no_trade else "FORWARD_TRADES_PRESENT"
        report["unobserved_paths"] = ["natural_partial_exit", "active_eod_flatten"] if no_trade else []
        if not issues:
            report["strategy_gate"] = gate_fn(inputs["local/trades.csv"], cutoff)
            report["status"] = "READY_FOR_REVIEW"
    except EvidenceError as exc:
        issues.append(str(exc))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        issues.append("missing_or_invalid_analysis_input")
    report["issues"] = sorted(set(issues))
    return report


def checkpoint_quality(inputs, forward, identity, issues, report):
    if "local/close_accounting.json" not in inputs:
        issues.append("authoritative_accounting_checkpoint_missing")
        return
    checkpoint = json.loads(inputs["local/close_accounting.json"])
    state = checkpoint["state"]
    if (checkpoint.get("version") != 1 or checkpoint.get("policy") != "exact_position_fills_or_pending_v1"
            or digest(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()) != checkpoint.get("sha256")):
        issues.append("accounting_checkpoint_invalid")
        return
    pending = sum(bool(meta.get("pending_close")) for meta in state["tracking"]["_entry_metadata"].values())
    report["accounting_checkpoint"] = {"policy": checkpoint["policy"], "pending_closes": pending,
                                       "authoritative_trades": len(state["all_trades"])}
    if pending:
        issues.append("pending_close_accounting")
    ledger = rows_from(inputs["local/trades.csv"])
    # CSV is a rounded legacy projection of the checkpoint, not authority.
    precision = {"entry_price": 4, "exit_price": 4, "pnl": 6, "predicted_return": 6,
                 "actual_return": 6, "confidence": 4, "mfe": 4, "mae": 4,
                 "time_in_trade_seconds": 2}
    if len(ledger) != len(state["all_trades"]):
        issues.append("ledger_checkpoint_length_mismatch")
    else:
        for index, (row, authoritative) in enumerate(zip(ledger, state["all_trades"])):
            for key, actual in row.items():
                if key not in authoritative:
                    continue
                expected = authoritative[key]
                if expected is None or isinstance(expected, float) and math.isnan(expected):
                    equal = actual in {"", "nan", "NaN"}
                elif isinstance(expected, bool):
                    equal = str(expected).lower() == str(actual).lower()
                elif isinstance(expected, (int, float)):
                    expected = round(expected, precision[key]) if key in precision else expected
                    try:
                        equal = math.isfinite(float(actual)) and float(actual) == expected
                    except (TypeError, ValueError):
                        equal = False
                else:
                    equal = str(expected) == actual
                if not equal:
                    issues.append(f"ledger_checkpoint_disagreement:{index}:{key}")
    completed = state["completed"]
    seen = set()
    for index, row in enumerate(forward):
        entry = row.get("entry_order_id")
        if not entry or entry in seen or completed.get(entry) != row["closed_at"]:
            issues.append(f"close_identity_unverified:{index}")
        seen.add(entry)
    entry_quality(inputs, forward, issues, report)


def entry_quality(inputs, forward, issues, report):
    receipts, duplicates, malformed = {}, 0, 0
    for raw in inputs.get("local/entry_evidence.jsonl", b"").splitlines():
        try:
            receipt = json.loads(raw)
            entry = receipt["entry_order_id"]
            if not entry:
                raise ValueError("missing_entry")
            if entry in receipts:
                duplicates += 1
                if receipts[entry] != receipt:
                    issues.append("conflicting_entry_receipts")
            receipts[entry] = receipt
        except (ValueError, KeyError, TypeError):
            malformed += 1
    if malformed:
        issues.append("malformed_entry_receipts")
    release = json.loads(inputs["local/release.json"])
    approved = release.get("approved_entry_identities", [release])
    identities = {(item["source_sha"], item["image_sha"], item["runtime_config_hash"]) for item in approved}
    freeze = json.loads(inputs["local/freeze.json"])
    feed = freeze.get("surface", {}).get("routing_data_env", {}).get("ALPACA_DATA_FEED")
    orders = json.loads(inputs["derived/orders.json"])
    verified, verified_buys = 0, 0
    for index, row in enumerate(forward):
        try:
            cycles = [match for match in report["reconciliation"]["matches"]
                      if match["symbol"] == row["symbol"] and match["closed_at"] == row["closed_at"]]
            if len(cycles) != 1:
                raise ValueError("entry_cycle_join_mismatch")
            buys = [order for order in orders if order.get("side") == "buy"
                    and digest(str(order["id"]).encode())[:16] in cycles[0]["order_refs"]]
            if not buys:
                raise ValueError("entry_cycle_missing_buys")
            anchored = False
            joined_entries = set()
            for order in buys:
                matching = [receipt for receipt in receipts.values()
                            if receipt.get("client_order_id") and receipt["client_order_id"] == order.get("client_order_id")]
                if len(matching) != 1:
                    raise ValueError("entry_broker_join_ambiguous")
                receipt = matching[0]
                validate_entry_receipt(receipt, row, order, identities, feed, release, freeze)
                if receipt["entry_order_id"] in joined_entries:
                    raise ValueError("reused_entry_receipt")
                joined_entries.add(receipt["entry_order_id"])
                anchored |= receipt["entry_order_id"] == row.get("entry_order_id")
            if not anchored:
                raise ValueError("anchor_receipt_not_in_cycle")
            verified += 1
            verified_buys += len(buys)
        except (ValueError, KeyError, TypeError, AttributeError):
            issues.append(f"entry_decision_provenance_unverified:{index}")
    report["decision_provenance"] = {
        "state": "OBSERVED" if forward and verified == len(forward) else "UNVERIFIED" if forward else "NO_FORWARD_DECISIONS",
        "forward_trades": len(forward), "verified_entries": verified, "verified_buy_decisions": verified_buys,
        "duplicate_identical_receipts": duplicates, "malformed_receipts": malformed,
        "limits": ["Every buy decision in the matched cycle needs its own exact receipt; frame hashes are not provider archives or proof of edge."]}


def validate_entry_receipt(receipt, row, order, identities, feed, release, freeze):
    """Apply identical provenance checks to initial entries and pyramid adds."""
    if receipt.get("schema") != "intra_entry_evidence_v1" or receipt.get("status") != "OBSERVED" or receipt.get("reasons"):
        raise ValueError("missing_or_unverified_receipt")
    if (receipt.get("git_sha"), receipt.get("image_sha"), receipt.get("runtime_config_hash")) not in identities:
        raise ValueError("unapproved_entry_identity")
    if (not feed or receipt.get("feed") != feed or receipt.get("symbol") != row["symbol"]
            or receipt.get("entry_source") != row["entry_source"] or receipt.get("direction", 0) <= 0
            or row.get("strategy_id") and receipt.get("strategy_id") != row["strategy_id"]):
        raise ValueError("entry_receipt_context")
    if (receipt.get("gate_passed") is not True or receipt.get("timestamp_complete") is not True
            or receipt.get("timestamp_ordered") is not True or receipt.get("frame_rows", 0) <= 0
            or not isinstance(receipt.get("frame_hash"), str) or len(receipt["frame_hash"]) != 64):
        raise ValueError("entry_frame_unverified")
    if receipt.get("method") != "pandas_hash_v1" or receipt.get("timeframe") != release.get("timeframe"):
        raise ValueError("entry_frame_method_or_timeframe_unverified")
    captured, submitted, recorded, bar = [timestamp(receipt[key]) for key in
                                          ("captured_at", "submitted_at", "recorded_at", "last_bar_at")]
    age = (submitted - bar).total_seconds()
    if (not timestamp(freeze["FROZEN_AT"]) < captured <= submitted <= recorded <= timestamp(row["closed_at"])
            or not 0 <= age <= 120 or abs(age - float(receipt["bar_age_seconds"])) > 0.001
            or (submitted - captured).total_seconds() > 120
            or abs((timestamp(order["submitted_at"]) - submitted).total_seconds()) > 120):
        raise ValueError("entry_frame_time_unverified")
    requested, filled = float(receipt["shares"]), float(order.get("filled_qty", 0))
    if (not math.isfinite(requested) or not math.isfinite(filled) or not 0 < filled <= requested
            or order.get("symbol") != row["symbol"] or order.get("side") != "buy"
            or receipt.get("broker_order_id") and receipt["broker_order_id"] != order["id"]):
        raise ValueError("entry_broker_join_mismatch")


def replay_order_collection(inputs, collection, cutoff, expected_orders):
    """Recompute completeness from stored request/response bytes, never a boolean."""
    requests = [row for row in collection["requests"] if row["input"].startswith("broker/orders-")]

    class ReplayTransport:
        def get(self, origin, path, params):
            if not requests:
                raise EvidenceError("order_trace_incomplete")
            row = requests.pop(0)
            if (row.get("origin"), row.get("method"), row.get("path"), row.get("params")) != (origin, "GET", path, params):
                raise EvidenceError("order_trace_scope_mismatch")
            raw = inputs[row["input"]]
            if digest(raw) != row["sha256"]:
                raise EvidenceError("order_trace_checksum")
            return raw

    orders, inventory = collect_orders(Recorder(ReplayTransport(), {}), cutoff, collection["captured_at"])
    if requests or orders != expected_orders or inventory != collection["order_inventory"]:
        raise EvidenceError("order_trace_result_mismatch")


def safe_output(output: Path, input_paths: list[Path], protected_roots: list[Path] | None = None) -> Path:
    resolved = output.resolve()
    if "organism_brain" in resolved.parts:
        raise EvidenceError("output_inside_brain")
    protected = list(protected_roots or [])
    for source in input_paths:
        if "organism_brain" in source.parts:
            protected.append(Path(*source.parts[:source.parts.index("organism_brain") + 1]))
    for path in protected:
        canonical = path.resolve()
        if resolved == canonical or canonical in resolved.parents:
            raise EvidenceError("output_inside_canonical_brain")
    for source in input_paths:
        target = source.resolve()
        if resolved == target or target in resolved.parents or resolved in target.parents:
            raise EvidenceError("output_aliases_input_tree")
        if output.exists() and source.exists() and output.samefile(source):
            raise EvidenceError("output_aliases_input")
    if output.is_symlink():
        raise EvidenceError("symlink_output")
    return resolved


def publish(output: Path, inputs: dict[str, bytes], collection: dict, report: dict,
            input_paths: list[Path] | None = None, protected_roots: list[Path] | None = None) -> Path:
    root = safe_output(output, input_paths or [], protected_roots)
    if date.fromisoformat(collection["session_date"]).isoformat() != collection["session_date"]:
        raise EvidenceError("invalid_output_session")
    input_index = {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(inputs.items())}
    manifest = {"schema": SCHEMA, "inputs": input_index, "collection": collection,
                "report_sha256": digest(encoded(report))}
    pack_id = digest(encoded(manifest))
    target = root / collection["session_date"] / pack_id
    if target.parent.is_symlink() or target.is_symlink():
        raise EvidenceError("symlink_pack_destination")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        verify_pack(target)
        if (target / "manifest.json").read_bytes() != encoded(manifest):
            raise EvidenceError("existing_pack_conflict")
        return target
    staging = Path(tempfile.mkdtemp(prefix=".incomplete-", dir=target.parent))
    try:
        for name, raw in inputs.items():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise EvidenceError("unsafe_input_name")
            path = staging / "inputs" / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            durable_write(path, raw)
        durable_write(staging / "report.json", encoded(report))
        durable_write(staging / "manifest.json", encoded(manifest))
        verify_pack(staging, verify_name=False)
        try:
            staging.rename(target)
        except OSError:
            if not target.exists():
                raise
            verify_pack(target)
            if (target / "manifest.json").read_bytes() != encoded(manifest):
                raise EvidenceError("concurrent_pack_conflict")
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_pack(path: Path, *, verify_name: bool = True) -> tuple[dict, dict]:
    if path.is_symlink():
        raise EvidenceError("symlink_pack")
    manifest_raw = stable_read(path / "manifest.json")
    manifest = json.loads(manifest_raw)
    if manifest.get("schema") != SCHEMA or (verify_name and path.name != digest(manifest_raw)):
        raise EvidenceError("invalid_pack_manifest")
    inputs = {}
    for name, expected in manifest["inputs"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise EvidenceError("unsafe_input_name")
        if (path / "inputs" / name).resolve() != path.resolve() / "inputs" / name:
            raise EvidenceError("symlink_pack_input_ancestor")
        raw = stable_read(path / "inputs" / name)
        if digest(raw) != expected["sha256"] or len(raw) != expected["bytes"]:
            raise EvidenceError("pack_input_checksum")
        inputs[name] = raw
    if digest(stable_read(path / "report.json")) != manifest["report_sha256"]:
        raise EvidenceError("pack_report_checksum")
    return inputs, manifest["collection"]


def durable_write(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def collect(root: Path, freeze: Path, activation: Path, release: Path, baseline: Path | None,
            day: str, transport, *, now: datetime | None = None, log_timezone=None) -> tuple[dict, dict, list]:
    now = now or datetime.now(timezone.utc)
    collection = {"session_date": day, "captured_at": now.isoformat(), "issues": [],
                  "collector": "actual_host_get_only", "log_timezone": log_timezone}
    inputs: dict[str, bytes] = {}
    paths = []
    recorder = Recorder(transport, inputs)
    try:
        calendar = recorder.get("broker/calendar.json", "paper", "/v2/calendar", {"start": day, "end": day})
        session = calendar_session(day, calendar, now)
        if session["state"] == "NO_SESSION":
            return inputs, collection, paths
        paths = capture_local(root, freeze, activation, release, baseline, inputs)
        inputs["runtime/container.json"] = transport.container_identity()
        cutoff = json.loads(inputs["local/freeze.json"])["FROZEN_AT"]
        for name, origin, endpoint in (
            ("broker/account.json", "paper", "/v2/account"),
            ("broker/clock.json", "paper", "/v2/clock"),
            ("broker/positions.json", "paper", "/v2/positions"),
            ("runtime/deploy.json", "local", "/api/v1/paper-monitor/deploy"),
            ("runtime/status.json", "local", "/api/v1/paper-monitor/organism/status")):
            recorder.get(name, origin, endpoint, {})
        orders, inventory = collect_orders(recorder, cutoff, now.isoformat())
        inputs["derived/orders.json"] = encoded(orders)
        collection["order_inventory"] = inventory
        # Detect unexpected concurrent trading instead of certifying a stale
        # bounded inventory. No upper limit on the final one-row probe.
        recorder.get("broker/final-order-probe.json", "paper", "/v2/orders",
                     {"status": "all", "limit": 1, "direction": "asc", "nested": "false", "after": (now - timedelta(microseconds=1)).isoformat()})
        recorder.get("broker/final-positions.json", "paper", "/v2/positions", {})
    except EvidenceError as exc:
        collection["issues"].append(str(exc))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        collection["issues"].append("collection_input_failure")
    finally:
        collection["requests"] = recorder.requests
    return inputs, collection, paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--activation", type=Path)
    parser.add_argument("--release", type=Path, help="Approved source/image/config identity for the current release")
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-pack", type=Path, help="Verify/recompute a previously collected immutable pack; no network")
    parser.add_argument("--log-timezone")
    args = parser.parse_args(argv)
    try:
        if args.replay_pack:
            inputs, collection = verify_pack(args.replay_pack)
            if collection["session_date"] != args.session:
                raise EvidenceError("replay_session_mismatch")
            paths = [args.replay_pack]
        else:
            if not args.freeze or not args.activation or not args.release:
                raise EvidenceError("freeze_activation_and_release_required")
            key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
            secret = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
            token = os.environ.get("INTRA_MONITOR_TOKEN")
            if not key or not secret or not token:
                raise EvidenceError("paper_credentials_and_monitor_token_required")
            transport = GetTransport(key, secret, token)
            inputs, collection, paths = collect(args.root, args.freeze, args.activation, args.release, args.baseline_dir,
                                                args.session, transport, log_timezone=args.log_timezone)
        report = analyze(inputs, collection)
        pack = publish(args.output, inputs, collection, report, paths, [args.root / "organism_brain"])
        print(json.dumps({"status": report["status"], "pack": str(pack),
                          "replayed": bool(args.replay_pack), "issues": report["issues"]}))
        return 0 if report["status"] in {"READY_FOR_REVIEW", "NO_SESSION"} else 1
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "BLOCKED", "reason": "invalid_or_unsafe_inputs", "replayed": bool(args.replay_pack)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
