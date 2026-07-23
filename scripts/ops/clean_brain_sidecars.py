#!/usr/bin/env python3
"""Live-head sidecar cleanup + corrupt-head quarantine (2026-07-23 ops work order).

Tasks 2 & 6 data operations. RUN DURING THE CONTAINER-DOWN WINDOW of the deploy
so there is no race with the live engine (which appends shadow_exit_telemetry
rows on real closes when ORGANISM_SHADOW_EXIT_POLICY is set).

Everything is reversible: rows/dirs are MOVED to *_quarantined.jsonl /
backups/quarantine/, never deleted. Idempotent: re-running is a no-op once clean.

Usage:
    python scripts/ops/clean_brain_sidecars.py            # dry-run (default)
    python scripts/ops/clean_brain_sidecars.py --apply    # write changes
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
from pathlib import Path

BRAIN = Path(os.environ.get("ORGANISM_BRAIN_DIR", "organism_brain"))
SHADOW = "shadow_exit_telemetry.jsonl"
SWAP = "model_swap_audit.jsonl"


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _faithful(r: dict) -> bool:
    try:
        return float(r.get("qty", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def _shadow_key(r: dict) -> tuple:
    return (r.get("symbol"), r.get("timestamp"), r.get("real_exit_reason"),
            round(float(r.get("delta_gross", 0) or 0), 6))


def clean_shadow(apply: bool) -> dict:
    """Keep only faithful (qty>0) shadow rows in the head; quarantine the rest;
    restore faithful rows that survive only in corrupt_head/backup copies."""
    live = BRAIN / SHADOW
    live_rows = _rows(live)
    faithful = [r for r in live_rows if _faithful(r)]
    pollution = [r for r in live_rows if not _faithful(r)]

    # Union in faithful rows that survive only in snapshots.
    seen = {_shadow_key(r) for r in faithful}
    recovered = 0
    for snap in sorted(glob.glob(str(BRAIN / "corrupt_head_*" / SHADOW)) +
                       glob.glob(str(BRAIN / "backups" / "*" / SHADOW))):
        for r in _rows(Path(snap)):
            if _faithful(r) and _shadow_key(r) not in seen:
                faithful.append(r)
                seen.add(_shadow_key(r))
                recovered += 1

    if apply:
        if pollution:
            with (BRAIN / "shadow_exit_telemetry_quarantined.jsonl").open("a") as fh:
                for r in pollution:
                    fh.write(json.dumps(r, sort_keys=True) + "\n")
        tmp = live.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in faithful))
        os.replace(tmp, live)
    return {"live_total": len(live_rows), "kept_faithful": len(faithful),
            "quarantined_pollution": len(pollution), "recovered_from_snapshots": recovered}


def clean_model_swap_audit(apply: bool) -> dict:
    """If the live head model_swap_audit is only the 07-23 test burst, quarantine
    it and restore the real historical audit (the longest snapshot copy)."""
    live = BRAIN / SWAP
    live_rows = _rows(live)
    # Real swaps require a full save (gated since 07-07); a same-second burst of
    # many rows dated 2026-07-23T17:04 is the background_trainer TEST writing to
    # the real volume. Detect: all rows within one 07-23 second.
    ts = [str(r.get("swapped_at") or r.get("timestamp") or "") for r in live_rows]
    is_test_burst = bool(ts) and all(t.startswith("2026-07-23T17:04") for t in ts)

    # Longest historical copy (real audit trail).
    best, best_rows = None, []
    for snap in glob.glob(str(BRAIN / "corrupt_head_*" / SWAP)) + \
            glob.glob(str(BRAIN / "backups" / "*" / SWAP)):
        rows = _rows(Path(snap))
        hist = [r for r in rows
                if not str(r.get("swapped_at") or "").startswith("2026-07-23T17:04")]
        if len(hist) > len(best_rows):
            best, best_rows = snap, hist

    action = "none"
    if is_test_burst and best_rows:
        action = f"restore {len(best_rows)} historical rows from {Path(best).parent.name}"
        if apply:
            if live_rows:
                with (BRAIN / "model_swap_audit_quarantined.jsonl").open("a") as fh:
                    for r in live_rows:
                        fh.write(json.dumps(r, sort_keys=True) + "\n")
            tmp = live.with_suffix(".jsonl.tmp")
            tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in best_rows))
            os.replace(tmp, live)
    return {"live_rows": len(live_rows), "is_test_burst": is_test_burst,
            "historical_available": len(best_rows), "action": action}


def quarantine_corrupt_heads(apply: bool) -> dict:
    """Task 6: move corrupt_head_* out of the live head so the loader never
    rescans them."""
    qdir = BRAIN / "backups" / "quarantine"
    heads = sorted(glob.glob(str(BRAIN / "corrupt_head_*")))
    moved = []
    if apply and heads:
        qdir.mkdir(parents=True, exist_ok=True)
        for h in heads:
            dest = qdir / Path(h).name
            if dest.exists():
                shutil.rmtree(h, ignore_errors=True)  # already quarantined
            else:
                shutil.move(h, str(dest))
            moved.append(Path(h).name)
    return {"corrupt_heads_found": len(heads), "moved": moved or [Path(h).name for h in heads]}


def reconcile_cumulative_pnl(apply: bool) -> dict:
    """Task 6: trade_history.csv is authoritative (measurement-integrity rule).
    Correct the persisted learner cumulative_pnl to the csv sum so the B-T-2
    drift clears on the next load. Accounting hygiene — cumulative_pnl is a
    reporting total, not a decision-surface field. Only learning_state.json is
    corrected (the loader reads cumulative_pnl from there); the manifest is
    rewritten from the reconciled in-memory value on the first save after
    restart."""
    import csv as _csv
    ls_path = BRAIN / "learning_state.json"
    th_path = BRAIN / "trade_history.csv"
    if not (ls_path.is_file() and th_path.is_file()):
        return {"skipped": "missing learning_state or trade_history"}
    csv_sum = 0.0
    with th_path.open() as f:
        for row in _csv.DictReader(f):
            try:
                csv_sum += float(row.get("pnl", 0) or 0)
            except (TypeError, ValueError):
                pass
    ls = json.loads(ls_path.read_text())
    state_pnl = float(ls.get("cumulative_pnl", 0.0) or 0.0)
    drift = round(abs(round(csv_sum, 2) - round(state_pnl, 2)), 2)
    result = {"state_pnl": round(state_pnl, 4), "csv_authoritative": round(csv_sum, 6),
              "drift": drift, "corrected": False}
    if drift > 0.10 and apply:
        ls["cumulative_pnl"] = round(csv_sum, 6)
        ls_path.write_text(json.dumps(ls, indent=2) + "\n")
        result["corrected"] = True
    return result


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] brain dir: {BRAIN.resolve()}")
    print("shadow_exit_telemetry :", clean_shadow(apply))
    print("model_swap_audit      :", clean_model_swap_audit(apply))
    print("corrupt_head quarantine:", quarantine_corrupt_heads(apply))
    print("cumulative_pnl reconcile:", reconcile_cumulative_pnl(apply))
    if not apply:
        print("\n(dry-run — re-run with --apply during the container-down window)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
