#!/usr/bin/env bash
# Run on your Mac from the repo. Does two things:
#   (1) commits the AlpacaClient.__del__ defensive fix
#   (2) runs the test tiers that CAN'T run in the cloud sandbox
#       (no Postgres/Redis, no broker egress, heavy ML libs skipped there)
#
# Prereqs: your ./venv exists, and if your integration tests need a DB/Redis,
# bring services up first (e.g. `docker compose up -d`).
set -uo pipefail
cd "$HOME/VS/intra"
PY=./venv/bin/python
LOG="test_run_$(date +%Y%m%d_%H%M).log"

echo ">> Step 1: commit the __del__ defensive fix"
rm -f .git/index.lock
git add backend/data/alpaca_client.py
git commit -m "fix(alpaca): guard __del__ against partially-initialized client" \
  -m "AlpacaClient.__del__ read self.connected unconditionally, raising AttributeError during GC when __init__ failed before setting it. Guard with getattr(self, 'connected', False)." \
  || echo "   (nothing to commit — already applied?)"
echo

echo ">> Step 2: run the live/integration tiers (output also saved to $LOG)"
echo "   If integration needs services, run first:  docker compose up -d"
echo
{
  echo "===== integration ====="
  $PY -m pytest -m integration -q -ra
  echo "===== live (paper workflow) ====="
  $PY -m pytest -m live -q -ra
  echo "===== api + services ====="
  $PY -m pytest -m "api or services" -q -ra
  echo "===== performance SLOs ====="
  $PY -m pytest -m performance -q -ra
  echo "===== full sweep (everything, incl. heavy-ML paths) ====="
  $PY -m pytest -q -ra
} 2>&1 | tee "$LOG"

echo
echo ">> Done. Summary saved to $LOG"
echo ">> Share that file back with me and I'll triage anything red (env vs real)."
