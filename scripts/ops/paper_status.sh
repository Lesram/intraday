#!/bin/bash
# `make paper-status` — 2026-07-23 ops work order Task 3.
# One glance at whether the paper stack is up, saving its brain, and trading.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

echo "=== containers ==="
if docker info >/dev/null 2>&1; then
    docker ps -a --filter "name=intra-" --filter "name=trading_platform_db_paper" \
        --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null
else
    echo "  Docker daemon NOT running (run 'make paper-up')"
fi

echo ""
echo "=== brain save freshness ==="
python3 - <<'PY'
import datetime, json, os
try:
    d = json.load(open("organism_brain/manifest.json"))
    dt = datetime.datetime.fromisoformat(d["saved_at"])
    age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 60.0
    flag = "  <-- STALE (>15 min)" if age > 15 else ""
    print(f"  manifest.saved_at = {d['saved_at']}  (age {age:.1f} min){flag}")
    print(f"  generation={d.get('generation')}  total_trades={d.get('total_trades')}  "
          f"cumulative_pnl={d.get('cumulative_pnl')}")
    sc = "organism_brain/.save_complete"
    print(f"  .save_complete = {open(sc).read().strip() if os.path.exists(sc) else 'MISSING'}")
except Exception as e:
    print(f"  could not read organism_brain/manifest.json: {e}")
PY

echo ""
echo "=== last trade_history row ==="
if [ -f organism_brain/trade_history.csv ]; then
    head -1 organism_brain/trade_history.csv | cut -d, -f1-6
    tail -1 organism_brain/trade_history.csv | cut -d, -f1-6
else
    echo "  (no trade_history.csv)"
fi
