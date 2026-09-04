"""Tests for the offline Binance Spot raw-kline adapter."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from crypto_trader.data import BinanceKlineParseError, parse_binance_spot_kline


def valid_raw_kline() -> list[object]:
    """Return one representative Binance Spot kline record."""
    return [
        1_704_067_200_000,
        "42000.123456789",
        "42500.200000001",
        "41900.300000009",
        "42300.400000007",
        "12.500000003",
    ]


def test_valid_kline_converts_to_exact_ohlcv_bar() -> None:
    bar = parse_binance_spot_kline(valid_raw_kline())

    assert bar.timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert bar.timestamp.tzinfo is timezone.utc
    assert bar.open == Decimal("42000.123456789")
    assert bar.high == Decimal("42500.200000001")
    assert bar.low == Decimal("41900.300000009")
    assert bar.close == Decimal("42300.400000007")
    assert bar.volume == Decimal("12.500000003")


def test_extra_binance_fields_are_ignored() -> None:
    raw = valid_raw_kline() + [object(), object(), object()]
    assert parse_binance_spot_kline(raw) == parse_binance_spot_kline(valid_raw_kline())


@pytest.mark.parametrize("raw", [[], [1, "1", "2"], "not a kline", 123, None])
def test_invalid_raw_record_shape_is_rejected(raw: object) -> None:
    with pytest.raises(BinanceKlineParseError, match="sequence|at least 6"):
        parse_binance_spot_kline(raw)  # type: ignore[arg-type]


@pytest.mark.parametrize("timestamp", [True, "1704067200000", 1.5])
def test_non_integer_open_time_is_rejected(timestamp: object) -> None:
    raw = valid_raw_kline()
    raw[0] = timestamp
    with pytest.raises(BinanceKlineParseError, match="integer Unix timestamp"):
        parse_binance_spot_kline(raw)


@pytest.mark.parametrize("timestamp", [-1, 10**30])
def test_invalid_or_out_of_range_open_time_is_rejected(timestamp: int) -> None:
    raw = valid_raw_kline()
    raw[0] = timestamp
    with pytest.raises(BinanceKlineParseError, match="open time"):
        parse_binance_spot_kline(raw)


@pytest.mark.parametrize(
    ("index", "field_name"),
    [(1, "open"), (5, "volume")],
)
def test_malformed_numeric_string_is_rejected(index: int, field_name: str) -> None:
    raw = valid_raw_kline()
    raw[index] = "not-a-number"
    with pytest.raises(BinanceKlineParseError, match=field_name):
        parse_binance_spot_kline(raw)


@pytest.mark.parametrize("value", [float("1.25"), 1])
def test_non_string_ohlcv_value_is_not_silently_accepted(value: object) -> None:
    raw = valid_raw_kline()
    raw[1] = value
    with pytest.raises(BinanceKlineParseError, match="open must be a decimal string"):
        parse_binance_spot_kline(raw)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_decimal_is_rejected_by_domain_contract(value: str) -> None:
    raw = valid_raw_kline()
    raw[4] = value
    with pytest.raises(ValueError, match="close must be finite"):
        parse_binance_spot_kline(raw)


def test_inconsistent_ohlc_is_rejected_by_domain_contract() -> None:
    raw = valid_raw_kline()
    raw[2] = "41000"
    with pytest.raises(ValueError, match="high must be"):
        parse_binance_spot_kline(raw)


def test_negative_volume_is_rejected_by_domain_contract() -> None:
    raw = valid_raw_kline()
    raw[5] = "-0.1"
    with pytest.raises(ValueError, match="volume must be non-negative"):
        parse_binance_spot_kline(raw)


def test_parsing_does_not_mutate_raw_record() -> None:
    raw = valid_raw_kline()
    original = raw.copy()
    parse_binance_spot_kline(raw)
    assert raw == original
