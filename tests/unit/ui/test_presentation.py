"""Tests for deterministic research-terminal presentation transforms."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from crypto_trader.data import (
    AcquisitionCoverage,
    OHLCVBar,
    SequenceIssueCode,
    SequenceValidationIssue,
)
from crypto_trader.ui import (
    bars_to_chart_values,
    bars_to_table_rows,
    coverage_percentage,
    format_utc_timestamp,
    validation_issues_to_rows,
)


def sample_bar() -> OHLCVBar:
    """Return a trusted bar with precision visible at presentation boundaries."""
    return OHLCVBar(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        open=Decimal("42000.123456789"),
        high=Decimal("42500.200000001"),
        low=Decimal("41900.300000009"),
        close=Decimal("42300.400000007"),
        volume=Decimal("12.500000003"),
    )


def test_table_rows_preserve_exact_decimal_text() -> None:
    row = bars_to_table_rows([sample_bar()])[0]
    assert row == {
        "UTC TIMESTAMP": "2024-01-01 00:00:00 UTC",
        "OPEN": "42000.123456789",
        "HIGH": "42500.200000001",
        "LOW": "41900.300000009",
        "CLOSE": "42300.400000007",
        "VOLUME": "12.500000003",
    }


def test_chart_values_convert_decimals_only_for_plotting() -> None:
    bar = sample_bar()
    values = bars_to_chart_values([bar])
    assert values["open"] == [float(Decimal("42000.123456789"))]
    assert values["volume"] == [float(Decimal("12.500000003"))]
    assert isinstance(bar.open, Decimal)


def test_empty_bars_produce_empty_presentation_collections() -> None:
    assert bars_to_table_rows(()) == ()
    assert bars_to_chart_values(()) == {
        "timestamp": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }


@pytest.mark.parametrize(
    ("expected", "observed", "percentage"),
    [(4, 3, Decimal("75")), (3, 1, Decimal(100) / Decimal(3)), (0, 0, Decimal("100"))],
)
def test_coverage_percentage(
    expected: int, observed: int, percentage: Decimal
) -> None:
    coverage = AcquisitionCoverage(expected, observed, expected - observed)
    assert coverage_percentage(coverage) == percentage


def test_validation_issues_become_display_rows() -> None:
    issue = SequenceValidationIssue(
        code=SequenceIssueCode.GAP,
        index=2,
        message="one expected bar is absent",
        missing_bar_count=1,
    )
    assert validation_issues_to_rows([issue]) == (
        {
            "CODE": "GAP",
            "INDEX": 2,
            "MESSAGE": "one expected bar is absent",
            "MISSING BARS": 1,
        },
    )


def test_validation_issue_without_missing_count_uses_placeholder() -> None:
    issue = SequenceValidationIssue(
        code=SequenceIssueCode.DUPLICATE_TIMESTAMP,
        index=1,
        message="duplicate",
    )
    assert validation_issues_to_rows([issue])[0]["MISSING BARS"] == "—"


def test_utc_format_normalizes_aware_offset() -> None:
    plus_two = timezone(timedelta(hours=2))
    value = datetime(2024, 1, 1, 2, 30, tzinfo=plus_two)
    assert format_utc_timestamp(value) == "2024-01-01 00:30:00 UTC"


def test_utc_format_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        format_utc_timestamp(datetime(2024, 1, 1))
