"""Market-data domain contract and deterministic validation."""

from crypto_trader.data.binance import BinanceKlineParseError, parse_binance_spot_kline
from crypto_trader.data.binance_fetcher import (
    AcquisitionCoverage,
    BinanceKlineAcquisitionError,
    BinanceKlineAcquisitionResult,
    fetch_binance_spot_klines,
)
from crypto_trader.data.models import OHLCVBar
from crypto_trader.data.validation import (
    HOURLY_CADENCE,
    SequenceIssueCode,
    SequenceValidationIssue,
    SequenceValidationResult,
    validate_hourly_bars,
)

__all__ = [
    "AcquisitionCoverage",
    "HOURLY_CADENCE",
    "BinanceKlineAcquisitionError",
    "BinanceKlineAcquisitionResult",
    "BinanceKlineParseError",
    "OHLCVBar",
    "SequenceIssueCode",
    "SequenceValidationIssue",
    "SequenceValidationResult",
    "fetch_binance_spot_klines",
    "parse_binance_spot_kline",
    "validate_hourly_bars",
]
