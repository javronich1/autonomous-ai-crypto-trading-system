"""Tests for the immutable OHLCV bar contract."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from crypto_trader.data import OHLCVBar


def make_bar(**overrides: object) -> OHLCVBar:
    """Build a valid bar, replacing fields requested by a test."""
    values = {
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "open": Decimal("42000.10"),
        "high": Decimal("42500.20"),
        "low": Decimal("41900.30"),
        "close": Decimal("42300.40"),
        "volume": Decimal("12.500"),
    }
    values.update(overrides)
    return OHLCVBar(**values)  # type: ignore[arg-type]


def test_valid_utc_bar_is_accepted() -> None:
    bar = make_bar()
    assert bar.timestamp.tzinfo is timezone.utc
    assert bar.volume == Decimal("12.500")


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_bar(timestamp=datetime(2024, 1, 1))


def test_non_utc_aware_timestamp_is_normalized_to_utc() -> None:
    source = datetime(2024, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    assert make_bar(timestamp=source).timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
@pytest.mark.parametrize("invalid", [Decimal("0"), Decimal("-1")])
def test_non_positive_price_is_rejected(field: str, invalid: Decimal) -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        make_bar(**{field: invalid})


def test_negative_volume_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        make_bar(volume=Decimal("-0.1"))


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_non_finite_value_is_rejected(invalid: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        make_bar(close=invalid)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("high", Decimal("41000"), "high must be"),
        ("low", Decimal("43000"), "low must be"),
    ],
)
def test_inconsistent_price_range_is_rejected(field: str, value: Decimal, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        make_bar(**{field: value})


def test_numeric_fields_require_decimal() -> None:
    with pytest.raises(TypeError, match="open must be a Decimal"):
        make_bar(open=42000.1)
