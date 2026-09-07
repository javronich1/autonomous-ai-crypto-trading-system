# Task 005 Persistence

## Status

Task 005A is the design milestone. Task 005B will implement and verify it. Task 004.5 remains complete. Persistence is not implemented yet.

## Scope

Bounded historical-data snapshots for the fixed Binance Spot `BTCUSDT` `1h` acquisition result only.

### In scope

- Standard-library, single-file, versioned UTF-8 JSON snapshots of `BinanceKlineAcquisitionResult`
- Canonical, immutable snapshot bytes and deterministic hashing
- Explicit file-path save/load helpers under caller-chosen locations, conventionally inside ignored `data/`
- Strict schema validation, boundary revalidation, and atomic local filesystem publication semantics
- Offline-only roundtrip and filesystem failure behavior

### Out of scope

- SQLite, Parquet, CSV, or any new dependency
- Network access, cache layers, merge/repair logic, retries, strategy logic, backtesting, trading, or UI integration
- Default output directories, hidden clock reads, or automatic directory creation
- Certification for live trading or backtesting completeness

## Public API

Namespace: `crypto_trader.data.snapshots`

- `serialize_snapshot(result) -> bytes`
- `deserialize_snapshot(data: bytes) -> BinanceKlineAcquisitionResult`
- `save_snapshot(result, destination: Path) -> None`
- `load_snapshot(source: Path) -> BinanceKlineAcquisitionResult`
- `SnapshotValidationError(ValueError)`
- `SnapshotIOError(OSError)`
- `SnapshotCleanupError(SnapshotIOError)` with `published=True`, `destination: Path`, and `temporary_path: Path`

Validation errors wrap invalid input with the original cause where available. I/O errors preserve their cause. A cleanup error explicitly reports successful publication; callers must not treat it as permission to overwrite or retry blindly.

## Snapshot format

The snapshot is a JSON envelope with exact top-level keys:

- `schema_version` integer `1`
- `payload`
- `payload_sha256` 64-character lowercase hexadecimal digest

Booleans are rejected as `schema_version` values.

The payload has exact keys:

- `source`
- `requested_start`
- `requested_end`
- `effective_end`
- `as_of`
- `bars`

`source` is the fixed contract label:

- `venue=binance`
- `market=spot`
- `symbol=BTCUSDT`
- `interval=1h`

`bars` is an ordered array of objects with exact keys:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

Timestamp strings use ISO 8601 with microseconds and `+00:00`. Decimal strings preserve the exact `Decimal` textual form, including trailing zeroes, exponents, and signed zero. JSON numeric OHLCV values are rejected. Original order and duplicates are preserved.

Canonical payload bytes are produced with:

`json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')`

The SHA-256 digest is computed over those canonical payload bytes. The envelope itself uses the same canonical encoding and no trailing newline. Equal normalized inputs with identical exact `Decimal` representations must produce identical bytes.

Readers accept envelope whitespace and key-order differences and verify the digest against the canonical payload. No creation timestamp, random identifier, or implicit Git lookup is included. The digest detects accidental changes; it does not authenticate the file or prove exchange provenance. `source` is a contract label. `as_of` establishes candle eligibility, not evidence that later exchange revisions were available at that instant.

## Validation rules

Validation occurs on both save and load.

- Duplicate JSON keys are rejected at all levels
- Unknown or missing keys are rejected
- Unsupported schema versions are rejected
- Wrong types are rejected, including `bool` where integer is required
- Malformed UTF-8, malformed JSON, nonfinite numeric constants, and digest mismatches are rejected
- Noncanonical timestamp and decimal strings are rejected
- Invalid OHLCV values, inconsistent bounds, and out-of-range bars are rejected

Decimal canonicality is defined as `str(Decimal(text)) == text` after parsing, without normalizing `Decimal` scale. The reader must not coerce numbers to strings or silently ignore fields.

## Result semantics

The snapshot roundtrip reconstructs `OHLCVBar` objects and reuses the existing hourly validator.

Validation is shared with acquisition where needed so the same boundary and coverage definitions apply. No broad refactor is implied.

Derived coverage is recomputed, not trusted from serialized metadata:

- `expected = max(0, (effective_end - start) // 1h)`
- `observed = count of unique UTC-hour-aligned in-range timestamps`
- `missing = expected - observed`

Save requires the supplied `sequence_validation` and `coverage` values to match recomputed values. Forged quality metadata is rejected. Load reconstructs the derived reports.

Save requires an acquisition result containing a tuple of domain-valid bars and correctly typed quality reports. Coverage counts must be integers, excluding booleans; equality alone must not allow boolean or floating-point counts. Extract only the shared pure helpers needed in Task 005B, preserving acquisition behavior and its public API.

Revalidation rules:

- Normalize aware datetimes to UTC on save
- `start` and `end` must be hourly aligned
- `start >= Unix epoch`
- `start < end`
- `effective_end = min(end, floor UTC hour(as_of))`
- If `effective_end <= start`, bars must be empty
- `effective_end` may fall before the Unix epoch when `as_of` is before the epoch, matching acquisition behavior
- Every bar must lie in `[start, effective_end)` and be domain-valid
- Misalignment, duplicates, out-of-order bars, and gaps are preserved as observations, not repaired

Incomplete datasets and both empty states remain valid. Persistence is not certification for backtesting.

## Publication semantics

Local POSIX publication is atomic and fail-if-exists.

- Validate and serialize before any disk mutation
- Create an exclusive temporary file in the destination parent
- Write, flush, fsync, and close
- Publish via hard link from temp to destination
- Unlink the owned temp afterward

Rules:

- Never perform an exists check before publication
- Never overwrite an existing destination, even if identical
- Simultaneous saves must allow exactly one publisher
- The destination parent must already exist
- Unsupported hard links or filesystems fail explicitly, with no overwrite fallback
- Load is read-only
- Cleanup applies only to the temp file owned by the call

Publication occurs at successful hard link creation. Post-publication cleanup failure raises `SnapshotCleanupError` with `published=True` and both paths; the destination contains the complete snapshot and must remain untouched. This explicit outcome does not depend on Python warning filters. Prepublication failure must not create or alter the destination; an existing file or a competing writer's snapshot remains untouched. Best-effort cleanup removes only this call's temporary file; if cleanup fails, include the orphan location in the error. No directory-entry durability claim is made across power failure because directory fsync is deferred. Distributed filesystem behavior and malicious same-directory writers are out of scope. Existing destination symlinks must not be overwritten. Abrupt process termination may leave a temporary file; automatic orphan cleanup is deferred.

## Acceptance

Task 005A documents the design only.

Task 005B will verify:

- Exact `Decimal.as_tuple` and timestamp/as_of microsecond roundtrips
- Deterministic bytes, source, and schema handling
- Capped ranges and `effective_end` before or equal to `start`
- Incomplete leading, trailing, and internal holes
- Misalignment, duplicates, and order preservation
- Forged save metadata, digest mismatches, malformed and type failures, duplicate keys, schema failures, and domain/interval failures
- Caller file absence/preservation, no overwrite of existing file or symlink, injected write/fsync/link failure cleanup, explicit post-publication cleanup errors with a valid destination, and two competing saves with one winner
- Offline execution with no sockets
- Optional UI absence remains supported

Tests use temporary directories; production callers choose their destination explicitly.

## Verification Plan

Task 005B will run the full offline suite, focused filesystem tests, diff review, compile checks, and a manual local roundtrip smoke test. If shared acquisition helpers change, the existing Streamlit smoke regression will also be run. No network access is required. There is no backtest yet. A scope and review gate remain explicit before calling implementation complete.

## Implementation references

Use the standard-library [JSON documentation](https://docs.python.org/3/library/json.html) for strict parsing hooks and encoding controls, and the [OS documentation](https://docs.python.org/3/library/os.html) for `link` and `fsync`. Platform guarantees must also be exercised by the Task 005B filesystem tests; these references do not replace those checks.
