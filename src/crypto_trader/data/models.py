"""Immutable domain values for historical market data."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    """A single historical OHLCV bar with a UTC timestamp and exact values.

    Numeric fields deliberately require :class:`~decimal.Decimal`. This keeps
    validation and later research reproducible without binary floating-point
    conversion surprises at the data-contract boundary.
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        """Normalize the timestamp to UTC and enforce OHLCV invariants."""
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))

        values = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        for name, value in values.items():
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal")
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")

        for name in ("open", "high", "low", "close"):
            if values[name] <= 0:
                raise ValueError(f"{name} must be strictly positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")

        if self.high < max(self.open, self.close):
            raise ValueError("high must be greater than or equal to open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be less than or equal to open and close")
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
