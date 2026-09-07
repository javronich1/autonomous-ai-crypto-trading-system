"""Deterministic transformations at the UI presentation boundary."""

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeAlias

from crypto_trader.data import AcquisitionCoverage, OHLCVBar, SequenceValidationIssue

ChartValues: TypeAlias = dict[str, list[datetime] | list[float]]
DisplayRow: TypeAlias = dict[str, str | int]


def format_utc_timestamp(value: datetime) -> str:
    """Format an aware timestamp as a compact, explicit UTC terminal value."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("display timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def bars_to_chart_values(bars: Sequence[OHLCVBar]) -> ChartValues:
    """Convert trusted decimals to floats only at the Plotly boundary."""
    return {
        "timestamp": [bar.timestamp for bar in bars],
        "open": [float(bar.open) for bar in bars],
        "high": [float(bar.high) for bar in bars],
        "low": [float(bar.low) for bar in bars],
        "close": [float(bar.close) for bar in bars],
        "volume": [float(bar.volume) for bar in bars],
    }


def bars_to_table_rows(bars: Sequence[OHLCVBar]) -> tuple[DisplayRow, ...]:
    """Build dense table rows while preserving exact decimal text."""
    return tuple(
        {
            "UTC TIMESTAMP": format_utc_timestamp(bar.timestamp),
            "OPEN": str(bar.open),
            "HIGH": str(bar.high),
            "LOW": str(bar.low),
            "CLOSE": str(bar.close),
            "VOLUME": str(bar.volume),
        }
        for bar in bars
    )


def coverage_percentage(coverage: AcquisitionCoverage) -> Decimal:
    """Return exact coverage percent; an empty eligible range is complete."""
    if coverage.expected_bar_count == 0:
        return Decimal("100")
    return (
        Decimal(coverage.observed_unique_aligned_bar_count)
        * Decimal("100")
        / Decimal(coverage.expected_bar_count)
    )


def validation_issues_to_rows(
    issues: Sequence[SequenceValidationIssue],
) -> tuple[DisplayRow, ...]:
    """Convert structured validation issues into compact display rows."""
    return tuple(
        {
            "CODE": issue.code.value.upper(),
            "INDEX": issue.index,
            "MESSAGE": issue.message,
            "MISSING BARS": (
                issue.missing_bar_count
                if issue.missing_bar_count is not None
                else "—"
            ),
        }
        for issue in issues
    )
