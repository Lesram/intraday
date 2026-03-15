"""
Pydantic models for signal API endpoints.
Provides backward/forward compatibility between confidence and signal_strength fields.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator


class SignalResponse(BaseModel):
    """
    Signal response model with backward/forward compatibility.

    Supports both 'confidence' (legacy) and 'signal_strength' (canonical).
    If only one is provided, the other is automatically mirrored during validation.
    """

    symbol: str
    action: Literal["buy", "sell", "hold"]  # Canonical action values
    signal_strength: float  # Canonical field [0.0, 1.0]
    confidence: float | None = None  # Legacy compatibility field [0.0, 1.0]
    tp_pct: float  # Take profit percentage
    sl_pct: float  # Stop loss percentage
    generated_at: datetime

    @field_validator('signal_strength', 'confidence')
    @classmethod
    def validate_strength_range(cls, v: float | None) -> float | None:
        """Ensure strength values are in valid range [0.0, 1.0]"""
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("Signal strength and confidence must be between 0.0 and 1.0")
        return v

    @model_validator(mode='after')
    def mirror_confidence_and_strength(self) -> 'SignalResponse':
        """
        Auto-mirror confidence and signal_strength for backward/forward compatibility.

        Rules:
        - If only signal_strength provided -> mirror to confidence
        - If only confidence provided -> mirror to signal_strength
        - If both provided -> validate they match (within tolerance)
        - If neither provided -> raise error
        """
        if self.signal_strength is not None and self.confidence is None:
            # Mirror signal_strength to confidence
            self.confidence = self.signal_strength
        elif self.confidence is not None and self.signal_strength is None:
            # Mirror confidence to signal_strength (legacy support)
            self.signal_strength = self.confidence
        elif self.signal_strength is not None and self.confidence is not None:
            # Both provided - validate they're roughly equal (allow small float differences)
            if abs(self.signal_strength - self.confidence) > 0.01:
                raise ValueError(
                    f"signal_strength ({self.signal_strength}) and confidence ({self.confidence}) "
                    f"must be equal or within 0.01 tolerance"
                )
        else:
            # Neither provided
            raise ValueError("Either signal_strength or confidence must be provided")

        return self

    @classmethod
    def from_decision(cls, symbol: str, decision_dict: dict[str, Any]) -> 'SignalResponse':
        """
        Create SignalResponse from BasicStrategy.decide() output.

        Args:
            symbol: Trading symbol (e.g., "AAPL")
            decision_dict: Dictionary returned from BasicStrategy.decide()
                Expected keys: action, confidence, tp_pct, sl_pct, timestamp

        Returns:
            SignalResponse instance with mirrored confidence/signal_strength
        """
        # Handle action field - normalize to lowercase
        action = str(decision_dict.get('action', 'hold')).lower()
        if action not in ['buy', 'sell', 'hold']:
            # Map common variations
            action_mapping = {
                'long': 'buy',
                'short': 'sell',
                'neutral': 'hold',
                'none': 'hold'
            }
            action = action_mapping.get(action, 'hold')

        # Extract confidence (will be mirrored to signal_strength by validator)
        confidence = float(decision_dict.get('confidence', 0.5))

        # Extract percentages with defaults
        tp_pct = float(decision_dict.get('tp_pct', 0.02))  # 2% default take profit
        sl_pct = float(decision_dict.get('sl_pct', 0.01))  # 1% default stop loss

        # Handle timestamp - use provided or current time
        timestamp = decision_dict.get('timestamp')
        if isinstance(timestamp, str):
            # Parse string timestamp if provided
            try:
                generated_at = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                generated_at = datetime.now(UTC)
        elif isinstance(timestamp, datetime):
            generated_at = timestamp
        else:
            generated_at = datetime.now(UTC)

        return cls(
            symbol=symbol,
            action=action,
            signal_strength=confidence,  # Will be mirrored to confidence by validator
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            generated_at=generated_at
        )


class SignalRequest(BaseModel):
    """Request model for submitting signals."""

    symbol: str
    signal_type: Literal["BUY", "SELL", "HOLD"]  # Legacy uppercase format
    confidence: float
    price: float | None = None
    timestamp: str | None = None

    @field_validator('confidence')
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        """Ensure confidence is in valid range [0.0, 1.0]"""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class BatchSignalRequest(BaseModel):
    """Request model for batch signal submission."""

    signals: list[SignalRequest]

    @field_validator('signals')
    @classmethod
    def validate_signals_not_empty(cls, v: list) -> list:
        """Ensure signals list is not empty."""
        if not v:
            raise ValueError("Signals list cannot be empty")
        return v
