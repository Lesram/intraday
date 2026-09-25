"""Explicitly selected offline evidence; no production patch or automatic stage."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
INSTALLED = Path('/Users/marselkei/VS/intra')
SOURCES = ('backend/organism/composite_indicators.py', 'backend/organism/ml_features.py',
           'backend/organism/alpha_scanner.py', 'backend/organism/strategies/momentum.py',
           'backend/organism/confidence_lab.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposed_function(module):
    original = inspect.getsource(module._safe_div)
    assert original.count('a_zero = a.abs() < 1e-12') == 1
    replacement = original.replace('a_zero = a.abs() < 1e-12', 'a_zero = abs(a) < 1e-12')
    namespace = dict(vars(module))
    exec(compile(replacement, '<evaluation-only-abs-numerator>', 'exec'), namespace)
    return namespace['_safe_div'], original, replacement


def candidate_summary(candidate):
    return {name: getattr(candidate, name) for name in (
        'symbol', 'composite_score', 'breakout_score', 'volume_score', 'momentum_score',
        'regime_score', 'institutional_score', 'momentum_quality_score', 'direction',
        'expected_return_source')}


def test_original_and_proposed_composite_contract(tmp_path, monkeypatch):
    for key in ('TESTING', 'USE_MOCK_DATA', 'USE_MOCK_BROKER'):
        assert os.environ.get(key) == 'true'
    monkeypatch.setenv('ORGANISM_LIVE_TIMEFRAME', '1Min')
    monkeypatch.chdir(tmp_path)
    before = {name: sha(ROOT / name) for name in SOURCES}
    installed = {name: sha(INSTALLED / name) for name in SOURCES}
    assert before == installed, 'Current computation must be source-identical to installed files'
    from scripts.diagnostics.profile_paper_pipeline import frame_hash, synthetic_bars
    from backend.organism import composite_indicators as composite
    from backend.organism.ml_features import compute_ml_features
    from backend.organism.alpha_scanner import AlphaScanner

    proposal, original_text, proposed_text = proposed_function(composite)
    original_function = composite._safe_div
    numerators = pd.Series([0., 1., -1., 1e-13, np.nan, 2.])
    denominators = pd.Series([0., 0., 2., 1e-13, 1., -2.])
    assert_series_equal(original_function(numerators, denominators), proposal(numerators, denominators))
    assert pd.isna(proposal(0, pd.Series([0.])).iloc[0])
    assert proposal(100, pd.Series([2.])).iloc[0] == 50.
    assert proposal(100, pd.Series([0.])).iloc[0] == 1e12
    columns = list(composite.COMPOSITE_COLUMNS)
    observations = []
    for rows in (80, 500):
        frames = {f'SYN{i:03d}': synthetic_bars(i, rows) for i in (1, 2, 3)}
        input_hashes = {symbol: frame_hash(frame) for symbol, frame in frames.items()}
        old, proposed = {}, {}
        for symbol, frame in frames.items():
            caught = None
            try:
                composite.compute_composite_indicators(frame)
            except AttributeError as error:
                caught = {'type': type(error).__name__, 'message': str(error),
                          'frames': [{'file': Path(item.filename).name, 'line': item.lineno, 'function': item.name}
                                     for item in traceback.extract_tb(error.__traceback__)]}
            assert caught is not None
            old[symbol] = compute_ml_features(frame, bars_per_day=390)
            assert (old[symbol][columns] == 0.).all().all()
            with patch.object(composite, '_safe_div', proposal):
                direct = composite.compute_composite_indicators(frame)
                proposed[symbol] = compute_ml_features(frame, bars_per_day=390)
            assert composite._safe_div is original_function
            assert np.isfinite(direct[columns].to_numpy()).all()
            assert (direct[columns] != 0.).any().all()
            # Full ML computation supplies extra base indicators (e.g. ADX);
            # raw-only direct composites need not equal that richer context.
            assert np.isfinite(proposed[symbol][columns].to_numpy()).all()
            assert (proposed[symbol][columns] != 0.).any().all()
            other = [column for column in old[symbol] if column not in columns and column != '_nan_missingness']
            assert_frame_equal(old[symbol][other], proposed[symbol][other])
            observations.append({'rows': rows, 'symbol': symbol, 'input_sha256': input_hashes[symbol],
                'original_direct_exception': caught, 'original_feature_sha256': frame_hash(old[symbol]),
                'proposed_feature_sha256': frame_hash(proposed[symbol]),
                'original_all_seven_zero': True,
                'proposed_nonzero_cells_by_column': {column: int((proposed[symbol][column] != 0).sum()) for column in columns},
                'original_last_composites': {column: float(old[symbol][column].iloc[-1]) for column in columns},
                'proposed_last_composites': {column: float(proposed[symbol][column].iloc[-1]) for column in columns},
                'original_nan_missingness': float(old[symbol]['_nan_missingness'].iloc[-1]),
                'proposed_nan_missingness': float(proposed[symbol]['_nan_missingness'].iloc[-1]),
                'other_features_exactly_equal': True})
        assert input_hashes == {symbol: frame_hash(frame) for symbol, frame in frames.items()}
        scans = []
        for regime in ('unknown', 'trending', 'high_vol', 'stress'):
            result = {'rows': rows, 'regime': regime, 'ml_signals': 0,
                      'learning_mode': True, 'derive_direction_from_observables': True}
            for label, features in (('original', old), ('proposal', proposed)):
                scanner = AlphaScanner(top_n=3)
                candidates = scanner.scan(features, {}, current_regime=regime, ml_is_trained=False,
                                          learning_mode=True, derive_direction_from_observables=True)
                result[label] = {'qualified_count': len(candidates),
                                 'qualified': [candidate_summary(item) for item in candidates],
                                 'all_scored': [candidate_summary(item) for item in scanner._last_full_scan]}
            scans.append(result)
        if rows == 80:
            alpha_comparisons = scans
        else:
            alpha_comparisons.extend(scans)
    assert before == {name: sha(ROOT / name) for name in SOURCES}
    assert installed == {name: sha(INSTALLED / name) for name in SOURCES}
    assert 'backend.organism.live_engine' not in sys.modules
    report = {'status': 'DEFECT_REPRODUCED_COUNTERFACTUAL_EVALUATED_ONLY',
        'source_sha256': before, 'installed_source_sha256': installed, 'installed_source_identical': True,
        'source_unchanged': True, 'python': sys.version, 'pandas': pd.__version__, 'numpy': np.__version__,
        'proposal': {'original_expression': 'a_zero = a.abs() < 1e-12',
                     'evaluation_only_expression': 'a_zero = abs(a) < 1e-12',
                     'original_function_source_sha256': hashlib.sha256(original_text.encode()).hexdigest(),
                     'proposed_function_source_sha256': hashlib.sha256(proposed_text.encode()).hexdigest(),
                     'series_parity_and_zero_over_zero_nan_preserved': True,
                     'production_patch_applied': False},
        'scalar_call_sites': [{'function': 'volume_price_divergence', 'line': 159},
                              {'function': 'mean_reversion_extremity', 'line': 341},
                              {'function': 'momentum_quality_score', 'line': 484}],
        'observations': observations, 'alpha_comparisons': alpha_comparisons,
        'scope': {'synthetic_ohlcv_only': True, 'bars_per_day': 390, 'timeframe': '1Min',
                  'engine_imported': False, 'models_loaded': False, 'broker_or_runtime_calls': False,
                  'cache_used': False},
        'limits': ['This tests the feature and alpha scoring path, not full replay or order/exit execution.',
                   'Changing these computed fields changes possible strategy inputs; no strategy acceptance or profitability claim.',
                   'No actual Sept24 input frames or saved model state are evaluated; this cannot attribute that day\'s zero trades.',
                   'Synthetic candidate eligibility is upstream of admission, timing, risk, liquidity and execution gates.',
                   'Installed file equality is a source observation, not a fresh live-process/image attestation.']}
    with (OUT/'results.json').open('x') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write('\n')


def test_all_three_scalar_call_sites(tmp_path, monkeypatch):
    for key in ('TESTING', 'USE_MOCK_DATA', 'USE_MOCK_BROKER'):
        assert os.environ.get(key) == 'true'
    monkeypatch.setenv('ORGANISM_LIVE_TIMEFRAME', '1Min')
    monkeypatch.chdir(tmp_path)
    from scripts.diagnostics.profile_paper_pipeline import synthetic_bars
    from backend.organism import composite_indicators as composite
    proposal, _, _ = proposed_function(composite)
    original = composite._safe_div
    source_before = sha(ROOT / SOURCES[0])
    rows = synthetic_bars(1, 80)
    findings = []
    for name, line in (('volume_price_divergence', 159), ('mean_reversion_extremity', 341),
                       ('momentum_quality_score', 484)):
        function = getattr(composite, name)
        assert '_safe_div(100,' in (ROOT / SOURCES[0]).read_text().splitlines()[line-1]
        failure = None
        try:
            function(rows)
        except AttributeError as error:
            failure = {'type': type(error).__name__, 'message': str(error)}
        assert failure is not None
        with patch.object(composite, '_safe_div', proposal):
            result = function(rows)
        assert composite._safe_div is original
        assert len(result) == len(rows) and np.isfinite(result.to_numpy()).all()
        findings.append({'function': name, 'source_line': line, 'original': failure,
                         'proposal_finite_rows': len(result)})
    assert sha(ROOT / SOURCES[0]) == source_before
    with (OUT/'call_site_results.json').open('x') as handle:
        json.dump({'source_sha256': source_before, 'source_unchanged': True,
                   'production_correction_applied': False, 'findings': findings}, handle, indent=2)
        handle.write('\n')
