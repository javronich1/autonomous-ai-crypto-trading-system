"""Deterministic acquisition of closed Binance Spot BTCUSDT hourly klines."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from crypto_trader.data.binance import BinanceKlineParseError, parse_binance_spot_kline
from crypto_trader.data.models import OHLCVBar
from crypto_trader.data.validation import SequenceValidationResult, validate_hourly_bars

BINANCE_DATA_API_BASE_URL = "https://data-api.binance.vision"
BINANCE_KLINES_PATH = "/api/v3/klines"
BINANCE_SPOT_SYMBOL = "BTCUSDT"
BINANCE_INTERVAL = "1h"
BINANCE_PAGE_LIMIT = 1000
DEFAULT_TIMEOUT_SECONDS = 10.0

_HOUR = timedelta(hours=1)
_MILLISECOND = timedelta(milliseconds=1)
_UNIX_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


class _HTTPResponse(Protocol):
    """Minimal response behavior used from ``urllib`` and test doubles."""

    status: int

    def read(self) -> bytes: ...

    def __enter__(self) -> "_HTTPResponse": ...

    def __exit__(self, *args: object) -> None: ...


class BinanceKlineAcquisitionError(RuntimeError):
    """Binance kline acquisition or remote-response validation failed."""


@dataclass(frozen=True, slots=True)
class AcquisitionCoverage:
    """Coverage of the expected hourly grid within an effective request range."""

    expected_bar_count: int
    observed_unique_aligned_bar_count: int
    missing_expected_bar_count: int

    @property
    def is_complete(self) -> bool:
        """Return whether every eligible expected hourly open was observed."""
        return self.missing_expected_bar_count == 0


@dataclass(frozen=True, slots=True)
class BinanceKlineAcquisitionResult:
    """Immutable bars, boundaries, sequence quality, and request coverage."""

    requested_start: datetime
    requested_end: datetime
    effective_end: datetime
    as_of: datetime
    bars: tuple[OHLCVBar, ...]
    sequence_validation: SequenceValidationResult
    coverage: AcquisitionCoverage

    @property
    def end_was_capped(self) -> bool:
        """Return whether open-candle protection reduced the requested end."""
        return self.effective_end < self.requested_end


def _normalize_aware_datetime(value: object, name: str) -> datetime:
    """Validate a datetime and normalize its represented instant to UTC."""
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _is_hour_aligned(value: datetime) -> bool:
    return not any((value.minute, value.second, value.microsecond))


def _to_unix_milliseconds(value: datetime) -> int:
    """Convert an aware UTC datetime to Unix milliseconds without floats."""
    delta = value - _UNIX_EPOCH_UTC
    milliseconds = delta // _MILLISECOND
    if milliseconds < 0:
        raise ValueError("historical range must not begin before the Unix epoch")
    return milliseconds


def _assess_coverage(
    start: datetime, effective_end: datetime, bars: tuple[OHLCVBar, ...]
) -> AcquisitionCoverage:
    """Compare unique aligned observations with the effective hourly grid."""
    expected_count = max(0, int((effective_end - start) // _HOUR))
    observed_timestamps = {
        bar.timestamp for bar in bars if _is_hour_aligned(bar.timestamp)
    }
    observed_count = len(observed_timestamps)
    return AcquisitionCoverage(
        expected_bar_count=expected_count,
        observed_unique_aligned_bar_count=observed_count,
        missing_expected_bar_count=max(0, expected_count - observed_count),
    )


def _build_klines_url(start_ms: int, inclusive_end_ms: int) -> str:
    query = urlencode(
        {
            "symbol": BINANCE_SPOT_SYMBOL,
            "interval": BINANCE_INTERVAL,
            "startTime": start_ms,
            "endTime": inclusive_end_ms,
            "limit": BINANCE_PAGE_LIMIT,
            "timeZone": 0,
        }
    )
    return f"{BINANCE_DATA_API_BASE_URL}{BINANCE_KLINES_PATH}?{query}"


def _load_page(
    url: str,
    timeout_seconds: float,
    opener: Callable[..., _HTTPResponse],
) -> list[object]:
    """Perform one public GET and validate its JSON collection boundary."""
    try:
        with opener(url, timeout=timeout_seconds) as response:
            status = response.status
            payload = response.read()
    except HTTPError as error:
        detail = "rate limited" if error.code == 429 else "HTTP failure"
        raise BinanceKlineAcquisitionError(
            f"Binance kline request failed: {detail} (status {error.code})"
        ) from error
    except (URLError, OSError) as error:
        raise BinanceKlineAcquisitionError("Binance kline transport failed") from error

    if not 200 <= status < 300:
        detail = "rate limited" if status == 429 else "HTTP failure"
        raise BinanceKlineAcquisitionError(
            f"Binance kline request failed: {detail} (status {status})"
        )

    try:
        decoded: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BinanceKlineAcquisitionError(
            "Binance kline response was not valid UTF-8 JSON"
        ) from error

    if not isinstance(decoded, list):
        if isinstance(decoded, dict) and "code" in decoded:
            raise BinanceKlineAcquisitionError(
                f"Binance returned an API error payload: code {decoded['code']}"
            )
        raise BinanceKlineAcquisitionError(
            "Binance kline response must be a JSON array"
        )
    return decoded


def fetch_binance_spot_klines(
    start: datetime,
    end: datetime,
    *,
    as_of: datetime,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    _opener: Callable[..., _HTTPResponse] = urlopen,
) -> BinanceKlineAcquisitionResult:
    """Fetch closed BTCUSDT 1h bars for the requested half-open ``[start, end)``.

    ``as_of`` is explicit so exclusion of the current, still-open UTC-hour bar
    is reproducible. The function neither retries nor persists data.
    """
    requested_start = _normalize_aware_datetime(start, "start")
    requested_end = _normalize_aware_datetime(end, "end")
    normalized_as_of = _normalize_aware_datetime(as_of, "as_of")

    if not _is_hour_aligned(requested_start):
        raise ValueError("start must align exactly to a UTC-hour boundary")
    if not _is_hour_aligned(requested_end):
        raise ValueError("end must align exactly to a UTC-hour boundary")
    if requested_start >= requested_end:
        raise ValueError("start must be earlier than end")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be finite and positive")

    start_ms = _to_unix_milliseconds(requested_start)
    current_hour_start = normalized_as_of.replace(minute=0, second=0, microsecond=0)
    effective_end = min(requested_end, current_hour_start)
    if effective_end <= requested_start:
        empty_validation = validate_hourly_bars(())
        empty_coverage = _assess_coverage(requested_start, effective_end, ())
        return BinanceKlineAcquisitionResult(
            requested_start=requested_start,
            requested_end=requested_end,
            effective_end=effective_end,
            as_of=normalized_as_of,
            bars=(),
            sequence_validation=empty_validation,
            coverage=empty_coverage,
        )

    effective_end_ms = _to_unix_milliseconds(effective_end)
    inclusive_end_ms = effective_end_ms - 1
    cursor_ms = start_ms
    bars: list[OHLCVBar] = []

    while cursor_ms < effective_end_ms:
        url = _build_klines_url(cursor_ms, inclusive_end_ms)
        raw_page = _load_page(url, timeout_seconds, _opener)
        if not raw_page:
            break

        page_bars: list[OHLCVBar] = []
        for raw_record in raw_page:
            try:
                bar = parse_binance_spot_kline(raw_record)  # type: ignore[arg-type]
            except (BinanceKlineParseError, TypeError, ValueError) as error:
                raise BinanceKlineAcquisitionError(
                    "Binance kline page contained an invalid raw record"
                ) from error
            if not requested_start <= bar.timestamp < effective_end:
                raise BinanceKlineAcquisitionError(
                    "Binance returned a bar outside the effective requested interval"
                )
            page_bars.append(bar)

        latest_open_ms = max(_to_unix_milliseconds(bar.timestamp) for bar in page_bars)
        if latest_open_ms < cursor_ms:
            raise BinanceKlineAcquisitionError(
                "Binance pagination did not make chronological progress"
            )

        next_cursor_ms = latest_open_ms + int(_HOUR // _MILLISECOND)
        if next_cursor_ms <= cursor_ms:
            raise BinanceKlineAcquisitionError(
                "Binance pagination did not make chronological progress"
            )

        bars.extend(page_bars)
        cursor_ms = next_cursor_ms

    immutable_bars = tuple(bars)
    return BinanceKlineAcquisitionResult(
        requested_start=requested_start,
        requested_end=requested_end,
        effective_end=effective_end,
        as_of=normalized_as_of,
        bars=immutable_bars,
        sequence_validation=validate_hourly_bars(immutable_bars),
        coverage=_assess_coverage(requested_start, effective_end, immutable_bars),
    )
