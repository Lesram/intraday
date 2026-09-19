"""Stage-1 capital configuration validator.

Run before any Stage-1 cutover. Verifies that all risk-control env
vars are set to Stage-1-safe values (and that we're NOT still in
paper mode if we mean to be live).

Usage:
    python scripts/runtime/check_stage1_config.py        # check current env
    python scripts/runtime/check_stage1_config.py --live # also assert live mode

Returns exit 0 on green, exit 1 on any violation.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any


# Stage-1 expected values (from STAGE_1_CAPITAL_PLAN.md)
STAGE_1_UNIVERSE = {"SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "IWM"}

CHECKS: list[dict[str, Any]] = [
    {
        "name": "ORGANISM_LIVE_SYMBOLS",
        "expected_subset_of": STAGE_1_UNIVERSE,
        "max_count": 8,
        "max_count_msg": "Stage-1 should trade <= 8 symbols",
    },
    {
        "name": "ORGANISM_MAX_POSITIONS",
        "expected_int": 2,
        "max_int": 3,
    },
    {
        "name": "ORGANISM_ALPHA_TOP_N",
        "max_int": 3,
    },
    {
        "name": "ORGANISM_MAX_NOTIONAL",
        "min_float": 50.0,
        "max_float": 200.0,
        "must_be_positive": True,  # 0 = disabled, BAD for Stage-1
    },
    {
        "name": "ORGANISM_MAX_DAILY_LOSS",
        "min_float": 10.0,
        "max_float": 50.0,
        "must_be_positive": True,
    },
    {
        "name": "ORGANISM_DRAWDOWN_KILL_PCT",
        "min_float": 0.03,
        "max_float": 0.08,
    },
    {
        "name": "ORGANISM_LIVE_TIMEFRAME",
        "expected_value": "1Min",
    },
    {
        "name": "ORGANISM_EXPLORATION_ENABLED",
        "expected_value_lower": "false",  # exploration is REMOVED
    },
]


def check_env_var(c: dict[str, Any], live_mode: bool) -> tuple[bool, str]:
    name = c["name"]
    val = os.getenv(name)
    if val is None or val == "":
        return False, f"{name}: NOT SET"

    msgs: list[str] = []

    if "expected_value" in c:
        if val != c["expected_value"]:
            msgs.append(f"expected '{c['expected_value']}' got '{val}'")

    if "expected_value_lower" in c:
        if val.lower() != c["expected_value_lower"].lower():
            msgs.append(f"expected '{c['expected_value_lower']}' got '{val}'")

    if "expected_int" in c:
        try:
            iv = int(val)
            if iv != c["expected_int"]:
                msgs.append(f"expected int {c['expected_int']} got {iv}")
        except ValueError:
            msgs.append(f"not int: '{val}'")

    if "max_int" in c:
        try:
            iv = int(val)
            if iv > c["max_int"]:
                msgs.append(f"value {iv} exceeds max {c['max_int']}")
        except ValueError:
            msgs.append(f"not int: '{val}'")

    if "min_float" in c or "max_float" in c:
        try:
            fv = float(val)
            if "min_float" in c and fv < c["min_float"]:
                msgs.append(f"value {fv} below min {c['min_float']}")
            if "max_float" in c and fv > c["max_float"]:
                msgs.append(f"value {fv} exceeds max {c['max_float']}")
            if c.get("must_be_positive") and fv <= 0:
                msgs.append(
                    f"value {fv} must be positive (0 disables this guard)"
                )
        except ValueError:
            msgs.append(f"not float: '{val}'")

    if "expected_subset_of" in c:
        symbols = {s.strip().upper() for s in val.split(",") if s.strip()}
        outside = symbols - c["expected_subset_of"]
        if outside:
            msgs.append(f"contains symbols outside Stage-1 universe: {outside}")
        if "max_count" in c and len(symbols) > c["max_count"]:
            msgs.append(
                f"{len(symbols)} symbols, max {c['max_count']}: "
                f"{c.get('max_count_msg', '')}"
            )

    if msgs:
        return False, f"{name} = '{val}': " + "; ".join(msgs)
    return True, f"{name} = '{val}': OK"


def check_alpaca_mode(live_mode: bool) -> tuple[bool, str]:
    val = os.getenv("ALPACA_PAPER", "true").lower()
    if live_mode:
        if val != "false":
            return False, (
                f"ALPACA_PAPER='{val}' but Stage-1 cutover requires 'false'. "
                "Live capital cannot route through paper account."
            )
        return True, "ALPACA_PAPER=false (LIVE) — confirmed"
    else:
        if val == "false":
            return False, (
                f"ALPACA_PAPER='false' but --live not specified. "
                "Aborting: refuse to silently validate live config."
            )
        return True, "ALPACA_PAPER=true (paper)"


def check_alpaca_keys() -> tuple[bool, str]:
    key = os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY", "")
    sec = os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY", "")
    if not key or not sec:
        return False, "Alpaca keys missing (ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY)"
    return True, f"Alpaca keys present (key={key[:6]}..., secret={sec[:4]}...)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Stage-1 config")
    parser.add_argument("--live", action="store_true",
                        help="Also assert ALPACA_PAPER=false (real-money cutover check)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"  STAGE-1 CAPITAL CONFIG CHECK ({'LIVE' if args.live else 'paper'} mode)")
    print("=" * 60)

    all_ok = True

    # Check Alpaca mode + keys
    for ok, msg in (check_alpaca_mode(args.live), check_alpaca_keys()):
        marker = "✓" if ok else "✗"
        print(f"  {marker} {msg}")
        if not ok:
            all_ok = False

    # Check each Stage-1 env var
    for c in CHECKS:
        ok, msg = check_env_var(c, args.live)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {msg}")
        if not ok:
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("  RESULT: GREEN — Stage-1 config valid")
        return 0
    else:
        print("  RESULT: RED — Stage-1 config has violations above")
        print()
        print("  Reference: STAGE_1_CAPITAL_PLAN.md for required values.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
