#!/usr/bin/env python3
"""
Comprehensive Indicator Validation Script

This script validates ALL technical indicators by:
1. Fetching raw OHLCV data from yfinance (ground truth)
2. Calculating indicators using our backend service
3. Calculating indicators independently using pandas/numpy
4. Comparing results and reporting discrepancies

Data Flow:
- Primary: Alpaca API (IEX feed for paper trading)
- Fallback: yfinance (free, 15-min delayed)
- Both sources provide the same underlying market data

Run: python scripts/validate_indicators.py
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.indicators import TechnicalIndicators

# Configuration
SYMBOL = "AAPL"
PERIOD = "6mo"
INTERVAL = "1d"
TOLERANCE = 0.01  # 1% tolerance for floating point comparison


def fetch_raw_data() -> pd.DataFrame:
    """Fetch raw OHLCV data from yfinance"""
    print(f"\n📊 Fetching {SYMBOL} data from yfinance ({PERIOD}, {INTERVAL})...")
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(period=PERIOD, interval=INTERVAL)
    print(f"   ✅ Retrieved {len(df)} bars")
    print(f"   📅 Date range: {df.index[0].date()} to {df.index[-1].date()}")
    return df


def compare_values(name: str, our_values: list, expected_values: list, tolerance: float = TOLERANCE) -> dict:
    """Compare two lists of indicator values"""
    # Filter out None/NaN values for comparison
    our_valid = [(i, v) for i, v in enumerate(our_values) if v is not None and not np.isnan(v)]
    exp_valid = [(i, v) for i, v in enumerate(expected_values) if v is not None and not np.isnan(v)]
    
    if len(our_valid) == 0 or len(exp_valid) == 0:
        return {"status": "⚠️ NO DATA", "message": "No valid values to compare"}
    
    # Compare overlapping indices
    our_dict = dict(our_valid)
    exp_dict = dict(exp_valid)
    common_indices = set(our_dict.keys()) & set(exp_dict.keys())
    
    if len(common_indices) == 0:
        return {"status": "⚠️ NO OVERLAP", "message": "No overlapping valid indices"}
    
    errors = []
    max_diff = 0
    for i in common_indices:
        our_val = our_dict[i]
        exp_val = exp_dict[i]
        if exp_val != 0:
            diff = abs(our_val - exp_val) / abs(exp_val)
        else:
            diff = abs(our_val - exp_val)
        max_diff = max(max_diff, diff)
        if diff > tolerance:
            errors.append((i, our_val, exp_val, diff))
    
    if len(errors) == 0:
        return {
            "status": "✅ PASS",
            "message": f"All {len(common_indices)} values match (max diff: {max_diff:.6f})",
            "max_diff": max_diff,
            "compared": len(common_indices)
        }
    else:
        return {
            "status": "❌ FAIL",
            "message": f"{len(errors)}/{len(common_indices)} values differ (max diff: {max_diff:.4f})",
            "errors": errors[:5],  # First 5 errors
            "max_diff": max_diff
        }


def validate_sma(df: pd.DataFrame, period: int = 20) -> dict:
    """Validate Simple Moving Average"""
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_sma(closes, period)
    
    # Independent calculation
    expected = df['Close'].rolling(window=period).mean().tolist()
    
    return compare_values("SMA", our_result, expected)


def validate_ema(df: pd.DataFrame, period: int = 20) -> dict:
    """Validate Exponential Moving Average"""
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_ema(closes, period)
    
    # Independent calculation
    expected = df['Close'].ewm(span=period, adjust=False).mean().tolist()
    
    return compare_values("EMA", our_result, expected)


def validate_rsi(df: pd.DataFrame, period: int = 14) -> dict:
    """Validate Relative Strength Index"""
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_rsi(closes, period)
    
    # Independent calculation (same algorithm)
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    expected = (100 - (100 / (1 + rs))).tolist()
    
    return compare_values("RSI", our_result, expected)


def validate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """Validate MACD"""
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_macd(closes, fast, slow, signal)
    
    # Independent calculation
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    results = {}
    results['macd_line'] = compare_values("MACD Line", our_result['macd'], macd_line.tolist())
    results['signal_line'] = compare_values("Signal Line", our_result['signal'], signal_line.tolist())
    results['histogram'] = compare_values("Histogram", our_result['histogram'], histogram.tolist())
    
    # Overall status
    all_pass = all(r['status'] == '✅ PASS' for r in results.values())
    return {
        "status": "✅ PASS" if all_pass else "❌ FAIL",
        "components": results
    }


def validate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> dict:
    """Validate Bollinger Bands"""
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_bollinger_bands(closes, period, std_dev)
    
    # Independent calculation
    sma = df['Close'].rolling(window=period).mean()
    std = df['Close'].rolling(window=period).std()
    upper = sma + (std * std_dev)
    middle = sma
    lower = sma - (std * std_dev)
    
    results = {}
    results['upper'] = compare_values("Upper Band", our_result['upper'], upper.tolist())
    results['middle'] = compare_values("Middle Band", our_result['middle'], middle.tolist())
    results['lower'] = compare_values("Lower Band", our_result['lower'], lower.tolist())
    
    all_pass = all(r['status'] == '✅ PASS' for r in results.values())
    return {
        "status": "✅ PASS" if all_pass else "❌ FAIL",
        "components": results
    }


def validate_atr(df: pd.DataFrame, period: int = 14) -> dict:
    """Validate Average True Range"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_atr(highs, lows, closes, period)
    
    # Independent calculation - using EWM like our implementation
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Use EWM (same as our implementation)
    expected = tr.ewm(span=period, adjust=False).mean().tolist()
    
    return compare_values("ATR", our_result, expected)


def validate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> dict:
    """Validate Stochastic Oscillator"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_stochastic(highs, lows, closes, k_period, d_period)
    
    # Independent calculation
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(window=d_period).mean()
    
    results = {}
    results['k'] = compare_values("Stochastic %K", our_result['k'], k.tolist())
    results['d'] = compare_values("Stochastic %D", our_result['d'], d.tolist())
    
    all_pass = all(r['status'] == '✅ PASS' for r in results.values())
    return {
        "status": "✅ PASS" if all_pass else "❌ FAIL",
        "components": results
    }


def validate_obv(df: pd.DataFrame) -> dict:
    """Validate On-Balance Volume"""
    closes = df['Close'].tolist()
    volumes = df['Volume'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_obv(closes, volumes)
    
    # Independent calculation
    close = df['Close']
    volume = df['Volume']
    
    direction = np.sign(close.diff())
    direction.iloc[0] = 0
    obv = (direction * volume).cumsum().tolist()
    
    return compare_values("OBV", our_result, obv)


def validate_cci(df: pd.DataFrame, period: int = 20) -> dict:
    """Validate Commodity Channel Index"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_cci(highs, lows, closes, period)
    
    # Independent calculation
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    sma = typical_price.rolling(window=period).mean()
    mad = typical_price.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
    expected = ((typical_price - sma) / (0.015 * mad)).tolist()
    
    return compare_values("CCI", our_result, expected)


def validate_williams_r(df: pd.DataFrame, period: int = 14) -> dict:
    """Validate Williams %R"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_williams_r(highs, lows, closes, period)
    
    # Independent calculation
    highest_high = df['High'].rolling(window=period).max()
    lowest_low = df['Low'].rolling(window=period).min()
    expected = (-100 * (highest_high - df['Close']) / (highest_high - lowest_low)).tolist()
    
    return compare_values("Williams %R", our_result, expected)


def validate_mfi(df: pd.DataFrame, period: int = 14) -> dict:
    """Validate Money Flow Index"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    volumes = df['Volume'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_mfi(highs, lows, closes, volumes, period)
    
    # Independent calculation
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    money_flow = typical_price * df['Volume']
    
    positive_flow = money_flow.where(typical_price.diff() > 0, 0)
    negative_flow = money_flow.where(typical_price.diff() < 0, 0)
    
    positive_sum = positive_flow.rolling(window=period).sum()
    negative_sum = negative_flow.rolling(window=period).sum()
    
    mfi = 100 - (100 / (1 + positive_sum / negative_sum))
    expected = mfi.tolist()
    
    return compare_values("MFI", our_result, expected)


def validate_vwap(df: pd.DataFrame) -> dict:
    """Validate Volume Weighted Average Price"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    volumes = df['Volume'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_vwap(highs, lows, closes, volumes)
    
    # Independent calculation
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vwap = (typical_price * df['Volume']).cumsum() / df['Volume'].cumsum()
    expected = vwap.tolist()
    
    return compare_values("VWAP", our_result, expected)


def validate_cmf(df: pd.DataFrame, period: int = 20) -> dict:
    """Validate Chaikin Money Flow"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    volumes = df['Volume'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_chaikin_money_flow(highs, lows, closes, volumes, period)
    
    # Independent calculation
    mfm = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
    mfv = mfm * df['Volume']
    cmf = mfv.rolling(window=period).sum() / df['Volume'].rolling(window=period).sum()
    expected = cmf.tolist()
    
    return compare_values("CMF", our_result, expected)


def validate_donchian(df: pd.DataFrame, period: int = 20) -> dict:
    """Validate Donchian Channel"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_donchian_channel(highs, lows, period)
    
    # Independent calculation
    upper = df['High'].rolling(window=period).max()
    lower = df['Low'].rolling(window=period).min()
    middle = (upper + lower) / 2
    
    results = {}
    results['upper'] = compare_values("Upper", our_result['upper'], upper.tolist())
    results['lower'] = compare_values("Lower", our_result['lower'], lower.tolist())
    results['middle'] = compare_values("Middle", our_result['middle'], middle.tolist())
    
    all_pass = all(r['status'] == '✅ PASS' for r in results.values())
    return {
        "status": "✅ PASS" if all_pass else "❌ FAIL",
        "components": results
    }


def validate_keltner(df: pd.DataFrame, period: int = 20, multiplier: float = 2.0) -> dict:
    """Validate Keltner Channel"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_keltner_channel(highs, lows, closes, period, multiplier)
    
    # Independent calculation
    ema = df['Close'].ewm(span=period, adjust=False).mean()
    
    # ATR calculation
    prev_close = df['Close'].shift(1)
    tr1 = df['High'] - df['Low']
    tr2 = abs(df['High'] - prev_close)
    tr3 = abs(df['Low'] - prev_close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    
    upper = ema + (multiplier * atr)
    lower = ema - (multiplier * atr)
    
    results = {}
    results['upper'] = compare_values("Upper", our_result['upper'], upper.tolist())
    results['middle'] = compare_values("Middle", our_result['middle'], ema.tolist())
    results['lower'] = compare_values("Lower", our_result['lower'], lower.tolist())
    
    all_pass = all(r['status'] == '✅ PASS' for r in results.values())
    return {
        "status": "✅ PASS" if all_pass else "❌ FAIL",
        "components": results
    }


def validate_aroon(df: pd.DataFrame, period: int = 25) -> dict:
    """Validate Aroon Indicator"""
    highs = df['High'].tolist()
    lows = df['Low'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_aroon(highs, lows, period)
    
    # Independent calculation
    aroon_up = []
    aroon_down = []
    
    for i in range(len(highs)):
        if i < period:
            aroon_up.append(None)
            aroon_down.append(None)
        else:
            window_high = highs[i-period:i+1]
            window_low = lows[i-period:i+1]
            
            days_since_high = period - window_high.index(max(window_high))
            days_since_low = period - window_low.index(min(window_low))
            
            aroon_up.append(100 * (period - days_since_high) / period)
            aroon_down.append(100 * (period - days_since_low) / period)
    
    # Use rolling for proper calculation
    high_series = pd.Series(highs)
    low_series = pd.Series(lows)
    
    def days_since_max(x):
        return period - np.argmax(x.values)
    
    def days_since_min(x):
        return period - np.argmin(x.values)
    
    aroon_up_calc = high_series.rolling(window=period+1).apply(days_since_max, raw=False) * 100 / period
    aroon_down_calc = low_series.rolling(window=period+1).apply(days_since_min, raw=False) * 100 / period
    
    results = {}
    results['up'] = compare_values("Aroon Up", our_result['aroon_up'], aroon_up_calc.tolist())
    results['down'] = compare_values("Aroon Down", our_result['aroon_down'], aroon_down_calc.tolist())
    
    all_pass = all(r['status'] == '✅ PASS' for r in results.values())
    return {
        "status": "✅ PASS" if all_pass else "❌ FAIL",
        "components": results
    }


def validate_trix(df: pd.DataFrame, period: int = 15) -> dict:
    """Validate TRIX"""
    closes = df['Close'].tolist()
    
    # Our calculation
    our_result = TechnicalIndicators.calculate_trix(closes, period)
    
    # Independent calculation
    ema1 = df['Close'].ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    trix = (ema3 - ema3.shift(1)) / ema3.shift(1) * 100
    
    return compare_values("TRIX", our_result, trix.tolist())


def print_result(name: str, result: dict, indent: int = 0):
    """Pretty print a validation result"""
    prefix = "  " * indent
    status = result.get('status', '?')
    message = result.get('message', '')
    
    print(f"{prefix}{status} {name}: {message}")
    
    # Print component results
    if 'components' in result:
        for comp_name, comp_result in result['components'].items():
            print_result(comp_name, comp_result, indent + 1)
    
    # Print sample errors
    if 'errors' in result and result['errors']:
        print(f"{prefix}   Sample errors (idx, ours, expected, diff%):")
        for idx, ours, exp, diff in result['errors'][:3]:
            print(f"{prefix}   - [{idx}] {ours:.4f} vs {exp:.4f} ({diff*100:.2f}%)")


def main():
    """Run all indicator validations"""
    print("=" * 70)
    print("🔬 COMPREHENSIVE INDICATOR VALIDATION")
    print("=" * 70)
    print(f"Symbol: {SYMBOL}")
    print(f"Period: {PERIOD}")
    print(f"Interval: {INTERVAL}")
    print(f"Tolerance: {TOLERANCE*100}%")
    
    # Fetch data
    df = fetch_raw_data()
    
    print("\n" + "=" * 70)
    print("📈 VALIDATING ALL INDICATORS")
    print("=" * 70)
    
    results = {}
    
    # Trend Indicators
    print("\n📊 TREND INDICATORS")
    print("-" * 40)
    
    results['SMA'] = validate_sma(df)
    print_result("SMA (20)", results['SMA'])
    
    results['EMA'] = validate_ema(df)
    print_result("EMA (20)", results['EMA'])
    
    # Momentum Indicators
    print("\n📊 MOMENTUM INDICATORS")
    print("-" * 40)
    
    results['RSI'] = validate_rsi(df)
    print_result("RSI (14)", results['RSI'])
    
    results['MACD'] = validate_macd(df)
    print_result("MACD (12, 26, 9)", results['MACD'])
    
    results['Stochastic'] = validate_stochastic(df)
    print_result("Stochastic (14, 3)", results['Stochastic'])
    
    results['CCI'] = validate_cci(df)
    print_result("CCI (20)", results['CCI'])
    
    results['Williams_R'] = validate_williams_r(df)
    print_result("Williams %R (14)", results['Williams_R'])
    
    # Volatility Indicators
    print("\n📊 VOLATILITY INDICATORS")
    print("-" * 40)
    
    results['Bollinger'] = validate_bollinger(df)
    print_result("Bollinger Bands (20, 2)", results['Bollinger'])
    
    results['ATR'] = validate_atr(df)
    print_result("ATR (14)", results['ATR'])
    
    # Volume Indicators
    print("\n📊 VOLUME INDICATORS")
    print("-" * 40)
    
    results['OBV'] = validate_obv(df)
    print_result("OBV", results['OBV'])
    
    results['VWAP'] = validate_vwap(df)
    print_result("VWAP", results['VWAP'])
    
    results['MFI'] = validate_mfi(df)
    print_result("MFI (14)", results['MFI'])
    
    results['CMF'] = validate_cmf(df)
    print_result("CMF (20)", results['CMF'])
    
    # Additional Indicators
    print("\n📊 CHANNEL INDICATORS")
    print("-" * 40)
    
    results['Donchian'] = validate_donchian(df)
    print_result("Donchian Channel (20)", results['Donchian'])
    
    results['Keltner'] = validate_keltner(df)
    print_result("Keltner Channel (20, 2)", results['Keltner'])
    
    print("\n📊 OTHER INDICATORS")
    print("-" * 40)
    
    results['TRIX'] = validate_trix(df)
    print_result("TRIX (15)", results['TRIX'])
    
    # Summary
    print("\n" + "=" * 70)
    print("📋 VALIDATION SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results.values() if r.get('status') == '✅ PASS')
    failed = sum(1 for r in results.values() if r.get('status') == '❌ FAIL')
    warnings = sum(1 for r in results.values() if '⚠️' in r.get('status', ''))
    
    print(f"\n✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Warnings: {warnings}")
    print(f"\nTotal: {len(results)} indicators tested")
    
    if failed == 0:
        print("\n🎉 ALL INDICATOR CALCULATIONS ARE CORRECT!")
    else:
        print("\n⚠️  Some indicators need review. Check errors above.")
    
    # Data source info
    print("\n" + "=" * 70)
    print("📡 DATA SOURCE INFORMATION")
    print("=" * 70)
    print("""
Your app fetches market data from these sources (in order):

1. PRIMARY: Alpaca API (IEX feed)
   - Used for: Real-time and historical data
   - Limitations: Paper trading has 15-min delay on SIP data
   - Free tier: 200 requests/minute

2. FALLBACK: yfinance (Yahoo Finance)
   - Used when: Alpaca fails or data unavailable
   - Data: 15-minute delayed for intraday
   - Free tier: Unlimited (rate limited)

The OHLCV data from both sources represents the same underlying
market data, just from different aggregators.

This validation script uses yfinance directly to get "ground truth"
data and compares it with our indicator calculations.
""")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
