"""Offline normalization of raw Binance Spot market-data records."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from crypto_trader.data.models import OHLCVBar

_REQUIRED_KLINE_FIELD_COUNT = 6
_UNIX_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


class BinanceKlineParseError(ValueError):
    """A raw Binance Spot kline does not satisfy the adapter contract."""


def _parse_decimal_string(value: object, field_name: str) -> Decimal:
    """Parse an exact decimal string with field-specific boundary errors."""
    if not isinstance(value, str):
        raise BinanceKlineParseError(f"{field_name} must be a decimal string")

    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise BinanceKlineParseError(
            f"{field_name} must be a valid decimal string"
        ) from error


def _parse_open_time(value: object) -> datetime:
    """Convert a Binance Unix-millisecond open time to an aware UTC datetime."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise BinanceKlineParseError(
            "open time must be an integer Unix timestamp in milliseconds"
        )
    if value < 0:
        raise BinanceKlineParseError("open time must be non-negative")

    try:
        return _UNIX_EPOCH_UTC + timedelta(milliseconds=value)
    except OverflowError as error:
        raise BinanceKlineParseError(
            "open time is outside the supported datetime range"
        ) from error


def parse_binance_spot_kline(raw_record: Sequence[object]) -> OHLCVBar:
    """Normalize one raw Binance Spot kline into the trusted OHLCV contract.

    Only open time, OHLC prices, and base-asset volume (indices zero through
    five) are read. Additional Binance fields are deliberately ignored.
    """
    if isinstance(raw_record, (str, bytes, bytearray)) or not isinstance(
        raw_record, Sequence
    ):
        raise BinanceKlineParseError("raw kline must be a sequence-like record")
    if len(raw_record) < _REQUIRED_KLINE_FIELD_COUNT:
        raise BinanceKlineParseError("raw kline must contain at least 6 fields")

    return OHLCVBar(
        timestamp=_parse_open_time(raw_record[0]),
        open=_parse_decimal_string(raw_record[1], "open"),
        high=_parse_decimal_string(raw_record[2], "high"),
        low=_parse_decimal_string(raw_record[3], "low"),
        close=_parse_decimal_string(raw_record[4], "close"),
        volume=_parse_decimal_string(raw_record[5], "volume"),
    )
