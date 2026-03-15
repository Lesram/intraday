"""
Technical Indicators API Endpoints

Provides REST API for calculating technical indicators on market data.

Phase 7 - Market Data & Charting
Created: October 16, 2025
"""

import logging
from math import isnan

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.infra.security import get_authenticated_user
from backend.services.indicators import get_indicators_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indicators", tags=["indicators"])


def clean_nan_values(values):
    """Convert NaN values to None for JSON serialization"""
    if isinstance(values, dict):
        return {k: clean_nan_values(v) for k, v in values.items()}
    elif isinstance(values, list):
        return [None if isinstance(v, float) and isnan(v) else v for v in values]
    elif isinstance(values, float) and isnan(values):
        return None
    return values


# Request/Response Models
class BarData(BaseModel):
    """Single OHLCV bar"""
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class IndicatorRequest(BaseModel):
    """Request for indicator calculation"""
    indicator: str
    symbol: str | None = None  # For fetching bars from market data
    timeframe: str | None = None
    start: str | None = None
    end: str | None = None
    bars: list[BarData] | None = None  # Or provide bars directly
    params: dict | None = {}


class IndicatorResponse(BaseModel):
    """Response with calculated indicator values"""
    indicator: str
    values: list[float | None] | dict
    params: dict


class IndicatorInfo(BaseModel):
    """Information about a single indicator"""
    name: str
    description: str
    params: list[str]


class IndicatorsListResponse(BaseModel):
    """Response with list of available indicators"""
    indicators: list[IndicatorInfo]


@router.post("/calculate", response_model=IndicatorResponse)
async def calculate_indicator(
    request: IndicatorRequest,
    user = Depends(get_authenticated_user)
) -> IndicatorResponse:
    """
    Calculate a technical indicator on provided bar data.

    Args:
        request: IndicatorRequest with indicator type, bars, and parameters

    Returns:
        IndicatorResponse with calculated values

    Example:
        POST /api/v1/indicators/calculate
        {
            "indicator": "SMA",
            "symbol": "AAPL",
            "timeframe": "5m",
            "start": "2025-01-01",
            "end": "2025-10-16",
            "params": {"period": 20}
        }
    """
    try:
        indicators_service = get_indicators_service()
        indicator_type = request.indicator.upper()

        # ✅ REAL DATA: Fetch bars from Alpaca if symbol provided
        if request.symbol and not request.bars:
            from datetime import UTC, datetime, timedelta
            import os

            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            # Initialize Alpaca client
            alpaca_client = StockHistoricalDataClient(
                api_key=os.getenv('ALPACA_API_KEY_ID'),
                secret_key=os.getenv('ALPACA_API_SECRET_KEY')
            )

            # Map timeframe to Alpaca TimeFrame
            timeframe_map = {
                '1m': TimeFrame(1, TimeFrameUnit.Minute),
                '5m': TimeFrame(5, TimeFrameUnit.Minute),
                '15m': TimeFrame(15, TimeFrameUnit.Minute),
                '30m': TimeFrame(30, TimeFrameUnit.Minute),
                '1h': TimeFrame(1, TimeFrameUnit.Hour),
                '4h': TimeFrame(4, TimeFrameUnit.Hour),
                '1D': TimeFrame(1, TimeFrameUnit.Day),
                '1W': TimeFrame(1, TimeFrameUnit.Week),
                '1M': TimeFrame(1, TimeFrameUnit.Month)
            }

            alpaca_timeframe = timeframe_map.get(request.timeframe or '1D', TimeFrame(1, TimeFrameUnit.Day))

            # Use provided date range or default to last 6 months
            limit = 1000

            if request.start and request.end:
                # Use provided dates
                from dateutil import parser
                start_date = parser.parse(request.start) if isinstance(request.start, str) else request.start
                end_date = parser.parse(request.end) if isinstance(request.end, str) else request.end

                # Ensure both dates are timezone-naive for comparison with now(UTC)
                if start_date.tzinfo is not None:
                    start_date = start_date.replace(tzinfo=None)
                if end_date.tzinfo is not None:
                    end_date = end_date.replace(tzinfo=None)

                # Alpaca paper trading limitation: Can't access very recent intraday data
                # For intraday timeframes (< 1 day), limit to 15+ days ago minimum
                if alpaca_timeframe.unit in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                    max_end_date = datetime.now(UTC) - timedelta(days=15)
                    if end_date > max_end_date:
                        logger.warning(f"Adjusting end date from {end_date} to {max_end_date} due to Alpaca paper trading limitations")
                        end_date = max_end_date

                    # Ensure we have enough data for indicators
                    min_start_date = end_date - timedelta(days=180)
                    if start_date > min_start_date:
                        logger.warning(f"Adjusting start date from {start_date} to {min_start_date} to ensure enough data")
                        start_date = min_start_date

                logger.info(f"Using provided date range: {start_date} to {end_date}")
            else:
                # Default to last 6 months for indicators
                end_date = datetime.now(UTC)

                # For intraday data, go back 15+ days to avoid subscription restrictions
                if alpaca_timeframe.unit in [TimeFrameUnit.Minute, TimeFrameUnit.Hour]:
                    end_date = end_date - timedelta(days=15)

                start_date = end_date - timedelta(days=180)
                logger.info(f"Using default date range: {start_date} to {end_date}")

            # Fetch real bars from Alpaca with error handling
            # IMPORTANT: Alpaca paper trading has severe restrictions on recent SIP data
            # We need to use data that's at least 15+ days old, or use IEX feed

            try:
                # First attempt: Try with provided dates
                bars_request = StockBarsRequest(
                    symbol_or_symbols=request.symbol.upper(),
                    timeframe=alpaca_timeframe,
                    start=start_date,
                    end=end_date,
                    limit=limit,
                    feed=os.getenv('ALPACA_DATA_FEED', 'sip')  # SIP with Algo Trader Plus subscription
                )

                logger.info(f"Fetching bars (IEX feed): symbol={request.symbol}, timeframe={alpaca_timeframe}, start={start_date}, end={end_date}")
                response = alpaca_client.get_stock_bars(bars_request)
                logger.info("Successfully fetched bars from Alpaca IEX feed")

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Alpaca IEX feed error: {error_msg}")

                # Fallback: Try with much older data (15+ days ago)
                try:
                    logger.warning("IEX feed failed, trying with older date range (15+ days ago)")

                    # Use daily timeframe with data ending 15 days ago
                    alpaca_timeframe = TimeFrame(1, TimeFrameUnit.Day)
                    fallback_end = datetime.now(UTC) - timedelta(days=15)  # End 15 days ago
                    fallback_start = fallback_end - timedelta(days=365)     # Get 1 year of data

                    logger.info(f"Fallback: Fetching daily bars from {fallback_start} to {fallback_end}")

                    bars_request = StockBarsRequest(
                        symbol_or_symbols=request.symbol.upper(),
                        timeframe=alpaca_timeframe,
                        start=fallback_start,
                        end=fallback_end,
                        limit=limit,
                        feed=os.getenv('ALPACA_DATA_FEED', 'sip')  # SIP with Algo Trader Plus subscription
                    )
                    response = alpaca_client.get_stock_bars(bars_request)
                    logger.info("Successfully fetched daily bars (fallback with old dates)")

                except Exception as fallback_error:
                    logger.error(f"Alpaca IEX and daily fallback failed: {str(fallback_error)}")

                    # FINAL FALLBACK: Try yfinance
                    try:
                        logger.warning(f"Trying yfinance as final fallback for {request.symbol}")
                        import yfinance as yf

                        ticker = yf.Ticker(request.symbol.upper())
                        df = ticker.history(
                            start=start_date.strftime('%Y-%m-%d'),
                            end=end_date.strftime('%Y-%m-%d'),
                            interval='1d'
                        )

                        if df.empty:
                            raise ValueError(f"No data from yfinance for {request.symbol}")

                        # Convert yfinance DataFrame to BarData
                        bars_list = []
                        for idx, row in df.iterrows():
                            bars_list.append(BarData(
                                time=idx.isoformat(),
                                open=float(row['Open']),
                                high=float(row['High']),
                                low=float(row['Low']),
                                close=float(row['Close']),
                                volume=int(row['Volume'])
                            ))

                        logger.info(f"Successfully fetched {len(bars_list)} bars from yfinance (FREE, 15-min delayed)")
                        request.bars = bars_list

                    except ImportError:
                        logger.error("yfinance not installed. Install with: pip install yfinance")
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Unable to fetch market data. All data sources failed. Please install yfinance (pip install yfinance) or upgrade your Alpaca subscription. Error: {str(fallback_error)}"
                        )
                    except Exception as yf_error:
                        logger.error(f"All data sources failed (Alpaca IEX, Alpaca old data, yfinance): {str(yf_error)}")
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Unable to fetch market data from any source (Alpaca, yfinance). Please check your internet connection or try a different symbol. Alpaca error: {str(fallback_error)}, yfinance error: {str(yf_error)}"
                            )

            # Convert Alpaca bars to BarData (only if we got response from Alpaca)
            bars_list = []

            # Check if we got Alpaca data
            if 'response' in locals() and response:
                if hasattr(response, 'data') and request.symbol.upper() in response.data:
                    # Response has .data attribute (newer SDK version)
                    for bar in response.data[request.symbol.upper()]:
                        bars_list.append(BarData(
                            time=bar.timestamp.isoformat(),
                            open=float(bar.open),
                            high=float(bar.high),
                            low=float(bar.low),
                            close=float(bar.close),
                            volume=int(bar.volume)
                        ))
                elif request.symbol.upper() in response:
                    # Response is dict-like (older SDK version)
                    for bar in response[request.symbol.upper()]:
                        bars_list.append(BarData(
                            time=bar.timestamp.isoformat(),
                            open=float(bar.open),
                            high=float(bar.high),
                            low=float(bar.low),
                            close=float(bar.close),
                            volume=int(bar.volume)
                        ))

            # If we got bars from yfinance, they're already in request.bars
            if not bars_list and hasattr(request, 'bars') and request.bars:
                bars_list = request.bars

            if not bars_list:
                logger.warning(f"No bars returned from Alpaca for {request.symbol}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No historical data found for {request.symbol}"
                )

            request.bars = bars_list

        if not request.bars:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Either 'bars' or 'symbol' must be provided"
            )

        # Extract price data and timestamps
        closes = [bar.close for bar in request.bars]
        highs = [bar.high for bar in request.bars]
        lows = [bar.low for bar in request.bars]
        volumes = [bar.volume for bar in request.bars]
        timestamps = [bar.time for bar in request.bars]  # Extract timestamps

        logger.info(f"Calculating {indicator_type} with {len(closes)} bars for {request.symbol}, params: {request.params}")

        # Helper function to create dict with timestamps
        def create_timestamped_values(values_list: list[float | None]) -> dict:
            """Convert list of values to dict with timestamps"""
            import math

            result = {
                str(timestamps[i]): values_list[i]
                for i in range(len(values_list))
                if values_list[i] is not None and not (isinstance(values_list[i], float) and math.isnan(values_list[i]))
            }

            # Log if result is empty
            if not result:
                none_count = sum(1 for v in values_list if v is None)
                nan_count = sum(1 for v in values_list if isinstance(v, float) and math.isnan(v))
                logger.warning(
                    f"create_timestamped_values returned empty dict. "
                    f"Input: {len(values_list)} values, {none_count} None, {nan_count} NaN, "
                    f"sample values: {values_list[:5]}"
                )
            else:
                logger.info(f"create_timestamped_values: {len(result)} valid values out of {len(values_list)} total")

            return result

        # Calculate based on indicator type
        if indicator_type == "SMA":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_sma(closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "EMA":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_ema(closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "RSI":
            period = request.params.get('period', 14)
            values = indicators_service.calculate_rsi(closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "MACD":
            fast = request.params.get('fast_period', 12)
            slow = request.params.get('slow_period', 26)
            signal_period = request.params.get('signal_period', 9)
            values = indicators_service.calculate_macd(closes, fast, slow, signal_period)

            # MACD returns dict with macd, signal, histogram
            timestamped_macd = {
                'macd': create_timestamped_values(values.get('macd', [])),
                'signal': create_timestamped_values(values.get('signal', [])),
                'histogram': create_timestamped_values(values.get('histogram', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_macd,
                params={'fast_period': fast, 'slow_period': slow, 'signal_period': signal_period}
            )

        elif indicator_type == "BB" or indicator_type == "BOLLINGER":
            period = request.params.get('period', 20)
            std_dev = request.params.get('std_dev', 2.0)
            values = indicators_service.calculate_bollinger_bands(closes, period, std_dev)

            # Bollinger Bands returns dict with upper, middle, lower
            timestamped_bb = {
                'upper': create_timestamped_values(values.get('upper', [])),
                'middle': create_timestamped_values(values.get('middle', [])),
                'lower': create_timestamped_values(values.get('lower', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_bb,
                params={'period': period, 'std_dev': std_dev}
            )

        elif indicator_type == "ATR":
            period = request.params.get('period', 14)
            values = indicators_service.calculate_atr(highs, lows, closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "STOCH" or indicator_type == "STOCHASTIC":
            k_period = request.params.get('k_period', 14)
            d_period = request.params.get('d_period', 3)
            values = indicators_service.calculate_stochastic(highs, lows, closes, k_period, d_period)

            # Stochastic returns dict with k and d
            timestamped_stoch = {
                'k': create_timestamped_values(values.get('k', [])),
                'd': create_timestamped_values(values.get('d', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_stoch,
                params={'k_period': k_period, 'd_period': d_period}
            )

        elif indicator_type == "ADX":
            period = request.params.get('period', 14)
            values = indicators_service.calculate_adx(highs, lows, closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "VOLUME_MA":
            # Volume Moving Average - SMA applied to volume
            period = request.params.get('period', 20)
            values = indicators_service.calculate_sma(volumes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "OBV":
            values = indicators_service.calculate_obv(closes, volumes)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={}
            )

        elif indicator_type == "VWAP":
            values = indicators_service.calculate_vwap(highs, lows, closes, volumes)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={}
            )

        elif indicator_type == "CCI":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_cci(highs, lows, closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "WILLIAMS" or indicator_type == "WILLIAMS_R":
            period = request.params.get('period', 14)
            values = indicators_service.calculate_williams_r(highs, lows, closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "MFI":
            period = request.params.get('period', 14)
            values = indicators_service.calculate_mfi(highs, lows, closes, volumes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "SAR" or indicator_type == "PSAR" or indicator_type == "PARABOLIC_SAR":
            af_start = request.params.get('af_start', 0.02)
            af_increment = request.params.get('af_increment', 0.02)
            af_max = request.params.get('af_max', 0.2)
            values = indicators_service.calculate_parabolic_sar(
                highs, lows, af_start, af_increment, af_max
            )
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'af_start': af_start, 'af_increment': af_increment, 'af_max': af_max}
            )

        elif indicator_type == "AROON":
            period = request.params.get('period', 25)
            values = indicators_service.calculate_aroon(highs, lows, period)

            # Aroon returns dict with aroon_up, aroon_down, and aroon_oscillator
            timestamped_aroon = {
                'up': create_timestamped_values(values.get('aroon_up', [])),
                'down': create_timestamped_values(values.get('aroon_down', [])),
                'oscillator': create_timestamped_values(values.get('aroon_oscillator', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_aroon,
                params={'period': period}
            )

        elif indicator_type == "CMF" or indicator_type == "CHAIKIN":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_chaikin_money_flow(
                highs, lows, closes, volumes, period
            )
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "TRIX":
            period = request.params.get('period', 15)
            values = indicators_service.calculate_trix(closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "VWMA":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_volume_weighted_ma(closes, volumes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "KST":
            values = indicators_service.calculate_know_sure_thing(closes)

            # KST returns dict with kst and signal
            timestamped_kst = {
                'kst': create_timestamped_values(values.get('kst', [])),
                'signal': create_timestamped_values(values.get('signal', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_kst,
                params={}
            )

        elif indicator_type == "UO" or indicator_type == "ULTIMATE":
            values = indicators_service.calculate_ultimate_oscillator(highs, lows, closes)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={}
            )

        elif indicator_type == "AO" or indicator_type == "AWESOME":
            values = indicators_service.calculate_awesome_oscillator(highs, lows)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={}
            )

        elif indicator_type == "DONCHIAN":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_donchian_channel(highs, lows, period)

            # Donchian returns dict with upper, middle, lower
            timestamped_donchian = {
                'upper': create_timestamped_values(values.get('upper', [])),
                'middle': create_timestamped_values(values.get('middle', [])),
                'lower': create_timestamped_values(values.get('lower', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_donchian,
                params={'period': period}
            )

        elif indicator_type == "KELTNER":
            period = request.params.get('period', 20)
            atr_multiplier = request.params.get('atr_multiplier', 2.0)
            values = indicators_service.calculate_keltner_channel(
                highs, lows, closes, period, atr_multiplier
            )

            # Keltner returns dict with upper, middle, lower
            timestamped_keltner = {
                'upper': create_timestamped_values(values.get('upper', [])),
                'middle': create_timestamped_values(values.get('middle', [])),
                'lower': create_timestamped_values(values.get('lower', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_keltner,
                params={'period': period, 'atr_multiplier': atr_multiplier}
            )

        elif indicator_type == "ICHIMOKU":
            values = indicators_service.calculate_ichimoku_cloud(highs, lows, closes)

            # Ichimoku returns dict with 5 lines
            timestamped_ichimoku = {
                'tenkan': create_timestamped_values(values.get('tenkan', [])),
                'kijun': create_timestamped_values(values.get('kijun', [])),
                'senkou_a': create_timestamped_values(values.get('senkou_a', [])),
                'senkou_b': create_timestamped_values(values.get('senkou_b', [])),
                'chikou': create_timestamped_values(values.get('chikou', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_ichimoku,
                params={}
            )

        elif indicator_type == "WMA":
            period = request.params.get('period', 20)
            values = indicators_service.calculate_wma(closes, period)
            return IndicatorResponse(
                indicator=indicator_type,
                values={'values': create_timestamped_values(values)},
                params={'period': period}
            )

        elif indicator_type == "PIVOT" or indicator_type == "PIVOT_POINTS":
            pivot_type = request.params.get('pivot_type', 'standard')
            values = indicators_service.calculate_pivot_points(
                highs, lows, closes, pivot_type
            )

            # Pivot returns dict with pivot, s1-s3, r1-r3
            timestamped_pivot = {
                'pivot': create_timestamped_values(values.get('pivot', [])),
                's1': create_timestamped_values(values.get('s1', [])),
                's2': create_timestamped_values(values.get('s2', [])),
                's3': create_timestamped_values(values.get('s3', [])),
                'r1': create_timestamped_values(values.get('r1', [])),
                'r2': create_timestamped_values(values.get('r2', [])),
                'r3': create_timestamped_values(values.get('r3', []))
            }

            return IndicatorResponse(
                indicator=indicator_type,
                values=timestamped_pivot,
                params={'pivot_type': pivot_type}
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown indicator type: {indicator_type}"
            )

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Failed to calculate indicator {request.indicator}: {e}\n{error_details}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate indicator {request.indicator}: {str(e)}"
        )


@router.get("/list", response_model=IndicatorsListResponse)
async def list_indicators() -> IndicatorsListResponse:
    """
    Get list of available indicators.

    Returns:
        List of available indicator names with descriptions
    """
    return IndicatorsListResponse(indicators=[
        IndicatorInfo(name="SMA", description="Simple Moving Average", params=["period"]),
        IndicatorInfo(name="EMA", description="Exponential Moving Average", params=["period"]),
        IndicatorInfo(name="RSI", description="Relative Strength Index", params=["period"]),
        IndicatorInfo(name="MACD", description="Moving Average Convergence Divergence",
             params=["fast_period", "slow_period", "signal_period"]),
        IndicatorInfo(name="BB", description="Bollinger Bands", params=["period", "std_dev"]),
        IndicatorInfo(name="ATR", description="Average True Range", params=["period"]),
        IndicatorInfo(name="STOCH", description="Stochastic Oscillator", params=["k_period", "d_period"]),
        IndicatorInfo(name="ADX", description="Average Directional Index", params=["period"]),
        IndicatorInfo(name="OBV", description="On Balance Volume", params=[]),
        IndicatorInfo(name="VOLUME_MA", description="Volume Moving Average", params=["period"]),
        IndicatorInfo(name="VWAP", description="Volume Weighted Average Price", params=[]),
        IndicatorInfo(name="CCI", description="Commodity Channel Index", params=["period"]),
        IndicatorInfo(name="WILLIAMS_R", description="Williams %R", params=["period"]),
        IndicatorInfo(name="MFI", description="Money Flow Index", params=["period"]),
        IndicatorInfo(name="PSAR", description="Parabolic SAR",
             params=["af_start", "af_increment", "af_max"]),

        # NEW INDICATORS
        IndicatorInfo(name="AROON", description="Aroon Indicator (Up/Down/Oscillator)", params=["period"]),
        IndicatorInfo(name="CMF", description="Chaikin Money Flow", params=["period"]),
        IndicatorInfo(name="TRIX", description="Triple Exponential Average", params=["period"]),
        IndicatorInfo(name="VWMA", description="Volume Weighted Moving Average", params=["period"]),
        IndicatorInfo(name="KST", description="Know Sure Thing Oscillator", params=[]),
        IndicatorInfo(name="UO", description="Ultimate Oscillator", params=[]),
        IndicatorInfo(name="AO", description="Awesome Oscillator", params=[]),
        IndicatorInfo(name="DONCHIAN", description="Donchian Channel", params=["period"]),
        IndicatorInfo(name="KELTNER", description="Keltner Channel", params=["period", "atr_multiplier"]),
        IndicatorInfo(name="ICHIMOKU", description="Ichimoku Cloud", params=[]),
        IndicatorInfo(name="WMA", description="Weighted Moving Average", params=["period"]),
        IndicatorInfo(name="PIVOT", description="Pivot Points (Support/Resistance)", params=["pivot_type"]),
    ])


# Export router
__all__ = ["router"]
