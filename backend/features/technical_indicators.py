"""
Technical Indicators Module
Provides technical analysis indicators with resilience to extreme conditions.
"""

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class IndicatorResult:
    """Result from technical indicator calculation."""
    value: float | None
    confidence: float
    error: str | None = None

class TechnicalIndicators:
    """
    Technical indicators calculator with resilience to extreme market conditions.
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.calculation_count = 0
        self.error_count = 0
        
    def calculate_all_features(self, data_frame):
        """Calculate all available technical indicators for the given data frame."""
        try:
            if data_frame is None or data_frame.empty:
                return None
            
            if 'close' not in data_frame.columns:
                return None
                
            close_prices = data_frame['close'].values.tolist()  # Convert to list
            
            if len(close_prices) < 10:  # Need minimum data points
                return None
            
            features = {}
            
            # SMA with different periods
            for period in [20, 50]:
                if len(close_prices) >= period:
                    sma_result = self.calculate_sma(close_prices, period)
                    if sma_result is not None and hasattr(sma_result, 'value') and sma_result.value is not None:
                        features[f'sma_{period}'] = sma_result.value
            
            # RSI
            if len(close_prices) >= 14:
                rsi_result = self.calculate_rsi(close_prices)
                if rsi_result is not None and hasattr(rsi_result, 'value') and rsi_result.value is not None:
                    features['rsi'] = rsi_result.value
            
            # Basic statistics
            features.update({
                'price_mean': np.mean(close_prices),
                'price_std': np.std(close_prices),
                'price_max': np.max(close_prices),
                'price_min': np.min(close_prices),
            })
            
            return features
            
        except Exception as e:
            # Log error but don't crash
            logger.warning("Error calculating features", exc_info=True, extra={"error": str(e)})
            return None

    def calculate_sma(self, prices, period):
        """
        Calculate Simple Moving Average with error handling.
        
        Args:
            prices: List of price values
            period: SMA period
            
        Returns:
            IndicatorResult with SMA value
        """
        try:
            if not prices or len(prices) < period:
                return IndicatorResult(
                    value=None,
                    confidence=0.0,
                    error="insufficient_data"
                )
            
            # Filter out invalid values
            valid_prices = []
            for price in prices[-period:]:
                if self._is_valid_price(price):
                    valid_prices.append(float(price))
            
            if len(valid_prices) < period * 0.5:  # Need at least 50% valid data
                return IndicatorResult(
                    value=None,
                    confidence=0.0,
                    error="too_many_invalid_prices"
                )
            
            sma = sum(valid_prices) / len(valid_prices)
            confidence = len(valid_prices) / period
            
            self.calculation_count += 1
            return IndicatorResult(value=sma, confidence=confidence)
            
        except Exception as e:
            self.error_count += 1
            logger.warning(f"SMA calculation error: {e}")
            return IndicatorResult(value=None, confidence=0.0, error=str(e))
    
    def calculate_rsi(self, prices: list[float], period: int = 14) -> IndicatorResult:
        """
        Calculate Relative Strength Index with error handling.
        
        Args:
            prices: List of price values
            period: RSI period
            
        Returns:
            IndicatorResult with RSI value
        """
        try:
            if not prices or len(prices) < period + 1:
                return IndicatorResult(
                    value=None,
                    confidence=0.0,
                    error="insufficient_data"
                )
            
            # Calculate price changes
            changes = []
            for i in range(1, len(prices)):
                if self._is_valid_price(prices[i]) and self._is_valid_price(prices[i-1]):
                    changes.append(float(prices[i]) - float(prices[i-1]))
            
            if len(changes) < period:
                return IndicatorResult(
                    value=None,
                    confidence=0.0,
                    error="insufficient_valid_changes"
                )
            
            # Calculate gains and losses
            gains = [max(0, change) for change in changes[-period:]]
            losses = [max(0, -change) for change in changes[-period:]]
            
            avg_gain = sum(gains) / len(gains)
            avg_loss = sum(losses) / len(losses)
            
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            confidence = len(changes) / period
            
            self.calculation_count += 1
            return IndicatorResult(value=rsi, confidence=confidence)
            
        except Exception as e:
            self.error_count += 1
            logger.warning(f"RSI calculation error: {e}")
            return IndicatorResult(value=None, confidence=0.0, error=str(e))
    
    def calculate_bollinger_bands(self, prices: list[float], period: int = 20, std_dev: float = 2.0) -> dict[str, IndicatorResult]:
        """
        Calculate Bollinger Bands with error handling.
        
        Args:
            prices: List of price values
            period: BB period
            std_dev: Standard deviation multiplier
            
        Returns:
            Dict with upper, middle, lower band results
        """
        try:
            sma_result = self.calculate_sma(prices, period)
            
            if sma_result.value is None:
                null_result = IndicatorResult(value=None, confidence=0.0, error="sma_calculation_failed")
                return {
                    "upper": null_result,
                    "middle": null_result, 
                    "lower": null_result
                }
            
            # Calculate standard deviation
            valid_prices = []
            for price in prices[-period:]:
                if self._is_valid_price(price):
                    valid_prices.append(float(price))
            
            if len(valid_prices) < 2:
                null_result = IndicatorResult(value=None, confidence=0.0, error="insufficient_data_for_std")
                return {
                    "upper": null_result,
                    "middle": null_result,
                    "lower": null_result
                }
            
            variance = sum((price - sma_result.value) ** 2 for price in valid_prices) / len(valid_prices)
            std = math.sqrt(variance)
            
            upper = sma_result.value + (std_dev * std)
            lower = sma_result.value - (std_dev * std)
            
            confidence = len(valid_prices) / period
            
            self.calculation_count += 3
            return {
                "upper": IndicatorResult(value=upper, confidence=confidence),
                "middle": IndicatorResult(value=sma_result.value, confidence=confidence),
                "lower": IndicatorResult(value=lower, confidence=confidence)
            }
            
        except Exception as e:
            self.error_count += 1
            logger.warning(f"Bollinger Bands calculation error: {e}")
            null_result = IndicatorResult(value=None, confidence=0.0, error=str(e))
            return {
                "upper": null_result,
                "middle": null_result,
                "lower": null_result
            }
    
    def handle_extreme_conditions(self, prices: list[float]) -> dict[str, Any]:
        """
        Handle extreme market conditions (flash crashes, gaps, etc.).
        
        Args:
            prices: List of price values
            
        Returns:
            Analysis of extreme conditions
        """
        try:
            if not prices or len(prices) < 2:
                return {"status": "insufficient_data", "extreme_conditions": []}
            
            extreme_conditions = []
            
            # Check for flash crashes (large price drops)
            for i in range(1, len(prices)):
                if self._is_valid_price(prices[i]) and self._is_valid_price(prices[i-1]):
                    price_change = (float(prices[i]) - float(prices[i-1])) / float(prices[i-1])
                    
                    if price_change < -0.1:  # 10% drop
                        extreme_conditions.append({
                            "type": "flash_crash",
                            "index": i,
                            "change": price_change,
                            "severity": "high" if price_change < -0.2 else "medium"
                        })
                    elif price_change > 0.1:  # 10% spike
                        extreme_conditions.append({
                            "type": "price_spike",
                            "index": i,
                            "change": price_change,
                            "severity": "high" if price_change > 0.2 else "medium"
                        })
            
            # Check for volatility clustering
            if len(prices) >= 10:
                volatilities = []
                for i in range(1, len(prices)):
                    if self._is_valid_price(prices[i]) and self._is_valid_price(prices[i-1]):
                        vol = abs(float(prices[i]) - float(prices[i-1])) / float(prices[i-1])
                        volatilities.append(vol)
                
                if volatilities:
                    avg_vol = sum(volatilities) / len(volatilities)
                    high_vol_periods = sum(1 for vol in volatilities if vol > avg_vol * 3)
                    
                    if high_vol_periods > len(volatilities) * 0.3:  # More than 30% high volatility
                        extreme_conditions.append({
                            "type": "high_volatility_cluster",
                            "high_vol_periods": high_vol_periods,
                            "total_periods": len(volatilities),
                            "avg_volatility": avg_vol
                        })
            
            return {
                "status": "analyzed",
                "extreme_conditions": extreme_conditions,
                "total_conditions": len(extreme_conditions)
            }
            
        except Exception as e:
            self.error_count += 1
            logger.warning(f"Extreme conditions analysis error: {e}")
            return {"status": "error", "error": str(e), "extreme_conditions": []}
    
    def _is_valid_price(self, price: Any) -> bool:
        """Check if price is valid for calculations."""
        try:
            if price is None:
                return False
                
            float_price = float(price)
            
            # Check for NaN, infinity, negative, or unreasonably large values
            if (math.isnan(float_price) or 
                math.isinf(float_price) or 
                float_price <= 0 or 
                float_price > 1000000):
                return False
                
            return True
            
        except (ValueError, TypeError, OverflowError):
            return False
    
    def get_calculation_stats(self) -> dict[str, Any]:
        """Get calculation statistics."""
        return {
            "calculation_count": self.calculation_count,
            "error_count": self.error_count,
            "success_rate": self.calculation_count / max(1, self.calculation_count + self.error_count)
        }
