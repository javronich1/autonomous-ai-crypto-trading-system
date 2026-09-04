"""Deterministic validation of chronological hourly OHLCV data."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Sequence

from crypto_trader.data.models import OHLCVBar

HOURLY_CADENCE = timedelta(hours=1)


class SequenceIssueCode(str, Enum):
    """Machine-readable categories of sequence validation problems."""

    DUPLICATE_TIMESTAMP = "duplicate_timestamp"
    OUT_OF_ORDER_TIMESTAMP = "out_of_order_timestamp"
    MISALIGNED_TIMESTAMP = "misaligned_timestamp"
    GAP = "gap"


@dataclass(frozen=True, slots=True)
class SequenceValidationIssue:
    """A problem at an input position, with optional cadence-gap context."""

    code: SequenceIssueCode
    index: int
    message: str
    missing_bar_count: int | None = None


@dataclass(frozen=True, slots=True)
class SequenceValidationResult:
    """Structured outcome of validating a bar sequence."""

    issues: tuple[SequenceValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether validation found no issues."""
        return not self.issues


def _is_hour_aligned(timestamp: datetime) -> bool:
    """Return whether a UTC timestamp lies exactly on an hourly boundary."""
    return not any((timestamp.minute, timestamp.second, timestamp.microsecond))


def validate_hourly_bars(bars: Sequence[OHLCVBar]) -> SequenceValidationResult:
    """Validate order, exact UTC-hour alignment, duplicates, and cadence gaps.

    The sequence is inspected only. Missing bars are reported and are never
    interpolated, filled, or synthesized.
    """
    issues: list[SequenceValidationIssue] = []
    seen_timestamps: set[datetime] = set()
    first_index_by_timestamp: dict[datetime, int] = {}

    for index, bar in enumerate(bars):
        timestamp = bar.timestamp
        if not _is_hour_aligned(timestamp):
            issues.append(
                SequenceValidationIssue(
                    code=SequenceIssueCode.MISALIGNED_TIMESTAMP,
                    index=index,
                    message=f"bar at index {index} is not aligned to a UTC hour boundary",
                )
            )

        is_duplicate = timestamp in seen_timestamps
        seen_timestamps.add(timestamp)
        first_index_by_timestamp.setdefault(timestamp, index)
        if is_duplicate:
            issues.append(
                SequenceValidationIssue(
                    code=SequenceIssueCode.DUPLICATE_TIMESTAMP,
                    index=index,
                    message=f"bar at index {index} duplicates an earlier timestamp",
                )
            )

        if index == 0:
            continue

        previous = bars[index - 1].timestamp
        if timestamp < previous:
            issues.append(
                SequenceValidationIssue(
                    code=SequenceIssueCode.OUT_OF_ORDER_TIMESTAMP,
                    index=index,
                    message=f"bar at index {index} is earlier than the previous bar",
                )
            )

    chronological_timestamps = sorted(
        timestamp for timestamp in seen_timestamps if _is_hour_aligned(timestamp)
    )
    for previous, timestamp in zip(
        chronological_timestamps, chronological_timestamps[1:], strict=False
    ):
        elapsed = timestamp - previous
        missing_count = int(elapsed // HOURLY_CADENCE) - 1
        if missing_count < 1:
            continue

        index = first_index_by_timestamp[timestamp]
        issues.append(
            SequenceValidationIssue(
                code=SequenceIssueCode.GAP,
                index=index,
                message=f"gap before index {index}: {missing_count} expected bar(s) missing",
                missing_bar_count=missing_count,
            )
        )

    return SequenceValidationResult(issues=tuple(issues))
