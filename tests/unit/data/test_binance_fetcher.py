"""Tests for deterministic acquisition of closed Binance Spot klines."""

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from crypto_trader.data import (
    BinanceKlineAcquisitionError,
    SequenceIssueCode,
    fetch_binance_spot_klines,
)

UTC = timezone.utc
HOUR_MS = 3_600_000


def raw_kline(open_time_ms: int, *, close: str = "11") -> list[object]:
    """Build a minimal valid raw Binance kline."""
    return [open_time_ms, "10", "12", "9", close, "5"]


class FakeResponse:
    """Small context-managed HTTP response used by the fake opener."""

    def __init__(self, payload: object, status: int = 200, *, encoded: bool = False) -> None:
        self.status = status
        self._body = payload if encoded else json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body  # type: ignore[return-value]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    """Return queued responses and retain exact request arguments."""

    def __init__(self, responses: Iterable[FakeResponse]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, *, timeout: float) -> FakeResponse:
        self.calls.append((url, timeout))
        return next(self._responses)


class HTTPErrorOpener:
    """Raise the same HTTP error type used by the production opener."""

    def __init__(self, status: int) -> None:
        self.status = status

    def __call__(self, url: str, *, timeout: float) -> FakeResponse:
        raise HTTPError(url, self.status, "test HTTP failure", None, None)


def utc(hour: int = 0) -> datetime:
    return datetime(2024, 1, 1, hour, tzinfo=UTC)


def milliseconds(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    return (value - epoch) // timedelta(milliseconds=1)


def fetch_with(
    opener: FakeOpener,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    as_of: datetime | None = None,
):
    return fetch_binance_spot_klines(
        start or utc(),
        end or utc(2),
        as_of=as_of or utc(3),
        _opener=opener,
    )


def test_valid_range_and_request_contract() -> None:
    start = utc()
    end = utc(2)
    opener = FakeOpener(
        [
            FakeResponse(
                [
                    raw_kline(milliseconds(start)),
                    raw_kline(milliseconds(start + timedelta(hours=1))),
                ]
            )
        ]
    )

    result = fetch_with(opener, start=start, end=end)

    assert result.requested_start == start
    assert result.requested_end == end
    assert result.effective_end == end
    assert not result.end_was_capped
    url, timeout = opener.calls[0]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "data-api.binance.vision"
    assert parsed.path == "/api/v3/klines"
    assert query == {
        "symbol": ["BTCUSDT"],
        "interval": ["1h"],
        "startTime": [str(milliseconds(start))],
        "endTime": [str(milliseconds(end) - 1)],
        "limit": ["1000"],
        "timeZone": ["0"],
    }
    assert timeout == 10.0


def test_aware_non_utc_boundaries_normalize_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    opener = FakeOpener([FakeResponse([])])
    result = fetch_binance_spot_klines(
        datetime(2024, 1, 1, 2, tzinfo=plus_two),
        datetime(2024, 1, 1, 4, tzinfo=plus_two),
        as_of=datetime(2024, 1, 1, 5, tzinfo=plus_two),
        _opener=opener,
    )
    assert result.requested_start == utc()
    assert result.requested_end == utc(2)
    assert result.as_of == utc(3)


@pytest.mark.parametrize("name", ["start", "end", "as_of"])
def test_naive_datetime_is_rejected(name: str) -> None:
    values = {"start": utc(), "end": utc(2), "as_of": utc(3)}
    values[name] = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match=f"{name} must be timezone-aware"):
        fetch_binance_spot_klines(**values, _opener=FakeOpener([]))


@pytest.mark.parametrize("name", ["start", "end"])
def test_misaligned_range_boundary_is_rejected(name: str) -> None:
    values = {"start": utc(), "end": utc(2)}
    values[name] = values[name] + timedelta(minutes=1)
    with pytest.raises(ValueError, match=f"{name} must align"):
        fetch_binance_spot_klines(**values, as_of=utc(3), _opener=FakeOpener([]))


@pytest.mark.parametrize("end", [utc(), utc() - timedelta(hours=1)])
def test_non_increasing_range_is_rejected(end: datetime) -> None:
    with pytest.raises(ValueError, match="start must be earlier"):
        fetch_binance_spot_klines(utc(), end, as_of=utc(3), _opener=FakeOpener([]))


def test_closed_candle_cap_excludes_current_hour() -> None:
    start = utc()
    current_hour = utc(12)
    page = [raw_kline(milliseconds(start) + index * HOUR_MS) for index in range(12)]
    opener = FakeOpener([FakeResponse(page)])

    result = fetch_with(
        opener,
        start=start,
        end=utc(13),
        as_of=current_hour + timedelta(minutes=37),
    )

    assert result.effective_end == current_hour
    assert result.end_was_capped
    assert result.bars[-1].timestamp == utc(11)
    assert all(bar.timestamp < current_hour for bar in result.bars)


def test_as_of_on_hour_boundary_excludes_bar_starting_at_that_boundary() -> None:
    opener = FakeOpener([FakeResponse([raw_kline(milliseconds(utc(11)))])])
    result = fetch_with(opener, start=utc(11), end=utc(13), as_of=utc(12))
    assert result.effective_end == utc(12)
    assert [bar.timestamp for bar in result.bars] == [utc(11)]


def test_requested_end_before_current_hour_is_preserved() -> None:
    opener = FakeOpener([FakeResponse([])])
    result = fetch_with(opener, end=utc(2), as_of=utc(12) + timedelta(minutes=30))
    assert result.effective_end == utc(2)
    assert not result.end_was_capped


def test_entirely_open_or_future_range_is_empty_without_request() -> None:
    opener = FakeOpener([])
    result = fetch_with(opener, start=utc(12), end=utc(14), as_of=utc(12,))
    assert result.bars == ()
    assert result.sequence_validation.is_valid
    assert result.coverage.expected_bar_count == 0
    assert result.coverage.observed_unique_aligned_bar_count == 0
    assert result.coverage.missing_expected_bar_count == 0
    assert result.coverage.is_complete
    assert opener.calls == []


def test_more_than_1000_hours_paginates_without_boundary_duplicate() -> None:
    start = utc()
    first = [raw_kline(milliseconds(start) + index * HOUR_MS) for index in range(1000)]
    second = [
        raw_kline(milliseconds(start) + index * HOUR_MS)
        for index in range(1000, 1002)
    ]
    opener = FakeOpener([FakeResponse(first), FakeResponse(second)])

    result = fetch_with(
        opener,
        start=start,
        end=start + timedelta(hours=1002),
        as_of=start + timedelta(hours=1003),
    )

    assert len(opener.calls) == 2
    assert len(result.bars) == 1002
    assert result.sequence_validation.is_valid
    second_query = parse_qs(urlparse(opener.calls[1][0]).query)
    assert second_query["startTime"] == [str(milliseconds(start) + 1000 * HOUR_MS)]


def test_short_page_is_followed_until_empty_page() -> None:
    opener = FakeOpener(
        [FakeResponse([raw_kline(milliseconds(utc()))]), FakeResponse([])]
    )
    result = fetch_with(opener, end=utc(3), as_of=utc(4))
    assert len(opener.calls) == 2
    assert len(result.bars) == 1


def test_non_progressing_page_fails_clearly() -> None:
    first = FakeResponse([raw_kline(milliseconds(utc()))])
    repeated = FakeResponse([raw_kline(milliseconds(utc()))])
    opener = FakeOpener([first, repeated])
    with pytest.raises(BinanceKlineAcquisitionError, match="did not make.*progress"):
        fetch_with(opener, end=utc(3), as_of=utc(4))


def test_genuine_gap_is_exposed_without_synthesis() -> None:
    opener = FakeOpener(
        [
            FakeResponse(
                [raw_kline(milliseconds(utc())), raw_kline(milliseconds(utc(2)))]
            )
        ]
    )
    result = fetch_with(opener, end=utc(3), as_of=utc(4))
    assert len(result.bars) == 2
    gaps = [
        issue
        for issue in result.sequence_validation.issues
        if issue.code is SequenceIssueCode.GAP
    ]
    assert len(gaps) == 1
    assert gaps[0].missing_bar_count == 1


def test_complete_requested_range_has_complete_coverage() -> None:
    page = [raw_kline(milliseconds(utc(hour))) for hour in range(3)]
    result = fetch_with(
        FakeOpener([FakeResponse(page)]), end=utc(3), as_of=utc(4)
    )
    assert result.coverage.expected_bar_count == 3
    assert result.coverage.observed_unique_aligned_bar_count == 3
    assert result.coverage.missing_expected_bar_count == 0
    assert result.coverage.is_complete


def test_missing_leading_bar_is_coverage_issue_not_sequence_issue() -> None:
    page = [raw_kline(milliseconds(utc(hour))) for hour in (1, 2)]
    result = fetch_with(
        FakeOpener([FakeResponse(page)]), end=utc(3), as_of=utc(4)
    )
    assert result.sequence_validation.is_valid
    assert result.coverage.observed_unique_aligned_bar_count == 2
    assert result.coverage.missing_expected_bar_count == 1
    assert not result.coverage.is_complete


def test_empty_page_after_first_bar_exposes_missing_trailing_coverage() -> None:
    opener = FakeOpener(
        [FakeResponse([raw_kline(milliseconds(utc()))]), FakeResponse([])]
    )
    result = fetch_with(opener, end=utc(3), as_of=utc(4))
    assert result.sequence_validation.is_valid
    assert result.coverage.expected_bar_count == 3
    assert result.coverage.observed_unique_aligned_bar_count == 1
    assert result.coverage.missing_expected_bar_count == 2
    assert not result.coverage.is_complete


def test_internal_gap_affects_sequence_quality_and_request_coverage() -> None:
    page = [raw_kline(milliseconds(utc(hour))) for hour in (0, 2)]
    result = fetch_with(
        FakeOpener([FakeResponse(page)]), end=utc(3), as_of=utc(4)
    )
    assert SequenceIssueCode.GAP in [
        issue.code for issue in result.sequence_validation.issues
    ]
    assert result.coverage.missing_expected_bar_count == 1
    assert not result.coverage.is_complete


def test_duplicate_does_not_inflate_unique_request_coverage() -> None:
    page = [raw_kline(milliseconds(utc(hour))) for hour in (0, 0, 1)]
    opener = FakeOpener([FakeResponse(page), FakeResponse([])])
    result = fetch_with(opener, end=utc(3), as_of=utc(4))
    assert SequenceIssueCode.DUPLICATE_TIMESTAMP in [
        issue.code for issue in result.sequence_validation.issues
    ]
    assert result.coverage.observed_unique_aligned_bar_count == 2
    assert result.coverage.missing_expected_bar_count == 1
    assert not result.coverage.is_complete


def test_misaligned_observation_does_not_satisfy_hourly_coverage() -> None:
    page = [
        raw_kline(milliseconds(utc())),
        raw_kline(milliseconds(utc(1) + timedelta(minutes=30))),
        raw_kline(milliseconds(utc(2))),
    ]
    result = fetch_with(
        FakeOpener([FakeResponse(page)]), end=utc(3), as_of=utc(4)
    )
    assert SequenceIssueCode.MISALIGNED_TIMESTAMP in [
        issue.code for issue in result.sequence_validation.issues
    ]
    assert result.coverage.observed_unique_aligned_bar_count == 2
    assert result.coverage.missing_expected_bar_count == 1
    assert not result.coverage.is_complete


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"code": -1121, "msg": "Invalid symbol."}, "API error payload"),
        ({"unexpected": "object"}, "JSON array"),
        ("wrong top level", "JSON array"),
    ],
)
def test_wrong_top_level_or_api_error_is_rejected(payload: Any, message: str) -> None:
    opener = FakeOpener([FakeResponse(payload)])
    with pytest.raises(BinanceKlineAcquisitionError, match=message):
        fetch_with(opener)


def test_malformed_json_is_rejected() -> None:
    opener = FakeOpener([FakeResponse(b"not json", encoded=True)])
    with pytest.raises(BinanceKlineAcquisitionError, match="valid UTF-8 JSON"):
        fetch_with(opener)


def test_malformed_raw_kline_is_contextualized() -> None:
    opener = FakeOpener([FakeResponse([[milliseconds(utc()), "10"]])])
    with pytest.raises(BinanceKlineAcquisitionError, match="invalid raw record"):
        fetch_with(opener)


def test_out_of_range_bar_is_rejected() -> None:
    opener = FakeOpener([FakeResponse([raw_kline(milliseconds(utc(2)))])])
    with pytest.raises(BinanceKlineAcquisitionError, match="outside the effective"):
        fetch_with(opener, end=utc(2), as_of=utc(3))


@pytest.mark.parametrize(
    ("status", "message"), [(500, "HTTP failure"), (429, "rate limited")]
)
def test_http_failure_is_explicit(status: int, message: str) -> None:
    with pytest.raises(BinanceKlineAcquisitionError, match=message):
        fetch_binance_spot_klines(
            utc(), utc(2), as_of=utc(3), _opener=HTTPErrorOpener(status)
        )
