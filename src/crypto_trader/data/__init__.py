"""Market-data domain contract and deterministic validation."""

from crypto_trader.data.binance import BinanceKlineParseError, parse_binance_spot_kline
from crypto_trader.data.models import OHLCVBar
from crypto_trader.data.validation import (
    HOURLY_CADENCE,
    SequenceIssueCode,
    SequenceValidationIssue,
    SequenceValidationResult,
    validate_hourly_bars,
)

__all__ = [
    "HOURLY_CADENCE",
    "BinanceKlineParseError",
    "OHLCVBar",
    "SequenceIssueCode",
    "SequenceValidationIssue",
    "SequenceValidationResult",
    "parse_binance_spot_kline",
    "validate_hourly_bars",
]
