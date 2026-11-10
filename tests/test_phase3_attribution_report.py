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


def test_verdict_and_attribution_reports_exclude_reconciliation_artifacts(tmp_path, monkeypatch, capsys):
    # Audit 2026-10-05 C06-01 review: an external close keeps a mapped
    # entry_source, so both reports counted it as a momentum trade.
    freeze = tmp_path / "param_freeze.json"
    freeze.write_text(json.dumps({"FROZEN_AT": "2026-08-03T14:00:00+00:00"}))
    trades = tmp_path / "trade_history.csv"
    pd.DataFrame({
        "closed_at": ["2026-08-03T14:01:00+00:00", "2026-08-03T14:02:00+00:00",
                      "2026-08-03T14:03:00+00:00"],
        "entry_source": ["alpha"] * 3,
        "regime_at_entry": ["trending_up"] * 3,
        "exit_reason": ["trailing_stop", "external_close", "external_close"],
        "is_reconciliation_artifact": [False, True, True],
        "price_source": ["db_position_fills", "external_close_db_fills",
                         "external_close_approximate_observed_bar_close"],
        "pnl": [2.0, -18.0, -126.0],
        "entry_price": [100.0] * 3,
        "shares": [10] * 3,
    }).to_csv(trades, index=False)
    for module in (gate_report, attribution):
        monkeypatch.setattr(module, "FREEZE", freeze)
        monkeypatch.setattr(module, "TRADES", trades)
    monkeypatch.setattr(attribution, "EVIDENCE", tmp_path / "no-shadow-feed.jsonl")
    assert gate_report.main() == 0
    assert "forward trades=1" in capsys.readouterr().out
    assert attribution.main() == 0
    output = capsys.readouterr().out
    assert "forward corpus: 1 trades" in output
    row = next(line for line in output.splitlines() if "trending_up" in line)
    assert "momentum" in row and "n=1" in row and "exp=+1.7000" in row  # 2.0 minus 3 bps


def test_primary_six_bps_report_processes_preserve_inputs_and_parent_env(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"FROZEN_AT": "2026-08-03T14:00:00+00:00"}))
    trades = tmp_path / "trades.csv"
    pd.DataFrame({
        "closed_at": ["2026-08-03T14:01:00+00:00", "2026-08-03T14:02:00+00:00"],
        "entry_source": ["alpha"]*2, "regime_at_entry": ["trending_up"]*2,
        "pnl": [2.0, 3.0], "entry_price": [100.0]*2, "shares": [10]*2,
    }).to_csv(trades, index=False)
    before = (freeze.read_bytes(), trades.read_bytes())
    parent_cost = os.environ.get("ORGANISM_COST_BPS")
    env = dict(os.environ)
    env["ORGANISM_COST_BPS"] = "6"  # report child only, not the runtime environment
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    program = """
import importlib, sys
from pathlib import Path
from backend.organism.costing import DEFAULT_COST_BPS
assert DEFAULT_COST_BPS == 6.0
module = importlib.import_module(sys.argv[1])
module.FREEZE, module.TRADES = Path(sys.argv[2]), Path(sys.argv[3])
module.EVIDENCE = Path(sys.argv[4])
assert module.load_forward_corpus(str(module.TRADES), '2026-08-03T14:00:00+00:00')['net_pnl'].tolist() == [1.4, 2.4]
raise SystemExit(module.main())
"""
    for name in ("scripts.phase2_gate", "scripts.phase3_attribution_report"):
        result = subprocess.run(
            [sys.executable, "-c", program, name, str(freeze), str(trades), str(tmp_path/"none.jsonl")],
            env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        if name.endswith("phase2_gate"):
            assert "forward trades=2" in result.stdout
        else:
            assert "forward corpus: 2 trades" in result.stdout
            assert "exp=+1.9000" in result.stdout  # gross mean 2.5 minus 0.6
    assert (freeze.read_bytes(), trades.read_bytes()) == before
    assert os.environ.get("ORGANISM_COST_BPS") == parent_cost


def _block(output, header):
    """Lines of the phase2_gate CLI block that starts with `header`."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header))
    return [line.strip() for line in lines[start + 1:start + 4]]


def test_reports_print_n_per_source_and_withhold_ambiguous_verdicts(tmp_path, monkeypatch, capsys):
    # Audit O2-02: while ML is isolated a pure breakout is recorded as
    # 'alpha+breakout' with predicted_return 0.005 + 0.015 * composite
    # (0.01325-0.0200); alpha trades carry exactly 0.01. Both with ml_spoke False.
    freeze = tmp_path / "param_freeze.json"
    freeze.write_text(json.dumps({"FROZEN_AT": "2026-08-03T14:00:00+00:00"}))
    trades = tmp_path / "trade_history.csv"
    ledger = pd.DataFrame({
        "closed_at": [f"2026-08-03T14:0{m}:00+00:00" for m in range(1, 6)],
        "entry_source": ["alpha", "alpha+breakout", "alpha+breakout", "alpha+breakout", "breakout"],
        "regime_at_entry": ["trending_up", "trending_up", "trending_up", "low_vol", "chop"],
        "predicted_return": [0.01, 0.01, 0.013544, 0.0175, 0.01],
        "ml_spoke": [False] * 5,
        "pnl": [2.0, 3.0, -1.0, 1.0, 0.5], "entry_price": [100.0] * 5, "shares": [10] * 5,
    })
    ledger.to_csv(trades, index=False)
    for module in (gate_report, attribution):
        monkeypatch.setattr(module, "FREEZE", freeze)
        monkeypatch.setattr(module, "TRADES", trades)
    monkeypatch.setattr(attribution, "EVIDENCE", tmp_path / "no-shadow-feed.jsonl")
    split = "n per source: alpha=2 pure_breakout=3 ambiguous=0 orb=0 mean_reversion=0"

    assert gate_report.main() == 0
    output = capsys.readouterr().out
    assert "forward trades=5" in output and split in output
    assert _block(output, "momentum")[:2] == ["state=INSUFFICIENT  n=2  look=None  t=None",
                                             "n per source: alpha=2 pure_breakout=0 ambiguous=0"]
    assert _block(output, "breakout")[:2] == ["state=INSUFFICIENT  n=3  look=None  t=None",
                                             "n per source: alpha=0 pure_breakout=3 ambiguous=0"]
    assert attribution.main() == 0
    output = capsys.readouterr().out
    assert "forward corpus: 5 trades" in output and split in output
    capital = {tuple(line.split()[:2]): line for line in output.splitlines() if "exp=" in line}
    assert "n=2 " in capital[("momentum", "trending_up")]
    assert "n=1 " in capital[("breakout", "trending_up")] and "n=1 " in capital[("breakout", "low_vol")]
    gates = {line.split()[0]: line for line in output.splitlines() if " state=" in line}
    assert "n=2  [n per source: alpha=2 pure_breakout=0 ambiguous=0]" in gates["momentum"]
    assert "n=3  [n per source: alpha=0 pure_breakout=3 ambiguous=0]" in gates["breakout"]

    # An 'alpha+breakout' trade ML spoke on cannot be split: both verdicts withheld.
    ledger.loc[len(ledger)] = ["2026-08-03T14:06:00+00:00", "alpha+breakout", "high_vol",
                               0.0142, True, 1.0, 100.0, 10]
    ledger.to_csv(trades, index=False)
    assert gate_report.main() == 0
    output = capsys.readouterr().out
    assert "n per source: alpha=2 pure_breakout=3 ambiguous=1 orb=0 mean_reversion=0" in output
    momentum, breakout = _block(output, "momentum"), _block(output, "breakout")
    assert momentum[0] == "state=AMBIGUOUS_ATTRIBUTION  n=2  look=None  t=None"
    assert momentum[1] == "n per source: alpha=2 pure_breakout=0 ambiguous=1"
    assert momentum[2].startswith("1 'alpha+breakout' trade(s) could be alpha or pure breakout")
    assert breakout[0] == "state=AMBIGUOUS_ATTRIBUTION  n=3  look=None  t=None"
    assert breakout[1] == "n per source: alpha=0 pure_breakout=3 ambiguous=1"
    assert "state=INSUFFICIENT" in _block(output, "orb")[0]
    assert attribution.main() == 0
    output = capsys.readouterr().out
    assert any(line.split()[:2] == ["ambiguous", "high_vol"] and "n=1" in line
               for line in output.splitlines())
    gates = {line.split()[0]: line for line in output.splitlines() if " state=" in line}
    assert "state=AMBIGUOUS_ATTRIBUTION n=2  [n per source: alpha=2 pure_breakout=0 ambiguous=1]" \
        in gates["momentum"]
    assert "state=AMBIGUOUS_ATTRIBUTION n=3  [n per source: alpha=0 pure_breakout=3 ambiguous=1]" \
        in gates["breakout"]
    assert "PASS" not in output and "FAIL" not in output
