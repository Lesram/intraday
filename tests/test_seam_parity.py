"""Intra 2.0 Phase 1 — Step 5 THIN-SEAM parity (candidate level).

The framework seam's ONLY mutation point is `_scan_entry_candidates`, and the
only thing it touches is each candidate's `.direction` (re-sourced through the
MomentumStrategy/StrategySelector). Everything downstream — confidence, gates,
ranking, Kelly sizing, exits — is untouched engine code. So if the candidate
list handed back is identical flag-on vs flag-off, full behavioral parity
follows by determinism.

This module proves that identity directly and exhaustively (every entry archetype
× every regime), proves the tripwire stays silent, and — with teeth — proves the
seam is NOT dead code: when the framework is forced to disagree, the override
actually changes direction AND the tripwire fires.

The heavy END-TO-END engine A/B (entered-set + share counts + exit reasons over a
real trading window) lives in scripts/verify_seam_parity.py; a slow-marked
wrapper around it is test_engine_level_parity below.
"""
from __future__ import annotations

import logging
import types as _types

import pandas as pd
import pytest

import backend.organism.live_engine as le
from backend.organism.alpha_scanner import AlphaScanner
from backend.organism.live_engine import OrganismLiveEngine

REGIMES = ["trending_up", "high_vol", "chop", "trending_down", "stress"]


def _df(readiness=0.0, squeeze=0.0, ret5=0.0, ret20=0.0, trend=0.0, n=60):
    """A feature frame whose last row carries the archetype values.

    >=50 rows so alpha_scanner.scan does not skip the symbol; constant columns so
    iloc[-1] is deterministic. Non-direction comp_* default sensibly via .get."""
    cols = {
        "comp_breakout_readiness": readiness, "comp_squeeze_momentum": squeeze,
        "ret_5d": ret5, "ret_20d": ret20, "trend_strength": trend,
        "comp_institutional_acc": 0.5, "comp_momentum_quality": 0.5,
        "comp_vol_price_div": 0.5, "vol_sma_ratio": 1.0, "close": 100.0,
    }
    return pd.DataFrame({k: [v] * n for k, v in cols.items()})


# Entry archetypes — each exercises a distinct _observable_direction branch,
# crucially including PURE MOMENTUM (readiness≈0) which sizes/gates very
# differently from breakouts and is the case most likely to diverge.
def _feats():
    return {
        "BRKO": _df(readiness=0.7),                       # bullish breakout
        "PUREM": _df(ret5=0.01),                          # pure momentum, readiness 0
        "SQZ": _df(readiness=0.55, squeeze=0.6),          # readiness+squeeze branch
        "RET20": _df(ret20=0.02, trend=0.1),             # 20d-momentum branch
        "FLAT": _df(),                                    # direction 0 -> no trade
        "SPY": _df(ret5=0.001),                           # benchmark / near-flat
    }


def _fake_engine(ml_isolation: bool):
    ns = _types.SimpleNamespace(
        alpha_scanner=AlphaScanner(top_n=5),
        signal_gen=_types.SimpleNamespace(is_trained=False),
        _ml_isolation_mode=ml_isolation,
        _strategy_selector=None,
    )
    ns._get_strategy_selector = _types.MethodType(
        OrganismLiveEngine._get_strategy_selector, ns)
    return ns


def _scan(ns, feats, regime):
    return OrganismLiveEngine._scan_entry_candidates(ns, feats, {}, regime)


def _fingerprint(cands):
    # The full surface the rest of the engine consumes off each candidate.
    return [(c.symbol, c.direction, round(c.composite_score, 9),
             round(c.breakout_score, 9)) for c in cands]


def test_seam_requires_drop_ml_from_gate_on():
    # The live config the framework models. If this ever flips, the seam's
    # activation guard (and these tests' premise) must be revisited.
    assert le.DROP_ML_FROM_GATE is True


@pytest.mark.parametrize("ml_isolation", [True, False])
@pytest.mark.parametrize("regime", REGIMES)
def test_candidate_parity_flag_on_equals_off(regime, ml_isolation, monkeypatch, caplog):
    """flag-on candidate list == flag-off, for every regime × ml-isolation."""
    ns = _fake_engine(ml_isolation)
    feats = _feats()

    monkeypatch.setattr(le, "FRAMEWORK_ROUTING_ENABLED", False)
    off = _fingerprint(_scan(ns, feats, regime))

    with caplog.at_level(logging.ERROR, logger="backend.organism.live_engine"):
        monkeypatch.setattr(le, "FRAMEWORK_ROUTING_ENABLED", True)
        on = _fingerprint(_scan(ns, feats, regime))

    assert on == off, f"seam changed candidates in regime={regime}: {off} != {on}"
    assert "FRAMEWORK SEAM MISMATCH" not in caplog.text, "tripwire fired on a no-op"


def test_seam_actually_routes_and_tripwire_has_teeth(monkeypatch, caplog):
    """Force the framework to DISAGREE with the scanner: the override must take
    effect (proving the seam is live, not dead code) AND the tripwire must fire.

    Uses trending_up so momentum is eligible and the selector emits candidates."""
    from backend.organism.strategies.momentum import MomentumStrategy

    ns = _fake_engine(ml_isolation=True)
    feats = {"BRKO": _df(readiness=0.7), "PUREM": _df(ret5=0.01), "SPY": _df()}

    monkeypatch.setattr(le, "FRAMEWORK_ROUTING_ENABLED", False)
    off = {c.symbol: c.direction for c in _scan(ns, feats, "trending_up")}
    assert any(d > 0 for d in off.values()), "fixture should yield long entries"

    # Make the framework flip the sign of every nonzero direction.
    orig_dir = MomentumStrategy._direction
    monkeypatch.setattr(MomentumStrategy, "_direction",
                        lambda self, row: -1.0 * orig_dir(self, row))

    ns2 = _fake_engine(ml_isolation=True)  # fresh selector picks up the patch
    with caplog.at_level(logging.ERROR, logger="backend.organism.live_engine"):
        monkeypatch.setattr(le, "FRAMEWORK_ROUTING_ENABLED", True)
        on = {c.symbol: c.direction for c in _scan(ns2, feats, "trending_up")}

    flipped = [s for s in off if off[s] != 0 and on.get(s) == -off[s]]
    assert flipped, f"override did not take effect: off={off} on={on}"
    assert "FRAMEWORK SEAM MISMATCH" in caplog.text, "tripwire failed to fire on real divergence"


def test_seam_inert_when_drop_ml_off(monkeypatch):
    """If ML is in the gate (DROP_ML_FROM_GATE False), the scanner's direction is
    ml-derived and the framework does not model it — the seam must NOT route."""
    ns = _fake_engine(ml_isolation=False)
    feats = _feats()
    monkeypatch.setattr(le, "DROP_ML_FROM_GATE", False)

    monkeypatch.setattr(le, "FRAMEWORK_ROUTING_ENABLED", False)
    off = _fingerprint(_scan(ns, feats, "trending_up"))
    monkeypatch.setattr(le, "FRAMEWORK_ROUTING_ENABLED", True)
    on = _fingerprint(_scan(ns, feats, "trending_up"))
    assert on == off  # seam guard is (FRAMEWORK_ROUTING_ENABLED and DROP_ML_FROM_GATE)


@pytest.mark.timeout(900)
@pytest.mark.slow
def test_engine_level_parity():
    """END-TO-END acceptance gate: run the real engine flag-off vs flag-on over a
    momentum-trading window; entered-set, sizes, exit reasons, ledger and equity
    curve must all match. Delegates to the evidence script."""
    import asyncio

    import scripts.verify_seam_parity as v
    rc = asyncio.run(v.main())
    assert rc == 0, "engine-level seam parity FAILED (see script output)"
