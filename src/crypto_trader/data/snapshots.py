"""Strict, deterministic snapshots with atomic local POSIX publication."""

from datetime import datetime
from decimal import Decimal, DecimalException, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from crypto_trader.data.binance_fetcher import (
    AcquisitionCoverage,
    BinanceKlineAcquisitionResult,
    _assess_coverage,
    _is_hour_aligned,
    _normalize_aware_datetime,
    _to_unix_milliseconds,
)
from crypto_trader.data.models import OHLCVBar
from crypto_trader.data.validation import (
    SequenceIssueCode,
    SequenceValidationIssue,
    SequenceValidationResult,
    validate_hourly_bars,
)

_SOURCE = {"venue": "binance", "market": "spot", "symbol": "BTCUSDT", "interval": "1h"}
_BOUNDARIES = ("requested_start", "requested_end", "effective_end", "as_of")
_VALUES = ("open", "high", "low", "close", "volume")
_PAYLOAD_KEYS = {*_BOUNDARIES, "source", "bars"}
_ENVELOPE_KEYS = {"schema_version", "payload", "payload_sha256"}
_BAR_KEYS = {"timestamp", *_VALUES}
_VALIDATION_FAILURES = (ValueError, TypeError, OverflowError, RecursionError, DecimalException)


class SnapshotValidationError(ValueError):
    """Snapshot bytes or supplied acquisition values violate the contract."""


class SnapshotIOError(OSError):
    """A snapshot filesystem operation failed; inspect the chained cause."""


class SnapshotCleanupError(SnapshotIOError):
    """Publication succeeded, but the owned temporary file could not be removed."""

    published = True

    def __init__(self, destination: Path, temporary_path: Path) -> None:
        self.destination = destination
        self.temporary_path = temporary_path
        super().__init__(
            f"Snapshot published at {destination}; temporary cleanup failed: {temporary_path}"
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotValidationError(message)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _object(value: Any, keys: set[str]) -> dict[str, Any]:
    _require(type(value) is dict and value.keys() == keys, f"Expected object keys: {sorted(keys)}")
    return value


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def _read_timestamp(value: object) -> datetime:
    _require(type(value) is str, "Timestamp must be a string")
    normalized = _normalize_aware_datetime(datetime.fromisoformat(value), "timestamp")
    _require(_timestamp(normalized) == value, "Timestamp must use canonical UTC microseconds")
    return normalized


def _read_decimal(value: object) -> Decimal:
    _require(type(value) is str, "OHLCV values must be decimal strings")
    with localcontext():
        parsed = Decimal(value)
    _require(_decimal_text(parsed) == value, "Noncanonical decimal string")
    return parsed


def _decimal_text(value: Decimal) -> str:
    """Preserve exact scale with exponent spelling independent of caller context."""
    with localcontext() as context:
        context.capitals = 1
        return str(value)


def _revalidate(
    boundaries: dict[str, datetime], bars: tuple[OHLCVBar, ...]
) -> BinanceKlineAcquisitionResult:
    """Rebuild domain bars and derive quality using acquisition's pure helpers."""
    normalized = {
        name: _normalize_aware_datetime(boundaries[name], name) for name in _BOUNDARIES
    }
    start, end, effective, as_of = (normalized[name] for name in _BOUNDARIES)
    _require(_is_hour_aligned(start) and _is_hour_aligned(end), "Bounds must be hour aligned")
    _require(start < end, "Start must precede end")
    _to_unix_milliseconds(start)
    _require(
        effective == min(end, as_of.replace(minute=0, second=0, microsecond=0)),
        "Inconsistent effective end",
    )
    _require(type(bars) is tuple, "Bars must be a tuple")
    rebuilt: list[OHLCVBar] = []
    for bar in bars:
        _require(isinstance(bar, OHLCVBar), "Every bar must be an OHLCVBar")
        trusted = OHLCVBar(bar.timestamp, **{name: getattr(bar, name) for name in _VALUES})
        _require(start <= trusted.timestamp < effective, "Bar outside effective interval")
        rebuilt.append(trusted)
    immutable = tuple(rebuilt)
    return BinanceKlineAcquisitionResult(
        **normalized,
        bars=immutable,
        sequence_validation=validate_hourly_bars(immutable),
        coverage=_assess_coverage(start, effective, immutable),
    )


def _validate_reports(result: BinanceKlineAcquisitionResult) -> None:
    """Reject equality-compatible impostors before comparing derived reports."""
    coverage = result.coverage
    _require(type(coverage) is AcquisitionCoverage, "Invalid coverage report type")
    for name in (
        "expected_bar_count", "observed_unique_aligned_bar_count", "missing_expected_bar_count"
    ):
        _require(type(getattr(coverage, name)) is int, "Coverage counts must be integers")
    report = result.sequence_validation
    _require(type(report) is SequenceValidationResult, "Invalid sequence report type")
    _require(type(report.issues) is tuple, "Sequence issues must be a tuple")
    for issue in report.issues:
        _require(type(issue) is SequenceValidationIssue, "Invalid sequence issue type")
        _require(type(issue.code) is SequenceIssueCode, "Invalid sequence issue code type")
        _require(type(issue.index) is int, "Issue index must be an integer")
        _require(type(issue.message) is str, "Issue message must be a string")
        _require(
            issue.missing_bar_count is None or type(issue.missing_bar_count) is int,
            "Issue missing count must be an integer or None",
        )


def serialize_snapshot(result: BinanceKlineAcquisitionResult) -> bytes:
    """Revalidate an acquisition result and encode canonical version-one bytes."""
    try:
        _require(type(result) is BinanceKlineAcquisitionResult, "Expected acquisition result")
        _validate_reports(result)
        trusted = _revalidate({name: getattr(result, name) for name in _BOUNDARIES}, result.bars)
        _require(result.coverage == trusted.coverage, "Coverage does not match observations")
        _require(
            result.sequence_validation == trusted.sequence_validation,
            "Sequence report does not match observations",
        )
        payload = {
            "source": dict(_SOURCE),
            **{name: _timestamp(getattr(trusted, name)) for name in _BOUNDARIES},
            "bars": [
                {"timestamp": _timestamp(bar.timestamp),
                 **{name: _decimal_text(getattr(bar, name)) for name in _VALUES}}
                for bar in trusted.bars
            ],
        }
        return _canonical({
            "schema_version": 1,
            "payload": payload,
            "payload_sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
        })
    except SnapshotValidationError:
        raise
    except _VALIDATION_FAILURES as error:
        raise SnapshotValidationError("Invalid acquisition result") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SnapshotValidationError(f"Nonfinite JSON constant: {value}")


def deserialize_snapshot(data: bytes) -> BinanceKlineAcquisitionResult:
    """Read strict UTF-8 JSON, verify its canonical digest, and rebuild reports."""
    try:
        _require(type(data) is bytes, "Snapshot data must be bytes")
        envelope = _object(json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant
        ), _ENVELOPE_KEYS)
        _require(type(envelope["schema_version"]) is int and envelope["schema_version"] == 1,
                 "Unsupported schema version")
        digest = envelope["payload_sha256"]
        _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                 "Invalid payload digest")
        payload = _object(envelope["payload"], _PAYLOAD_KEYS)
        _require(hashlib.sha256(_canonical(payload)).hexdigest() == digest, "Payload digest mismatch")
        source = _object(payload["source"], set(_SOURCE))
        _require(source == _SOURCE, "Unsupported source contract")
        _require(type(payload["bars"]) is list, "Bars must be an array")
        bars: list[OHLCVBar] = []
        for item in payload["bars"]:
            bar = _object(item, _BAR_KEYS)
            bars.append(OHLCVBar(
                _read_timestamp(bar["timestamp"]),
                **{name: _read_decimal(bar[name]) for name in _VALUES},
            ))
        return _revalidate(
            {name: _read_timestamp(payload[name]) for name in _BOUNDARIES}, tuple(bars)
        )
    except SnapshotValidationError:
        raise
    except _VALIDATION_FAILURES as error:
        raise SnapshotValidationError("Invalid snapshot data") from error


def save_snapshot(result: BinanceKlineAcquisitionResult, destination: Path) -> None:
    """Publish once by hard link; never overwrite or remove a destination.

    The caller supplies an existing parent directory. Publication does not
    fsync that directory and makes no power-loss durability guarantee.
    """
    data = serialize_snapshot(result)
    destination = Path(destination)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".snapshot-", suffix=".tmp", dir=destination.parent)
        temporary = Path(name)
        # Keep ownership of the raw descriptor even if fdopen or buffered close fails.
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                if stream.write(data) != len(data):
                    raise OSError("Incomplete snapshot write")
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, destination)
    except BaseException as error:
        detail = f"Snapshot publication failed: {destination}"
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError as cleanup_error:
                detail += f"; temporary cleanup failed at {temporary}: {cleanup_error}"
        if isinstance(error, OSError):
            raise SnapshotIOError(detail) from error
        error.add_note(detail)
        raise
    # A successful link is the publication boundary. Never clean up destination.
    try:
        temporary.unlink()
    except OSError as error:
        raise SnapshotCleanupError(destination, temporary) from error


def load_snapshot(source: Path) -> BinanceKlineAcquisitionResult:
    """Read a caller-selected file without modifying it or its parent directory."""
    try:
        data = Path(source).read_bytes()
    except OSError as error:
        raise SnapshotIOError(f"Snapshot read failed: {source}") from error
    return deserialize_snapshot(data)
