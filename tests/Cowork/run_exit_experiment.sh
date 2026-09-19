#!/usr/bin/env bash
# Tier-2 exit-logic experiment — run on your Mac (fast CPU + real venv).
#
# Runs the REAL organism engine in COSTED replay (next-open fills + auto spread +
# >=1bps slippage) across exit-policy arms, over cached minute bars
# (artifacts/**/bars*.pkl). Fully offline: no DB, no network, no broker.
#
# New code exercised this run (already in your working tree):
#   - backend/organism/experimental/alt_exit_engine.py   (NON-production AltExitEngine)
#   - scripts/edge_experiments.py                         (+ time_only / retracement arms,
#                                                           + real per-arm TradeRecord metrics)
# Nothing in the live trading path is touched; the policy is swapped only inside
# the replay subprocess via an env-gated monkeypatch.
set -uo pipefail
cd "$HOME/VS/intra"
PY=./venv/bin/python
ARMS="baseline,wide_exits,time_only,retracement,chop_standdown,combined"

echo ">> 1) SMOKE (500 ticks) — confirms all six arms execute and the AltExitEngine path works"
$PY scripts/edge_experiments.py --arms "$ARMS" --max-ticks 500 \
  || { echo "!! smoke run failed — stop and check the traceback above"; exit 1; }

echo
read -rp ">> Smoke OK? Press Enter to run the FULL replay (all cached bars; a few min/arm), or Ctrl-C to stop. " _

echo ">> 2) FULL replay"
$PY scripts/edge_experiments.py --arms "$ARMS"

echo
echo ">> Done. Output: artifacts/edge_experiments_<UTCdate>/  (report.json + one JSON per arm)."
echo ">> Each arm JSON now carries REAL metrics from the engine's TradeRecords:"
echo ">>   th_net_pnl, th_expectancy, th_profit_factor, th_win_rate,"
echo ">>   th_pnl_by_exit_reason, th_mfe_giveback"
echo ">> Share report.json back with me and I'll do the Gate-2 read:"
echo ">>   expectancy > 0 at t>=2 after costs, PF >= 1.3, MFE retention vs baseline,"
echo ">>   and stability across two non-overlapping sub-periods."
