# Current Project State

## Current Phase

Phase 1 — market-data foundation (Task 004 complete and reviewed).

## Current Objective

Deterministic public Binance Spot BTCUSDT 1h historical acquisition is implemented and reviewed.

## Scope

BTC/USDT spot research on hourly bars from one public venue, long or flat, no leverage, and historical validation only.

## Implemented

Repository foundations, the reviewed OHLCV contract, hourly sequence validator, and Binance raw-kline adapter, plus deterministic public REST acquisition with explicit UTC range semantics, time-based pagination, and finite timeouts. Explicit `as_of` semantics ensure that only fully closed candles are eligible. Acquisition results expose observed-sequence quality and requested-range coverage independently.

## Validated

The complete test suite currently passes 85 tests. Validation covers the existing data contracts plus half-open ranges, timezone normalization, closed-candle protection, exact request construction, pagination beyond 1000 bars, remote-response failures, non-progress defense, out-of-range rejection, sequence-quality reporting, and requested-range coverage without repair.

## Experiments Run

None.

## Decisions Made

Initial decisions and the Task 002 through Task 004 market-data decisions are recorded in `DECISIONS.md`.

## Known Risks / Open Questions

- Cost and execution assumptions are not yet specified.
- Formal benchmark and evaluation protocols remain to be designed.
- Data licensing, retention, and quality requirements remain open.
- Historical acquisition currently targets only the fixed public Binance Spot BTCUSDT 1h contract; data licensing remains open.
- No persistence, retries or backoff, strategies, backtesting, agents, execution, paper trading, or live trading exists.

## Next Actions

Perform a controlled live-source smoke validation before designing persistence.
