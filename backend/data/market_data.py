"""
Market Data Processing Module
Provides resilient market data processing with error handling.
"""

import math
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class MarketDataPoint:
    """Single market data point."""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: int

class MarketDataProcessor:
    """
    Processes market data with resilience to malformed inputs.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.processed_count = 0
        self.error_count = 0
        
    def process_tick(self, tick_data):
        """Process a single market tick - alias for process_raw_data for compatibility."""
        return self.process_raw_data(tick_data)
    
    def process_raw_data(self, raw_data):
        """
        Process raw market data with resilience to malformed inputs.
        
        Args:
            raw_data: Raw market data (can be malformed)
            
        Returns:
            Processed data result with status
        """
        try:
            if raw_data is None:
                return {"status": "rejected", "error": "null_data"}
                
            # More aggressive validation for malformed data
            if isinstance(raw_data, dict):
                # Check for obviously malformed data patterns
                if 'price' in raw_data:
                    price = raw_data['price']
                    if isinstance(price, str) and price not in ['0', '0.0']:
                        return {"status": "rejected", "error": "invalid_price_format"}
                    try:
                        price_val = float(price)
                        if math.isnan(price_val) or math.isinf(price_val) or price_val <= 0:
                            return {"status": "rejected", "error": "invalid_price_value"}
                        if price_val > 1000000:  # Extremely high price
                            return {"status": "rejected", "error": "price_too_high"}
                    except (ValueError, TypeError):
                        return {"status": "rejected", "error": "price_conversion_failed"}
                
                if 'symbol' in raw_data:
                    symbol = raw_data['symbol']
                    if not isinstance(symbol, str) or len(symbol) == 0 or len(symbol) > 10:
                        return {"status": "rejected", "error": "invalid_symbol"}
                
                if 'volume' in raw_data:
                    volume = raw_data['volume']
                    if isinstance(volume, str) and volume not in ['0', '0.0']:
                        return {"status": "rejected", "error": "invalid_volume_format"}
                    try:
                        vol_val = float(volume)
                        if math.isnan(vol_val) or math.isinf(vol_val) or vol_val < 0:
                            return {"status": "rejected", "error": "invalid_volume_value"}
                    except (ValueError, TypeError):
                        return {"status": "rejected", "error": "volume_conversion_failed"}
                
            # Handle different input types safely
            if isinstance(raw_data, str):
                return self._process_string_data(raw_data)
            elif isinstance(raw_data, dict):
                return self._process_dict_data(raw_data)
            elif isinstance(raw_data, list):
                return self._process_list_data(raw_data)
            elif hasattr(raw_data, '__iter__'):
                return self._process_iterable_data(raw_data)
            else:
                return {"status": "rejected", "error": "unsupported_type"}
                
        except Exception as e:
            self.error_count += 1
            logger.warning(f"Market data processing error: {e}")
            return {"status": "error", "error": str(e)}
    
    def _process_string_data(self, data: str) -> Dict[str, Any]:
        """Process string-based market data."""
        try:
            if not data.strip():
                return {"status": "error", "error": "empty_string"}
                
            # Try to parse as JSON-like data
            if data.startswith('{') or data.startswith('['):
                import json
                parsed = json.loads(data)
                return self._process_dict_data(parsed) if isinstance(parsed, dict) else self._process_list_data(parsed)
            
            # Try to parse as CSV-like data
            lines = data.strip().split('\n')
            if len(lines) > 1:
                return {"status": "processed", "rows": len(lines), "format": "csv_like"}
                
            return {"status": "processed", "format": "string", "length": len(data)}
            
        except Exception as e:
            return {"status": "error", "error": f"string_parsing: {e}"}
    
    def _process_dict_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process dictionary-based market data."""
        try:
            processed_fields = 0
            
            # Look for common market data fields
            price_fields = ['open', 'high', 'low', 'close', 'price']
            volume_fields = ['volume', 'vol', 'quantity']
            time_fields = ['timestamp', 'time', 'date', 'datetime']
            
            for field_group in [price_fields, volume_fields, time_fields]:
                for field in field_group:
                    if field in data:
                        value = data[field]
                        if self._validate_numeric_field(value, field):
                            processed_fields += 1
            
            self.processed_count += 1
            result = {
                "status": "processed",
                "fields_processed": processed_fields,
                "total_fields": len(data),
                "format": "dict"
            }
            
            # Preserve important fields in the result
            if 'symbol' in data:
                result['symbol'] = data['symbol']
            if 'price' in data:
                result['price'] = data['price']
                
            return result
            
        except Exception as e:
            return {"status": "error", "error": f"dict_processing: {e}"}
    
    def _process_list_data(self, data: List[Any]) -> Dict[str, Any]:
        """Process list-based market data."""
        try:
            if not data:
                return {"status": "error", "error": "empty_list"}
                
            processed_items = 0
            for item in data[:100]:  # Limit processing to prevent memory issues
                if isinstance(item, dict):
                    result = self._process_dict_data(item)
                    if result["status"] == "processed":
                        processed_items += 1
                elif isinstance(item, (int, float)):
                    if self._validate_numeric_field(item, "list_item"):
                        processed_items += 1
            
            return {
                "status": "processed",
                "items_processed": processed_items,
                "total_items": len(data),
                "format": "list"
            }
            
        except Exception as e:
            return {"status": "error", "error": f"list_processing: {e}"}
    
    def _process_iterable_data(self, data: Any) -> Dict[str, Any]:
        """Process other iterable data types."""
        try:
            items = list(data)  # Convert to list safely
            return self._process_list_data(items)
        except Exception as e:
            return {"status": "error", "error": f"iterable_processing: {e}"}
    
    def _validate_numeric_field(self, value: Any, field_name: str) -> bool:
        """Validate numeric field values."""
        try:
            if value is None:
                return False
                
            # Convert to float if possible
            if isinstance(value, str):
                float_val = float(value)
            elif isinstance(value, (int, float)):
                float_val = float(value)
            else:
                return False
            
            # Check for invalid values
            if np.isnan(float_val) or np.isinf(float_val):
                return False
                
            # Basic sanity checks for market data
            if field_name in ['open', 'high', 'low', 'close', 'price']:
                return 0 < float_val < 1000000  # Reasonable price range
            elif field_name in ['volume', 'vol', 'quantity']:
                return float_val >= 0  # Volume can't be negative
            
            return True
            
        except (ValueError, TypeError, OverflowError):
            return False
    
    def get_processing_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        return {
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "success_rate": self.processed_count / max(1, self.processed_count + self.error_count)
        }
