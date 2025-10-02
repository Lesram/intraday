"""Production guardrails with transactional daily caps and event deduplication

Enhanced guardrails implementation using:
1. SELECT FOR UPDATE for atomic daily cap checking
2. Event deduplication via order_events table
3. Transactional rollback on guardrail violations
4. Circuit breaker with broker error classification
"""
import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, update, func, and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging
from enum import Enum

from backend.infra.db import get_db_session
from backend.database.models_production import DailyLedger, OrderEvent
from backend.infra.repositories.orders import OrdersRepo
from backend.integrations.alpaca_broker import AlpacaBrokerClient


logger = logging.getLogger(__name__)


class BrokerErrorType(Enum):
    """Classification of broker errors for circuit breaker logic"""
    BROKER_REJECT = "BROKER_REJECT"  # Invalid order parameters, insufficient funds
    BROKER_DOWN = "BROKER_DOWN"      # 5xx errors, timeouts, connection failures  
    RATE_LIMITED = "RATE_LIMITED"    # 429 Too Many Requests
    NETWORK_ERROR = "NETWORK_ERROR"  # DNS, connection refused, etc.
    UNKNOWN = "UNKNOWN"              # Unclassified errors


class GuardrailViolation(Exception):
    """Raised when trading guardrails are violated"""
    def __init__(self, message: str, violation_type: str, current_value: Optional[float] = None, limit: Optional[float] = None):
        self.violation_type = violation_type
        self.current_value = current_value
        self.limit = limit
        super().__init__(message)


class TransactionalGuardrails:
    """Production guardrails with atomic daily cap operations"""
    
    def __init__(self, 
                 symbol_whitelist: List[str],
                 max_daily_orders: int = 1000,
                 max_daily_notional: float = 10000.0,
                 max_order_size: float = 1000.0,
                 trading_start_hour: int = 9,  # 9 AM ET
                 trading_end_hour: int = 16,   # 4 PM ET
                 circuit_breaker_threshold: int = 10,  # Consecutive broker errors
                 circuit_breaker_window_minutes: int = 5):
        
        self.symbol_whitelist = set(symbol_whitelist)
        self.max_daily_orders = max_daily_orders
        self.max_daily_notional = Decimal(str(max_daily_notional))
        self.max_order_size = Decimal(str(max_order_size))
        self.trading_start_hour = trading_start_hour
        self.trading_end_hour = trading_end_hour
        
        # Circuit breaker state
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_window_minutes = circuit_breaker_window_minutes
        self.consecutive_errors = 0
        self.circuit_open = False
        self.last_error_time: Optional[datetime] = None
        
        # Broker error tracking for classification
        self.recent_errors: List[Tuple[datetime, BrokerErrorType]] = []
    
    async def validate_order_atomic(self, 
                                  account_id: str,
                                  symbol: str, 
                                  notional_usd: float,
                                  client_order_id: str) -> None:
        """
        Atomically validate order against all guardrails using SELECT FOR UPDATE.
        
        This ensures race-condition-free daily cap checking by:
        1. Acquiring row-level lock on daily ledger
        2. Checking all constraints within transaction
        3. Updating daily counters atomically
        4. Rolling back on any violation
        """
        if self.circuit_open:
            raise GuardrailViolation(
                "Circuit breaker is OPEN - broker integration temporarily disabled",
                "CIRCUIT_BREAKER"
            )
        
        # Basic validations (no DB needed)
        self._validate_symbol(symbol)
        self._validate_order_size(notional_usd)
        self._validate_trading_hours()
        
        # Atomic daily cap validation with SELECT FOR UPDATE
        async for session in get_db_session():
            async with session.begin():  # Start transaction
                
                # Get or create daily ledger with row lock
                today = date.today()
                
                # SELECT FOR UPDATE to prevent race conditions
                query = select(DailyLedger).where(
                    and_(
                        DailyLedger.account_id == account_id,
                        DailyLedger.day_utc == today
                    )
                ).with_for_update()
                
                result = await session.execute(query)
                daily_ledger = result.scalar_one_or_none()
                
                if daily_ledger is None:
                    # Create new daily ledger
                    daily_ledger = DailyLedger(
                        account_id=account_id,
                        day_utc=today,
                        orders_count=0,
                        submitted_notional_usd=Decimal('0.00'),
                        filled_notional_usd=Decimal('0.00')
                    )
                    session.add(daily_ledger)
                    await session.flush()  # Get the ID
                
                # Check daily limits (atomic within transaction)
                new_orders_count = daily_ledger.orders_count + 1
                new_notional = daily_ledger.submitted_notional_usd + Decimal(str(notional_usd))
                
                if new_orders_count > self.max_daily_orders:
                    raise GuardrailViolation(
                        f"Daily order limit exceeded: {new_orders_count} > {self.max_daily_orders}",
                        "DAILY_ORDERS_LIMIT",
                        current_value=new_orders_count,
                        limit=self.max_daily_orders
                    )
                
                if new_notional > self.max_daily_notional:
                    raise GuardrailViolation(
                        f"Daily notional limit exceeded: ${new_notional} > ${self.max_daily_notional}",
                        "DAILY_NOTIONAL_LIMIT", 
                        current_value=float(new_notional),
                        limit=float(self.max_daily_notional)
                    )
                
                # Update daily counters atomically
                daily_ledger.orders_count = new_orders_count
                daily_ledger.submitted_notional_usd = new_notional
                daily_ledger.updated_at = func.now()
                
                logger.info(f"Guardrails passed for {symbol}: {new_orders_count} orders, ${new_notional} notional")
                
                # Transaction will commit automatically when exiting async with session.begin()
    
    async def record_trade_event(self,
                                order_id: str,
                                broker_order_id: str,
                                event_type: str,
                                event_time: datetime,
                                event_data: Optional[Dict] = None) -> bool:
        """
        Record trade event with deduplication.
        
        Returns:
            True if event was newly recorded
            False if event was already processed (duplicate)
        """
        async for session in get_db_session():
            try:
                event = OrderEvent(
                    order_id=order_id,
                    broker_order_id=broker_order_id,
                    event_type=event_type,
                    event_time=event_time,
                    event_data=event_data
                )
                session.add(event)
                await session.commit()
                logger.info(f"Recorded new {event_type} event for order {broker_order_id}")
                return True
                
            except IntegrityError as e:
                await session.rollback()
                if "uq_events_broker_type_time" in str(e):
                    logger.debug(f"Duplicate {event_type} event for order {broker_order_id} at {event_time} - ignoring")
                    return False
                else:
                    logger.error(f"Failed to record trade event: {e}")
                    raise
    
    def classify_broker_error(self, error: Exception) -> BrokerErrorType:
        """Classify broker errors for circuit breaker logic"""
        error_msg = str(error).lower()
        
        if hasattr(error, 'status_code'):
            if error.status_code == 429:
                return BrokerErrorType.RATE_LIMITED
            elif 400 <= error.status_code < 500:
                return BrokerErrorType.BROKER_REJECT
            elif error.status_code >= 500:
                return BrokerErrorType.BROKER_DOWN
        
        # Classify by error message patterns
        if any(pattern in error_msg for pattern in [
            'insufficient', 'invalid', 'rejected', 'not allowed', 'forbidden'
        ]):
            return BrokerErrorType.BROKER_REJECT
            
        elif any(pattern in error_msg for pattern in [
            'timeout', 'connection', 'unavailable', 'internal server'
        ]):
            return BrokerErrorType.BROKER_DOWN
            
        elif 'rate limit' in error_msg or '429' in error_msg:
            return BrokerErrorType.RATE_LIMITED
            
        else:
            return BrokerErrorType.UNKNOWN
    
    def record_broker_error(self, error: Exception) -> None:
        """Record broker error and update circuit breaker state"""
        now = datetime.now(timezone.utc)
        error_type = self.classify_broker_error(error)
        
        # Track recent errors
        self.recent_errors.append((now, error_type))
        
        # Clean old errors (outside window)
        cutoff = now.timestamp() - (self.circuit_breaker_window_minutes * 60)
        self.recent_errors = [
            (ts, err_type) for ts, err_type in self.recent_errors 
            if ts.timestamp() > cutoff
        ]
        
        # Count consecutive errors (only BROKER_DOWN and NETWORK_ERROR trip breaker)
        tripping_errors = [BrokerErrorType.BROKER_DOWN, BrokerErrorType.NETWORK_ERROR]
        
        if error_type in tripping_errors:
            if self.last_error_time and (now - self.last_error_time).total_seconds() < 60:
                self.consecutive_errors += 1
            else:
                self.consecutive_errors = 1
            
            self.last_error_time = now
            
            if self.consecutive_errors >= self.circuit_breaker_threshold:
                self.circuit_open = True
                logger.error(f"CIRCUIT BREAKER OPENED after {self.consecutive_errors} consecutive {error_type.value} errors")
        else:
            # Non-tripping errors reset consecutive count
            self.consecutive_errors = 0
        
        logger.warning(f"Broker error classified as {error_type.value}: {error}")
    
    def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker (admin operation)"""
        self.circuit_open = False
        self.consecutive_errors = 0
        self.last_error_time = None
        logger.info("Circuit breaker manually reset")
    
    def _validate_symbol(self, symbol: str) -> None:
        """Validate symbol against whitelist"""
        if symbol not in self.symbol_whitelist:
            raise GuardrailViolation(
                f"Symbol {symbol} not in whitelist: {sorted(self.symbol_whitelist)}",
                "SYMBOL_WHITELIST"
            )
    
    def _validate_order_size(self, notional_usd: float) -> None:
        """Validate individual order size"""
        if notional_usd > self.max_order_size:
            raise GuardrailViolation(
                f"Order size ${notional_usd} exceeds limit ${self.max_order_size}",
                "ORDER_SIZE_LIMIT",
                current_value=notional_usd,
                limit=self.max_order_size
            )
    
    def _validate_trading_hours(self) -> None:
        """Validate current time against trading hours (ET)"""
        # Simple validation - extend for market holidays, etc.
        now = datetime.now(timezone.utc)
        # Convert to ET (approximate - doesn't handle DST properly)
        et_hour = (now.hour - 5) % 24  # UTC-5 for EST
        
        if not (self.trading_start_hour <= et_hour < self.trading_end_hour):
            raise GuardrailViolation(
                f"Trading outside allowed hours: {et_hour}:00 ET (allowed: {self.trading_start_hour}:00-{self.trading_end_hour}:00 ET)",
                "TRADING_HOURS"
            )
    
    def get_circuit_breaker_status(self) -> Dict:
        """Get circuit breaker status for monitoring"""
        return {
            "circuit_open": self.circuit_open,
            "consecutive_errors": self.consecutive_errors,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "recent_errors_count": len(self.recent_errors),
            "recent_errors_by_type": {
                error_type.value: sum(1 for _, et in self.recent_errors if et == error_type)
                for error_type in BrokerErrorType
            }
        }