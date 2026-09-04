"""Tests for deterministic hourly sequence validation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from crypto_trader.data import OHLCVBar, SequenceIssueCode, validate_hourly_bars


def bar_at(timestamp: datetime) -> OHLCVBar:
    """Return a valid bar at ``timestamp``."""
    return OHLCVBar(
        timestamp=timestamp,
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        volume=Decimal("5"),
    )


def codes_for(timestamps: list[datetime]) -> list[SequenceIssueCode]:
    return [issue.code for issue in validate_hourly_bars([bar_at(ts) for ts in timestamps]).issues]


def test_ordered_hourly_sequence_passes() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = validate_hourly_bars([bar_at(start + timedelta(hours=i)) for i in range(3)])
    assert result.is_valid
    assert result.issues == ()


def test_duplicate_timestamp_is_detected() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert codes_for([start, start]) == [SequenceIssueCode.DUPLICATE_TIMESTAMP]


def test_non_adjacent_duplicate_timestamp_is_detected() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    codes = codes_for([start, start + timedelta(hours=1), start])
    assert SequenceIssueCode.DUPLICATE_TIMESTAMP in codes
    assert SequenceIssueCode.OUT_OF_ORDER_TIMESTAMP in codes


def test_out_of_order_timestamp_is_detected() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert codes_for([start + timedelta(hours=1), start]) == [SequenceIssueCode.OUT_OF_ORDER_TIMESTAMP]


def test_timestamp_not_on_hour_boundary_is_detected() -> None:
    timestamp = datetime(2024, 1, 1, minute=30, tzinfo=timezone.utc)
    assert codes_for([timestamp]) == [SequenceIssueCode.MISALIGNED_TIMESTAMP]


def test_one_hour_of_missing_data_is_reported_without_filling() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [bar_at(start), bar_at(start + timedelta(hours=2))]
    result = validate_hourly_bars(bars)
    assert len(bars) == 2
    assert result.issues[0].code is SequenceIssueCode.GAP
    assert result.issues[0].missing_bar_count == 1


def test_multi_hour_gap_reports_each_expected_missing_bar() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = validate_hourly_bars([bar_at(start), bar_at(start + timedelta(hours=4))])
    assert result.issues[0].code is SequenceIssueCode.GAP
    assert result.issues[0].missing_bar_count == 3


def test_out_of_order_complete_sequence_does_not_report_gap() -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    result = validate_hourly_bars(
        [bar_at(start), bar_at(start + timedelta(hours=2)), bar_at(start + timedelta(hours=1))]
    )
    codes = [issue.code for issue in result.issues]
    assert SequenceIssueCode.OUT_OF_ORDER_TIMESTAMP in codes
    assert SequenceIssueCode.GAP not in codes


def test_out_of_order_sequence_reports_only_genuinely_missing_hour() -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    result = validate_hourly_bars(
        [bar_at(start), bar_at(start + timedelta(hours=3)), bar_at(start + timedelta(hours=1))]
    )
    assert SequenceIssueCode.OUT_OF_ORDER_TIMESTAMP in [issue.code for issue in result.issues]
    gaps = [issue for issue in result.issues if issue.code is SequenceIssueCode.GAP]
    assert len(gaps) == 1
    assert gaps[0].missing_bar_count == 1


def test_misaligned_interval_never_reports_zero_length_gap() -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    result = validate_hourly_bars([bar_at(start), bar_at(start + timedelta(hours=1, minutes=30))])
    codes = [issue.code for issue in result.issues]
    assert SequenceIssueCode.MISALIGNED_TIMESTAMP in codes
    assert SequenceIssueCode.GAP not in codes
    assert all(
        issue.missing_bar_count is None or issue.missing_bar_count >= 1
        for issue in result.issues
    )


def test_ordered_gap_regression_reports_one_missing_hour() -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    result = validate_hourly_bars([bar_at(start), bar_at(start + timedelta(hours=2))])
    gaps = [issue for issue in result.issues if issue.code is SequenceIssueCode.GAP]
    assert len(gaps) == 1
    assert gaps[0].missing_bar_count == 1


def test_misaligned_observation_does_not_hide_two_missing_hours() -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    result = validate_hourly_bars(
        [
            bar_at(start),
            bar_at(start + timedelta(hours=1, minutes=30)),
            bar_at(start + timedelta(hours=3)),
        ]
    )
    assert SequenceIssueCode.MISALIGNED_TIMESTAMP in [issue.code for issue in result.issues]
    gaps = [issue for issue in result.issues if issue.code is SequenceIssueCode.GAP]
    assert len(gaps) == 1
    assert gaps[0].missing_bar_count == 2


def test_misaligned_observation_near_later_endpoint_does_not_hide_gap() -> None:
    start = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    result = validate_hourly_bars(
        [
            bar_at(start),
            bar_at(start + timedelta(hours=2, minutes=30)),
            bar_at(start + timedelta(hours=3)),
        ]
    )
    assert SequenceIssueCode.MISALIGNED_TIMESTAMP in [issue.code for issue in result.issues]
    gaps = [issue for issue in result.issues if issue.code is SequenceIssueCode.GAP]
    assert len(gaps) == 1
    assert gaps[0].missing_bar_count == 2
