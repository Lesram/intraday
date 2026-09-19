"""Report real normalized cohorts using only temporary synthetic history."""
import json

import pandas as pd
import pytest

from scripts import phase2_gate as gate_report
from scripts import phase3_attribution_report as attribution


@pytest.mark.parametrize("cutoff,expected_count,expected_mean", [
    ("2026-08-02T00:00:00+00:00", 4, 8.45),
    ("2026-08-03T14:00:00+00:00", 2, 2.2),
    ("2026-08-04T00:00:00+00:00", 0, None),
])
def test_reports_share_active_cutoff_and_nonempty_normalized_regime(
    tmp_path, monkeypatch, capsys, cutoff, expected_count, expected_mean,
):
    # These timestamps are synthetic test boundaries, not activation approval.
    freeze = tmp_path / "param_freeze.json"
    freeze.write_text(json.dumps({"FROZEN_AT": cutoff}))
    trades = tmp_path / "trade_history.csv"
    pd.DataFrame({
        "closed_at": ["2026-08-03T13:59:00+00:00", "2026-08-03T14:00:00+00:00",
                      "2026-08-03T14:01:00+00:00", "2026-08-03T14:02:00+00:00"],
        "entry_source": ["alpha"]*4,
        "regime_at_entry": ["trending_up"]*4,
        "pnl": [10.0, 20.0, 2.0, 3.0],
        "entry_price": [100.0]*4,
        "shares": [10]*4,
    }).to_csv(trades, index=False)
    before = (freeze.read_bytes(), trades.read_bytes())
    for module in (gate_report, attribution):
        monkeypatch.setattr(module, "FREEZE", freeze)
        monkeypatch.setattr(module, "TRADES", trades)
    monkeypatch.setattr(attribution, "EVIDENCE", tmp_path / "no-shadow-feed.jsonl")
    # Use the actual loader and gate/statistic functions, not a mocked schema.
    assert gate_report.main() == 0
    gate_output = capsys.readouterr().out
    assert f"forward trades={expected_count}" in gate_output
    assert "state=INSUFFICIENT" in gate_output
    assert attribution.main() == 0
    output = capsys.readouterr().out
    assert f"forward corpus: {expected_count} trades" in output
    if expected_count:
        row = next(line for line in output.splitlines() if "trending_up" in line)
        assert "momentum" in row and f"n={expected_count}" in row
        assert f"exp={expected_mean:+.4f}" in row  # existing 3 bps round-trip default
    else:
        assert "empty — corpus fills from the freeze cutoff" in output
    assert (freeze.read_bytes(), trades.read_bytes()) == before
