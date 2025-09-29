"""
Alpaca Broker Client Implementation

This module provides integration with Alpaca's Trading API for paper and live trading.
Used when USE_MOCK_BROKER=False to place real orders through Alpaca.
"""

import os
import uuid
from typing import Dict, Optional

import httpx
from fastapi import HTTPException

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class AlpacaBrokerClient:
    """
    Alpaca Trading API client for order management.
    
    Provides methods to place, retrieve, and cancel orders through Alpaca's trading API.
    Automatically routes to paper or live trading based on ALPACA_PAPER setting.
    """
    
    def __init__(self):
        """Initialize Alpaca Broker Client with configuration from environment."""
        self.api_key = os.getenv("ALPACA_API_KEY_ID")
        self.api_secret = os.getenv("ALPACA_API_SECRET_KEY")
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")
        
        # Set base URL based on paper/live mode
        if self.is_paper:
            self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        else:
            self.base_url = os.getenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
        
        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca API credentials not configured",
                         api_key_present=bool(self.api_key),
                         api_secret_present=bool(self.api_secret),
                         is_paper=self.is_paper)
        
        logger.info("Alpaca broker client initialized",
                   is_paper=self.is_paper,
                   base_url=self.base_url)
        
        # HTTP client with timeout and connection limits
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for Alpaca API requests."""
        if not self.api_key or not self.api_secret:
            raise HTTPException(
                status_code=503,
                detail="Alpaca API credentials not configured"
            )
        
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    def _map_order_side(self, side: str) -> str:
        """Map internal order side to Alpaca format."""
        side_lower = side.lower()
        if side_lower in ("buy", "long"):
            return "buy"
        elif side_lower in ("sell", "short"):
            return "sell"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order side: {side}. Must be 'buy' or 'sell'"
            )
    
    def _map_order_type(self, order_type: str) -> str:
        """Map internal order type to Alpaca format."""
        type_lower = order_type.lower()
        alpaca_types = ["market", "limit", "stop", "stop_limit", "trailing_stop"]
        
        if type_lower in alpaca_types:
            return type_lower
        elif type_lower == "mkt":
            return "market"
        elif type_lower == "lmt":
            return "limit"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order type: {order_type}. Must be one of {alpaca_types}"
            )
    
    def _map_time_in_force(self, tif: str) -> str:
        """Map time in force to Alpaca format."""
        tif_lower = tif.lower()
        alpaca_tifs = ["day", "gtc", "opg", "cls", "ioc", "fok"]
        
        if tif_lower in alpaca_tifs:
            return tif_lower
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid time in force: {tif}. Must be one of {alpaca_tifs}"
            )
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        type: str = "market",
        tif: str = "day",
        client_order_id: Optional[str] = None
    ) -> Dict:
        """
        Place an order with Alpaca.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'MSFT')
            side: Order side ('buy' or 'sell')
            qty: Order quantity (number of shares)
            type: Order type ('market', 'limit', etc.)
            tif: Time in force ('day', 'gtc', etc.)
            client_order_id: Optional client order ID for idempotency
            
        Returns:
            Dict containing order details from Alpaca API
            
        Raises:
            HTTPException: On API errors or validation failures
        """
        try:
            # Validate and map parameters
            alpaca_side = self._map_order_side(side)
            alpaca_type = self._map_order_type(type)
            alpaca_tif = self._map_time_in_force(tif)
            
            # Generate client order ID if not provided
            if not client_order_id:
                client_order_id = f"order_{uuid.uuid4().hex[:8]}"
            
            # Build order payload
            order_data = {
                "symbol": symbol.upper(),
                "side": alpaca_side,
                "type": alpaca_type,
                "time_in_force": alpaca_tif,
                "qty": str(qty),  # Alpaca expects string
                "client_order_id": client_order_id
            }
            
            logger.info("Placing order with Alpaca",
                       symbol=symbol,
                       side=alpaca_side,
                       qty=qty,
                       type=alpaca_type,
                       client_order_id=client_order_id,
                       is_paper=self.is_paper)
            
            # Make API request
            url = f"{self.base_url}/v2/orders"
            headers = self._get_auth_headers()
            
            response = await self.client.post(url, json=order_data, headers=headers)
            
            # Handle API response
            if response.status_code == 201:
                order_result = response.json()
                logger.info("Order placed successfully",
                           order_id=order_result.get("id"),
                           client_order_id=client_order_id,
                           status=order_result.get("status"))
                return order_result
            
            elif response.status_code in (400, 422):
                # Client error - invalid request
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": response.text}
                error_msg = error_data.get("message", "Invalid order request")
                logger.warning("Order rejected by Alpaca",
                             status_code=response.status_code,
                             error=error_msg,
                             client_order_id=client_order_id)
                raise HTTPException(status_code=response.status_code, detail=error_msg)
            
            else:
                # Server error or other issues
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"
                
                logger.error("Order placement failed",
                           status_code=response.status_code,
                           error=error_msg,
                           client_order_id=client_order_id)
                raise HTTPException(status_code=502, detail=error_msg)
                
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error placing order",
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to place order: {str(e)}"
            )
    
    async def get_order(self, order_id: str) -> Dict:
        """
        Retrieve order details by order ID.
        
        Args:
            order_id: Alpaca order ID or client order ID
            
        Returns:
            Dict containing order details
            
        Raises:
            HTTPException: On API errors or if order not found
        """
        try:
            logger.info("Retrieving order from Alpaca", order_id=order_id)
            
            # Try to get order by Alpaca order ID first
            url = f"{self.base_url}/v2/orders/{order_id}"
            headers = self._get_auth_headers()
            
            response = await self.client.get(url, headers=headers)
            
            if response.status_code == 200:
                order_data = response.json()
                logger.info("Order retrieved successfully",
                           order_id=order_id,
                           status=order_data.get("status"),
                           symbol=order_data.get("symbol"))
                return order_data
            
            elif response.status_code == 404:
                # Try by client_order_id if direct lookup failed
                try:
                    list_url = f"{self.base_url}/v2/orders"
                    params = {"status": "all", "limit": 100}
                    list_response = await self.client.get(list_url, headers=headers, params=params)
                    
                    if list_response.status_code == 200:
                        orders = list_response.json()
                        for order in orders:
                            if order.get("client_order_id") == order_id:
                                logger.info("Order found by client_order_id",
                                           client_order_id=order_id,
                                           alpaca_order_id=order.get("id"))
                                return order
                except Exception as e:
                    logger.warning("Failed to search by client_order_id", error=str(e))
                
                logger.warning("Order not found", order_id=order_id)
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
            
            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"
                
                logger.error("Failed to retrieve order",
                           order_id=order_id,
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)
                
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error retrieving order",
                        order_id=order_id,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to retrieve order: {str(e)}"
            )
    
    async def cancel_order(self, order_id: str) -> None:
        """
        Cancel an order by order ID.
        
        Args:
            order_id: Alpaca order ID or client order ID
            
        Raises:
            HTTPException: On API errors or if order cannot be canceled
        """
        try:
            logger.info("Canceling order with Alpaca", order_id=order_id)
            
            url = f"{self.base_url}/v2/orders/{order_id}"
            headers = self._get_auth_headers()
            
            response = await self.client.delete(url, headers=headers)
            
            if response.status_code == 204:
                logger.info("Order canceled successfully", order_id=order_id)
                return
            
            elif response.status_code == 404:
                logger.warning("Order not found for cancellation", order_id=order_id)
                raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")
            
            elif response.status_code == 422:
                # Order cannot be canceled (already filled, etc.)
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"message": "Cannot cancel order"}
                error_msg = error_data.get("message", "Order cannot be canceled")
                logger.warning("Order cancellation rejected",
                             order_id=order_id,
                             error=error_msg)
                raise HTTPException(status_code=422, detail=error_msg)
            
            else:
                error_msg = f"Alpaca API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f" - {error_data['message']}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"
                
                logger.error("Order cancellation failed",
                           order_id=order_id,
                           status_code=response.status_code,
                           error=error_msg)
                raise HTTPException(status_code=502, detail=error_msg)
                
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error("Unexpected error canceling order",
                        order_id=order_id,
                        error=str(e),
                        error_type=type(e).__name__)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to cancel order: {str(e)}"
            )
    
    async def close(self):
        """Close the HTTP client connection."""
        await self.client.aclose()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global client instance for dependency injection
_broker_client: AlpacaBrokerClient | None = None


def get_alpaca_broker_client() -> AlpacaBrokerClient:
    """
    Get or create global AlpacaBrokerClient instance.
    
    Returns:
        AlpacaBrokerClient instance for making trading API requests
    """
    global _broker_client
    if _broker_client is None:
        _broker_client = AlpacaBrokerClient()
    return _broker_client


async def cleanup_alpaca_broker_client():
    """Clean up global broker client resources."""
    global _broker_client
    if _broker_client:
        await _broker_client.close()
        _broker_client = None