"""
Technical Indicators Service

Provides calculation functions for 20+ technical indicators.
Uses pandas for efficient array operations.

Phase 7 - Market Data & Charting
Created: October 16, 2025
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """
    Technical indicators calculator using pandas.
    All methods are static for stateless calculations.
    """

    @staticmethod
    def calculate_sma(prices: list[float], period: int = 20) -> list[float | None]:
        """
        Simple Moving Average (SMA)

        Args:
            prices: List of closing prices
            period: Lookback period (default: 20)

        Returns:
            List of SMA values (None for insufficient data)
        """
        if len(prices) < period:
            return [None] * len(prices)

        df = pd.DataFrame({'close': prices})
        df['sma'] = df['close'].rolling(window=period).mean()
        return df['sma'].tolist()

    @staticmethod
    def calculate_ema(prices: list[float], period: int = 20) -> list[float | None]:
        """
        Exponential Moving Average (EMA)

        Args:
            prices: List of closing prices
            period: Lookback period (default: 20)

        Returns:
            List of EMA values
        """
        if len(prices) < period:
            return [None] * len(prices)

        df = pd.DataFrame({'close': prices})
        df['ema'] = df['close'].ewm(span=period, adjust=False).mean()
        return df['ema'].tolist()

    @staticmethod
    def calculate_rsi(prices: list[float], period: int = 14) -> list[float | None]:
        """
        Relative Strength Index (RSI)

        Args:
            prices: List of closing prices
            period: Lookback period (default: 14)

        Returns:
            List of RSI values (0-100)
        """
        if len(prices) < period + 1:
            return [None] * len(prices)

        df = pd.DataFrame({'close': prices})

        # Calculate price changes
        delta = df['close'].diff()

        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # Calculate average gain and loss
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.tolist()

    @staticmethod
    def calculate_macd(
        prices: list[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> dict[str, list[float | None]]:
        """
        Moving Average Convergence Divergence (MACD)

        Args:
            prices: List of closing prices
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line period (default: 9)

        Returns:
            Dict with 'macd', 'signal', and 'histogram' lists
        """
        if len(prices) < slow_period + signal_period:
            null_list = [None] * len(prices)
            return {'macd': null_list, 'signal': null_list, 'histogram': null_list}

        df = pd.DataFrame({'close': prices})

        # Calculate MACD line
        fast_ema = df['close'].ewm(span=fast_period, adjust=False).mean()
        slow_ema = df['close'].ewm(span=slow_period, adjust=False).mean()
        macd_line = fast_ema - slow_ema

        # Calculate signal line
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

        # Calculate histogram
        histogram = macd_line - signal_line

        return {
            'macd': macd_line.tolist(),
            'signal': signal_line.tolist(),
            'histogram': histogram.tolist()
        }

    @staticmethod
    def calculate_bollinger_bands(
        prices: list[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> dict[str, list[float | None]]:
        """
        Bollinger Bands

        Args:
            prices: List of closing prices
            period: SMA period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)

        Returns:
            Dict with 'upper', 'middle', and 'lower' band lists
        """
        if len(prices) < period:
            null_list = [None] * len(prices)
            return {'upper': null_list, 'middle': null_list, 'lower': null_list}

        df = pd.DataFrame({'close': prices})

        # Calculate middle band (SMA)
        middle = df['close'].rolling(window=period).mean()

        # Calculate standard deviation
        std = df['close'].rolling(window=period).std()

        # Calculate upper and lower bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return {
            'upper': upper.tolist(),
            'middle': middle.tolist(),
            'lower': lower.tolist()
        }

    @staticmethod
    def calculate_atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14
    ) -> list[float | None]:
        """
        Average True Range (ATR)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: Lookback period (default: 14)

        Returns:
            List of ATR values
        """
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Calculate True Range
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['close'].shift())
        df['tr3'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

        # Calculate ATR (EMA of TR)
        df['atr'] = df['tr'].ewm(span=period, adjust=False).mean()

        return df['atr'].tolist()

    @staticmethod
    def calculate_stochastic(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        k_period: int = 14,
        d_period: int = 3
    ) -> dict[str, list[float | None]]:
        """
        Stochastic Oscillator

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            k_period: %K period (default: 14)
            d_period: %D period (default: 3)

        Returns:
            Dict with 'k' and 'd' lists
        """
        if len(highs) < k_period or len(lows) < k_period or len(closes) < k_period:
            null_list = [None] * len(closes)
            return {'k': null_list, 'd': null_list}

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Calculate %K
        df['lowest_low'] = df['low'].rolling(window=k_period).min()
        df['highest_high'] = df['high'].rolling(window=k_period).max()
        df['k'] = 100 * (df['close'] - df['lowest_low']) / (df['highest_high'] - df['lowest_low'])

        # Calculate %D (SMA of %K)
        df['d'] = df['k'].rolling(window=d_period).mean()

        return {
            'k': df['k'].tolist(),
            'd': df['d'].tolist()
        }

    @staticmethod
    def calculate_adx(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14
    ) -> list[float | None]:
        """
        Average Directional Index (ADX)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: Lookback period (default: 14)

        Returns:
            List of ADX values (0-100)
        """
        if len(highs) < period * 2 or len(lows) < period * 2 or len(closes) < period * 2:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Calculate True Range
        df['tr'] = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        ], axis=1).max(axis=1)

        # Calculate directional movement
        df['up_move'] = df['high'] - df['high'].shift()
        df['down_move'] = df['low'].shift() - df['low']

        # Vectorized directional movement calculation (10-100x faster than apply)
        df['plus_dm'] = np.where(
            (df['up_move'] > df['down_move']) & (df['up_move'] > 0),
            df['up_move'],
            0
        )
        df['minus_dm'] = np.where(
            (df['down_move'] > df['up_move']) & (df['down_move'] > 0),
            df['down_move'],
            0
        )

        # Smooth the values
        df['atr'] = df['tr'].ewm(span=period, adjust=False).mean()
        df['plus_di'] = 100 * (df['plus_dm'].ewm(span=period, adjust=False).mean() / df['atr'])
        df['minus_di'] = 100 * (df['minus_dm'].ewm(span=period, adjust=False).mean() / df['atr'])

        # Calculate DX and ADX
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
        df['adx'] = df['dx'].ewm(span=period, adjust=False).mean()

        return df['adx'].tolist()

    @staticmethod
    def calculate_obv(closes: list[float], volumes: list[float]) -> list[float | None]:
        """
        On Balance Volume (OBV)

        Args:
            closes: List of closing prices
            volumes: List of volumes

        Returns:
            List of OBV values
        """
        if len(closes) < 2 or len(volumes) < 2:
            return [None] * len(closes)

        df = pd.DataFrame({
            'close': closes,
            'volume': volumes
        })

        # Calculate OBV
        df['price_change'] = df['close'].diff()
        df['direction'] = df['price_change'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        df['obv'] = (df['volume'] * df['direction']).cumsum()

        return df['obv'].tolist()

    @staticmethod
    def calculate_vwap(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[float]
    ) -> list[float | None]:
        """
        Volume Weighted Average Price (VWAP)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            volumes: List of volumes

        Returns:
            List of VWAP values
        """
        if not all([highs, lows, closes, volumes]):
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })

        # Calculate typical price
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3

        # Calculate VWAP
        df['tp_volume'] = df['typical_price'] * df['volume']
        df['vwap'] = df['tp_volume'].cumsum() / df['volume'].cumsum()

        return df['vwap'].tolist()

    @staticmethod
    def calculate_cci(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 20
    ) -> list[float | None]:
        """
        Commodity Channel Index (CCI)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: Lookback period (default: 20)

        Returns:
            List of CCI values
        """
        if len(highs) < period or len(lows) < period or len(closes) < period:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Calculate typical price
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3

        # Calculate SMA of typical price
        df['tp_sma'] = df['tp'].rolling(window=period).mean()

        # Calculate mean deviation
        df['mean_dev'] = df['tp'].rolling(window=period).apply(
            lambda x: np.abs(x - x.mean()).mean()
        )

        # Calculate CCI
        df['cci'] = (df['tp'] - df['tp_sma']) / (0.015 * df['mean_dev'])

        return df['cci'].tolist()

    @staticmethod
    def calculate_williams_r(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14
    ) -> list[float | None]:
        """
        Williams %R

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: Lookback period (default: 14)

        Returns:
            List of Williams %R values (-100 to 0)
        """
        if len(highs) < period or len(lows) < period or len(closes) < period:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Calculate Williams %R
        df['highest_high'] = df['high'].rolling(window=period).max()
        df['lowest_low'] = df['low'].rolling(window=period).min()
        df['williams_r'] = -100 * (df['highest_high'] - df['close']) / (df['highest_high'] - df['lowest_low'])

        return df['williams_r'].tolist()

    @staticmethod
    def calculate_mfi(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[float],
        period: int = 14
    ) -> list[float | None]:
        """
        Money Flow Index (MFI)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            volumes: List of volumes
            period: Lookback period (default: 14)

        Returns:
            List of MFI values (0-100)
        """
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })

        # Calculate typical price
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3

        # Calculate raw money flow
        df['raw_mf'] = df['tp'] * df['volume']

        # Determine positive and negative money flow (vectorized)
        df['tp_change'] = df['tp'].diff()
        df['pos_mf'] = np.where(df['tp_change'] > 0, df['raw_mf'], 0)
        df['neg_mf'] = np.where(df['tp_change'] < 0, df['raw_mf'], 0)

        # Calculate money flow ratio
        df['pos_mf_sum'] = df['pos_mf'].rolling(window=period).sum()
        df['neg_mf_sum'] = df['neg_mf'].rolling(window=period).sum()
        df['mf_ratio'] = df['pos_mf_sum'] / df['neg_mf_sum']

        # Calculate MFI
        df['mfi'] = 100 - (100 / (1 + df['mf_ratio']))

        return df['mfi'].tolist()

    @staticmethod
    def calculate_parabolic_sar(
        highs: list[float],
        lows: list[float],
        af_start: float = 0.02,
        af_increment: float = 0.02,
        af_max: float = 0.2
    ) -> list[float | None]:
        """
        Parabolic SAR (Stop and Reverse)

        Args:
            highs: List of high prices
            lows: List of low prices
            af_start: Starting acceleration factor (default: 0.02)
            af_increment: AF increment (default: 0.02)
            af_max: Maximum AF (default: 0.2)

        Returns:
            List of SAR values
        """
        if len(highs) < 5 or len(lows) < 5:
            return [None] * len(highs)

        sar_values = [None] * len(highs)

        # Initialize
        trend = 1  # 1 for uptrend, -1 for downtrend
        sar = lows[0]
        ep = highs[0]  # Extreme point
        af = af_start

        for i in range(1, len(highs)):
            # Calculate SAR
            sar = sar + af * (ep - sar)

            # Check for reversal
            if trend == 1:  # Uptrend
                sar = min(sar, lows[i-1])
                if i > 1:
                    sar = min(sar, lows[i-2])

                if lows[i] < sar:
                    # Reversal to downtrend
                    trend = -1
                    sar = ep
                    ep = lows[i]
                    af = af_start
                elif highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_increment, af_max)
            else:  # Downtrend
                sar = max(sar, highs[i-1])
                if i > 1:
                    sar = max(sar, highs[i-2])

                if highs[i] > sar:
                    # Reversal to uptrend
                    trend = 1
                    sar = ep
                    ep = highs[i]
                    af = af_start
                elif lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_increment, af_max)

            sar_values[i] = sar

        return sar_values

    @staticmethod
    def calculate_aroon(highs: list[float], lows: list[float], period: int = 25) -> dict[str, list[float | None]]:
        """
        Aroon Indicator (Aroon Up and Aroon Down)

        Measures time since highest high and lowest low.

        Args:
            highs: List of high prices
            lows: List of low prices
            period: Lookback period (default: 25)

        Returns:
            Dictionary with 'aroon_up' and 'aroon_down' lists
        """
        if len(highs) < period or len(lows) < period:
            return {
                'aroon_up': [None] * len(highs),
                'aroon_down': [None] * len(lows),
                'aroon_oscillator': [None] * len(highs)
            }

        # Vectorized Aroon calculation using pandas rolling
        df = pd.DataFrame({
            'high': highs,
            'low': lows
        })

        # Find position of max/min within rolling window
        # argmax/argmin returns position relative to the start of the window
        df['periods_since_high'] = period - 1 - df['high'].rolling(window=period).apply(
            lambda x: np.argmax(x), raw=True
        )
        df['periods_since_low'] = period - 1 - df['low'].rolling(window=period).apply(
            lambda x: np.argmin(x), raw=True
        )

        df['aroon_up'] = ((period - df['periods_since_high']) / period) * 100
        df['aroon_down'] = ((period - df['periods_since_low']) / period) * 100
        df['aroon_oscillator'] = df['aroon_up'] - df['aroon_down']

        return {
            'aroon_up': df['aroon_up'].tolist(),
            'aroon_down': df['aroon_down'].tolist(),
            'aroon_oscillator': df['aroon_oscillator'].tolist()
        }

    @staticmethod
    def calculate_chaikin_money_flow(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[float],
        period: int = 20
    ) -> list[float | None]:
        """
        Chaikin Money Flow (CMF)

        Measures buying and selling pressure over a period.

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            volumes: List of volumes
            period: Lookback period (default: 20)

        Returns:
            List of CMF values (-1 to 1)
        """
        if len(closes) < period:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })

        # Calculate Money Flow Multiplier
        df['mf_multiplier'] = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
        df['mf_multiplier'] = df['mf_multiplier'].fillna(0)

        # Calculate Money Flow Volume
        df['mf_volume'] = df['mf_multiplier'] * df['volume']

        # Calculate CMF
        df['cmf'] = df['mf_volume'].rolling(window=period).sum() / df['volume'].rolling(window=period).sum()

        return df['cmf'].tolist()

    @staticmethod
    def calculate_trix(prices: list[float], period: int = 15) -> list[float | None]:
        """
        TRIX (Triple Exponential Average)

        Shows rate of change of triple exponentially smoothed moving average.

        Args:
            prices: List of closing prices
            period: Lookback period (default: 15)

        Returns:
            List of TRIX values
        """
        if len(prices) < period * 3:
            return [None] * len(prices)

        df = pd.DataFrame({'close': prices})

        # Triple EMA
        df['ema1'] = df['close'].ewm(span=period, adjust=False).mean()
        df['ema2'] = df['ema1'].ewm(span=period, adjust=False).mean()
        df['ema3'] = df['ema2'].ewm(span=period, adjust=False).mean()

        # TRIX = 1-period percent change of triple EMA
        df['trix'] = df['ema3'].pct_change(periods=1) * 100

        return df['trix'].tolist()

    @staticmethod
    def calculate_volume_weighted_ma(
        prices: list[float],
        volumes: list[float],
        period: int = 20
    ) -> list[float | None]:
        """
        Volume Weighted Moving Average (VWMA)

        Similar to SMA but weighted by volume.

        Args:
            prices: List of closing prices
            volumes: List of volumes
            period: Lookback period (default: 20)

        Returns:
            List of VWMA values
        """
        if len(prices) < period:
            return [None] * len(prices)

        df = pd.DataFrame({
            'close': prices,
            'volume': volumes
        })

        df['pv'] = df['close'] * df['volume']
        df['vwma'] = df['pv'].rolling(window=period).sum() / df['volume'].rolling(window=period).sum()

        return df['vwma'].tolist()

    @staticmethod
    def calculate_know_sure_thing(prices: list[float]) -> dict[str, list[float | None]]:
        """
        Know Sure Thing (KST) Oscillator

        Momentum oscillator based on smoothed rate-of-change.

        Args:
            prices: List of closing prices

        Returns:
            Dictionary with 'kst' and 'signal' lists
        """
        if len(prices) < 26:
            return {
                'kst': [None] * len(prices),
                'signal': [None] * len(prices)
            }

        df = pd.DataFrame({'close': prices})

        # Calculate 4 ROC values
        df['roc1'] = df['close'].pct_change(periods=10) * 100
        df['roc2'] = df['close'].pct_change(periods=15) * 100
        df['roc3'] = df['close'].pct_change(periods=20) * 100
        df['roc4'] = df['close'].pct_change(periods=30) * 100

        # Smooth ROCs with SMA
        df['roc1_sma'] = df['roc1'].rolling(window=10).mean()
        df['roc2_sma'] = df['roc2'].rolling(window=10).mean()
        df['roc3_sma'] = df['roc3'].rolling(window=10).mean()
        df['roc4_sma'] = df['roc4'].rolling(window=15).mean()

        # Calculate KST
        df['kst'] = (df['roc1_sma'] * 1) + (df['roc2_sma'] * 2) + (df['roc3_sma'] * 3) + (df['roc4_sma'] * 4)

        # Signal line
        df['signal'] = df['kst'].rolling(window=9).mean()

        return {
            'kst': df['kst'].tolist(),
            'signal': df['signal'].tolist()
        }

    @staticmethod
    def calculate_ultimate_oscillator(
        highs: list[float],
        lows: list[float],
        closes: list[float]
    ) -> list[float | None]:
        """
        Ultimate Oscillator

        Combines short, medium, and long-term price action.

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices

        Returns:
            List of Ultimate Oscillator values (0-100)
        """
        if len(closes) < 28:
            return [None] * len(closes)

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Calculate buying pressure
        df['prior_close'] = df['close'].shift(1)
        df['bp'] = df['close'] - df[['low', 'prior_close']].min(axis=1)
        df['tr'] = df[['high', 'prior_close']].max(axis=1) - df[['low', 'prior_close']].min(axis=1)

        # Calculate average for 3 periods
        df['avg7'] = df['bp'].rolling(window=7).sum() / df['tr'].rolling(window=7).sum()
        df['avg14'] = df['bp'].rolling(window=14).sum() / df['tr'].rolling(window=14).sum()
        df['avg28'] = df['bp'].rolling(window=28).sum() / df['tr'].rolling(window=28).sum()

        # Calculate Ultimate Oscillator
        df['uo'] = 100 * ((4 * df['avg7']) + (2 * df['avg14']) + df['avg28']) / (4 + 2 + 1)

        return df['uo'].tolist()

    @staticmethod
    def calculate_awesome_oscillator(highs: list[float], lows: list[float]) -> list[float | None]:
        """
        Awesome Oscillator (AO)

        Difference between 34-period and 5-period simple moving averages.
        Uses midpoint (high + low) / 2.

        Args:
            highs: List of high prices
            lows: List of low prices

        Returns:
            List of AO values
        """
        if len(highs) < 34:
            return [None] * len(highs)

        df = pd.DataFrame({
            'high': highs,
            'low': lows
        })

        df['midpoint'] = (df['high'] + df['low']) / 2
        df['sma_5'] = df['midpoint'].rolling(window=5).mean()
        df['sma_34'] = df['midpoint'].rolling(window=34).mean()
        df['ao'] = df['sma_5'] - df['sma_34']

        return df['ao'].tolist()

    @staticmethod
    def calculate_donchian_channel(
        highs: list[float],
        lows: list[float],
        period: int = 20
    ) -> dict[str, list[float | None]]:
        """
        Donchian Channel

        Shows highest high and lowest low over a period.

        Args:
            highs: List of high prices
            lows: List of low prices
            period: Lookback period (default: 20)

        Returns:
            Dictionary with 'upper', 'middle', and 'lower' lists
        """
        if len(highs) < period:
            return {
                'upper': [None] * len(highs),
                'middle': [None] * len(highs),
                'lower': [None] * len(lows)
            }

        df = pd.DataFrame({
            'high': highs,
            'low': lows
        })

        df['upper'] = df['high'].rolling(window=period).max()
        df['lower'] = df['low'].rolling(window=period).min()
        df['middle'] = (df['upper'] + df['lower']) / 2

        return {
            'upper': df['upper'].tolist(),
            'middle': df['middle'].tolist(),
            'lower': df['lower'].tolist()
        }

    @staticmethod
    def calculate_keltner_channel(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 20,
        atr_multiplier: float = 2.0
    ) -> dict[str, list[float | None]]:
        """
        Keltner Channel

        Similar to Bollinger Bands but uses ATR instead of standard deviation.

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: Lookback period (default: 20)
            atr_multiplier: ATR multiplier (default: 2.0)

        Returns:
            Dictionary with 'upper', 'middle', and 'lower' lists
        """
        if len(closes) < period:
            return {
                'upper': [None] * len(closes),
                'middle': [None] * len(closes),
                'lower': [None] * len(closes)
            }

        # Calculate EMA as middle line
        df = pd.DataFrame({'close': closes})
        df['middle'] = df['close'].ewm(span=period, adjust=False).mean()

        # Calculate ATR
        atr = TechnicalIndicators.calculate_atr(highs, lows, closes, period)
        df['atr'] = atr

        # Calculate bands
        df['upper'] = df['middle'] + (df['atr'] * atr_multiplier)
        df['lower'] = df['middle'] - (df['atr'] * atr_multiplier)

        return {
            'upper': df['upper'].tolist(),
            'middle': df['middle'].tolist(),
            'lower': df['lower'].tolist()
        }

    @staticmethod
    def calculate_ichimoku_cloud(
        highs: list[float],
        lows: list[float],
        closes: list[float]
    ) -> dict[str, list[float | None]]:
        """
        Ichimoku Cloud

        Comprehensive indicator showing support/resistance, momentum, and trend.

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices

        Returns:
            Dictionary with 'tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou' lists
        """
        if len(closes) < 52:
            return {
                'tenkan': [None] * len(closes),
                'kijun': [None] * len(closes),
                'senkou_a': [None] * len(closes),
                'senkou_b': [None] * len(closes),
                'chikou': [None] * len(closes)
            }

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Tenkan-sen (Conversion Line): 9-period
        df['tenkan'] = (df['high'].rolling(window=9).max() + df['low'].rolling(window=9).min()) / 2

        # Kijun-sen (Base Line): 26-period
        df['kijun'] = (df['high'].rolling(window=26).max() + df['low'].rolling(window=26).min()) / 2

        # Senkou Span A (Leading Span A): (Tenkan + Kijun) / 2, shifted forward 26 periods
        df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)

        # Senkou Span B (Leading Span B): 52-period, shifted forward 26 periods
        df['senkou_b'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)

        # Chikou Span (Lagging Span): Close shifted backward 26 periods
        df['chikou'] = df['close'].shift(-26)

        return {
            'tenkan': df['tenkan'].tolist(),
            'kijun': df['kijun'].tolist(),
            'senkou_a': df['senkou_a'].tolist(),
            'senkou_b': df['senkou_b'].tolist(),
            'chikou': df['chikou'].tolist()
        }

    @staticmethod
    def calculate_wma(prices: list[float], period: int = 20) -> list[float | None]:
        """
        Weighted Moving Average (WMA)
        
        Gives more weight to recent prices using linear weights.

        Args:
            prices: List of closing prices
            period: Lookback period (default: 20)

        Returns:
            List of WMA values (None for insufficient data)
        """
        if len(prices) < period:
            return [None] * len(prices)

        df = pd.DataFrame({'close': prices})

        # Create weights: [1, 2, 3, ..., period]
        weights = np.arange(1, period + 1)

        def weighted_avg(x):
            return np.sum(weights * x) / weights.sum()

        df['wma'] = df['close'].rolling(window=period).apply(weighted_avg, raw=True)
        return df['wma'].tolist()

    @staticmethod
    def calculate_pivot_points(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        pivot_type: str = 'standard'
    ) -> dict[str, list[float | None]]:
        """
        Pivot Points (Support and Resistance levels)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            pivot_type: Type of pivot ('standard', 'fibonacci', 'woodie', 'camarilla')

        Returns:
            Dictionary with pivot, s1, s2, s3, r1, r2, r3 values
        """
        n = len(closes)
        if n < 2:
            empty = [None] * n
            return {
                'pivot': empty, 's1': empty, 's2': empty, 's3': empty,
                'r1': empty, 'r2': empty, 'r3': empty
            }

        df = pd.DataFrame({
            'high': highs,
            'low': lows,
            'close': closes
        })

        # Shift to use previous day's data
        prev_high = df['high'].shift(1)
        prev_low = df['low'].shift(1)
        prev_close = df['close'].shift(1)

        if pivot_type == 'standard':
            # Standard Pivot Points
            pivot = (prev_high + prev_low + prev_close) / 3
            r1 = (2 * pivot) - prev_low
            s1 = (2 * pivot) - prev_high
            r2 = pivot + (prev_high - prev_low)
            s2 = pivot - (prev_high - prev_low)
            r3 = prev_high + 2 * (pivot - prev_low)
            s3 = prev_low - 2 * (prev_high - pivot)

        elif pivot_type == 'fibonacci':
            # Fibonacci Pivot Points
            pivot = (prev_high + prev_low + prev_close) / 3
            diff = prev_high - prev_low
            r1 = pivot + 0.382 * diff
            s1 = pivot - 0.382 * diff
            r2 = pivot + 0.618 * diff
            s2 = pivot - 0.618 * diff
            r3 = pivot + diff
            s3 = pivot - diff

        elif pivot_type == 'woodie':
            # Woodie Pivot Points
            pivot = (prev_high + prev_low + 2 * prev_close) / 4
            r1 = (2 * pivot) - prev_low
            s1 = (2 * pivot) - prev_high
            r2 = pivot + (prev_high - prev_low)
            s2 = pivot - (prev_high - prev_low)
            r3 = prev_high + 2 * (pivot - prev_low)
            s3 = prev_low - 2 * (prev_high - pivot)

        elif pivot_type == 'camarilla':
            # Camarilla Pivot Points
            pivot = (prev_high + prev_low + prev_close) / 3
            diff = prev_high - prev_low
            r1 = prev_close + diff * 1.1 / 12
            s1 = prev_close - diff * 1.1 / 12
            r2 = prev_close + diff * 1.1 / 6
            s2 = prev_close - diff * 1.1 / 6
            r3 = prev_close + diff * 1.1 / 4
            s3 = prev_close - diff * 1.1 / 4

        else:
            # Default to standard
            pivot = (prev_high + prev_low + prev_close) / 3
            r1 = (2 * pivot) - prev_low
            s1 = (2 * pivot) - prev_high
            r2 = pivot + (prev_high - prev_low)
            s2 = pivot - (prev_high - prev_low)
            r3 = prev_high + 2 * (pivot - prev_low)
            s3 = prev_low - 2 * (prev_high - pivot)

        return {
            'pivot': pivot.tolist(),
            's1': s1.tolist(),
            's2': s2.tolist(),
            's3': s3.tolist(),
            'r1': r1.tolist(),
            'r2': r2.tolist(),
            'r3': r3.tolist()
        }


# Export singleton instance
_indicators_instance = TechnicalIndicators()


def get_indicators_service() -> TechnicalIndicators:
    """Get indicators service instance"""
    return _indicators_instance
