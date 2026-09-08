"""Offline snapshot integrity, strict boundaries, and local publication failures."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import socket
from threading import Barrier

import pytest

from crypto_trader.data.binance_fetcher import AcquisitionCoverage, BinanceKlineAcquisitionResult
from crypto_trader.data.models import OHLCVBar
from crypto_trader.data.validation import SequenceValidationResult, validate_hourly_bars
from crypto_trader.data import snapshots as s

START = datetime(2024, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempted network use is a test failure."""
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Snapshot tests must remain offline")
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


def result(hours: tuple[float, ...] = (0, 1, 2), *, as_of: datetime | None = None) -> BinanceKlineAcquisitionResult:
    """Build reports independently of the snapshot coverage implementation."""
    as_of = as_of if as_of is not None else START + 3 * HOUR + timedelta(microseconds=123456)
    effective = min(START + 3 * HOUR, as_of.replace(minute=0, second=0, microsecond=0))
    bars = tuple(OHLCVBar(
        START + hour * HOUR, Decimal("10.00"), Decimal("2E+1"),
        Decimal("1.000"), Decimal("12.3400"), Decimal("-0.000"),
    ) for hour in hours)
    expected = max(0, (effective - START) // HOUR)
    observed = len({bar.timestamp for bar in bars if bar.timestamp.minute == 0 and bar.timestamp.microsecond == 0})
    return BinanceKlineAcquisitionResult(
        START, START + 3 * HOUR, effective, as_of, bars,
        validate_hourly_bars(bars), AcquisitionCoverage(expected, observed, expected - observed),
    )


def encode(envelope: dict, *, rehash: bool = True) -> bytes:
    """Encode modified fixtures with an independently computed payload digest."""
    if rehash:
        payload = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        envelope["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    return json.dumps(envelope).encode()


@pytest.mark.parametrize("hours", [(0, 1, 2), (), (1, 2), (0, 1), (0, 2), (2, 0, 0, 1.5)])
def test_roundtrip_preserves_observations_and_exact_values(hours: tuple[float, ...]) -> None:
    original = result(hours)
    restored = s.deserialize_snapshot(s.serialize_snapshot(original))
    assert restored == original
    assert restored.as_of.microsecond == 123456
    for before, after in zip(original.bars, restored.bars, strict=True):
        assert before.timestamp == after.timestamp
        for field in ("open", "high", "low", "close", "volume"):
            assert getattr(before, field).as_tuple() == getattr(after, field).as_tuple()
    assert s.serialize_snapshot(restored) == s.serialize_snapshot(original)


def test_bar_microseconds_and_timezone_normalization() -> None:
    original = result((0.5,))
    bar = replace(original.bars[0], timestamp=START + timedelta(microseconds=1))
    original = replace(original, bars=(bar,), sequence_validation=validate_hourly_bars((bar,)))
    offset = timezone(timedelta(hours=5, minutes=30))
    shifted = replace(original, **{
        name: getattr(original, name).astimezone(offset)
        for name in ("requested_start", "requested_end", "effective_end", "as_of")
    })
    assert s.serialize_snapshot(shifted) == s.serialize_snapshot(original)
    assert s.deserialize_snapshot(s.serialize_snapshot(shifted)).bars[0].timestamp.microsecond == 1


@pytest.mark.parametrize("as_of,hours,expected", [
    (START + 2 * HOUR + timedelta(minutes=30), (0, 1), 2),
    (START + timedelta(minutes=30), (), 0),
    (START - HOUR, (), 0),
    (datetime(1960, 1, 1, tzinfo=timezone.utc), (), 0),
])
def test_capped_and_empty_ranges(as_of: datetime, hours: tuple, expected: int) -> None:
    original = result(hours, as_of=as_of)
    restored = s.deserialize_snapshot(s.serialize_snapshot(original))
    assert restored == original
    assert restored.coverage.expected_bar_count == expected


def test_canonical_envelope_and_whitespace_tolerant_reader() -> None:
    data = s.serialize_snapshot(result())
    envelope = json.loads(data)
    assert set(envelope) == {"schema_version", "payload", "payload_sha256"}
    assert envelope["schema_version"] == 1
    assert envelope["payload"]["source"] == {
        "venue": "binance", "market": "spot", "symbol": "BTCUSDT", "interval": "1h"
    }
    assert data == json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    assert not data.endswith(b"\n")
    assert envelope["payload"]["requested_start"] == "2024-01-01T00:00:00.000000+00:00"
    assert envelope["payload"]["bars"][0]["high"] == "2E+1"
    assert s.deserialize_snapshot(json.dumps(dict(reversed(list(envelope.items()))), indent=4).encode()) == result()


@pytest.mark.parametrize("data", [
    b"\xff", b"{", b"{} trailing", b"", b"null", b"[]", b"1", b"true",
    b"NaN", b"Infinity", b"-Infinity", b"[" * 2000 + b"]" * 2000,
    b"1" * 5000, "{}", bytearray(b"{}"), None,
])
def test_malformed_recursive_and_wrong_input(data: object) -> None:
    with pytest.raises(s.SnapshotValidationError):
        s.deserialize_snapshot(data)


@pytest.mark.parametrize("level", ["envelope", "payload", "source", "bar"])
def test_duplicate_json_keys_at_every_level(level: str) -> None:
    data = s.serialize_snapshot(result())
    key = {"envelope": "schema_version", "payload": "as_of", "source": "venue", "bar": "open"}[level]
    # Duplicate an existing key without changing its value.
    value = {"schema_version": "1", "as_of": '"2024-01-01T03:00:00.123456+00:00"', "venue": '"binance"', "open": '"10.00"'}[key]
    token = f'"{key}":{value}'.encode()
    assert token in data
    with pytest.raises(s.SnapshotValidationError, match="Duplicate JSON key"):
        s.deserialize_snapshot(data.replace(token, token + b"," + token, 1))


@pytest.mark.parametrize("level", ["envelope", "payload", "source", "bar"])
@pytest.mark.parametrize("change", ["extra", "missing", "wrong_type"])
def test_exact_object_schemas(level: str, change: str) -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    parent, key = {
        "envelope": ({"root": envelope}, "root"),
        "payload": (envelope, "payload"),
        "source": (envelope["payload"], "source"),
        "bar": (envelope["payload"]["bars"], 0),
    }[level]
    obj = parent[key]
    if change == "extra":
        obj["unexpected"] = 1
    elif change == "missing":
        del obj[next(iter(obj))]
    else:
        parent[key] = []
    data = encode(envelope, rehash="payload" in envelope) if level != "envelope" else json.dumps(parent[key]).encode()
    with pytest.raises(s.SnapshotValidationError):
        s.deserialize_snapshot(data)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 1.0), ("schema_version", "1"), ("schema_version", 2),
    ("payload_sha256", "A" * 64), ("payload_sha256", "0" * 63),
    ("payload_sha256", "g" * 64), ("payload_sha256", 1), ("payload_sha256", "0" * 64),
])
def test_schema_and_digest(field: str, value: object) -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope[field] = value
    with pytest.raises(s.SnapshotValidationError):
        s.deserialize_snapshot(encode(envelope, rehash=False))


@pytest.mark.parametrize("field,value", [
    ("open", 10), ("open", True), ("open", None), ("open", "010"),
    ("open", "+10"), ("open", "10e0"), ("open", " 10"), ("open", "garbage"),
    ("open", "1e99999999999999999999999999999999"),
    ("open", "NaN"), ("open", "sNaN"), ("open", "Infinity"), ("open", "0"),
    ("high", "1"), ("low", "15"), ("volume", "-1"),
    ("timestamp", "2024-01-01T00:00:00Z"),
    ("timestamp", "2024-01-01T00:00:00+00:00"),
    ("timestamp", "2024-01-01T01:00:00.000000+01:00"),
    ("timestamp", "2024-01-01T00:00:00.000000"),
    ("timestamp", "2024-01-01T03:00:00.000000+00:00"),
    ("timestamp", 0),
])
def test_invalid_bar_payload_with_valid_digest(field: str, value: object) -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope["payload"]["bars"][0][field] = value
    with pytest.raises(s.SnapshotValidationError):
        s.deserialize_snapshot(encode(envelope))


def test_decimal_parse_failure_preserves_cause() -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope["payload"]["bars"][0]["open"] = "invalid"
    with pytest.raises(s.SnapshotValidationError) as caught:
        s.deserialize_snapshot(encode(envelope))
    assert isinstance(caught.value.__cause__, InvalidOperation)


@pytest.mark.parametrize("field,value", [
    ("requested_start", "1969-12-31T23:00:00.000000+00:00"),
    ("requested_start", "2024-01-01T03:00:00.000000+00:00"),
    ("requested_start", "2024-01-01T00:01:00.000000+00:00"),
    ("requested_end", "2024-01-01T03:00:01.000000+00:00"),
    ("effective_end", "2024-01-01T02:00:00.000000+00:00"),
    ("as_of", "2024-01-01T00:00:00.000000+00:00"),
    ("bars", {}), ("source", {"venue": "other", "market": "spot", "symbol": "BTCUSDT", "interval": "1h"}),
])
def test_invalid_payload_bounds_and_contract(field: str, value: object) -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope["payload"][field] = value
    with pytest.raises(s.SnapshotValidationError):
        s.deserialize_snapshot(encode(envelope))


@pytest.mark.parametrize("field", ["expected_bar_count", "observed_unique_aligned_bar_count", "missing_expected_bar_count"])
@pytest.mark.parametrize("value", [True, False, 0.0, 3.0, "3", -1])
def test_forged_coverage(field: str, value: object) -> None:
    original = result()
    forged = replace(original, coverage=replace(original.coverage, **{field: value}))
    with pytest.raises(s.SnapshotValidationError):
        s.serialize_snapshot(forged)


@pytest.mark.parametrize("field,value", [
    ("code", "misaligned_timestamp"), ("code", 1),
    ("index", False), ("index", 0.0), ("index", "0"),
    ("message", None), ("message", "forged"),
    ("missing_bar_count", False), ("missing_bar_count", 0.0),
])
def test_strict_issue_types_and_content(field: str, value: object) -> None:
    original = result((0.5,))
    issue = replace(original.sequence_validation.issues[0], **{field: value})
    forged = replace(original, sequence_validation=SequenceValidationResult((issue,)))
    with pytest.raises(s.SnapshotValidationError):
        s.serialize_snapshot(forged)


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_gap_count_equality_cannot_bypass_types(value: object) -> None:
    original = result((0, 2))
    issue = replace(original.sequence_validation.issues[0], missing_bar_count=value)
    with pytest.raises(s.SnapshotValidationError):
        s.serialize_snapshot(replace(original, sequence_validation=SequenceValidationResult((issue,))))


@pytest.mark.parametrize("field,value", [
    ("bars", []), ("bars", (object(),)), ("coverage", None), ("coverage", (3, 3, 0)),
    ("sequence_validation", ()), ("sequence_validation", SequenceValidationResult([])),
    ("sequence_validation", SequenceValidationResult((object(),))),
    ("sequence_validation", SequenceValidationResult(())),
    ("requested_start", START.replace(tzinfo=None)), ("requested_end", START),
    ("effective_end", START), ("as_of", "invalid"),
])
def test_invalid_save_results(field: str, value: object, tmp_path: Path) -> None:
    original = result((0, 2))
    with pytest.raises(s.SnapshotValidationError):
        s.save_snapshot(replace(original, **{field: value}), tmp_path / "snapshot.json")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("field,value", [("open", Decimal("-1")), ("volume", 0), ("timestamp", START.replace(tzinfo=None))])
def test_save_revalidates_forged_domain_bar(field: str, value: object) -> None:
    original = result()
    object.__setattr__(original.bars[0], field, value)
    with pytest.raises(s.SnapshotValidationError):
        s.serialize_snapshot(original)


def test_save_load_and_read_only_validation(tmp_path: Path) -> None:
    destination = tmp_path / "snapshot.json"
    s.save_snapshot(result(), destination)
    assert destination.read_bytes() == s.serialize_snapshot(result())
    assert s.load_snapshot(destination) == result()
    assert list(tmp_path.iterdir()) == [destination]
    destination.write_bytes(b"bad json")
    with pytest.raises(s.SnapshotValidationError):
        s.load_snapshot(destination)
    assert destination.read_bytes() == b"bad json"


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling_symlink", "directory"])
def test_existing_destination_never_overwritten(tmp_path: Path, kind: str) -> None:
    destination = tmp_path / "snapshot.json"
    target = tmp_path / "target"
    if kind == "file":
        destination.write_bytes(b"original")
    elif kind == "directory":
        destination.mkdir()
    else:
        if kind == "symlink":
            target.write_bytes(b"target")
        destination.symlink_to(target)
    before = set(tmp_path.iterdir())
    with pytest.raises(s.SnapshotIOError) as caught:
        s.save_snapshot(result(), destination)
    assert isinstance(caught.value.__cause__, FileExistsError)
    assert set(tmp_path.iterdir()) == before
    if kind == "file":
        assert destination.read_bytes() == b"original"
    elif kind != "directory":
        assert destination.is_symlink() and destination.readlink() == target
        if kind == "symlink":
            assert target.read_bytes() == b"target"


def test_missing_parent_and_load_failure(tmp_path: Path) -> None:
    destination = tmp_path / "absent" / "snapshot.json"
    for action in (lambda: s.save_snapshot(result(), destination), lambda: s.load_snapshot(destination)):
        with pytest.raises(s.SnapshotIOError) as caught:
            action()
        assert isinstance(caught.value.__cause__, FileNotFoundError)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("stage", ["mkstemp", "fdopen", "write", "flush", "fsync", "buffer_close", "raw_close", "link"])
@pytest.mark.parametrize("existing", [False, True])
def test_injected_prepublication_failures_clean_owned_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, existing: bool
) -> None:
    destination = tmp_path / "snapshot.json"
    if existing:
        destination.write_bytes(b"keep")
    unrelated = tmp_path / ".snapshot-unrelated.tmp"
    unrelated.write_bytes(b"not ours")
    descriptors: list[int] = []
    real_mkstemp, real_fdopen, real_close = s.tempfile.mkstemp, os.fdopen, os.close
    failure = OSError(f"injected {stage}")

    def fail(*args: object, **kwargs: object) -> None:
        raise failure

    def tracked_temp(*args: object, **kwargs: object) -> tuple[int, str]:
        descriptor, name = real_mkstemp(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor, name

    class FaultyStream:
        """Inject buffered failures while the raw descriptor remains caller-owned."""
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.stream = real_fdopen(*args, **kwargs)
        def __enter__(self) -> "FaultyStream":
            return self
        def write(self, data: bytes) -> int:
            if stage == "write":
                self.stream.write(data[:20])
                raise failure
            return self.stream.write(data)
        def flush(self) -> None:
            if stage == "flush":
                raise failure
            self.stream.flush()
        def __exit__(self, *args: object) -> None:
            self.stream.close()
            if stage == "buffer_close":
                raise failure

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise failure

    monkeypatch.setattr(s.tempfile, "mkstemp", fail if stage == "mkstemp" else tracked_temp)
    if stage == "fdopen":
        monkeypatch.setattr(os, "fdopen", fail)
    elif stage in {"write", "flush", "buffer_close"}:
        monkeypatch.setattr(os, "fdopen", FaultyStream)
    elif stage in {"fsync", "link"}:
        monkeypatch.setattr(os, stage, fail)
    elif stage == "raw_close":
        monkeypatch.setattr(os, "close", close_then_fail)
    with pytest.raises(s.SnapshotIOError) as caught:
        s.save_snapshot(result(), destination)
    assert caught.value.__cause__ is failure
    assert unrelated.read_bytes() == b"not ours"
    assert set(tmp_path.iterdir()) == ({unrelated, destination} if existing else {unrelated})
    if existing:
        assert destination.read_bytes() == b"keep"
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize("published", [False, True])
def test_cleanup_failure_reports_orphan_and_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, published: bool
) -> None:
    destination = tmp_path / "snapshot.json"
    real_unlink = Path.unlink
    cleanup_failure = OSError("cannot unlink")
    link_failure = OSError("cannot link")
    def fail_unlink(path: Path, *args: object, **kwargs: object) -> None:
        raise cleanup_failure
    def fail_link(*args: object, **kwargs: object) -> None:
        raise link_failure
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    if not published:
        destination.write_bytes(b"existing")
        monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(s.SnapshotIOError) as caught:
        s.save_snapshot(result(), destination)
    orphan, = [path for path in tmp_path.iterdir() if path != destination]
    assert str(orphan) in str(caught.value)
    assert orphan.read_bytes() == s.serialize_snapshot(result())
    if published:
        assert isinstance(caught.value, s.SnapshotCleanupError)
        assert caught.value.published is True
        assert caught.value.destination == destination
        assert caught.value.temporary_path == orphan
        assert caught.value.__cause__ is cleanup_failure
        assert s.load_snapshot(destination) == result()
    else:
        assert not isinstance(caught.value, s.SnapshotCleanupError)
        assert caught.value.__cause__ is link_failure
        assert destination.read_bytes() == b"existing"
    real_unlink(orphan)


def test_competing_publishers_exactly_one_winner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "snapshot.json"
    barrier = Barrier(2)
    real_link = os.link
    contenders = [result(), result((0, 2))]
    def synchronized_link(source: Path, target: Path) -> None:
        # Both complete files exist before either may publish.
        assert s.load_snapshot(source) in contenders
        barrier.wait(timeout=10)
        real_link(source, target)
    monkeypatch.setattr(os, "link", synchronized_link)
    def publish(index: int) -> tuple[int, Exception | None]:
        try:
            s.save_snapshot(contenders[index], destination)
        except s.SnapshotIOError as error:
            return index, error
        return index, None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(publish, (0, 1)))
    winner, = [index for index, error in outcomes if error is None]
    loser, = [error for _, error in outcomes if error is not None]
    assert isinstance(loser.__cause__, FileExistsError)
    assert destination.read_bytes() == s.serialize_snapshot(contenders[winner])
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("field,value", [
    ("venue", "coinbase"), ("market", "futures"), ("symbol", "ETHUSDT"),
    ("interval", "5m"), ("venue", True), ("symbol", None),
])
def test_source_contract_is_fixed(field: str, value: object) -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope["payload"]["source"][field] = value
    with pytest.raises(s.SnapshotValidationError):
        s.deserialize_snapshot(encode(envelope))


@pytest.mark.parametrize("field,value", [
    ("requested_start", START - timedelta(days=365 * 60)),
    ("requested_start", START + timedelta(microseconds=1)),
    ("requested_end", START + timedelta(minutes=1)),
    ("as_of", START - HOUR),
])
def test_save_checks_bounds_before_mutation(field: str, value: datetime, tmp_path: Path) -> None:
    destination = tmp_path / "snapshot.json"
    destination.write_bytes(b"original")
    with pytest.raises(s.SnapshotValidationError):
        s.save_snapshot(replace(result(), **{field: value}), destination)
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [destination]


def test_changed_payload_requires_new_digest() -> None:
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope["payload"]["bars"][0]["volume"] = "1"
    with pytest.raises(s.SnapshotValidationError, match="digest mismatch"):
        s.deserialize_snapshot(encode(envelope, rehash=False))


def test_read_failure_preserves_cause_and_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "snapshot.json"
    s.save_snapshot(result(), destination)
    failure = PermissionError("injected read denial")
    real_read = Path.read_bytes
    def fail_read(path: Path) -> bytes:
        raise failure
    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(s.SnapshotIOError) as caught:
        s.load_snapshot(destination)
    assert caught.value.__cause__ is failure
    assert real_read(destination) == s.serialize_snapshot(result())


@pytest.mark.parametrize("failure", [ValueError("fdopen rejected"), RuntimeError("unexpected"), KeyboardInterrupt()])
def test_non_os_failure_still_cleans_owned_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    descriptors = []
    def fail_open(descriptor: int, *args: object, **kwargs: object) -> None:
        descriptors.append(descriptor)
        raise failure
    monkeypatch.setattr(os, "fdopen", fail_open)
    with pytest.raises(type(failure)) as caught:
        s.save_snapshot(result(), tmp_path / "snapshot.json")
    assert caught.value is failure
    assert list(tmp_path.iterdir()) == []
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_publication_order_and_no_existence_precheck(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "snapshot.json"
    real_fdopen, real_fsync, real_close, real_link = os.fdopen, os.fsync, os.close, os.link
    events = []
    descriptors = []
    class TracedStream:
        def __init__(self, descriptor: int, *args: object, **kwargs: object) -> None:
            descriptors.append(descriptor)
            self.stream = real_fdopen(descriptor, *args, **kwargs)
        def __enter__(self) -> "TracedStream":
            return self
        def write(self, data: bytes) -> int:
            events.append("write")
            return self.stream.write(data)
        def flush(self) -> None:
            events.append("flush")
            self.stream.flush()
        def __exit__(self, *args: object) -> None:
            events.append("buffer_close")
            self.stream.close()
    def sync(descriptor: int) -> None:
        events.append("fsync")
        assert os.fstat(descriptor).st_size == len(s.serialize_snapshot(result()))
        real_fsync(descriptor)
    def close(descriptor: int) -> None:
        events.append("raw_close")
        real_close(descriptor)
    def link(source: Path, target: Path) -> None:
        events.append("link")
        assert source.parent == target.parent
        assert s.load_snapshot(source) == result()
        with pytest.raises(OSError):
            os.fstat(descriptors[0])
        real_link(source, target)
    def no_exists(*args: object) -> None:
        raise AssertionError("Publication must not precheck existence")
    monkeypatch.setattr(os, "fdopen", TracedStream)
    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "close", close)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(Path, "exists", no_exists)
    s.save_snapshot(result(), destination)
    assert events == ["write", "flush", "fsync", "buffer_close", "raw_close", "link"]
    assert list(tmp_path.iterdir()) == [destination]


def test_failure_preserves_snapshot_published_by_another_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "snapshot.json"
    other_bytes = s.serialize_snapshot(result((0, 2)))
    def fail_sync(descriptor: int) -> None:
        destination.write_bytes(other_bytes)
        raise OSError("failed while another publisher succeeded")
    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(s.SnapshotIOError):
        s.save_snapshot(result(), destination)
    assert destination.read_bytes() == other_bytes
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("trapped", [False, True])
def test_bad_decimal_does_not_change_caller_context(trapped: bool) -> None:
    from decimal import localcontext
    envelope = json.loads(s.serialize_snapshot(result()))
    envelope["payload"]["bars"][0]["open"] = "bad decimal"
    with localcontext() as context:
        context.clear_flags()
        context.traps[InvalidOperation] = trapped
        with pytest.raises(s.SnapshotValidationError):
            s.deserialize_snapshot(encode(envelope))
        assert not any(context.flags.values())
        assert context.traps[InvalidOperation] is trapped


def test_short_write_is_not_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_fdopen = os.fdopen
    class ShortWriter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.stream = real_fdopen(*args, **kwargs)
        def __enter__(self) -> "ShortWriter":
            return self
        def write(self, data: bytes) -> int:
            return self.stream.write(data[:1])
        def __exit__(self, *args: object) -> None:
            self.stream.close()
    monkeypatch.setattr(os, "fdopen", ShortWriter)
    with pytest.raises(s.SnapshotIOError) as caught:
        s.save_snapshot(result(), tmp_path / "snapshot.json")
    assert "Incomplete snapshot write" in str(caught.value.__cause__)
    assert list(tmp_path.iterdir()) == []
