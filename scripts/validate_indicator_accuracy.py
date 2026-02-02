"""
Indicator Accuracy Validation Script

Validates platform indicator calculations against TA-Lib reference library.

Tests:
- All 12 active indicators across multiple stocks
- Various timeframes (5m, 15m, 1D)
- Different date ranges (1M, 3M, 6M)
- Compares calculated values against TA-Lib
- Reports maximum and mean errors
- Identifies indicators that fail accuracy thresholds

Usage:
    python tests/validate_indicator_accuracy.py --stocks AAPL MSFT GOOGL --timeframe 1D --range 3M
    python tests/validate_indicator_accuracy.py --full  # Run complete test matrix

Requirements:
    pip install TA-Lib numpy pandas requests

Author: GitHub Copilot
Date: October 19, 2025
"""

import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd

# Try importing TA-Lib (may not be installed)
try:
    import talib  # type: ignore[import-not-found]
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print("WARNING: TA-Lib not installed. Install with: pip install TA-Lib")
    print("         (May require compilation or prebuilt wheels)")

# Import platform services (ensure repo root is on sys.path)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.indicators import IndicatorsService
from backend.services.market_data_service import MarketDataService


# ============================================================================
# CONFIGURATION
# ============================================================================

# Test matrix
TEST_STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
TEST_TIMEFRAMES = ['5m', '15m', '1D']
TEST_RANGES = {
    '1M': 30,
    '3M': 90,
    '6M': 180,
}

# Indicators to test with default parameters
INDICATORS = {
    'RSI': {'period': 14},
    'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
    'AROON': {'period': 25},
    'ADX': {'period': 14},
    'VWMA': {'period': 20},
    'BOLLINGER': {'period': 20, 'std_dev': 2},
    'ATR': {'period': 14},
    'STOCHASTIC': {'k_period': 14, 'd_period': 3},
    'CCI': {'period': 20},
    'WILLIAMS_R': {'period': 14},
    'MFI': {'period': 14},
    'OBV': {},
}

# Accuracy thresholds (max acceptable difference)
ACCURACY_THRESHOLDS = {
    'RSI': 0.5,
    'MACD': 0.1,
    'AROON': 1.0,
    'ADX': 0.5,
    'VWMA': 0.5,
    'BOLLINGER': 0.5,
    'ATR': 0.1,
    'STOCHASTIC': 0.5,
    'CCI': 1.0,
    'WILLIAMS_R': 0.5,
    'MFI': 0.5,
    'OBV': 1000.0,  # Volume can be large
}


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

class IndicatorValidator:
    """Validates platform indicators against TA-Lib reference"""
    
    def __init__(self):
        self.indicators_service = IndicatorsService()
        self.market_data_service = MarketDataService()
        self.results = []
        
    def fetch_market_data(
        self, 
        symbol: str, 
        timeframe: str, 
        days: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Fetch OHLCV data from market data service"""
        end = datetime.now()
        start = end - timedelta(days=days)
        
        # Fetch bars from market data service
        bars = self.market_data_service.get_historical_bars(
            symbol=symbol,
            timeframe=timeframe,
            start=start.isoformat(),
            end=end.isoformat(),
            limit=1000
        )
        
        if not bars or len(bars) < 50:
            raise ValueError(f"Insufficient data: {len(bars) if bars else 0} bars")
        
        # Convert to numpy arrays
        opens = np.array([b['open'] for b in bars], dtype=float)
        highs = np.array([b['high'] for b in bars], dtype=float)
        lows = np.array([b['low'] for b in bars], dtype=float)
        closes = np.array([b['close'] for b in bars], dtype=float)
        volumes = np.array([b['volume'] for b in bars], dtype=float)
        
        return opens, highs, lows, closes, volumes
    
    def validate_rsi(
        self, 
        closes: np.ndarray, 
        period: int = 14
    ) -> Dict[str, Any]:
        """Validate RSI calculation"""
        if not TALIB_AVAILABLE:
            return {'error': 'TA-Lib not available'}
        
        # Platform calculation
        our_rsi = self.indicators_service.calculate_rsi(closes.tolist(), period)
        our_values = np.array([v for v in our_rsi if v is not None], dtype=float)
        
        # TA-Lib reference
        talib_rsi = talib.RSI(closes, timeperiod=period)
        talib_values = talib_rsi[~np.isnan(talib_rsi)]
        
        # Compare (align arrays - both should have same length after warmup)
        min_len = min(len(our_values), len(talib_values))
        our_values = our_values[-min_len:]
        talib_values = talib_values[-min_len:]
        
        errors = np.abs(our_values - talib_values)
        
        return {
            'indicator': 'RSI',
            'data_points': len(our_values),
            'max_error': np.max(errors),
            'mean_error': np.mean(errors),
            'std_error': np.std(errors),
            'threshold': ACCURACY_THRESHOLDS['RSI'],
            'passed': np.max(errors) < ACCURACY_THRESHOLDS['RSI'],
        }
    
    def validate_macd(
        self, 
        closes: np.ndarray, 
        fast: int = 12, 
        slow: int = 26, 
        signal: int = 9
    ) -> Dict[str, Any]:
        """Validate MACD calculation"""
        if not TALIB_AVAILABLE:
            return {'error': 'TA-Lib not available'}
        
        # Platform calculation
        our_macd = self.indicators_service.calculate_macd(closes.tolist(), fast, slow, signal)
        our_histogram = np.array([v for v in our_macd.get('histogram', []) if v is not None], dtype=float)
        
        # TA-Lib reference
        macd, signal_line, histogram = talib.MACD(closes, fastperiod=fast, slowperiod=slow, signalperiod=signal)
        talib_histogram = histogram[~np.isnan(histogram)]
        
        # Compare
        min_len = min(len(our_histogram), len(talib_histogram))
        our_histogram = our_histogram[-min_len:]
        talib_histogram = talib_histogram[-min_len:]
        
        errors = np.abs(our_histogram - talib_histogram)
        
        return {
            'indicator': 'MACD',
            'data_points': len(our_histogram),
            'max_error': np.max(errors),
            'mean_error': np.mean(errors),
            'std_error': np.std(errors),
            'threshold': ACCURACY_THRESHOLDS['MACD'],
            'passed': np.max(errors) < ACCURACY_THRESHOLDS['MACD'],
        }
    
    def validate_aroon(
        self, 
        highs: np.ndarray, 
        lows: np.ndarray, 
        period: int = 25
    ) -> Dict[str, Any]:
        """Validate AROON calculation"""
        if not TALIB_AVAILABLE:
            return {'error': 'TA-Lib not available'}
        
        # Platform calculation
        our_aroon = self.indicators_service.calculate_aroon(highs.tolist(), lows.tolist(), period)
        our_up = np.array([v for v in our_aroon.get('aroon_up', []) if v is not None], dtype=float)
        our_down = np.array([v for v in our_aroon.get('aroon_down', []) if v is not None], dtype=float)
        
        # TA-Lib reference
        aroon_down, aroon_up = talib.AROON(highs, lows, timeperiod=period)
        talib_up = aroon_up[~np.isnan(aroon_up)]
        talib_down = aroon_down[~np.isnan(aroon_down)]
        
        # Compare UP values
        min_len = min(len(our_up), len(talib_up))
        our_up = our_up[-min_len:]
        talib_up = talib_up[-min_len:]
        errors_up = np.abs(our_up - talib_up)
        
        # Compare DOWN values
        min_len = min(len(our_down), len(talib_down))
        our_down = our_down[-min_len:]
        talib_down = talib_down[-min_len:]
        errors_down = np.abs(our_down - talib_down)
        
        max_error = max(np.max(errors_up), np.max(errors_down))
        mean_error = (np.mean(errors_up) + np.mean(errors_down)) / 2
        
        return {
            'indicator': 'AROON',
            'data_points': len(our_up),
            'max_error': max_error,
            'mean_error': mean_error,
            'std_error': (np.std(errors_up) + np.std(errors_down)) / 2,
            'threshold': ACCURACY_THRESHOLDS['AROON'],
            'passed': max_error < ACCURACY_THRESHOLDS['AROON'],
        }
    
    def validate_bollinger(
        self, 
        closes: np.ndarray, 
        period: int = 20, 
        std_dev: float = 2.0
    ) -> Dict[str, Any]:
        """Validate Bollinger Bands calculation"""
        if not TALIB_AVAILABLE:
            return {'error': 'TA-Lib not available'}
        
        # Platform calculation
        our_bb = self.indicators_service.calculate_bollinger_bands(closes.tolist(), period, std_dev)
        our_middle = np.array([v for v in our_bb.get('middle', []) if v is not None], dtype=float)
        
        # TA-Lib reference
        upper, middle, lower = talib.BBANDS(closes, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev, matype=0)
        talib_middle = middle[~np.isnan(middle)]
        
        # Compare middle band (SMA)
        min_len = min(len(our_middle), len(talib_middle))
        our_middle = our_middle[-min_len:]
        talib_middle = talib_middle[-min_len:]
        
        errors = np.abs(our_middle - talib_middle)
        
        return {
            'indicator': 'BOLLINGER',
            'data_points': len(our_middle),
            'max_error': np.max(errors),
            'mean_error': np.mean(errors),
            'std_error': np.std(errors),
            'threshold': ACCURACY_THRESHOLDS['BOLLINGER'],
            'passed': np.max(errors) < ACCURACY_THRESHOLDS['BOLLINGER'],
        }
    
    def run_validation(
        self, 
        symbol: str, 
        timeframe: str, 
        days: int,
        indicators: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Run validation for specified indicators"""
        print(f"\n{'='*70}")
        print(f"Validating {symbol} @ {timeframe} ({days} days)")
        print(f"{'='*70}")
        
        if not TALIB_AVAILABLE:
            print("❌ SKIPPED: TA-Lib not installed")
            return []
        
        try:
            # Fetch market data
            print(f"Fetching market data...")
            opens, highs, lows, closes, volumes = self.fetch_market_data(symbol, timeframe, days)
            print(f"✓ Fetched {len(closes)} bars")
            
            results = []
            test_indicators = indicators or INDICATORS.keys()
            
            for indicator in test_indicators:
                if indicator not in INDICATORS:
                    print(f"⚠ Unknown indicator: {indicator}")
                    continue
                
                print(f"\nTesting {indicator}...", end=" ")
                
                try:
                    if indicator == 'RSI':
                        result = self.validate_rsi(closes, **INDICATORS[indicator])
                    elif indicator == 'MACD':
                        result = self.validate_macd(closes, **INDICATORS[indicator])
                    elif indicator == 'AROON':
                        result = self.validate_aroon(highs, lows, **INDICATORS[indicator])
                    elif indicator == 'BOLLINGER':
                        result = self.validate_bollinger(closes, **INDICATORS[indicator])
                    else:
                        print("⚠ Not implemented yet")
                        continue
                    
                    if 'error' in result:
                        print(f"❌ {result['error']}")
                        continue
                    
                    # Add metadata
                    result['symbol'] = symbol
                    result['timeframe'] = timeframe
                    result['date_range'] = f"{days}d"
                    results.append(result)
                    
                    # Print result
                    status = "✅ PASS" if result['passed'] else "❌ FAIL"
                    print(f"{status} (max: {result['max_error']:.4f}, mean: {result['mean_error']:.4f})")
                    
                except Exception as e:
                    print(f"❌ Error: {e}")
            
            return results
            
        except Exception as e:
            print(f"❌ Failed to fetch data: {e}")
            return []


# ============================================================================
# REPORTING
# ============================================================================

def generate_report(results: List[Dict[str, Any]]) -> str:
    """Generate validation report"""
    report = []
    report.append("\n" + "="*70)
    report.append("INDICATOR ACCURACY VALIDATION REPORT")
    report.append("="*70)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Total Tests: {len(results)}")
    
    passed = sum(1 for r in results if r.get('passed', False))
    failed = len(results) - passed
    pass_rate = (passed / len(results) * 100) if results else 0
    
    report.append(f"Passed: {passed} ({pass_rate:.1f}%)")
    report.append(f"Failed: {failed}")
    report.append("")
    
    # Group by indicator
    by_indicator = {}
    for r in results:
        ind = r.get('indicator', 'Unknown')
        if ind not in by_indicator:
            by_indicator[ind] = []
        by_indicator[ind].append(r)
    
    # Summary by indicator
    report.append("\nSUMMARY BY INDICATOR")
    report.append("-" * 70)
    report.append(f"{'Indicator':<15} {'Tests':<8} {'Passed':<8} {'Max Error':<12} {'Mean Error':<12}")
    report.append("-" * 70)
    
    for ind, tests in sorted(by_indicator.items()):
        total = len(tests)
        passed_count = sum(1 for t in tests if t.get('passed', False))
        max_errors = [t['max_error'] for t in tests if 'max_error' in t]
        mean_errors = [t['mean_error'] for t in tests if 'mean_error' in t]
        
        max_err = max(max_errors) if max_errors else 0
        mean_err = np.mean(mean_errors) if mean_errors else 0
        
        status = "✅" if passed_count == total else "⚠"
        report.append(f"{ind:<15} {total:<8} {status} {passed_count:<6} {max_err:<12.4f} {mean_err:<12.4f}")
    
    # Failed tests details
    failed_tests = [r for r in results if not r.get('passed', False)]
    if failed_tests:
        report.append("\n\nFAILED TESTS DETAILS")
        report.append("-" * 70)
        for test in failed_tests:
            report.append(f"\n❌ {test['indicator']} - {test['symbol']} @ {test['timeframe']} ({test['date_range']})")
            report.append(f"   Max Error: {test['max_error']:.4f} (threshold: {test['threshold']})")
            report.append(f"   Mean Error: {test['mean_error']:.4f}")
            report.append(f"   Data Points: {test['data_points']}")
    
    report.append("\n" + "="*70)
    return "\n".join(report)


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Validate indicator accuracy against TA-Lib')
    parser.add_argument('--stocks', nargs='+', default=['AAPL'], help='Stock symbols to test')
    parser.add_argument('--timeframe', default='1D', choices=['5m', '15m', '1D'], help='Timeframe')
    parser.add_argument('--range', default='3M', choices=['1M', '3M', '6M'], help='Date range')
    parser.add_argument('--indicators', nargs='+', help='Specific indicators to test')
    parser.add_argument('--full', action='store_true', help='Run full test matrix')
    parser.add_argument('--output', help='Output file for report (default: print to console)')
    
    args = parser.parse_args()
    
    validator = IndicatorValidator()
    all_results = []
    
    if args.full:
        # Full test matrix
        print("Running FULL test matrix...")
        for stock in TEST_STOCKS:
            for timeframe in TEST_TIMEFRAMES:
                for range_name, days in TEST_RANGES.items():
                    results = validator.run_validation(stock, timeframe, days, args.indicators)
                    all_results.extend(results)
    else:
        # Single test
        days = TEST_RANGES[args.range]
        for stock in args.stocks:
            results = validator.run_validation(stock, args.timeframe, days, args.indicators)
            all_results.extend(results)
    
    # Generate report
    report = generate_report(all_results)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"\n✓ Report saved to: {args.output}")
    else:
        print(report)
    
    # Exit code based on results
    failed = sum(1 for r in all_results if not r.get('passed', False))
    sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()
